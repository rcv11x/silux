"""No rate from a window that is not one, in every calculation that makes one.

A power chart got 1336648637.3 W from an Iris Xe drawing 9 W: 9 J over a
window of nanoseconds. Every difference between two readings over the time
between them goes through `silux/providers/counters.py`, and here each one is
given the three readings that must not give a figure: the same instant, 7 ns
later, and the counter gone back. None gives one, none raises, and the next
reading an interval later does give one: the bad reading became the base.

Each calculation is fed as it is in a run: its files or its helper's
answers, and `time.monotonic` where it reads its own clock.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux.privileged.client import LecturaImc
from silux.providers import counters
from silux.providers.base import Draft
from tests.interval import fake_clock

INTERVAL = 1.0
START = 1000.0


class _Calculation:
    """One calculation: `read(instant, counter)` feeds it a reading at that
    instant with its counters at `counter`, and returns its figure."""

    def __init__(self, tmp: pathlib.Path, clock):
        self.tmp, self.clock = tmp, clock

    def draft(self) -> Draft:
        draft = Draft()
        draft.interval_s = INTERVAL
        return draft


class Rapl(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers import rapl
        self.zone = tmp / "intel-rapl:0"
        self.zone.mkdir()
        (self.zone / "name").write_text("package-0\n")
        # Without the impossible-watts ceiling: it is the window that has to
        # stop 1 J over 7 ns, not the safety net behind it.
        patches = (mock.patch.object(rapl, "POWERCAP", tmp),
                   mock.patch.object(rapl, "package_ceiling_w", lambda: float("inf")))
        for patch in patches:
            patch.start()
        self.stop = lambda: [patch.stop() for patch in patches]
        self.provider = rapl.RaplPower()

    def read(self, instant, counter):
        self.clock.now = instant
        (self.zone / "energy_uj").write_text(f"{10_000_000 + counter * 1_000_000}\n")
        draft = self.draft()
        self.provider.collect(draft)
        power = draft.cpu_extra.get("power")
        return power.package_w if power else None


class _Helper:
    def __init__(self):
        self.answer = None

    def connected(self):
        return True

    def gpu_pmu(self):
        return self.answer

    def imc(self):
        return self.answer


class GpuEnergyAndBusy(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers.drm import GpuState
        self.helper = _Helper()
        self.provider = GpuState(client=self.helper)

    def read(self, instant, counter):
        escala = 2.3283064365386963e-10
        engines = {"i915": {"rcs0-busy": 10**9 + counter * 10**8},
                   "power": {"energy-gpu": int((100 + counter) / escala)}}
        self.helper.answer = (int(instant * 1e9), engines, {"power": {"energy-gpu": escala}})
        busy, watts = self.provider._contadores(INTERVAL)
        busy = (busy or {}).get("i915", {}).get("rcs0-busy")
        return None if busy is None and watts is None else (busy, watts)


class GpuSleep(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers.drm import GpuState
        (tmp / "gt" / "gt0").mkdir(parents=True)
        self.provider = GpuState()

    def read(self, instant, counter):
        self.clock.now = instant
        (self.tmp / "gt" / "gt0" / "rc6_residency_ms").write_text(f"{5000 + counter * 400}\n")
        return self.provider._reposo("card1", self.tmp, INTERVAL)


class CpuUsage(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers import procfs
        self.stat = tmp / "stat"
        patch = mock.patch.object(procfs.sysroot, "ruta",
                                  lambda camino: str(self.stat) if camino == "/proc/stat"
                                  else camino)
        patch.start()
        self.stop = patch.stop
        self.provider = procfs.CpuUsage()

    def read(self, instant, counter):
        self.clock.now = instant
        # user nice system idle iowait: 60 busy jiffies and 40 idle each step.
        self.stat.write_text(f"cpu  {1000 + counter * 60} 0 0 {5000 + counter * 40} 0 0 0 0\n")
        draft = self.draft()
        self.provider.collect(draft)
        return draft.cpu_extra.get("usage_percent")


class CpuIdleStates(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers.cpuidle import CpuIdle
        (tmp / "state1").mkdir()
        self.provider = CpuIdle()
        self.provider._states = {0: [(str(tmp / "state1"), "C1", None)]}

    def read(self, instant, counter):
        self.clock.now = instant
        (self.tmp / "state1" / "time").write_text(f"{10**6 + counter * 300_000}\n")
        draft = self.draft()
        self.provider.collect(draft)
        return draft.cpu_extra.get("idle_states")


class MemoryTraffic(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers import imc
        patch = mock.patch.object(imc, "has_controller", lambda: True)
        patch.start()
        self.stop = patch.stop
        self.helper = _Helper()
        self.provider = imc.ImcTraffic(client=self.helper)

    def read(self, instant, counter):
        cuentas = {"uncore_imc_free_running_0": {"data_read": 100 + counter * 50,
                                                 "data_write": 100 + counter * 20}}
        escalas = {"uncore_imc_free_running_0": {"data_read": 6.103515625e-5,
                                                 "data_write": 6.103515625e-5}}
        unidades = {"uncore_imc_free_running_0": {"data_read": "MiB", "data_write": "MiB"}}
        self.helper.answer = LecturaImc(int(instant * 1e9), cuentas, escalas, unidades, False)
        draft = self.draft()
        self.provider.collect(draft)
        trafico = draft.memory_traffic
        return trafico.read_bytes_s if trafico else None


class NetworkRate(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers.network import COUNTERS, NetworkInterfaces
        self.campos = COUNTERS
        self.provider = NetworkInterfaces()
        self.provider._interval_s = INTERVAL

    def read(self, instant, counter):
        self.clock.now = instant
        valores = {campo: 0 for campo in self.campos}
        valores.update(rx_bytes=10_000 + counter * 5_000, tx_bytes=10_000 + counter * 2_000)
        return self.provider._traffic("wlan0", self.tmp, valores).rx_rate_bps


class DiskRate(_Calculation):
    def __init__(self, tmp, clock):
        super().__init__(tmp, clock)
        from silux.providers.storage import Disks
        self.provider = Disks(client=_Helper())
        self.provider._interval_s = INTERVAL

    def read(self, instant, counter):
        self.clock.now = instant
        sectores = 1000 + counter * 2048
        (self.tmp / "stat").write_text(f"10 0 {sectores} 0 10 0 {sectores} 0 0 0 0\n")
        return self.provider._trafico("nvme0n1", self.tmp).read_rate_bps


CALCULATIONS = (Rapl, GpuEnergyAndBusy, GpuSleep, CpuUsage, CpuIdleStates,
                MemoryTraffic, NetworkRate, DiskRate)

# How far the second reading is from the first, and where its counter is.
BAD_READINGS = {
    "the same instant": (0.0, 1),
    "7 ns later": (7e-9, 1),
    "the counter gone back": (INTERVAL, -1),
}


class TestEveryRate(unittest.TestCase):

    def _run(self, calculation, steps):
        with tempfile.TemporaryDirectory() as tmp, fake_clock(START) as clock:
            calculo = calculation(pathlib.Path(tmp), clock)
            try:
                return [calculo.read(instante, contador) for instante, contador in steps]
            finally:
                getattr(calculo, "stop", lambda: None)()

    def test_an_interval_apart_it_gives_a_figure(self):
        for calculation in CALCULATIONS:
            with self.subTest(calculation=calculation.__name__):
                base, figura = self._run(calculation, [(START, 0), (START + INTERVAL, 1)])
                self.assertIsNone(base)
                self.assertTrue(figura)

    def test_a_bad_window_gives_nothing_and_becomes_the_base(self):
        for calculation in CALCULATIONS:
            for caso, (despues, contador) in BAD_READINGS.items():
                with self.subTest(calculation=calculation.__name__, case=caso):
                    segunda = START + despues
                    _base, mala, siguiente = self._run(calculation, [
                        (START, 0), (segunda, contador), (segunda + INTERVAL, contador + 1)])
                    self.assertIsNone(mala or None)
                    self.assertTrue(siguiente)


class TestTheRule(unittest.TestCase):

    def test_half_the_interval_is_the_shortest_window(self):
        self.assertIsNone(counters.window_s(10.0, 10.4, 1.0))
        self.assertEqual(counters.window_s(10.0, 10.5, 1.0), 0.5)

    def test_a_counter_that_wraps_goes_round_once(self):
        self.assertEqual(counters.increase(90, 10, wrap=100), 20)
        self.assertIsNone(counters.increase(90, 10))


if __name__ == "__main__":
    unittest.main()


class TestHomesGpuChart(unittest.TestCase):
    """Inicio's GPU card draws its usage or, without it, its clock. A sample
    without usage (a short window now gives none) drew megahertz on the
    percentages' history."""

    def test_usage_and_clock_never_share_the_chart(self):
        import dataclasses
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.home import HomePage
        from tests import qt
        from tests.test_equipos import EQUIPOS, foto

        f = foto(EQUIPOS / "i5-10400")[0]
        gpu = f.gpus[0]
        relojes = dataclasses.replace(gpu.clocks, core_hz=350_000_000)
        con_uso = dataclasses.replace(f, gpus=(dataclasses.replace(
            gpu, busy_percent=40.0, clocks=relojes),))
        sin_uso = dataclasses.replace(f, gpus=(dataclasses.replace(
            gpu, busy_percent=None, power_w=None, temp_c=None, clocks=relojes),))
        pagina = HomePage(theme.palette_for(qt.app(), "dark"), Preferences().normalized())
        pagina.apply(con_uso)
        pagina.apply(con_uso)
        pagina.apply(sin_uso)
        self.assertEqual(list(pagina.gpu.grafica._values), [350.0])
        pagina.apply(con_uso)
        self.assertEqual(list(pagina.gpu.grafica._values), [40.0])
