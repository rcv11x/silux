"""The link a SATA or USB disk runs over, as an NVMe's: read from the dumps,
named in `render`, shown in Storage, and what the disk test measures a
share of.

The SATA one is this office's i5-10400: its port's `sata_spd` and its SSD's
IDENTIFY (serial words at zero), added to that machine's dump. The USB ones
are what the dumps of a Celeron N4000 (5 Gb/s) and an Athlon 3000G (480
Mb/s) already carried.
"""

import pathlib
import unittest

from silux import render
from silux.model import Disk, PcieLink
from silux.providers import storage
from tests.test_equipos import EQUIPOS, shared_snapshot

IDENTIFY = (EQUIPOS / "i5-10400" / "sys/devices/pci0000:00/0000:00:17.0/ata3/link3/dev3.0"
            / "ata_device/dev3.0/id")


def disk(machine: str, name: str) -> Disk:
    return next(d for d in shared_snapshot(EQUIPOS / machine).disks if d.name == name)


class TestReadFromTheDumps(unittest.TestCase):
    def test_a_sata_disk_says_its_link_and_what_it_supports(self):
        kioxia = disk("i5-10400", "sda")
        self.assertEqual((kioxia.sata_gbps, kioxia.sata_max_gbps), (6.0, 6.0))
        self.assertIsNone(kioxia.usb_mbps)

    def test_a_disk_behind_usb_says_its_port_s_speed(self):
        self.assertEqual(disk("celeron-n4000", "sdb").usb_mbps, 5000.0)
        self.assertEqual(disk("athlon-3000g", "sdb").usb_mbps, 480.0)
        self.assertIsNone(disk("athlon-3000g", "sdb").sata_gbps)

    def test_without_the_files_there_is_nothing_made_up(self):
        """The 5800X3D's dump carries no `sata_spd` nor IDENTIFY."""
        for name in ("sda", "sdb", "sdc"):
            found = disk("5800x3d", name)
            self.assertEqual((found.sata_gbps, found.sata_max_gbps), (None, None))


class TestTheIdentifyWords(unittest.TestCase):
    """Words 76 and 77 against ATA8-ACS: bits 1 to 3 of 76 are the
    generations supported; bits 3:1 of 77, the one negotiated."""

    def words(self) -> list[int]:
        return [int(word, 16) for word in IDENTIFY.read_text().split()]

    def test_the_real_ssd_supports_the_three_and_runs_at_the_third(self):
        words = self.words()
        self.assertEqual(len(words), 256)
        self.assertEqual(words[76] & 0b1110, 0b1110)
        self.assertEqual(words[77] >> 1 & 0b111, 3)
        # Its serial is at zero in the dump.
        self.assertEqual(words[10:20], [0] * 10)

    def test_without_sata_spd_word_77_says_the_speed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            port = pathlib.Path(folder) / "ata3"
            ident = port / "link3/dev3.0/ata_device/dev3.0/id"
            ident.parent.mkdir(parents=True)
            ident.write_text(IDENTIFY.read_text())
            block = pathlib.Path(folder) / "block" / "sda"
            device = port / "host2" / "target2:0:0" / "2:0:0:0"
            device.mkdir(parents=True)
            block.mkdir(parents=True)
            (block / "device").symlink_to(device)
            self.assertEqual(storage._sata_link(block), (6.0, 6.0))


class TestNamedAndMeasured(unittest.TestCase):
    def test_each_link_by_its_name(self):
        for found, name in ((Disk(name="a", sata_gbps=6.0), "SATA 6 Gb/s"),
                            (Disk(name="a", sata_gbps=1.5), "SATA 1.5 Gb/s"),
                            (Disk(name="a", usb_mbps=480.0), "USB 480 Mb/s"),
                            (Disk(name="a", usb_mbps=5000.0), "USB 5 Gb/s"),
                            (Disk(name="a", link=PcieLink(16.0, 4, 16.0, 4)), "PCIe 4.0 × 4"),
                            (Disk(name="a"), render.DASH)):
            with self.subTest(name=name):
                self.assertEqual(render.disk_link(found), name)

    def test_the_most_each_link_carries(self):
        """Line rate less line code: 8b/10b for SATA and USB 3.0, 128b/132b
        for USB 3.1 and 3.2, 128b/130b for PCIe 3.0 on."""
        for found, most in ((Disk(name="a", sata_gbps=6.0), 600e6),
                            (Disk(name="a", sata_gbps=3.0), 300e6),
                            (Disk(name="a", usb_mbps=480.0), 60e6),
                            (Disk(name="a", usb_mbps=5000.0), 500e6),
                            (Disk(name="a", usb_mbps=10000.0), 1212.1e6),
                            (Disk(name="a", usb_mbps=20000.0), 2424.2e6),
                            (Disk(name="a", link=PcieLink(16.0, 4, 16.0, 4)), 7876.9e6),
                            (Disk(name="a", link=PcieLink(8.0, 4, 8.0, 4)), 3938.5e6)):
            with self.subTest(most=most):
                self.assertAlmostEqual(render.link_bytes_per_second(found) / 1e6, most / 1e6,
                                       places=0)
        self.assertIsNone(render.link_bytes_per_second(Disk(name="a")))

    def test_a_sata_link_slower_than_the_disk_says_so(self):
        slow = Disk(name="a", sata_gbps=3.0, sata_max_gbps=6.0)
        self.assertIn("6 Gb/s", render.disk_link_note(slow))
        self.assertIsNone(render.disk_link_note(Disk(name="a", sata_gbps=6.0, sata_max_gbps=6.0)))


class TestShownInStorage(unittest.TestCase):
    def test_the_link_row_names_a_sata_and_a_usb_disk(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage
        from tests import qt
        from tests.pantalla import textos_de

        for machine, expected in (("i5-10400", "SATA 6 Gb/s"), ("celeron-n4000", "USB 5 Gb/s")):
            with self.subTest(machine=machine):
                page = StoragePage(theme.palette_for(qt.app(), "dark"),
                                   Preferences().normalized())
                page.apply(shared_snapshot(EQUIPOS / machine))
                seen = textos_de(page)
                self.assertIn(expected, seen)
                self.assertIn(_("gpu.clock.link"), seen)


if __name__ == "__main__":
    unittest.main()
