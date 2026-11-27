"""A USB device none of whose interfaces has a driver bound shows in
Devices' «Sin driver», with its name and its ID, like a PCI one.

On the i5-10400 dump every interface has its driver. The same dump with
the keyboard's interfaces unbound, as `echo … > unbind` leaves them, lists
the keyboard. A dump made before the interfaces' links were kept says
nothing of USB: without them every device would look driverless.
"""

import pathlib
import shutil
import tempfile
import unittest

from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

KEYBOARD = "sys/devices/pci0000:00/0000:00:14.0/usb1/1-1"


def unbound_keyboard() -> pathlib.Path:
    """A copy of the i5-10400 dump with the keyboard's interfaces unbound."""
    tmp = tempfile.mkdtemp(prefix="silux-usb-")
    copy = pathlib.Path(tmp) / "i5-10400"
    shutil.copytree(EQUIPOS / "i5-10400", copy, symlinks=True)
    for interface in (copy / KEYBOARD).glob("1-1:*"):
        (interface / "driver").unlink()
    return copy


class TestUsbWithoutDriver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def rows(self, snapshot):
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Dispositivos")
            geometry.settle(self.app)
            page = window.devices_page
            visible = page.nodriver_card.isVisibleTo(page)
            return visible, [[c.full_text() for c in row] for row in page.nodriver._cells]

    def test_every_interface_with_its_driver_is_not_listed(self):
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        self.assertFalse(any(u.without_driver for u in snapshot.usb_devices))
        self.assertEqual(self.rows(snapshot), (False, []))

    def test_a_device_with_none_bound_is_listed_with_its_name_and_id(self):
        copy = unbound_keyboard()
        self.addCleanup(shutil.rmtree, copy.parent)
        snapshot = foto(copy)[0]
        keyboard = next(u for u in snapshot.usb_devices if u.port == "1-1")
        self.assertTrue(keyboard.without_driver)
        visible, rows = self.rows(snapshot)
        self.assertTrue(visible)
        self.assertEqual([(row[0], row[2]) for row in rows], [("NK65", "8968:4e4b")])

    def test_without_the_links_it_says_nothing_of_usb(self):
        snapshot = shared_snapshot(EQUIPOS / "i7-4710hq")
        self.assertTrue(snapshot.usb_devices)
        self.assertEqual({u.without_driver for u in snapshot.usb_devices}, {None})


if __name__ == "__main__":
    unittest.main()
