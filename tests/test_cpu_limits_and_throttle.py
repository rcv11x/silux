"""Two cheap Intel readings: the window of PL1 and PL2, and thermal throttling.

PL1 holds the average power over its window, which is how long the processor
can stay above it; the kernel publishes it next to the limit. And every core
and package counts the times it hit its temperature limit since boot.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import ThermalThrottle
from silux.providers.base import Draft
from silux.providers.rapl import PowerLimits
from silux.providers.thermal_throttle import ThermalThrottleCounts
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

RAPL = "/sys/class/powercap/intel-rapl:0/"
LIMITS = {RAPL + "name": "package-0\n",
          RAPL + "constraint_0_name": "long_term\n",
          RAPL + "constraint_0_power_limit_uw": "65000000\n",
          RAPL + "constraint_0_time_window_us": "27983872\n",
          RAPL + "constraint_1_name": "short_term\n",
          RAPL + "constraint_1_power_limit_uw": "115000000\n",
          RAPL + "constraint_1_time_window_us": "2440\n"}


def _throttle_tree(per_core: dict) -> dict:
    """Two threads per core, as on the i5-10400: siblings share a counter."""
    files = {}
    for cpu in range(2 * len(per_core)):
        core = cpu % len(per_core)
        base = f"/sys/devices/system/cpu/cpu{cpu}/"
        count, ms = per_core[core]
        files.update({base + "topology/physical_package_id": "0\n",
                      base + "topology/core_id": f"{core}\n",
                      base + "thermal_throttle/core_throttle_count": f"{count}\n",
                      base + "thermal_throttle/core_throttle_total_time_ms": f"{ms}\n",
                      base + "thermal_throttle/package_throttle_count": "2\n",
                      base + "thermal_throttle/package_throttle_total_time_ms": "1400\n"})
    return files


def _collect(provider, files):
    with arbol(files):
        draft = Draft()
        provider.collect(draft)
    return draft


class TestTheWindowOfEachLimit(unittest.TestCase):

    def test_read_next_to_the_limit(self):
        power = _collect(PowerLimits(), LIMITS).cpu_extra["power"]
        self.assertEqual((power.limit_long_w, power.window_long_s), (65.0, 27.983872))
        self.assertEqual((power.limit_short_w, power.window_short_s), (115.0, 0.00244))

    def test_shown_in_seconds_or_milliseconds(self):
        self.assertEqual(render.power_limit(65.0, 27.983872),
                         _("cpu.limit.window").format(limite="65 W", ventana="28.0 s"))
        self.assertEqual(render.time_window(0.00244), "2.4 ms")
        self.assertEqual(render.power_limit(65.0, None), render.watts(65.0))


class TestThermalThrottling(unittest.TestCase):

    def test_each_core_once_and_the_package_once(self):
        throttle = _collect(ThermalThrottleCounts(),
                            _throttle_tree({0: (3, 200), 1: (2, 400)})).cpu_extra["thermal_throttle"]
        self.assertEqual(throttle, ThermalThrottle(package_count=2, package_ms=1400,
                                                   core_count=5, core_ms=600))

    def test_said_in_words(self):
        self.assertEqual(render.thermal_throttle(ThermalThrottle()), _("cpu.throttle.none"))
        text = render.thermal_throttle(ThermalThrottle(2, 1400, 5, 600))
        self.assertEqual(text, " · ".join((_("cpu.throttle.cores").format(n=5, tiempo="0.6 s"),
                                           _("cpu.throttle.package").format(n=2, tiempo="1.4 s"))))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnTheCpuPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _page(self, window):
        window.select_section("CPU")
        for _turn in range(4):
            self.app.processEvents()
        return window.cpu_page

    def test_the_intel_dump_shows_both(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400-turbo")) as window:
            limits = self._page(window).limits
            self.assertEqual(limits._values[_("cpu.limit.pl1")].full_text(),
                             render.power_limit(65.0, 27.983872))
            self.assertEqual(limits._values[_("cpu.limit.pl2")].full_text(),
                             render.power_limit(115.0, 0.00244))
            self.assertTrue(limits._values[_("cpu.throttle")].isVisible())
            self.assertEqual(limits._values[_("cpu.throttle")].full_text(), _("cpu.throttle.none"))

    def test_counts_that_arrive_with_the_page_open(self):
        photo = shared_snapshot(EQUIPOS / "i5-10400-turbo")
        with pantalla.Ventana(photo) as window:
            page = self._page(window)
            window._on_sample(dataclasses.replace(photo, cpu=dataclasses.replace(
                photo.cpu, thermal_throttle=ThermalThrottle(1, 300, 0, 0))))
            self.app.processEvents()
            self.assertEqual(page.limits._values[_("cpu.throttle")].full_text(),
                             _("cpu.throttle.package").format(n=1, tiempo="0.3 s"))

    def test_amd_has_no_row(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            self.assertFalse(self._page(window).limits._names[_("cpu.throttle")].isVisible())


if __name__ == "__main__":
    unittest.main()


class TestALimitLeftOpen(unittest.TestCase):
    """A RAPL limit of 4095 W is the most its register holds: the firmware's
    way of setting none, not a limit of 4095 W."""

    HYBRID = EQUIPOS / "i7-12700kf"

    def test_the_dump_has_pl1_and_no_pl2(self):
        power = shared_snapshot(self.HYBRID).cpu.power
        self.assertEqual((power.limit_long_w, power.limit_long_unlimited), (125.0, False))
        self.assertEqual((power.limit_short_w, power.window_short_s), (None, None))
        self.assertTrue(power.limit_short_unlimited)

    def test_any_limit_with_that_value(self):
        for raw in ("4095000000\n", "4095875000\n"):
            with self.subTest(raw=raw):
                files = dict(LIMITS, **{RAPL + "constraint_0_power_limit_uw": raw})
                power = _collect(PowerLimits(), files).cpu_extra["power"]
                self.assertEqual((power.limit_long_w, power.limit_long_unlimited), (None, True))
                self.assertEqual((power.limit_short_w, power.limit_short_unlimited), (115.0, False))

    def test_a_copy_with_watts_is_the_one_enforced(self):
        from silux.providers.rapl import effective_limits

        mmio = {"limit_short_w": 64.0, "window_short_s": 0.002}
        self.assertEqual(effective_limits({"limit_short_unlimited": True}, mmio), mmio)
        self.assertEqual(effective_limits(mmio, {"limit_short_unlimited": True}), mmio)
        self.assertEqual(effective_limits({"limit_short_unlimited": True}, {}),
                         {"limit_short_unlimited": True})

    def test_it_is_no_threshold_of_the_package_sensor(self):
        from silux.providers.derived import DerivedSensors

        draft = Draft()
        draft.cpu_extra["power"] = dataclasses.replace(
            shared_snapshot(self.HYBRID).cpu.power, package_w=95.0)
        package = next(s for s in DerivedSensors._power(draft, "CPU") if s.key == "rapl/package_w")
        self.assertEqual((package.high, package.critical), (125.0, None))

    @unittest.skipIf(QApplication is None, "sin PySide6")
    def test_said_on_the_cpu_page(self):
        qt.app()
        with pantalla.Ventana(shared_snapshot(self.HYBRID)) as window:
            window.select_section("CPU")
            text = "\n".join(pantalla.textos_de(window.stack.currentWidget()))
        self.assertIn(_("cpu.limit.pl2"), text)
        self.assertIn(_("cpu.limit.unlimited"), text)
        self.assertNotIn("4095", text)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestFavouredCores(unittest.TestCase):
    """With Turbo Boost Max 3.0 each core has its own ceiling: the type's is
    the highest, and the page says some reach higher instead of «the kernel
    caps it». The i7-12700KF's annex kept cpu0's (4.90 GHz) and cpu16's only:
    the others are added with the shape of a favoured pair."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile

        cls.app = qt.app()
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        dump = shutil.copytree(EQUIPOS / "i7-12700kf", f"{tmp.name}/i7-12700kf", symlinks=True)
        policies = f"{dump}/sys/devices/system/cpu/cpufreq"
        for cpu in range(1, 16):
            with open(f"{policies}/policy{cpu}/cpuinfo_max_freq", "w") as out:
                out.write("5000000\n" if cpu in (4, 5) else "4900000\n")
        cls.snapshot = foto(dump)[0]

    def test_the_type_reaches_its_favoured_cores_ceiling(self):
        performance = self.snapshot.cpu.types[0].clocks
        self.assertEqual((performance.max_hz, performance.max_turbo_hz),
                         (5_000_000_000, 5_000_000_000))
        self.assertEqual((performance.favoured_cpus, performance.others_max_hz),
                         ((4, 5), 4_900_000_000))
        self.assertIsNone(performance.turbo_headroom_hz)

    def test_said_on_the_cpu_page_instead_of_a_cap(self):
        from PySide6.QtWidgets import QLabel

        sentence = _("clock.max.favoured").format(
            cpus="4, 5", max=render.hz(5_000_000_000), others=render.hz(4_900_000_000))
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("CPU")
            page = window.stack.currentWidget()
            text = "\n".join(pantalla.textos_de(page))
            label = next(w for w in page.findChildren(QLabel) if w.text() == sentence)
            # A fact of the part, not a warning.
            self.assertEqual(label.objectName(), "Muted")
        self.assertIn(sentence, text)
        self.assertNotIn(_("clock.turbo.capped").split("{")[0], text)

    def test_and_in_the_short_report(self):
        from silux import report

        self.assertIn("máx kernel 5.00 GHz en las CPU 4, 5 y 4.90 GHz en las demás",
                      report.build(self.snapshot))
