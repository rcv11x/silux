"""A partition in use as swap isn't «unmounted»: it shows as swap.

The kernel lists it in /proc/swaps; it is never in the mount table.
"""

import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot


class TestTheBar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-5200u")

    def test_the_numbers(self):
        sda = next(d for d in self.snapshot.disks if d.name == "sda")
        _used, _free, _reserved, swap, unmounted = render.space((sda,), self.snapshot.system.swaps)
        sda2 = next(p for p in sda.partitions if p.name == "sda2")
        self.assertEqual(swap, sda2.size_bytes)
        self.assertEqual(unmounted, 0)

    def test_zram_is_not_a_disk(self):
        swaps = [s for s in self.snapshot.system.swaps if s.zram]
        self.assertTrue(swaps)
        self.assertEqual(render.space(self.snapshot.disks, swaps)[3], 0)

    def test_on_the_pages(self):
        from silux.ui.widgets import StackedBar

        # Another disk may have space of its own outside any partition: what
        # is shown as unmounted is only that.
        swaps = self.snapshot.system.swaps
        others = tuple(d for d in self.snapshot.disks if d.name != "sda")
        sda = next(d for d in self.snapshot.disks if d.name == "sda")
        swap = next(p for p in sda.partitions if p.name == "sda2")
        unmounted = render.space(self.snapshot.disks, swaps)[4]
        self.assertLess(unmounted, render.space(others, swaps)[4] + swap.size_bytes)
        with pantalla.Ventana(self.snapshot) as window:
            for section in ("Inicio", "Almacenamiento"):
                window.select_section(section)
                segments = [seg for bar in window.stack.currentWidget().findChildren(StackedBar)
                            for seg in bar._segments]
                with self.subTest(section):
                    self.assertIn("swap", {seg.key for seg in segments})
                    self.assertLessEqual(
                        {seg.value for seg in segments if seg.key == "unmounted"},
                        {unmounted} | {render.space((d,), swaps)[4] for d in others})


if __name__ == "__main__":
    unittest.main()
