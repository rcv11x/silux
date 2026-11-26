"""Memory's permission card says when the modules read are not all there is.

A desktop with two DDR5 modules showed one without permissions: the kernel
registered only one SPD chip. The header said «the rest could not be read»,
but the card asking for permissions, the one people read, spoke of «the
module above» as if it were all the memory.
"""

import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


def card_text(snapshot) -> str:
    qt.app()
    with pantalla.Ventana(snapshot) as window:
        window.select_section("Memoria")
        return window.memory_page.elevation_text.text()


class TestTheCard(unittest.TestCase):
    def test_one_module_of_more_says_how_much_it_covers(self):
        snapshot = shared_snapshot(EQUIPOS / "ryzen9-7900")
        self.assertEqual(len(snapshot.spd), 1)
        self.assertFalse(snapshot.spd_accounts_for_all_memory)
        text = card_text(snapshot)
        self.assertIn(render.size(snapshot.spd[0].capacity_bytes), text)
        self.assertIn(render.size(snapshot.system.memory.total_bytes), text)

    def test_modules_that_cover_all_the_memory_say_nothing_of_a_rest(self):
        snapshot = next(s for s in (shared_snapshot(EQUIPOS / name) for name in (
            "i5-1135g7", "celeron-560", "i5-3330", "i7-12700kf", "i5-8350u"))
            if s.spd and s.spd_accounts_for_all_memory)
        text = card_text(snapshot)
        self.assertNotIn(render.size(snapshot.system.memory.total_bytes), text)
