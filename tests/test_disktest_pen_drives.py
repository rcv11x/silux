"""Pen drives and cards in the Disk tab: FAT32's largest file, how long
writing the file takes on a slow disk, and a file system that went through
the page cache. On the dumps of machines that have them mounted."""

import dataclasses
import json

from silux import disktest, render, sysroot
from silux.collector import Collector
from silux.disktest import GIB, KIB, MIB
from silux.i18n import _
from tests.test_disktest import recorded
from tests.test_disktest_page import Running, TabCase, visible_texts


def plain(text: str) -> str:
    return text.replace("\u00a0", " ").replace("\u202f", " ")


class TestFat32(TabCase):
    """A SATA disk with a small FAT32 partition, nearly full; and, with
    what is free changed in the dump's copy, a pen drive with room."""

    DUMP = "i7-12700kf"
    FAT = "/media/unidad1"

    def with_free(self, total: int, free: int):
        """The tab once the FAT32 partition has `free` bytes free of
        `total`, sampled again as the sampler does."""
        recorded_file = self.root / "grabado.json"
        data = json.loads(recorded_file.read_text())
        data["statfs"][self.FAT] = [total // KIB, free // KIB, free // KIB, KIB]
        recorded_file.write_text(json.dumps(data))
        sysroot.forget()
        collector = Collector()
        self.addCleanup(collector.close)
        tab = self.tab()
        tab.apply(collector.snapshot())
        self.pick(tab, self.FAT + " ")
        return tab

    def button(self, tab, text: str):
        return next(b for b in tab.findChildren(type(tab.run_button))
                    if b.isVisibleTo(tab) and plain(b.text()) == text)

    def test_a_nearly_full_one_says_no_test_fits(self):
        tab = self.tab()
        self.pick(tab, self.FAT + " ")
        self.assertEqual(tab.plan().filesystem, "vfat")
        self.assertIn("214 MB", plain(tab.place_box.currentText()))
        for size in (4 * GIB, GIB, 64 * MIB):
            tab.size_box.setCurrentIndex(tab.size_box.findData(size))
            tab._describe()
            text = plain(visible_texts(tab))
            self.assertIn(_("disktest.note.no_room"), text)
            self.assertIn("214 MB", text)
            self.assertNotIn(_("disktest.note.too_big_for_fat"), text)
            self.assertNotIn("4 095", text)
            self.assertFalse(tab.run_button.isEnabled())
        self.button(tab, _("disktest.action.folder"))

    def test_a_file_too_large_for_it_is_said_before_and_the_largest_offered(self):
        tab = self.with_free(32 * GIB, 20 * GIB)
        self.assertEqual(tab.plan().filesystem, "vfat")
        self.assertTrue(tab.run_button.isEnabled())
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.too_big_for_fat"), text)
        self.assertIn("4 095 MiB", text)
        self.assertFalse(tab.run_button.isEnabled())

        notice = next(n for n in tab.findChildren(type(tab._note("too_big_for_fat", "fits",
                                                                 largest="", size="")))
                      if n.isVisibleTo(tab) and "4 095" in n.findChild(
                          type(tab.run_button)).text().replace(" ", " "))
        notice.findChild(type(tab.run_button)).click()
        self.assertEqual(tab.plan().bytes_, 4095 * MIB)
        self.assertEqual(tab.size_box.currentText().replace(" ", " "), "4 095 MiB")
        self.assertNotIn(_("disktest.note.too_big_for_fat"), visible_texts(tab))
        self.assertTrue(tab.run_button.isEnabled())
        self.assertIn("4 095 MiB", tab.about.text().replace(" ", " "))
        # The sizes stay in order, and it is offered only once.
        sizes = [tab.size_box.itemData(i) for i in range(tab.size_box.count())]
        self.assertEqual(sizes, sorted(sizes))
        tab._largest_that_fits()
        self.assertEqual(tab.size_box.count(), len(sizes))

    def test_where_what_is_free_is_the_limit_the_largest_that_fits_is_offered(self):
        tab = self.with_free(32 * GIB, 3 * GIB)
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        text = plain(visible_texts(tab))
        self.assertIn(_("disktest.note.no_space"), text)
        self.assertNotIn(_("disktest.note.too_big_for_fat"), text)
        self.assertFalse(tab.run_button.isEnabled())
        self.button(tab, _("disktest.action.fits").format(size="1 GiB")).click()
        self.assertEqual(tab.plan().bytes_, GIB)
        self.assertNotIn(_("disktest.note.no_space"), visible_texts(tab))
        self.assertTrue(tab.run_button.isEnabled())

    def test_elsewhere_the_same_size_is_no_trouble(self):
        tab = self.tab()
        self.pick(tab, "/media/unidad5 ")
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        self.assertNotIn(_("disktest.note.too_big_for_fat"), visible_texts(tab))
        self.assertTrue(tab.run_button.isEnabled())

    def test_a_file_the_engine_finds_too_large_is_not_a_failing_disk(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        tab = self.tab(run=run)
        run._on_done(disktest.Result(reason="too_big", bytes_=16 * GIB,
                                     figures=(("bytes", 16 * GIB),)))
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.too_big"), text)
        self.assertIn("16 GiB", text)
        self.assertIn(_("disktest.action.smaller"), text)
        self.assertNotIn(_("disktest.note.io"), text)


class TestASlowPenDrive(TabCase):
    """A pen drive on USB 2.0, with exFAT."""

    DUMP = "athlon-3000g"

    def pen(self, tab) -> None:
        self.pick(tab, "/media/unidad1 ")
        self.assertEqual(tab.plan().disks, ("sdb",))

    def test_how_long_writing_the_file_takes_at_least_by_its_link(self):
        tab = self.tab()
        self.pen(tab)
        # 1 GiB at 60 MB/s, which USB 2.0 carries at most: not worth saying.
        self.assertNotIn(_("disktest.note.slow_fill_link").split("{")[0], visible_texts(tab))
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.slow_fill_link").format(fill="1 min 11 s"), text)
        self.assertIn("USB 480 Mb/s", text)
        self.assertIn(_("disktest.action.smaller"), text)
        tab._smaller_file()
        self.assertEqual(tab.plan().bytes_, GIB)
        self.assertNotIn(_("disktest.note.slow_fill_link").split("{")[0], visible_texts(tab))

    def test_and_by_what_it_wrote_last_time(self):
        last = recorded("sn850x-btrfs")
        slow = tuple(dataclasses.replace(measure, laps=tuple(
            dataclasses.replace(lap, bytes_per_second=10_000_000) for lap in measure.laps))
            for measure in last.measures)
        disktest.save_history([dataclasses.replace(
            last, disks=("sdb",), model="DataTraveler 3.0", measures=slow)])
        tab = self.tab()
        self.pen(tab)
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.slow_fill").format(fill="1 min 47 s"), text)
        self.assertIn(render.disk_rate(10_000_000).replace(" ", " "), text)

    def test_another_pen_drive_that_came_up_under_its_name_isnt_it(self):
        """sdb is whatever was plugged in first: its last result is only its
        own if the model is the same."""
        mine = dataclasses.replace(recorded("sn850x-btrfs"), disks=("sdb",),
                                   model="DataTraveler 3.0", written_bytes=3 * GIB)
        for model, own in (("Another pen", False), ("DataTraveler 3.0", True)):
            with self.subTest(model=model):
                disktest.save_history([dataclasses.replace(mine, model=model)])
                tab = self.tab()
                self.pen(tab)
                text = visible_texts(tab)
                self.assertEqual(_("disktest.empty") not in text, own)
                self.assertEqual("3.2 GB" in tab.about.text(), own)

    def test_while_writing_it_says_how_long_is_left(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        plan = disktest.make_plan("/media/unidad1")
        with Running(run, plan, {}):
            run.last = {"phase": "fill", "done": 0.25, "left_seconds": 90}
            tab = self.tab(run=run)
            self.assertEqual(tab.progress.label.text(), _("disktest.step").format(
                what=_("disktest.step.fill.left").format(left="1 min 30 s"), n=1,
                of=1 + 2 * len(plan.tests)))
            # Before its pace is known, it says only what it is doing.
            tab._on_progress({"phase": "fill", "done": 0.01})
            self.assertTrue(tab.progress.label.text().startswith(_("disktest.step.fill") + " ("))


class TestNtfsThroughTheCache(TabCase):
    """A hard disk with NTFS (ntfs3)."""

    DUMP = "ryzen5-5600g"

    def test_a_test_stopped_by_the_cache_says_why_and_offers_another_folder(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        tab = self.tab(run=run)
        self.pick(tab, "/media/unidad2 ")
        run._on_done(disktest.Result(reason="cache_fallback", filesystem="ntfs3",
                                     figures=(("cached_bytes", 4 * MIB),)))
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.cache_fallback"), text)
        self.assertIn(_("disktest.action.folder"), text)
        self.assertNotIn(_("disktest.note.failed"), text)
        # Nothing went to the history.
        self.assertEqual(disktest.load_history(), [])
