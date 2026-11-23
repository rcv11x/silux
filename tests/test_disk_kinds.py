"""Every disk counted by kind, and a USB SSD named as one.

Over USB the kernel marks almost everything as rotating: a fixed disk
there had no kind, and the header counted two of three disks.
"""

import unittest

from silux import render
from silux.i18n import _
from silux.model import Disk
from silux.providers.storage import _kind
from tests import pantalla, qt
from tests.test_interface_language import visible_texts
from tests.test_equipos import EQUIPOS, foto, shared_snapshot


class TestTheKind(unittest.TestCase):

    def test_over_usb(self):
        self.assertEqual(_kind(1, "usb", removable=True, model="Cruzer U"), "Flash")
        self.assertEqual(_kind(1, "usb", model="SSD PLUS 240 GB"), "SSD")
        self.assertIsNone(_kind(1, "usb", model="Expansion Desk"))

    def test_the_unknown_ones_are_counted(self):
        disks = [Disk(name="sda", kind="HDD"), Disk(name="sdb", kind=None)]
        self.assertEqual(render.disk_kinds(disks),
                         ["1 × HDD", f"1 × {_('storage.kind.unknown')}"])


class TestOnThePages(unittest.TestCase):

    def test_three_disks_three_counted(self):
        qt.app()
        snapshot = shared_snapshot(EQUIPOS / "celeron-560")
        counts = render.disk_kinds(snapshot.disks)
        self.assertEqual(sum(int(c.split(" ×")[0]) for c in counts), len(snapshot.disks))
        self.assertIn("1 × SSD", counts)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Inicio")
            self.assertIn("1 × SSD", " ".join(visible_texts(window.stack.currentWidget())))
            window.select_section("Almacenamiento")
            badges = [text for text, _loud in window.stack.currentWidget().badges._chips]
            self.assertEqual(badges, counts)


if __name__ == "__main__":
    unittest.main()
