"""A row of a text and a control turns into a column before the control
cuts its text: with the largest font at 720 px, Settings showed «Bytes por
segundo…» beside a description one word wide."""

import unittest

from silux.ui import theme
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestRowsFoldBeforeCutting(unittest.TestCase):
    def test_settings_lists_whole_with_the_largest_font(self):
        app = qt.app()
        saved = theme.METRICS
        self.addCleanup(lambda: (setattr(theme, "METRICS", saved),
                                 theme.apply(app, "dark", "normal")))
        theme.set_density("normal", "máximo")
        theme.apply(app, "dark", "normal", "máximo")
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.resize(720, 900)
            window.select_section("Ajustes")
            geometry.settle(app, 8)
            page = window.stack.currentWidget()
            for box in (page.language_box, page.theme_box, page.network_box):
                with self.subTest(box=box.currentText()):
                    self.assertGreaterEqual(box.width(), box.sizeHint().width())


if __name__ == "__main__":
    unittest.main()
