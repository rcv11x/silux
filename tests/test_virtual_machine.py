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


if __name__ == "__main__":
    unittest.main()
