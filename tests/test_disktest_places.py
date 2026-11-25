"""The Disk tab's «Where» follows what is mounted, at once (rule 9): a disk
that is plugged in or unmounted is offered or goes without leaving the tab,
and the one chosen says it went. On a dump with a pen drive, unmounting and
unplugging it in the dump's copy and sampling again, as the sampler does."""

import dataclasses
from unittest import mock

from silux import disktest, sysroot
from silux.collector import Collector
from silux.i18n import _
from tests.test_disktest import recorded
from tests.test_disktest_page import Running, TabCase, visible_texts

PEN = "/media/unidad1"
PEN_MOUNT = "/dev/sdb1 /media/unidad1 exfat"


class TestWhereFollowsTheMounts(TabCase):
    DUMP = "athlon-3000g"

    def setUp(self):
        super().setUp()
        self.collector = Collector()
        self.addCleanup(self.collector.close)
        self.collector.snapshot()
        self.mounts = self.root / "proc" / "self" / "mounts"
        self.mounted = self.mounts.read_text()
        self.block = self.root / "sys" / "block" / "sdb"
        self.device = self.block.readlink()

    def sample(self):
        sysroot.forget()
        return self.collector.snapshot()

    def unmount(self) -> None:
        self.mounts.write_text("".join(line for line in self.mounted.splitlines(True)
                                       if not line.startswith(PEN_MOUNT)))

    def unplug(self) -> None:
        self.unmount()
        self.block.unlink()

    def plug_back(self) -> None:
        if not self.block.is_symlink():
            self.block.symlink_to(self.device)
        self.mounts.write_text(self.mounted)

    def offered(self, tab) -> list[str]:
        return [tab.place_box.itemData(i) for i in range(tab.place_box.count())]

    def on_the_pen(self):
        tab = self.tab()
        tab.apply(self.sample())
        self.pick(tab, PEN + " ")
        self.assertEqual(tab.plan().disks, ("sdb",))
        return tab

    def assert_as_if_opened_now(self, tab, snapshot) -> None:
        """Rule 9: the same list as a tab opened with that snapshot."""
        fresh = self.tab()
        fresh.apply(snapshot)
        self.assertEqual([tab.place_box.itemText(i) for i in range(tab.place_box.count())],
                         [fresh.place_box.itemText(i) for i in range(fresh.place_box.count())])

    def test_a_card_taken_out_while_chosen_has_gone_not_unmounted(self):
        # The reader's slot stays in /sys/block, with nothing in it.
        tab = self.on_the_pen()
        self.unmount()
        (self.block / "size").write_text("0\n")
        tab.apply(self.sample())
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.gone_disk"), text)
        self.assertNotIn(_("disktest.note.gone_mount"), text)

    def test_a_disk_unplugged_while_chosen_says_so_and_is_no_longer_chosen(self):
        tab = self.on_the_pen()
        self.unplug()
        snapshot = self.sample()
        tab.apply(snapshot)
        self.assertNotIn(PEN, self.offered(tab))
        self.assertEqual(tab.place_box.currentIndex(), 0)
        self.assertNotEqual(tab.plan().disks, ("sdb",))
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.gone_disk"), text)
        self.assertIn("DataTraveler 3.0", text)
        self.assertNotIn(_("disktest.note.gone_mount"), text)
        self.assertTrue(tab.run_button.isEnabled())
        self.assert_as_if_opened_now(tab, snapshot)

        # Plugged in again, it is offered again and the note goes; what is
        # chosen stays as it is.
        self.plug_back()
        snapshot = self.sample()
        tab.apply(snapshot)
        self.assertIn(PEN, self.offered(tab))
        self.assertEqual(tab.place_box.currentIndex(), 0)
        self.assertNotIn(_("disktest.note.gone_disk"), visible_texts(tab))
        self.assert_as_if_opened_now(tab, snapshot)

    def test_the_disk_it_falls_back_to_shows_its_own_last_result(self):
        snapshot = self.sample()
        hard_disk = next(disk for disk in snapshot.disks if disk.name == "sda")
        pen = recorded("sn850x-btrfs")
        disktest.save_history([
            dataclasses.replace(pen, disks=("sdb",), model="DataTraveler 3.0"),
            dataclasses.replace(recorded("970-evo-plus-ext4"), disks=("sda",),
                                model=hard_disk.model)])
        tab = self.on_the_pen()
        self.assertIn("6 592", visible_texts(tab))
        self.unplug()
        tab.apply(self.sample())
        self.assertEqual(tab.plan().disks, ("sda",))
        text = visible_texts(tab)
        self.assertEqual(tab.disk_name.text(), hard_disk.model)
        self.assertNotIn(_("disktest.empty"), text)
        self.assertEqual(tab.result.disks, ("sda",))
        self.assertIn("3 579", text)

    def test_one_unmounted_but_still_there_says_that(self):
        tab = self.on_the_pen()
        self.unmount()
        tab.apply(self.sample())
        self.assertNotIn(PEN, self.offered(tab))
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.gone_mount"), text)
        self.assertNotIn(_("disktest.note.gone_disk"), text)
        # Choosing another place puts the note away.
        self.pick(tab, "/boot ")
        self.assertNotIn(_("disktest.note.gone_mount"), visible_texts(tab))

    def test_a_folder_chosen_on_it_goes_too(self):
        tab = self.tab()
        tab.apply(self.sample())
        tab.choose(PEN + "/fotos")
        self.assertEqual(tab.plan().disks, ("sdb",))
        self.unplug()
        tab.apply(self.sample())
        self.assertNotIn(PEN + "/fotos", self.offered(tab))
        self.assertIn(_("disktest.note.gone_disk"), visible_texts(tab))

    def test_one_that_is_mounted_is_offered_at_once(self):
        self.unmount()
        tab = self.tab()
        tab.apply(self.sample())
        self.assertNotIn(PEN, self.offered(tab))
        self.plug_back()
        snapshot = self.sample()
        tab.apply(snapshot)
        self.assertIn(PEN, self.offered(tab))
        self.assertNotIn(_("disktest.note.gone_disk"), visible_texts(tab))
        self.assert_as_if_opened_now(tab, snapshot)

    def test_what_is_free_is_rewritten_without_making_the_list_again(self):
        """With the list open, making it again would close it."""
        tab = self.tab()
        snapshot = self.sample()
        tab.apply(snapshot)
        index = self.offered(tab).index(PEN)
        tab.place_box.setCurrentIndex(index)
        pen = next(d for d in snapshot.disks if d.name == "sdb")
        fuller = dataclasses.replace(pen, partitions=tuple(
            dataclasses.replace(p, free_bytes=1_000_000_000) for p in pen.partitions))
        changed = dataclasses.replace(snapshot, disks=tuple(
            fuller if d.name == "sdb" else d for d in snapshot.disks))
        with mock.patch.object(tab.place_box, "clear") as clear, \
                mock.patch.object(disktest, "where", wraps=disktest.where) as where:
            tab.apply(changed)
        clear.assert_not_called()
        # Where each folder is was not asked again: nothing was mounted.
        self.assertEqual([c for c in where.call_args_list
                          if c.args and str(c.args[0]).endswith("home/someone")], [])
        self.assertEqual(tab.place_box.currentIndex(), index)
        self.assertIn("1.0 GB", tab.place_box.itemText(index))

    def test_unplugged_mid_test_it_is_said_once_and_as_what_it_is(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        plan = disktest.make_plan(PEN)
        with Running(run, plan, {}):
            tab = self.tab(run=run)
            tab.apply(self.sample())
            self.pick(tab, PEN + " ")
            self.unplug()
            tab.apply(self.sample())
            # The run says it when it ends; not the list before.
            self.assertNotIn(_("disktest.note.gone_disk"), visible_texts(tab))
        # What the engine answers to a write on a disk that went.
        answer = {"reason": "io", "detail": "pwrite failed (errno 5)",
                  "figures": {"call": "pwrite", "errno": 5}}
        run._on_done(disktest._result(answer, plan, 0.0))
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.disconnected"), text)
        self.assertNotIn(_("disktest.note.io"), text)
        self.assertNotIn(_("disktest.note.gone_disk"), text)


class TestAnErrorOnADiskThatWent(TabCase):
    DUMP = "athlon-3000g"

    def test_is_a_disconnection_and_only_then(self):
        plan = disktest.make_plan(PEN)
        answer = {"reason": "io", "detail": "pread failed (errno 5)"}
        self.assertEqual(disktest._result(answer, plan, 0.0).reason, "io")
        (self.root / "sys" / "block" / "sdb").unlink()
        self.assertEqual(disktest._result(answer, plan, 0.0).reason, "disconnected")
        self.assertEqual(disktest._result({"reason": "cancelled"}, plan, 0.0).reason,
                         "cancelled")
        self.assertIsNone(disktest._result({}, plan, 0.0).reason)

    def test_a_card_taken_out_of_its_reader_has_gone_too(self):
        # The reader's slot stays in /sys/block, removable and with nothing in it.
        plan = disktest.make_plan(PEN)
        answer = {"reason": "io", "detail": "pread failed (errno 5)"}
        (self.root / "sys" / "block" / "sdb" / "size").write_text("0\n")
        self.assertEqual(disktest._result(answer, plan, 0.0).reason, "disconnected")
