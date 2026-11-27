"""The figures a GPU's spec sheet gives that are worked out from what the
driver reads: shading and texture units, FP32 TFLOPS and fill rates. Each
says on the page that it is calculated, and with what.

The formulas are checked against AMD's own spec sheets, with the boost
clock each one states: RX 9070 XT (64 CU, 2970 MHz) 48.7 TFLOPS; RX 9060 XT
(32 CU, 3130 MHz) 25.6; RX 7600 (32 CU, 2655 MHz) 21.75; RX 6600 (28 CU,
2491 MHz, RDNA 2, no dual issue) 8.93.
"""

import unittest

from silux import gpu_figures


class TestTheFormulas(unittest.TestCase):
    def test_amd_s_spec_sheets(self):
        for name, cus, isa, clock, tflops in (("RX 9070 XT", 64, "gfx1201", 2970, 48.7),
                                              ("RX 9060 XT", 32, "gfx1200", 3130, 25.6),
                                              ("RX 7600", 32, "gfx1102", 2655, 21.75),
                                              ("RX 6600", 28, "gfx1032", 2491, 8.93)):
            figures = gpu_figures.amd(cus, 64, isa, clock * 1_000_000)
            with self.subTest(card=name):
                self.assertEqual(figures.shading_units, cus * 64)
                self.assertEqual(figures.texture_units, cus * 4)
                self.assertAlmostEqual(figures.tflops, tflops, delta=0.05)

    def test_fill_rates_are_units_by_clock(self):
        figures = gpu_figures.amd(64, 128, "gfx1201", 2_520_000_000)
        self.assertAlmostEqual(figures.gigapixels, 128 * 2.52)
        self.assertAlmostEqual(figures.gigatexels, 256 * 2.52)

    def test_an_architecture_without_a_formula_gives_none(self):
        self.assertIsNone(gpu_figures.amd(64, 128, "gfx1301", 2_520_000_000))
        self.assertIsNone(gpu_figures.amd(64, 128, None, 2_520_000_000))
        self.assertIsNone(gpu_figures.amd(None, 128, "gfx1201", 2_520_000_000))


class TestOnThePage(unittest.TestCase):
    def test_each_says_it_is_calculated(self):
        from silux import render
        from silux.i18n import _
        from tests import geometry, pantalla, qt
        from tests.test_equipos import EQUIPOS, shared_snapshot

        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        gpu = snapshot.gpus[snapshot.working_gpu]
        from silux.ui.pages.graphics import GpuSection

        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            geometry.settle(app)
            section = window.graphics_page.findChildren(GpuSection)[0]
            figures = gpu_figures.of(gpu)
            for field, text in (("gpu.field.units", render.thousands(figures.shading_units)),
                                ("gpu.field.fp32", render.tflops(figures.tflops))):
                label = section.card.value_label(_(field))
                with self.subTest(field=field):
                    self.assertFalse(label.isHidden())
                    self.assertIn(text, label.full_text())
                    self.assertIn(_("gpu.calculated"), label.full_text())
                    self.assertTrue(label.toolTip())


if __name__ == "__main__":
    unittest.main()
