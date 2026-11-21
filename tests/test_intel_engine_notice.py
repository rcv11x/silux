"""An Intel GPU's notice says what is known of its engines' usage.

A Lenovo LOQ, with permissions: the helper opened the package's
energy-gpu and none of the UHD's engine counters, and the notice said their
usage «ya se está leyendo» over a «Ahora mismo» with no bars. Any counter
coming back is not this card's coming back.

The i5-10400's dump with its i915 PMU as the kernel publishes it, and the
helper's answer as the client hands it over.
"""

import pathlib
import unittest

from silux import volcado
from silux.collector import Collector
from silux.i18n import _
from silux.model import Need
from silux.privileged.client import PmuUnsupported
from silux.providers.drm import GpuState
from tests import pantalla, qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"
ENERGY_SCALE = 2.3283064365386963e-10
# What i915 publishes with and without engines: the busy counters are one per
# engine the GT brought up.
WITH_ENGINES = ("actual-frequency", "interrupts", "rc6-residency", "requested-frequency",
                "rcs0-busy", "bcs0-busy", "vcs0-busy", "vecs0-busy")
WITHOUT_ENGINES = ("actual-frequency", "interrupts", "rc6-residency", "requested-frequency")


class Helper:
    """The client as GpuState sees it once the user gave permissions."""

    def __init__(self, i915: bool = True, unsupported: bool = False, allowed: bool = True):
        self._allowed = allowed
        self._i915 = i915
        self._unsupported = unsupported
        self._clock = 0

    def connected(self):
        return self._allowed

    def gpu_pmu(self):
        if self._unsupported:
            raise PmuUnsupported("no hay ninguna gráfica con contadores de ocupación")
        self._clock += 1_000_000_000
        counters = {"power": {"energy-gpu": self._clock // 4}}
        if self._i915:
            counters["i915"] = {"rcs0-busy": self._clock // 10, "vcs0-busy": 0,
                                "bcs0-busy": 0, "vecs0-busy": 0}
        return self._clock, counters, {"power": {"energy-gpu": ENERGY_SCALE}}

    def close(self):
        pass


def _the_pmu(root, events):
    pmu = root / "sys/devices/i915"
    (pmu / "events").mkdir(parents=True, exist_ok=True)
    (pmu / "type").write_text("14\n")
    for event in events:
        (pmu / "events" / event).write_text("config=0x0\n")


def _photo(events, helper):
    with volcado.montado(EQUIPOS / "i5-10400") as root:
        _the_pmu(root, events)
        collector = Collector()
        estado = next(p for p in collector.providers if isinstance(p, GpuState))
        estado.client = helper
        try:
            collector.snapshot()
            return collector.snapshot()
        finally:
            collector.close()


def _notice(photo):
    return next((n for n in photo.notes if n.path == "gpus.0"), None)


class TestTheNoticeOfAnIntelsEngines(unittest.TestCase):

    def test_when_the_helper_goes_it_asks_for_them_again(self):
        # F-M21: read once, the notice kept saying the usage was being read
        # after the helper died, and there was no usage any more.
        helper = Helper()
        with volcado.montado(EQUIPOS / "i5-10400") as root:
            _the_pmu(root, WITH_ENGINES)
            collector = Collector()
            next(p for p in collector.providers if isinstance(p, GpuState)).client = helper
            try:
                collector.snapshot()
                # Read, there is nothing about its usage to say.
                self.assertIsNone(_notice(collector.snapshot()))
                helper._allowed = False
                photo = collector.snapshot()
            finally:
                collector.close()
        self.assertIsNone(photo.gpus[0].busy_percent)
        self.assertEqual(_notice(photo).need, Need.ROOT)

    def test_without_permissions_it_asks_for_them(self):
        photo = _photo(WITH_ENGINES, Helper(allowed=False))
        self.assertEqual(_notice(photo).need, Need.ROOT)

    def test_its_counters_came_back(self):
        photo = _photo(WITH_ENGINES, Helper())
        self.assertIsNotNone(photo.gpus[0].busy_percent)
        self.assertIsNone(_notice(photo))

    def test_only_the_energy_came_back(self):
        # The LOQ's case: the kernel publishes them and they did not come.
        photo = _photo(WITH_ENGINES, Helper(i915=False))
        self.assertIsNone(photo.gpus[0].busy_percent)
        self.assertEqual(_notice(photo).need, Need.ERROR)
        self.assertEqual(_notice(photo).hint, _("prov.drm.intelunopened.hint"))

    def test_the_kernel_publishes_no_engine_counters(self):
        photo = _photo(WITHOUT_ENGINES, Helper(i915=False))
        self.assertEqual(_notice(photo).need, Need.HARDWARE)
        self.assertEqual(_notice(photo).hint, _("prov.drm.inteldriver.hint"))

    def test_the_helper_opened_none_of_them(self):
        photo = _photo(WITH_ENGINES, Helper(unsupported=True))
        self.assertEqual(_notice(photo).hint, _("prov.drm.intelunopened.hint"))
        photo = _photo(WITHOUT_ENGINES, Helper(unsupported=True))
        self.assertEqual(_notice(photo).hint, _("prov.drm.inteldriver.hint"))

    def test_on_screen_it_no_longer_says_it_is_being_read(self):
        qt.app()
        photo = _photo(WITH_ENGINES, Helper(i915=False))
        with pantalla.Ventana(photo) as ventana:
            ventana.select_section("Gráficos")
            textos = " ".join(pantalla.textos_de(ventana.graphics_page))
        self.assertIn(_("prov.drm.intelunopened.hint"), textos)
        self.assertNotIn(_("prov.drm.intelroot"), textos)


if __name__ == "__main__":
    unittest.main()
