"""No page grows past its view, sample after sample, on any dump: every page
and every Performance tab, at a common window and at a wide one
(`tests/geometry.py`)."""

import unittest

from tests import geometry, pantalla, qt
from tests.per_dump import per_dump
from tests.test_equipos import shared_snapshot

SIZES = ((1100, 720), (1900, 1000))


class TestPagesStayInTheirView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")

    def _every_page(self, folder):
        snapshot = shared_snapshot(folder)
        with pantalla.Ventana(snapshot) as window:
            for width, height in SIZES:
                window.resize(width, height)
                geometry.settle(self.app)
                for section, page in pantalla.recorrer(window):
                    for tab, area in geometry.scroll_areas(page):
                        with self.subTest(width=width, section=section, tab=tab):
                            geometry.stays_in_view(self, window, area, snapshot)


per_dump(TestPagesStayInTheirView, "every_page", TestPagesStayInTheirView._every_page)


if __name__ == "__main__":
    unittest.main()
