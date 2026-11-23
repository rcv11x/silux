"""Graphics: the card's power limit, its factory value and the range it accepts.

amdgpu publishes power1_cap with power1_cap_default, _min and _max; only
the current cap was read. A cap above the factory one means someone raised
it, which is worth seeing next to the power draw.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestTheReading(unittest.TestCase):

    def test_the_whole_limit_from_amdgpu(self):
        gpu = shared_snapshot(EQUIPOS / "5800x3d").gpus[0]
        self.assertEqual((gpu.power_cap_w, gpu.power_cap_default_w,
                          gpu.power_cap_min_w, gpu.power_cap_max_w),
                         (340.0, 330.0, 231.0, 340.0))
        # In force and factory in the row, in whole watts as the maker writes
        # them; the range, which didn't fit, in its tooltip.
        self.assertEqual(render.gpu_factory_power_limit(gpu), " · ".join((
            "340 W", _("gpu.power.factory").format(w="330 W"))))
        self.assertIn(_("gpu.power.range").format(desde="231", hasta="340 W")[1:],
                      render.gpu_power_limit_tip(gpu))
        # 340 over a factory 330: the tooltip says it was raised.
        self.assertIn(_("gpu.power.raised"), render.gpu_power_limit_tip(gpu))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnTheGraphicsPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_shown_with_the_radeon(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            window.select_section("Gráficos")
            self.app.processEvents()
            label = next(s for s in self._sections(window)).sensors._values[_("gpu.sensor.powercap")]
            self.assertTrue(label.isVisible())
            self.assertIn(_("gpu.power.factory").format(w="330 W"), label.full_text())

    def test_hidden_with_the_intel_integrated(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.select_section("Gráficos")
            self.app.processEvents()
            label = next(s for s in self._sections(window)).sensors._values[_("gpu.sensor.powercap")]
            self.assertFalse(label.isVisible())

    @staticmethod
    def _sections(window):
        from silux.ui.pages.graphics import GpuSection
        return window.graphics_page.findChildren(GpuSection)


if __name__ == "__main__":
    unittest.main()
