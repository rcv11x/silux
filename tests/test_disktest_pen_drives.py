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

    def test_a_nearly_full_one_is_measured_with_what_fits(self):
        """214 MB free on a 256 MiB partition: with 5 % of it, at least
        32 MiB, as the margin, 64 MiB fit."""
        tab = self.tab()
        self.pick(tab, self.FAT + " ")
        self.assertEqual(tab.plan().filesystem, "vfat")
        self.assertEqual(tab.plan().margin, 32 * MIB)
        self.assertIn("214 MB", plain(tab.place_box.currentText()))
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        text = plain(visible_texts(tab))
        self.assertIn(_("disktest.note.no_space"), text)
        self.assertNotIn(_("disktest.note.too_big_for_fat"), text)
        self.assertFalse(tab.run_button.isEnabled())
        self.button(tab, _("disktest.action.fits").format(size="64 MiB")).click()
        self.assertEqual(tab.plan().bytes_, 64 * MIB)
        self.assertTrue(tab.run_button.isEnabled())

    def test_one_with_even_less_says_no_test_fits(self):
        tab = self.with_free(256 * MIB, 60_000_000)
        for size in (4 * GIB, 64 * MIB):
            tab.size_box.setCurrentIndex(tab.size_box.findData(size))
            tab._describe()
            text = plain(visible_texts(tab))
            self.assertIn(_("disktest.note.no_room"), text)
            self.assertIn("60.0 MB", text)
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


def notices(tab) -> list[str]:
    """The text of each note shown: its title, its body and its button."""
    from PySide6.QtWidgets import QAbstractButton, QLabel

    from silux.ui.widgets import Notice

    visible_texts(tab)
    return [plain(" ".join(child.text() for kind in (QLabel, QAbstractButton)
                           for child in notice.findChildren(kind)))
            for notice in tab.findChildren(Notice) if notice.isVisibleTo(tab)]


class TestASlowPenDrive(TabCase):
    """A pen drive on USB 2.0, with exFAT, and a hard disk."""

    DUMP = "athlon-3000g"

    def pen(self, tab) -> None:
        self.pick(tab, "/media/unidad1 ")
        self.assertEqual(tab.plan().disks, ("sdb",))

    def test_how_long_writing_the_file_takes_is_said_once_in_its_note(self):
        """A pen drive's note says it can take long; with a figure, in it."""
        tab = self.tab()
        self.pen(tab)
        for size, fill in ((GIB, None), (4 * GIB, "1 min 11 s")):
            with self.subTest(size=size):
                tab.size_box.setCurrentIndex(tab.size_box.findData(size))
                tab._describe()
                shown = notices(tab)
                about = [n for n in shown if n.startswith(_("disktest.note.removable"))]
                self.assertEqual(len(about), 1, shown)
                said = [n for n in shown if "min" in n]
                if fill is None:
                    self.assertEqual(said, [])
                    continue
                self.assertEqual(said, about)
                self.assertIn(fill, about[0])
                self.assertIn(_("disktest.action.smaller"), about[0])

    def test_on_a_hard_disk_it_has_a_note_of_its_own(self):
        model = next(d for d in self.snapshot.disks if d.name == "sda").model
        last = recorded("970-evo-plus-ext4")
        slow = tuple(dataclasses.replace(measure, laps=tuple(
            dataclasses.replace(lap, bytes_per_second=100_000_000) for lap in measure.laps))
            for measure in last.measures)
        disktest.save_history([dataclasses.replace(last, disks=("sda",), model=model,
                                                   measures=slow)])
        tab = self.tab()
        tab.size_box.setCurrentIndex(tab.size_box.findData(16 * GIB))
        tab._describe()
        said = [n for n in notices(tab) if "min" in n]
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0].startswith(_("disktest.note.slow_fill").format(fill="2 min 51 s")))

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
        # And the whole test, with it: 4 min 40 s of tests and 1 min 47 s.
        total = render.duration(disktest.seconds_estimate(tab.plan()) + GIB / 10_000_000)
        self.assertEqual(plain(total), "6 min 27 s")
        self.assertIn(total, tab.about.text())
        self.assertIn(render.disk_rate(10_000_000).replace(" ", " "), text)

    def test_its_slowest_figures_are_not_said_as_nothing(self):
        """A cheap pen drive writes 4K at random at tens of kB/s."""
        self.assertEqual(render.rate_figure(24_000, 1e6), "0.024")
        self.assertEqual(render.rate_figure(920_000, 1e6), "0.920")
        self.assertEqual(render.rate_figure(1_000_000, 1e6), "1.0")
        self.assertEqual(render.rate_figure(63_300_000, 1e6), "63.3")
        last = recorded("sn850x-btrfs")
        slow = tuple(dataclasses.replace(measure, laps=tuple(
            dataclasses.replace(lap, bytes_per_second=24_000) for lap in measure.laps))
            if measure.pattern == "random" and measure.direction == "write" else measure
            for measure in last.measures)
        disktest.save_history([dataclasses.replace(
            last, disks=("sdb",), model="DataTraveler 3.0", measures=slow)])
        tab = self.tab()
        self.pen(tab)
        text = visible_texts(tab)
        self.assertIn("0.024", text)
        self.assertNotIn("\n0.0\n", text)
        # Below where the scale starts, a dot at its start, never nothing;
        # the rest as they were.
        bars = {key: bar for key, (bar, _figure) in tab.rows._cells.items()}
        dot = bars["RND4K Q1T1", "write"]
        self.assertEqual(dot.filled_width(), dot.height() - 2)
        self.assertGreater(dot.filled_width(), 0)
        wide = bars["SEQ1M Q8T1", "read"]
        self.assertAlmostEqual(wide.filled_width(), wide.width() * wide.fraction)
        dot.set_rate(None)
        self.assertEqual(dot.filled_width(), 0)

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

    def test_while_fat32_reserves_the_file_the_bar_moves_and_says_so(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        plan = disktest.make_plan("/media/unidad1")
        total = 1 + 2 * len(plan.tests)
        with Running(run, plan, {}):
            run.last = {"phase": "reserve", "done": 0.5, "left_seconds": 30}
            run.reserved = True
            tab = self.tab(run=run)
            self.assertEqual(tab.progress.label.text(), _("disktest.step").format(
                what=_("disktest.step.reserve.left").format(left="30 s"), n=1, of=total))
            reserving = tab.progress.bar.value()
            self.assertEqual(reserving, round(0.25 / total * 100))
            # Writing it is the second half of the step: the bar doesn't go back.
            tab._on_progress({"phase": "fill", "done": 0.0})
            self.assertGreaterEqual(tab.progress.bar.value(), reserving)
            tab._on_progress({"phase": "fill", "done": 1.0})
            self.assertEqual(tab.progress.bar.value(), round(1 / total * 100))


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
