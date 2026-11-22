"""A partition in use as swap isn't «unmounted»: it shows as swap.

The kernel lists it in /proc/swaps; it is never in the mount table.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto


class TestTheBar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshot = foto(EQUIPOS / "i5-5200u")[0]

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
        with pantalla.Ventana(self.snapshot) as window:
            for section in ("Inicio", "Almacenamiento"):
                window.select_section(section)
                text = " ".join(pantalla.textos_de(window.stack.currentWidget()))
                with self.subTest(section):
                    self.assertIn(_("storage.bar.swap"), text)
                    self.assertNotIn(_("storage.bar.unmounted"), text)


if __name__ == "__main__":
    unittest.main()
