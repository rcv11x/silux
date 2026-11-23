"""Graphics: the errors the card's PCIe link counted since boot (AER).

Corrected errors are fixed by resending, but many of them point to a bad
slot, riser or cable; non-fatal and fatal ones are real failures. The
kernel publishes the three totals in the device's own directory.
"""

import dataclasses
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

    def test_the_radeon_counts_nothing(self):
        link = shared_snapshot(EQUIPOS / "5800x3d").gpus[0].link
        self.assertEqual((link.correctable_errors, link.nonfatal_errors, link.fatal_errors),
                         (0, 0, 0))
        self.assertEqual(render.pcie_errors(link), _("pcie.errors.none"))

    def test_only_the_kinds_that_happened_are_named(self):
        link = dataclasses.replace(shared_snapshot(EQUIPOS / "5800x3d").gpus[0].link,
                                   correctable_errors=1, fatal_errors=2)
        self.assertEqual(render.pcie_errors(link), " · ".join((
            _("pcie.errors.correctable.one").format(n="1"),
            _("pcie.errors.fatal").format(n="2"))))

    def test_without_aer_there_is_no_count(self):
        link = shared_snapshot(EQUIPOS / "i5-10400").gpus[0].link
        self.assertIsNone(link.correctable_errors)


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnTheGraphicsPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def label(self, window):
        from silux.ui.pages.graphics import GpuSection
        window.select_section("Gráficos")
        self.app.processEvents()
        section = window.graphics_page.findChildren(GpuSection)[0]
        return section.clocks._values[_("gpu.clock.linkerrors")]

    def test_shown_with_the_radeon(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            label = self.label(window)
            self.assertTrue(label.isVisible())
            self.assertEqual(label.full_text(), _("pcie.errors.none"))

    def test_hidden_with_the_intel_integrated(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            self.assertFalse(self.label(window).isVisible())


if __name__ == "__main__":
    unittest.main()
