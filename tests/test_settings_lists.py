"""Settings' lists, one under another down the page, all as wide as the
widest of them: each at its own width, their left edges made a saw."""

import unittest

from PySide6.QtWidgets import QComboBox

from tests import geometry, pantalla, qt
from tests.test_anchura import list_content_width
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestOneWidth(unittest.TestCase):
    def test_every_list_as_wide_as_the_widest(self):
        app = qt.app()
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.resize(1400, 900)
            window.select_section("Ajustes")
            geometry.settle(app, 6)
            page = window.settings_page
            boxes = [b for b in page.findChildren(QComboBox) if b.isVisibleTo(page)]
            self.assertGreaterEqual(len(boxes), 6)
            widths = {b.width() for b in boxes}
            self.assertEqual(len(widths), 1, sorted(widths))
            widest = max(list_content_width(b) for b in boxes)
            self.assertLessEqual(abs(widths.pop() - widest), 1)


if __name__ == "__main__":
    unittest.main()
