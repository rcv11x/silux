"""Where an integrated GPU is: in the processor or in the chipset.

An APU's Vega 3 said «PCIe 3.0 × 16» in its header, in Clocks and link and
on the board's list: that link is the processor's own wiring, not a slot.
Its Resizable BAR said «activo»: the processor sees all of its memory. Home
named its temperature «Gráfica», though its sensor reads the whole chip. And
an old Intel's graphics in the GM965 chipset was said to be in the processor.
"""

import unittest

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, shared_snapshot


def _report(dump: str, sections) -> str:
    from silux.ui import full_report

    qt.app()
    return full_report.build(shared_snapshot(EQUIPOS / dump), sections=sections)


class TestWhereItIs(unittest.TestCase):

    def test_by_maker_and_generation(self):
        for dump, where in (("athlon-3000g", "cpu"), ("celeron-n4000", "cpu"),
                            ("i5-10400", "cpu"), ("celeron-560", "chipset"),
                            ("5800x3d", None), ("ryzen3-4100", None)):
            with self.subTest(dump=dump):
                gpu = shared_snapshot(EQUIPOS / dump).gpus[0]
                self.assertEqual(gpu.built_in, where)


class TestAnApu(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.graphics = _report("athlon-3000g", ["graficos"])
        cls.home = _report("athlon-3000g", ["inicio"])
        cls.board = _report("athlon-3000g", ["placa"])

    def test_no_slot_link(self):
        for text in (self.graphics, self.home, self.board):
            self.assertNotIn("PCIe 3.0 × 16", text)
        self.assertIn(f"Picasso/Raven 2 · {_('board.pci.oncpu')}", self.graphics)
        self.assertIn(_("gpu.na.apu.link"), self.graphics)
        self.assertIn(f"| AMD Radeon Vega 3 Graphics | {_('board.pci.oncpu')} |", self.board)

    def test_no_resizable_bar(self):
        self.assertNotIn(f"- {_('gpu.vram.rebar')}:", self.graphics)
        self.assertIn(_("gpu.na.apu.rebar"), self.graphics)

    def test_its_temperature_is_the_chips(self):
        self.assertIn(_("home.temp.gpu.shared"), self.home)


class TestChipsetGraphics(unittest.TestCase):

    def test_both_functions_in_the_chipset(self):
        board = _report("celeron-560", ["placa"])
        rows = [line for line in board.splitlines() if "| Mobile GM965" in line]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(f"| {_('board.pci.onchipset')} |" in row for row in rows), rows)


if __name__ == "__main__":
    unittest.main()
