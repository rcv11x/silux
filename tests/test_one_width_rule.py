"""Every page takes the window's width the same way: its margins at the
sides and its content across the rest. Performance kept its content to a
column of 120 characters, centred, and at 2560 px left most of the page
empty while every other page went from side to side.
"""

import unittest

from PySide6.QtWidgets import QWidget

from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestOneWidthRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_at_2560_every_page_keeps_only_its_margins(self):
        from silux.ui import theme

        margin = theme.METRICS.page_margin
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.resize(2560, 1300)
            geometry.settle(self.app)
            for name, page in pantalla.recorrer(window):
                geometry.settle(self.app)
                # A section this machine lacks (a desktop's battery) has none.
                roots = [w for w in page.findChildren(QWidget) if w.objectName() == "Root"]
                for root in roots:
                    margins = root.layout().contentsMargins()
                    with self.subTest(page=name, root=root.parent().__class__.__name__):
                        self.assertEqual((margins.left(), margins.right()), (margin, margin))


if __name__ == "__main__":
    unittest.main()
