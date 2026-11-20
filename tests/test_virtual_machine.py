"""What a virtual machine shows, page by page, with the `qemu-kvm` dump.

A tester's KVM guest: a «1 × HDD» that admitted TRIM and so was «a disk
with SMR», a graphics page full of dashes for an emulated VGA, «Gráfica 0»,
locks asking for permissions to read module details, disk health and a
core voltage that a virtual machine does not have, and explanations about
SMBus, chipsets and memory controllers that are about real boards.
"""

import unittest

from silux import render
from silux.i18n import _
from silux.model import Need
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def vm():
    return foto(EQUIPOS / "qemu-kvm")[0]


class TestTheDisk(unittest.TestCase):

    def test_a_virtual_disk_is_not_a_hdd(self):
        disco = vm().disks[0]
        self.assertEqual(disco.model, "QEMU HARDDISK")
        self.assertEqual(disco.kind, "Virtual")

    def test_nor_a_disk_with_smr(self):
        disco = vm().disks[0]
        self.assertTrue(disco.discard and disco.rotational)
        self.assertNotIn(_("disk.trim.smr"), render.trim(disco) or "")

    def test_its_health_is_not_asked_for(self):
        # QEMU makes up the SMART of its disks: there is nothing to unlock.
        self.assertNotIn("disks.health", [n.path for n in vm().notes if n.need is Need.ROOT])

    def test_a_real_hdd_still_is_one(self):
        discos = foto(EQUIPOS / "5800x3d")[0].disks
        self.assertIn("HDD", {d.kind for d in discos})



@unittest.skipIf(QApplication is None, "sin PySide6")
class TestTheStoragePage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_no_dashes_for_what_a_virtual_disk_does_not_have(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        pagina = StoragePage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.show()
        pagina.apply(vm())
        self.app.processEvents()
        grid = pagina._grids["sda"]
        for clave in ("gpu.sensor.temp", "storage.field.hours", "storage.field.written",
                      "storage.field.life"):
            with self.subTest(fila=clave):
                self.assertFalse(grid._values[_(clave)].isVisibleTo(grid))
        self.assertEqual(pagina._pies["sda"].text(), _("storage.na.virtual"))
        # Nor a card asking for permissions to read it.
        self.assertFalse(pagina.elevation_card.isVisibleTo(pagina))


class TestTheProcessor(unittest.TestCase):

    def test_no_voltage_to_unlock(self):
        # KVM answers the voltage register with a constant: with permissions
        # it would read as a made-up voltage.
        notas = {n.path: n.need for n in vm().notes}
        self.assertNotIn("cpu.voltage_v", notas)

    def test_nor_a_base_clock_or_bclk_to_explain(self):
        # The hypervisor does not expose the clock: that note says it, once.
        rutas = [n.path for n in vm().notes]
        self.assertIn("cpu.clocks.current_hz", rutas)
        self.assertNotIn("cpu.clocks.base_hz", rutas)
        self.assertNotIn("cpu.clocks.bus_hz", rutas)

    def test_real_hardware_still_asks(self):
        notas = {n.path: n.need for n in foto(EQUIPOS / "i5-10400")[0].notes}
        self.assertIs(notas.get("cpu.voltage_v"), Need.ROOT)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestTheCpuPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _section(self, f):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.cpu import CpuPage

        page = CpuPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.resize(1200, 900)
        page.show()
        page.apply(f)
        self.app.processEvents()
        return next(iter(page._sections.values()))

    def test_what_a_virtual_cpu_does_not_have_is_not_a_dash(self):
        section = self._section(vm())
        self.assertFalse(section.processor._values[_("cpu.field.voltage")]
                         .isVisibleTo(section.processor))
        self.assertFalse(section.identity._values[_("cpu.field.microcode")]
                         .isVisibleTo(section.identity))
        # Not one clock to show: the card goes, and the notice below says why.
        self.assertFalse(section.clocks_card.isVisibleTo(section))

    def test_real_hardware_keeps_them(self):
        section = self._section(foto(EQUIPOS / "i5-10400")[0])
        self.assertTrue(section.clocks_card.isVisibleTo(section))
        self.assertTrue(section.identity._values[_("cpu.field.microcode")]
                        .isVisibleTo(section.identity))


class TestTheMemory(unittest.TestCase):

    def test_nothing_to_unlock_or_to_blame_on_a_board(self):
        rutas = [n.path for n in vm().notes]
        for ruta in ("modules", "spd", "memory.traffic"):
            with self.subTest(nota=ruta):
                self.assertNotIn(ruta, rutas)

    def test_nor_a_chipset_controlling_it(self):
        from silux import db
        self.assertFalse(db.memory_controller_in_chipset(vm().cpu.types[0]))

    def test_nothing_asks_for_permissions(self):
        self.assertEqual(vm().permission_notes, ())

    def test_the_page_says_what_it_is(self):
        if QApplication is None:
            self.skipTest("sin PySide6")
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        app = qt.app()
        pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(vm())
        self.assertEqual(pagina._subtitle(vm()), _("memory.detail.virtual"))
        self.assertNotIn(_("mem.chipset"), pagina.avisos.text())


if __name__ == "__main__":
    unittest.main()
