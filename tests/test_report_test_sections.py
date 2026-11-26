"""The reports carry the latest memory and disk tests whole, and where the
disk test ran is covered as every other mount.

The full report, the one people send, walked the pages and left both out:
only Memory's one-line summary reached it. And the short one wrote the
disk test's mount as it was, which on a pen drive carries its owner's name
and its label.
"""

import dataclasses
import re
import unittest

from silux import disktest, i18n, memtest, privacidad, report
from silux.i18n import _
from tests.test_disktest import recorded as disk_run
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_memtest import recorded as memory_run

# Where a desktop mounts a pen drive: its owner and its label.
OWNER, LABEL = "lucia", "VIAJE 2026"
PEN_DRIVE = f"/run/media/{OWNER}/{LABEL}"
SPANISH = re.compile(r"[áéíóúñ¿¡]", re.I)


def section(text: str, title: str) -> str:
    """One `## ` section of a report, to its end."""
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import qt

        qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def setUp(self):
        for module in (memtest, disktest):
            module.clear_history()
            self.addCleanup(module.clear_history)


class TestTheFullReport(Case):
    def test_carries_both_tests_whole(self):
        from silux.ui import full_report

        memtest.save_history([memory_run()])
        disktest.save_history([disk_run("sn850x-btrfs")])
        text = full_report.build(self.snapshot)
        memory = section(text, _("report.memtest.title"))
        self.assertIn("| RAM |", memory)
        # The curve, which no page shows.
        self.assertIn(_("report.memtest.points.columns"), memory)
        disk = section(text, _("report.disktest.title"))
        self.assertIn("SEQ1M Q8T1", disk)
        # Before the diagnosis, as in the short report.
        self.assertLess(text.index(memory), text.index(f"\n## {_('report.diag.title')}"))

    def test_in_english_with_no_spanish(self):
        from silux.ui import full_report

        memtest.save_history([memory_run()])
        disktest.save_history([disk_run("cruzer-blade-fat32")])
        previous = i18n.current()
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, previous)
        text = full_report.build(shared_snapshot(EQUIPOS / "5800x3d"))
        tests = section(text, "Memory test") + section(text, "Disk test")
        self.assertEqual([line for line in tests.splitlines() if SPANISH.search(line)], [])


class TestWhereTheDiskTestRan(Case):
    def reports(self, snapshot):
        from silux.ui import full_report

        return {"short": report.build(snapshot), "full": full_report.build(snapshot)}

    def test_a_pen_drive_since_unplugged(self):
        disktest.save_history([dataclasses.replace(disk_run("cruzer-blade-fat32"),
                                                   mountpoint=PEN_DRIVE)])
        for name, text in self.reports(self.snapshot).items():
            with self.subTest(report=name):
                self.assertNotIn(OWNER, text)
                self.assertNotIn(LABEL, text)
                disk = section(text, _("report.disktest.title")
                               if name == "full" else "Prueba de disco")
                self.assertRegex(disk, r"/media/unidad\d+ \(vfat\)")

    def test_a_pen_drive_still_plugged_in_is_the_same_unit_as_in_storage(self):
        from silux.ui import full_report

        disk = next(d for d in self.snapshot.disks if d.partitions)
        plugged = dataclasses.replace(self.snapshot, disks=tuple(
            dataclasses.replace(d, partitions=(
                dataclasses.replace(d.partitions[0], mountpoint=PEN_DRIVE),
                *d.partitions[1:])) if d is disk else d
            for d in self.snapshot.disks))
        unit = privacidad.mount_substitutes(plugged)[PEN_DRIVE]
        disktest.save_history([dataclasses.replace(disk_run("cruzer-blade-fat32"),
                                                   mountpoint=PEN_DRIVE)])
        text = full_report.build(plugged)
        self.assertNotIn(OWNER, text)
        self.assertNotIn(LABEL, text)
        self.assertIn(unit, section(text, _("nav.storage")))
        self.assertIn(f"{unit} (vfat)", section(text, _("report.disktest.title")))


if __name__ == "__main__":
    unittest.main()
