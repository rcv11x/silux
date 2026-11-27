"""Devices lists what has no kernel driver bound, and what can be done.

Real cases from the dumps: a Broadcom Wi-Fi with no driver, a VL805 USB
controller, a chipset's sound. A graphics card's second function, whose
first one has its driver, is no case: it needs none of its own.
"""

import unittest

from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestWithoutDriver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def page(self, dump):
        ventana = pantalla.Ventana(shared_snapshot(EQUIPOS / dump))
        window = ventana.__enter__()
        self.addCleanup(ventana.__exit__, None, None, None)
        window.select_section("Dispositivos")
        geometry.settle(self.app)
        return window.devices_page

    def rows(self, page):
        table = page.nodriver
        return [[cell.full_text() for cell in row] for row in table._cells]

    def test_the_ones_without_a_driver_are_listed_with_their_id(self):
        for dump, name, ids in (("i7-4710hq", "BCM43142", "14e4:4365"),
                                ("fx-8150", "VL805", "1106:3483")):
            page = self.page(dump)
            with self.subTest(dump=dump):
                self.assertTrue(page.nodriver_card.isVisibleTo(page))
                rows = self.rows(page)
                self.assertTrue(any(name in row[0] for row in rows), rows)
                self.assertTrue(any(ids in row[2] for row in rows), rows)

    def test_a_second_function_of_a_card_with_its_driver_is_not_one(self):
        page = self.page("celeron-560")
        self.assertFalse(any("secondary" in row[0] for row in self.rows(page)))

    def test_with_none_the_card_is_not_there(self):
        page = self.page("5800x3d")
        self.assertFalse(page.nodriver_card.isVisibleTo(page))


if __name__ == "__main__":
    unittest.main()
