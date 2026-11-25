"""A memory speed is named as it is sold wherever it shows: «DDR4-2666».

The firmware's table writes a grade with a third in it rounded its own way,
2666 or 2667; an i5-10400's BIOS writes 2667. Memory already named the grade
while Home, the share card, the report and the memory test wrote the raw
figure.
"""

import dataclasses
import unittest
from unittest import mock

from silux import memtest, render, report
from silux.model import MemoryModule
from silux.settings import Preferences
from tests import qt
from tests.pantalla import textos_de
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_memtest import recorded

GIB = 1024 ** 3


def with_modules():
    """The i5-10400 as its BIOS describes its two modules."""
    module = MemoryModule(locator="DIMM1", populated=True, size_bytes=8 * GIB, type="DDR4",
                          speed_mts=2667, configured_mts=2667)
    return dataclasses.replace(shared_snapshot(EQUIPOS / "i5-10400"),
                               modules=(module, dataclasses.replace(module, locator="DIMM2")))


class TestTheGradeEverywhere(unittest.TestCase):
    def test_home(self):
        from silux.ui import theme
        from silux.ui.pages.home import HomePage

        page = HomePage(theme.palette_for(qt.app(), "dark"), Preferences().normalized())
        page.apply(with_modules())
        seen = " ".join(textos_de(page))
        self.assertIn("DDR4-2666", seen)
        self.assertNotIn("2667", seen)

    def test_share_card(self):
        from silux.ui import tarjeta

        seen = " ".join(" ".join(row) for row in tarjeta._fila(with_modules()))
        self.assertIn("2666 MT/s", seen)
        self.assertNotIn("2667", seen)

    def test_report(self):
        text = report.build(with_modules())
        self.assertIn("2666 MT/s", text)
        self.assertNotIn("2667 MT/s", text)

    def test_the_memory_test_s_share_of_the_maximum(self):
        """Measured in the window with permissions: 78 % of 2 × 2667 × 8 B."""
        from silux.ui import theme
        from silux.ui.pages.memtest import MemoryTestTab

        result = recorded("i5-10400-window")
        self.assertEqual(result.speed_mts, 2667)
        tab = MemoryTestTab(theme.palette_for(qt.app(), "dark"), Preferences().normalized())
        tab.show_result(result)
        seen = " ".join(textos_de(tab))
        self.assertIn(f"{render.memory_speed(2667)} MT/s", seen)
        self.assertNotIn("2667", seen)
        with mock.patch.object(memtest, "load_history", return_value=[result]):
            text = report._memory_test()
        self.assertIn(f"× {render.memory_speed(2667)} MT/s × 8 B", text)
        self.assertNotIn("2667", text)


if __name__ == "__main__":
    unittest.main()
