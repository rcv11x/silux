"""A drive's health at a glance: fine, watch, or back it up now, from what
the NVMe specification or the drive itself declares, never a threshold of
ours; and «no data» or «with permissions» when there is nothing to judge.

The NVMe Critical Warning byte is set bit by bit as the specification
defines it (NVM Express Base, SMART / Health Information log, byte 0):
bit 0 spare below its threshold, bit 1 temperature, bit 2 reliability
degraded, bit 3 read-only, bit 4 volatile memory backup failed, bit 5
persistent memory region read-only.
"""

import unittest

from silux import disk_health
from silux.model import DiskHealth


def nvme(**fields) -> DiskHealth:
    base = dict(power_on_hours=9237, critical_warning=0, percentage_used=3,
                spare_percent=100, media_errors=0)
    base.update(fields)
    return DiskHealth(**base)


class TestNvme(unittest.TestCase):
    def test_nothing_to_say_is_fine(self):
        self.assertEqual(disk_health.verdict(nvme()).level, disk_health.FINE)

    def test_spare_reliability_and_read_only_mean_back_it_up_now(self):
        for bit in (0, 2, 3):
            with self.subTest(bit=bit):
                verdict = disk_health.verdict(nvme(critical_warning=1 << bit))
                self.assertEqual(verdict.level, disk_health.BACKUP)

    def test_temperature_and_the_backup_device_mean_watch(self):
        for bit in (1, 4, 5):
            with self.subTest(bit=bit):
                self.assertEqual(disk_health.verdict(nvme(critical_warning=1 << bit)).level,
                                 disk_health.WATCH)

    def test_its_life_used_up_means_back_it_up_now(self):
        self.assertEqual(disk_health.verdict(nvme(percentage_used=100)).level, disk_health.BACKUP)
        self.assertEqual(disk_health.verdict(nvme(percentage_used=120)).level, disk_health.BACKUP)

    def test_data_it_could_not_give_back_means_watch(self):
        verdict = disk_health.verdict(nvme(media_errors=2))
        self.assertEqual(verdict.level, disk_health.WATCH)
        self.assertEqual([(r.code, r.count) for r in verdict.reasons], [("media_errors", 2)])


class TestSata(unittest.TestCase):
    def sata(self, **fields):
        base = dict(power_on_hours=3148, reallocated_sectors=0, pending_sectors=0,
                    uncorrectable_sectors=0, attributes=((5, 100, 0), (199, 200, 0)))
        base.update(fields)
        return DiskHealth(**base)

    def test_sectors_replaced_mean_watch_never_back_it_up(self):
        verdict = disk_health.verdict(self.sata(reallocated_sectors=3))
        self.assertEqual(verdict.level, disk_health.WATCH)

    def test_a_cable_error_says_it_is_the_cable(self):
        verdict = disk_health.verdict(self.sata(attributes=((5, 100, 0), (199, 200, 12))))
        self.assertEqual(verdict.level, disk_health.WATCH)
        self.assertEqual([(r.code, r.count) for r in verdict.reasons], [("cable", 12)])


class TestNothingToJudge(unittest.TestCase):
    def test_without_the_log_it_is_locked_or_no_data(self):
        self.assertEqual(disk_health.verdict(DiskHealth(), locked=True).level, disk_health.LOCKED)
        self.assertEqual(disk_health.verdict(DiskHealth()).level, disk_health.NO_DATA)
        self.assertEqual(disk_health.verdict(None).level, disk_health.NO_DATA)


class TestTheWarningsAgree(unittest.TestCase):
    def test_render_s_warnings_come_from_the_verdict(self):
        from silux import render

        for health in (nvme(critical_warning=1), nvme(critical_warning=2), nvme(media_errors=1)):
            verdict = disk_health.verdict(health)
            levels = [level for level, _text in render.disk_warnings(health)]
            expected = ["crítico" if verdict.level == disk_health.BACKUP else "alto"]
            with self.subTest(health=health.critical_warning):
                self.assertEqual(levels, expected)


if __name__ == "__main__":
    unittest.main()


class TestOnScreen(unittest.TestCase):
    """Each drive's card shows its level and why, in its colour: here the
    health of three drives as the helper reads it."""

    def test_each_card_says_its_level(self):
        import dataclasses

        from silux import render
        from silux.i18n import _
        from tests import geometry, pantalla, qt
        from tests.test_equipos import EQUIPOS, shared_snapshot

        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "ryzen5-9600x")
        healths = {"nvme0n1": nvme(critical_warning=1), "nvme1n1": nvme(media_errors=2),
                   "sda": DiskHealth(power_on_hours=3148, reallocated_sectors=0,
                                     attributes=((5, 100, 0),))}
        read = dataclasses.replace(snapshot, disks=tuple(
            dataclasses.replace(d, health=healths[d.name]) for d in snapshot.disks))
        with pantalla.Ventana(read) as window:
            window.select_section("Almacenamiento")
            geometry.settle(app)
            page = window.storage_page
            palette = page._p
            for name, level, colour in (("nvme0n1", disk_health.BACKUP, palette.crit),
                                        ("nvme1n1", disk_health.WATCH, palette.warn),
                                        ("sda", disk_health.FINE, palette.ok)):
                label, why = page._health[name]
                with self.subTest(disk=name):
                    self.assertTrue(label.isVisibleTo(page))
                    self.assertEqual(label.text(), f"● {render.disk_health_level(level)}")
                    self.assertIn(colour, label.styleSheet())
                    self.assertTrue(why.text())
            self.assertEqual(page._health["sda"][1].text(), _("disk.health.fine.text"))
            self.assertIn(_("disk.health.watch.hint"), page._health["nvme1n1"][1].text())
