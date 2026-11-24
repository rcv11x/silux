"""Watts from an energy counter, and the ones that cannot be.

The author's T14 ran glmark2 on battery: its Iris Xe drew 9 W, and its power
chart got a point at 1336648637.3 W that flattened the rest. Whatever the
reading went through (the counter wrapping, a reading from sysfs and the next
from the helper, the helper's 100 ms pace), a negative watt or one above what
the part can draw is dropped and told in the report, with its numbers.

A powercap tree as the T14's: its package declares PL4 (`peak_power`, 121 W).
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux.model import Need
from silux.providers import rapl
from silux.providers.base import Draft

MAX_RANGE_UJ = 262143328850


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class Helper:
    """The RAPL helper as the client hands its answer over; `wait` is the
    100 ms the helper may wait for its pace before reading."""

    def __init__(self, clock, zones=None, wait=0.0):
        self.clock, self.zones, self.wait = clock, zones or {}, wait

    def connected(self):
        return True

    def rapl(self):
        self.clock.now += self.wait
        return dict(self.zones)


class _Tree(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.package = self.root / "intel-rapl:0"
        self.package.mkdir()
        (self.package / "name").write_text("package-0\n")
        (self.package / "max_energy_range_uj").write_text(f"{MAX_RANGE_UJ}\n")
        for n, name, watts in ((0, "long_term", 28), (1, "short_term", 64), (2, "peak_power", 121)):
            (self.package / f"constraint_{n}_name").write_text(name + "\n")
            (self.package / f"constraint_{n}_power_limit_uw").write_text(f"{watts * 10**6}\n")
        self.clock = Clock()
        for patch in (mock.patch.object(rapl, "POWERCAP", self.root),
                      mock.patch.object(rapl.time, "monotonic", self.clock)):
            patch.start()
            self.addCleanup(patch.stop)

    def energy(self, microjoules):
        (self.package / "energy_uj").write_text(f"{microjoules}\n")

    def sample(self, provider, seconds=1.0):
        self.clock.now += seconds
        draft = Draft()
        provider.collect(draft)
        power = draft.cpu_extra.get("power")
        return (power.package_w if power else None), draft


class TestTheCounterWrapping(_Tree):

    def test_with_its_range_it_counts_round(self):
        provider = rapl.RaplPower()
        self.energy(MAX_RANGE_UJ - 500_000)
        self.sample(provider)
        self.energy(1_500_000)
        self.assertAlmostEqual(self.sample(provider)[0], 2.0)

    def test_without_its_range_that_second_has_no_figure(self):
        (self.package / "max_energy_range_uj").unlink()
        provider = rapl.RaplPower()
        self.energy(MAX_RANGE_UJ - 500_000)
        self.sample(provider)
        self.energy(1_500_000)
        self.assertIsNone(self.sample(provider)[0])


class TestTheSourceChanging(_Tree):

    def test_sysfs_then_the_helper_is_not_subtracted(self):
        helper = Helper(self.clock, {"intel-rapl:0": 5_000_000})
        provider = rapl.RaplPower(client=helper)
        self.energy(1_000_000)
        self.sample(provider)
        (self.package / "energy_uj").unlink()       # the kernel keeps it for root now
        self.assertIsNone(self.sample(provider)[0])
        helper.zones = {"intel-rapl:0": 14_000_000}
        self.assertAlmostEqual(self.sample(provider)[0], 9.0)

    def test_the_helpers_wait_is_timed_where_it_read(self):
        # Read 100 ms late the first time, on time the second: 8.1 J in 0.9 s
        # is 9 W, not the 8.1 W of timing both from before the request.
        helper = Helper(self.clock, {"intel-rapl:0": 900_000}, wait=0.1)
        provider = rapl.RaplPower(client=helper)
        self.sample(provider, seconds=0.0)
        helper.wait = 0.0
        helper.zones = {"intel-rapl:0": 9_000_000}
        self.assertAlmostEqual(self.sample(provider, seconds=0.9)[0], 9.0)


class TestTheImpossible(_Tree):

    def test_above_pl4_it_is_dropped_and_told(self):
        provider = rapl.RaplPower()
        self.energy(1_000_000)
        self.sample(provider)
        self.energy(1_000_000 + 5_000 * 10**6)    # 5000 J in a second
        watts, draft = self.sample(provider)
        self.assertIsNone(watts)
        nota = next(n for n in draft.notes if n.path == rapl.DISCARDED_PATH)
        self.assertIs(nota.need, Need.ERROR)
        self.assertIn("5000.0", nota.message)
        # The next good second is there again.
        self.energy(1_000_000 + 5_000 * 10**6 + 9_000_000)
        self.assertAlmostEqual(self.sample(provider)[0], 9.0)

    def test_the_ceiling_is_what_the_package_declares(self):
        self.assertEqual(rapl.package_ceiling_w(), 121.0)
        (self.package / "constraint_2_name").unlink()
        self.assertEqual(rapl.package_ceiling_w(), 128.0)       # twice PL2
        for n in (0, 1):
            (self.package / f"constraint_{n}_name").unlink()
        self.assertEqual(rapl.package_ceiling_w(), rapl.FALLBACK_CEILING_W)

    def test_a_limit_left_open_caps_nothing(self):
        # Twice PL1 would drop what an unlimited board really draws.
        (self.package / "constraint_2_name").unlink()
        (self.package / "constraint_1_power_limit_uw").write_text("4095000000\n")
        self.assertEqual(rapl.package_ceiling_w(), rapl.FALLBACK_CEILING_W)


class TestTheIntegratedGpusEnergy(_Tree):
    """Its watts come from the helper's energy-gpu, and it is part of the
    package: above the package's ceiling it cannot be."""

    def _state(self, lecturas):
        from silux.providers.drm import GpuState
        from tests.test_gpu import ClienteFalso
        return GpuState(client=ClienteFalso(lecturas))

    def _reading(self, ns, julios):
        escala = 2.3283064365386963e-10
        return ns, {"power": {"energy-gpu": int(julios / escala)}}, {"power": {"energy-gpu": escala}}

    def test_a_jump_is_dropped(self):
        estado = self._state([self._reading(10**9, 100.0), self._reading(2 * 10**9, 1_336_648_746.3)])
        estado._counters(1.0)
        _ocupacion, vatios = estado._counters(1.0)
        self.assertIsNone(vatios)
        draft = Draft()
        estado._discarded.note(draft)
        self.assertTrue([n for n in draft.notes if n.path == rapl.DISCARDED_PATH])

    def test_nine_watts_stay(self):
        estado = self._state([self._reading(10**9, 100.0), self._reading(2 * 10**9, 109.0)])
        estado._counters(1.0)
        self.assertAlmostEqual(estado._counters(1.0)[1], 9.0, places=3)


if __name__ == "__main__":
    unittest.main()
