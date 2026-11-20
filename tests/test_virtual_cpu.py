"""A virtual processor is not looked up in the processor table.

A tester's KVM guest showed «Xeon (Cranford) · 90 nm» for QEMU's virtual CPU
and asked for the report so its package could go into the next version.
What a virtual CPU declares is up to the hypervisor: QEMU invents family and
model, and with `-cpu host` the chip is the host's, whose package and caches
are not the guest's. In a virtual machine the codename, the process and the
package are not shown, and the page says why. With the `qemu-kvm` dump.
"""

import unittest
from unittest import mock

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

TABLE_ROWS = ("cpu.field.codename", "cpu.field.process", "cpu.field.package")
TABLE_NOTES = ("cpu.codename", "cpu.technology", "cpu.socket")


class TestNotLookedUp(unittest.TestCase):

    def test_the_dump_is_a_virtual_machine(self):
        cpu = foto(EQUIPOS / "qemu-kvm")[0].cpu.types[0]
        self.assertTrue(cpu.in_virtual_machine)
        self.assertEqual(cpu.signature, 0x00060FB1)

    def test_nothing_comes_from_the_table(self):
        f = foto(EQUIPOS / "qemu-kvm")[0]
        cpu = f.cpu.types[0]
        self.assertEqual((cpu.codename, cpu.technology, cpu.socket), (None, None, None))
        # Nor a notice asking for the report to fill it in.
        self.assertFalse([n.path for n in f.notes if n.path in TABLE_NOTES])

    def test_the_table_is_not_even_asked(self):
        # With `-cpu host` the signature is the host's and the table would
        # match it: the decision is the virtual machine, not the signature.
        from silux.providers import cpuid_x86

        with mock.patch.object(cpuid_x86.db, "identify_x86") as identify:
            foto(EQUIPOS / "qemu-kvm")
        identify.assert_not_called()

    def test_real_hardware_still_is(self):
        cpu = foto(EQUIPOS / "5800x3d")[0].cpu.types[0]
        self.assertIn("Vermeer", cpu.codename)
        self.assertIsNotNone(cpu.socket)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestOnThePage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _section(self, equipo):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.cpu import CpuPage

        page = CpuPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.resize(1200, 900)
        page.show()
        page.apply(foto(EQUIPOS / equipo)[0])
        self.app.processEvents()
        return next(iter(page._sections.values()))

    def test_the_three_rows_hide_and_the_foot_says_why(self):
        section = self._section("qemu-kvm")
        grid = section.processor
        for row in TABLE_ROWS:
            with self.subTest(row=row):
                self.assertFalse(grid._values[_(row)].isVisibleTo(grid))
        self.assertTrue(section.virtual_foot.isVisibleTo(section))
        self.assertEqual(section.virtual_foot.text(), _("cpu.virtual.foot"))

    def test_on_real_hardware_there_is_no_foot(self):
        section = self._section("5800x3d")
        self.assertFalse(section.virtual_foot.isVisibleTo(section))
        self.assertTrue(section.processor._values[_("cpu.field.codename")]
                        .isVisibleTo(section.processor))


if __name__ == "__main__":
    unittest.main()
