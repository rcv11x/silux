"""A Ryzen of two chiplets: its L3, one per CCD, on the CPU page.

sysfs gives one L3 per CCD with the CPUs that share it. With V-Cache on one
of the two (7950X3D, 9950X3D) they are different sizes and come out as two
caches of level 3; the CPU page named both rows «L3», and the second one
replaced the first: a 7950X3D said «L3: 32 MB». The Caches page already
said it right.
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.providers.sysfs_cpu import SysfsTopology
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

SYS = "/sys/devices/system/cpu/"


def _l3_tree(sizes_mb: tuple[int, int]) -> dict:
    """Two CCDs of two CPUs each, with their L3 as sysfs gives it."""
    files = {}
    for cpu in range(4):
        ccd = cpu // 2
        base = f"{SYS}cpu{cpu}/cache/index3/"
        size = sizes_mb[ccd]
        files.update({base + "level": "3\n", base + "type": "Unified\n",
                      base + "size": f"{size * 1024}K\n",
                      base + "ways_of_associativity": "16\n",
                      base + "coherency_line_size": "64\n",
                      base + "number_of_sets": f"{size * 1024 * 1024 // (64 * 16)}\n",
                      base + "shared_cpu_list": f"{ccd * 2}-{ccd * 2 + 1}\n"})
    return files


def _caches(sizes_mb):
    with arbol(_l3_tree(sizes_mb)):
        return tuple(SysfsTopology._caches_for([0, 1, 2, 3]))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheCpuPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.base = foto(EQUIPOS / "5800x3d")[0]

    def _l3_row(self, caches, brand):
        from silux.ui.pages.cpu import TypeSection

        tipo = dataclasses.replace(self.base.cpu.types[0], caches=caches, brand=brand)
        photo = dataclasses.replace(self.base, cpu=dataclasses.replace(self.base.cpu, types=(tipo,)))
        with pantalla.Ventana(photo) as window:
            window.select_section("CPU")
            self.app.processEvents()
            grid = window.cpu_page.findChildren(TypeSection)[0].caches
            row = grid._values[_("cache.label.unified").format(n=3)]
            return row.full_text(), row.toolTip(), [n for n in grid._values]

    def test_with_v_cache_on_one_ccd_both_are_there(self):
        caches = _caches((96, 32))
        self.assertEqual(sorted(c.size_bytes >> 20 for c in caches), [32, 96])
        text, tip, rows = self._l3_row(caches, "AMD Ryzen 9 7950X3D 16-Core Processor")
        self.assertEqual(rows.count(_("cache.label.unified").format(n=3)), 1)
        self.assertIn("96 MB + 32 MB", text)
        self.assertIn(_("cache.l3.part").format(tam="96 MB", donde="0, 1"), tip)
        self.assertIn(_("cache.l3.part").format(tam="32 MB", donde="2, 3"), tip)

    def test_two_equal_ccds_are_two_times_one(self):
        caches = _caches((32, 32))
        self.assertEqual(len(caches), 1)
        text, _tip, _rows = self._l3_row(caches, "AMD Ryzen 9 5950X 16-Core Processor")
        self.assertIn("2 × 32 MB", text)


if __name__ == "__main__":
    unittest.main()
