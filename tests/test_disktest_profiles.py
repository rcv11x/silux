"""The Disk tab's profiles: «Standard», the four tests of CrystalDiskMark,
and «Real use», one request at a time. Whatever tells a result by its
sequential test follows the profile's."""

import dataclasses
import pathlib
import shutil
import tempfile
import unittest

from silux import disktest
from silux.disktest import GIB, MIB
from silux.i18n import _
from tests.test_disk_native import _base
from tests.test_disktest import recorded
from tests.test_disktest_page import OURS, Running, TabCase, visible_texts
from tests.test_storage_last_disk_test import open_storage, plain
from tests import pantalla

REAL = ("SEQ1M Q1T1", "RND4K Q1T1")


def as_real_use(result: disktest.Result) -> disktest.Result:
    """A recorded run's two tests that «Real use» has, as that profile
    saves them."""
    return dataclasses.replace(result, profile="real", measures=tuple(
        m for m in result.measures if m.name in REAL))


class TestTheirWords(unittest.TestCase):
    def test_each_says_what_it_does_and_names_no_other_program(self):
        from silux import i18n
        from silux.ui.pages.disktest import PROFILE_TIPS

        for language in ("es", "en"):
            i18n.set_language(language)
            self.addCleanup(i18n.set_language, "es")
            for profile, key in PROFILE_TIPS.items():
                with self.subTest(language=language, profile=profile):
                    tip = _(key)
                    self.assertNotEqual(tip, key)
                    for program in ("CrystalDiskMark", "KDiskMark", "fio"):
                        self.assertNotIn(program, tip)


class TestTheirTips(TabCase):
    def test_a_tip_opens_beside_the_list_and_covers_no_option(self):
        from PySide6.QtCore import QEvent, QRect, Qt
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtWidgets import QApplication

        from silux.ui.widgets import TipsBeside

        tab = self.tab()
        box = tab.profile_box
        box.showPopup()
        self.addCleanup(box.hidePopup)
        for _turn in range(5):
            self.app.processEvents()
        view = box.view()
        popup = view.window()
        self.assertTrue(popup.isVisible())
        shown = QRect(popup.mapToGlobal(popup.rect().topLeft()), popup.size())
        for row in range(box.count()):
            with self.subTest(row=row):
                rect = view.visualRect(box.model().index(row, 0))
                inside = rect.center()
                QApplication.sendEvent(view.viewport(), QHelpEvent(
                    QEvent.Type.ToolTip, inside, view.viewport().mapToGlobal(inside)))
                self.app.processEvents()
                label = TipsBeside.tip_label()
                self.assertIsNotNone(label)
                self.assertEqual(label.text(), box.itemData(row, Qt.ItemDataRole.ToolTipRole))
                self.assertFalse(label.frameGeometry().intersects(shown),
                                 (label.frameGeometry(), shown))
                self.assertEqual(label.y(), view.viewport().mapToGlobal(rect.topLeft()).y())


class TestTheProfiles(unittest.TestCase):
    def test_real_use_is_one_request_at_a_time(self):
        self.assertEqual([t.name for t in disktest.PROFILES["real"]], list(REAL))
        self.assertEqual(disktest.headline_test("standard"), "SEQ1M Q8T1")
        self.assertEqual(disktest.headline_test("real"), "SEQ1M Q1T1")
        self.assertEqual(disktest.headline_test("unknown"), "SEQ1M Q8T1")

    def test_a_run_with_it_measures_its_tests(self):
        _base().mkdir(parents=True, exist_ok=True)
        folder = pathlib.Path(tempfile.mkdtemp(prefix="disktest-", dir=_base()))
        self.addCleanup(shutil.rmtree, folder, True)
        plan = disktest.make_plan(folder, profile="real", bytes_=8 * MIB, laps=1,
                                  lap_seconds=0.05, pause_seconds=0.0)
        result = disktest.run(plan)
        if result.reason in ("in_memory", "no_direct", "no_space", "no_module"):
            self.skipTest(result.detail or result.reason)
        self.assertIsNone(result.reason, result.detail)
        self.assertEqual(result.profile, "real")
        self.assertEqual([(m.name, m.direction) for m in result.measures],
                         [(name, direction) for name in REAL for direction in ("read", "write")])

    def test_writing_the_file_is_told_by_its_sequential_write(self):
        mine = as_real_use(dataclasses.replace(recorded("sn850x-btrfs"), disks=("sdb",),
                                               model="Pen"))
        plan = disktest.Plan("/media/pen", disktest.PROFILES["standard"], bytes_=GIB,
                             disks=("sdb",))
        rate = mine.measure("SEQ1M Q1T1", "write").median.bytes_per_second
        self.assertEqual(disktest.fill_estimate(plan, [mine], "Pen", None), (GIB / rate, "last"))


class TestChoosingIt(TabCase):
    def test_it_changes_the_plan_and_what_is_said_before(self):
        tab = self.tab()
        names = [tab.profile_box.itemText(i) for i in range(tab.profile_box.count())]
        self.assertEqual(names, [_("disktest.profile.standard"), _("disktest.profile.real"),
                                 _("disktest.profile.custom")])
        self.assertIn("4 min 40 s", tab.about.text())
        tab.profile_box.setCurrentIndex(tab.profile_box.findData("real"))
        tab.profile_box.activated.emit(tab.profile_box.currentIndex())
        self.assertEqual([t.name for t in tab.plan().tests], list(REAL))
        self.assertEqual(tab.plan().profile, "real")
        self.assertIn("2 min 20 s", tab.about.text())

    def test_a_run_of_it_shows_its_rows_and_steps(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        plan = disktest.make_plan(OURS, profile="real")
        with Running(run, plan, {}):
            run.last = {"phase": "lap", "test": "RND4K Q1T1", "direction": "write", "lap": 2,
                        "laps": 5, "done": 0.9}
            tab = self.tab(run=run)
            self.assertEqual(sorted({name for name, _way in tab.rows._cells}), sorted(REAL))
            self.assertEqual(len(tab.rows.names), 2)
            self.assertTrue(tab.progress.label.text().endswith(
                _("disktest.step").format(what="", n=5, of=5).strip()),
                tab.progress.label.text())

    def test_its_results_have_their_own_rows_in_the_history(self):
        disktest.save_history([as_real_use(recorded("sn850x-btrfs")), recorded("sn850x-btrfs")])
        tab = self.tab()
        headings = [heading.text() for heading, _table in tab.history_tables]
        self.assertEqual(len(headings), 2)
        self.assertTrue(headings[0].endswith(_("disktest.profile.real")), headings)
        from silux.ui.pages.disktest import test_words

        _heading, table = tab.history_tables[0]
        text = visible_texts(table)
        self.assertIn(test_words(disktest.PROFILES["real"][0]).upper(), text.upper())
        self.assertIn("3 172", text)      # SEQ1M Q1T1, read
        self.assertNotIn("6 592", text)   # SEQ1M Q8T1 isn't in it


class TestInStorage(TabCase):
    def test_the_last_test_of_another_profile_is_named(self):
        disktest.save_history([as_real_use(recorded("sn850x-btrfs"))])
        with pantalla.Ventana(self.snapshot) as window:
            open_storage(window)
            text = plain(window.storage_page._tests["nvme0n1"][1].text())
        self.assertIn(_("disktest.profile.real").lower(), text)
        self.assertIn("3 172 MB/s", text)
