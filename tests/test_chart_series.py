"""A chart draws one series: nothing else gets in.

Inicio's GPU chart drew megahertz over percentages when a sample came without
usage, and the author's T14 had a point at 1336648637.3 W in a 9 W chart.
Every chart takes its points through one door (`Sparkline.set_series` and
`push`): a series is a key and a unit; another key starts it over, and a value
that cannot be in its unit (a raw counter: millidegrees, microjoules, a byte
count faster than the link) does not get in.

One chart of each page, on a dump, after a normal sample gets three more:
without its datum (it does not move), with a raw value (it does not move),
and of another series (another card, disk, interface, unit or headline: it
starts over with only the new point). Sensores keeps its history per sensor,
so it has no other series; a raw reading gets neither in its line nor in its
minimum, maximum or mean.
"""

import dataclasses
import unittest

from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

RAW_WATTS = 1336648637.3        # what the T14's chart got
RAW_DEGREES = 45000.0           # hwmon's millidegrees


def _cpu_temp(f, grados):
    cpu = dataclasses.replace(f.cpu, package_temp_c=grados,
                              types=tuple(dataclasses.replace(t, temp_c=grados) for t in f.cpu.types))
    return dataclasses.replace(f, cpu=cpu)


def _gpu(f, **campos):
    return dataclasses.replace(f, gpus=(dataclasses.replace(f.gpus[0], **campos),) + f.gpus[1:])


def _disks(f, temps):
    discos = tuple(dataclasses.replace(d, temp_c=temps.get(d.name)) if d.name in temps else d
                   for d in f.disks)
    return dataclasses.replace(f, disks=discos)


def _main_iface(f, nombre, **trafico):
    redes = []
    for interfaz in f.network:
        if interfaz.name == nombre:
            interfaz = dataclasses.replace(
                interfaz, traffic=dataclasses.replace(interfaz.traffic, **trafico))
        redes.append(interfaz)
    return dataclasses.replace(f, network=tuple(redes))


def _rename(f, nombre, nuevo):
    return dataclasses.replace(f, network=tuple(
        dataclasses.replace(i, name=nuevo) if i.name == nombre else i for i in f.network))


class _Page(unittest.TestCase):
    """`base` and the three samples; `chart(ventana)`; `other` may change the
    preferences before its sample."""

    dump = "i5-10400"
    section = ""

    def setUp(self):
        qt.app()
        self.f = shared_snapshot(EQUIPOS / self.dump)

    def _run(self):
        base = self.base(self.f)
        with pantalla.Ventana(base) as ventana:
            ventana.select_section(self.section)
            ventana._on_sample(base)
            grafica = self.chart(ventana)
            antes = list(grafica._values)
            self.assertTrue(antes, "the normal sample drew its point")
            for nombre, muestra in (("without the datum", self.missing(self.f)),
                                    ("a raw value", self.raw(self.f))):
                ventana._on_sample(muestra)
                with self.subTest(sample=nombre):
                    self.assertEqual(list(grafica._values), antes)
            otra, esperado = self.other(self.f, ventana)
            ventana._on_sample(otra)
            self.assertEqual(list(self.chart(ventana)._values), [esperado])


class TestCpu(_Page):
    section = "CPU"

    def base(self, f): return _cpu_temp(f, 50.0)
    def missing(self, f): return _cpu_temp(f, None)
    def raw(self, f): return _cpu_temp(f, RAW_DEGREES)
    def chart(self, v): return v.cpu_page.live.tile_temp.chart

    def other(self, f, ventana):
        ventana._on_preferences(dataclasses.replace(ventana.prefs, temperature_unit="f"))
        return _cpu_temp(f, 50.0), 122.0                 # the same 50 °C, in °F

    def test_one_series(self): self._run()


class TestGraphics(_Page):
    section = "Gráficos"

    def base(self, f): return _gpu(f, power_w=9.0)
    def missing(self, f): return _gpu(f, power_w=None)
    def raw(self, f): return _gpu(f, power_w=RAW_WATTS)
    def chart(self, v): return v.graphics_page._sections[0].tile_power.chart

    def other(self, f, ventana):
        # The first section gets another card.
        return _gpu(f, power_w=7.0, pci_slot="0000:01:00.0"), 7.0

    def test_one_series(self): self._run()


class TestHome(_Page):
    section = "Inicio"

    def base(self, f): return _disks(_cpu_temp(f, 50.0), {"sda": 25.0})
    def missing(self, f): return _disks(_cpu_temp(f, None), {"sda": None})
    def raw(self, f): return _disks(_cpu_temp(f, RAW_DEGREES), {"sda": 25.0})
    def chart(self, v): return v.home_page.temperaturas.grafica

    def other(self, f, ventana):
        # The disk takes the headline: the chart is the disk's now.
        return _disks(_cpu_temp(f, 30.0), {"sda": 60.0}), 60.0

    def test_one_series(self): self._run()


class TestNetwork(_Page):
    section = "Red"

    def base(self, f): return _main_iface(f, "enp1s0", rx_rate_bps=1000.0)
    def missing(self, f): return _main_iface(f, "enp1s0", rx_rate_bps=None)
    # A byte count of 3.2 GB in one second, on a 1 Gb/s link.
    def raw(self, f): return _main_iface(f, "enp1s0", rx_rate_bps=3.2e9)
    def chart(self, v): return v.network_page.tile_down.chart

    def other(self, f, ventana):
        # Another interface is the main one.
        return _rename(_main_iface(f, "enp1s0", rx_rate_bps=500.0), "enp1s0", "enp2s0"), 500.0

    def test_one_series(self): self._run()


class TestStorage(_Page):
    dump = "5800x3d"
    section = "Almacenamiento"

    def base(self, f): return _disks(f, {"nvme0n1": 45.0, "nvme1n1": 40.0})
    def missing(self, f): return _disks(f, {"nvme0n1": None, "nvme1n1": None})
    def raw(self, f): return _disks(f, {"nvme0n1": RAW_DEGREES, "nvme1n1": 40.0})
    def chart(self, v): return v.storage_page.tile_temp.chart

    def other(self, f, ventana):
        # The other disk is the hottest.
        return _disks(f, {"nvme0n1": 40.0, "nvme1n1": 55.0}), 55.0

    def test_one_series(self): self._run()


class TestSensores(unittest.TestCase):
    """Its history is per sensor: without its reading it does not move, and a
    raw reading gets neither in its line nor in its extremes."""

    def test_a_sensors_history(self):
        qt.app()
        f = shared_snapshot(EQUIPOS / "i5-10400")
        sensor = next(s for s in f.sensors if s.kind.value == "temperature")

        def con(valor):
            return dataclasses.replace(f, sensors=tuple(
                dataclasses.replace(s, value=valor) if s.key == sensor.key else s
                for s in f.sensors))

        sin = dataclasses.replace(f, sensors=tuple(s for s in f.sensors if s.key != sensor.key))
        with pantalla.Ventana(con(50.0)) as ventana:
            ventana.select_section("Sensores")
            ventana._on_sample(con(50.0))
            antes = ventana._tracker.get(sensor.key)
            historia, maximo = list(antes.history), antes.maximum
            for muestra in (sin, con(RAW_DEGREES)):
                ventana._on_sample(muestra)
                despues = ventana._tracker.get(sensor.key)
                self.assertEqual((list(despues.history), despues.maximum), (historia, maximo))


class TestTheDoor(unittest.TestCase):

    def test_no_point_without_its_series(self):
        from silux.ui import theme
        from silux.ui.widgets import Sparkline
        qt.app()
        with self.assertRaises(TypeError):
            Sparkline(theme.DARK).push(9.0)


if __name__ == "__main__":
    unittest.main()
