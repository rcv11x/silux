"""A USB stick is not a hard disk.

Over USB the kernel marks nearly every device as rotational, so a pen drive
showed «HDD», with dashes for a temperature and a diagnosis it doesn't keep.
"""

import dataclasses
import os
import pathlib
import unittest

from silux import render, sysroot, volcado
from silux.i18n import _
from silux.providers.storage import _kind
from tests.test_equipos import EQUIPOS

USB_DEVICE = "devices/pci0000:00/0000:00:14.0/usb2/2-1/2-1:1.0/host6/target6:0:0/6:0:0:0"


def _plug(raiz: pathlib.Path, removable: bool) -> None:
    """A USB mass storage device as the kernel lays it out in sysfs."""
    sys_ = raiz / "sys"
    device = sys_ / USB_DEVICE
    block = device / "block" / "sdb"
    (block / "queue").mkdir(parents=True)
    (block / "size").write_text("241172480\n")            # 115.2 GB in 512 B sectors
    (block / "removable").write_text("1\n" if removable else "0\n")
    (block / "queue" / "rotational").write_text("1\n")
    (block / "queue" / "logical_block_size").write_text("512\n")
    (device / "model").write_text("DataTraveler 3.0\n")
    (device / "vendor").write_text("Kingston\n")
    os.symlink(os.path.relpath(device, block), block / "device")
    os.symlink(os.path.relpath(block, sys_ / "block"), sys_ / "block" / "sdb")


def _snapshot(removable: bool, permissions: bool):
    from silux.collector import Collector
    from tests.interval import second_snapshot

    with volcado.montado(EQUIPOS / "i5-10400") as raiz:
        _plug(raiz, removable)
        sysroot.forget()
        recolector = Collector()
        try:
            f = second_snapshot(recolector)
        finally:
            recolector.close()
    if permissions:
        # Given, and the stick answered no diagnosis, as it doesn't keep one.
        f = dataclasses.replace(f, notes=tuple(n for n in f.notes if n.path != "disks.health"))
    return f


def _page(f):
    from tests import pantalla, qt
    qt.app()
    gestor = pantalla.Ventana(f)
    ventana = gestor.__enter__()
    ventana.select_section("Almacenamiento")
    return gestor, ventana.stack.currentWidget()


class TestTheKind(unittest.TestCase):

    def test_over_usb_rotational_says_nothing(self):
        self.assertEqual(_kind(1, "usb", removable=True), "Flash")
        self.assertIsNone(_kind(1, "usb", removable=False))
        self.assertEqual(_kind(0, "usb", removable=False), "SSD")
        self.assertEqual(_kind(1, "sata"), "HDD")


class TestAPenDrive(unittest.TestCase):

    def test_named_as_flash_without_dashes(self):
        f = _snapshot(removable=True, permissions=True)
        stick = next(d for d in f.disks if d.name == "sdb")
        self.assertEqual((stick.kind, stick.transport, stick.removable), ("Flash", "usb", True))
        ventana, pagina = _page(f)
        try:
            ficha = pagina._grids["sdb"]
            self.assertEqual(ficha._values[_("gpu.vram.type")].full_text(), _("storage.kind.flash"))
            for clave in ("gpu.sensor.temp", "storage.field.hours", "storage.field.written",
                          "storage.field.life"):
                with self.subTest(campo=clave):
                    self.assertFalse(ficha._values[_(clave)].isVisibleTo(pagina))
            self.assertIn(_("storage.na.flash"), pagina._pies["sdb"].text())
        finally:
            ventana.__exit__(None, None, None)

    def test_without_permissions_the_padlocks_stay(self):
        ventana, pagina = _page(_snapshot(removable=True, permissions=False))
        try:
            self.assertTrue(pagina._grids["sdb"].is_locked(_("storage.field.hours")))
        finally:
            ventana.__exit__(None, None, None)

    def test_a_fixed_usb_disk_has_no_kind_and_says_why(self):
        ventana, pagina = _page(_snapshot(removable=False, permissions=True))
        try:
            ficha = pagina._grids["sdb"]
            self.assertFalse(ficha._values[_("gpu.vram.type")].isVisibleTo(pagina))
            self.assertIn(_("storage.na.kind.usb"), pagina._pies["sdb"].text())
        finally:
            ventana.__exit__(None, None, None)

    def test_the_badge_names_it(self):
        self.assertEqual(render.disk_kind("Flash"), _("storage.kind.flash"))
        self.assertEqual(render.disk_kind("SSD"), "SSD")


if __name__ == "__main__":
    unittest.main()
