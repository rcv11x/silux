"""The Disk tab of Performance, mounted for real, in each of its designs.

The results shown are whole runs recorded on real disks (`test_disktest`),
and the machine they are shown on is the dump of the one they were measured
on: its mounts, its disks and its links."""

import contextlib
import dataclasses
import json
import os
import pathlib
import unittest
from unittest import mock

from silux import disktest, sysroot
from silux.i18n import _
from tests.qt import app
from tests.test_disktest import recorded
from tests.test_equipos import EQUIPOS, _herramienta, shared_snapshot

DESIGNS = ("now", "a", "b")
HOME = pathlib.Path("/home/someone")
OURS = str(HOME / ".cache" / "silux")


def visible_texts(widget) -> str:
    from PySide6.QtWidgets import QAbstractButton, QLabel

    # What is added to a page already shown is shown on the next turn of
    # the event loop.
    for _turn in range(3):
        app().processEvents()
    found = [w.text() for w in widget.findChildren(QLabel) if w.isVisibleTo(widget)]
    found += [w.text() for w in widget.findChildren(QAbstractButton) if w.isVisibleTo(widget)]
    # Thousands are set apart with a narrow space; here, a plain one.
    return "\n".join(text for text in found if text).replace("\u202f", " ")


class Running:
    """A run as a tab that arrives half way finds it."""

    def __init__(self, run, plan, laps):
        self._run, self._plan, self._laps = run, plan, laps

    def __enter__(self):
        self._run.plan, self._run.model, self._run.laps = self._plan, "A disk", self._laps
        self._run.last = {"phase": "lap", "test": "RND4K Q32T1", "direction": "write",
                          "lap": 3, "laps": 5, "done": 0.5}
        self._patch = mock.patch.object(type(self._run), "running", True)
        self._patch.start()
        return self._run

    def __exit__(self, *_exc):
        self._patch.stop()


class TabCase(unittest.TestCase):
    """Each test, on the dump of the machine the recorded runs came from."""

    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = app()
        theme.apply(cls.app, "dark", "normal")
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def setUp(self):
        self.clear()
        self.addCleanup(self.clear)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(_herramienta().mounted(EQUIPOS / "5800x3d"))
        sysroot.forget()
        self.addCleanup(sysroot.forget)
        # The dump's folders aren't this machine's: every one can be
        # written to, and the home is one of the dump's.
        stack.enter_context(mock.patch.object(os, "access", lambda *_a, **_k: True))
        stack.enter_context(mock.patch.object(os.path, "realpath", lambda p, **_k: os.fspath(p)))
        stack.enter_context(mock.patch.object(pathlib.Path, "home", classmethod(lambda _c: HOME)))

    def clear(self) -> None:
        for file in disktest.history_path().parent.glob("disk-tests.json*"):
            file.unlink()

    def tab(self, design: str, prefs=None, run=None):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.disktest import DiskTestTab

        tab = DiskTestTab(theme.palette_for(self.app, "dark"),
                          prefs or Preferences().normalized(), run=run, design=design)
        self.addCleanup(tab.deleteLater)
        tab.resize(900, 900)
        tab.show()
        tab.apply(self.snapshot)
        return tab

    def pick(self, tab, part: str) -> None:
        index = next(i for i in range(tab.place_box.count()) if part in tab.place_box.itemText(i))
        tab.place_box.setCurrentIndex(index)
        tab._on_place(index)


class TestBeforeAnyTest(TabCase):
    def test_every_disk_that_can_be_written_to_is_offered_with_what_it_is(self):
        for design in DESIGNS:
            tab = self.tab(design)
            offered = [tab.place_box.itemText(i) for i in range(tab.place_box.count())]
            self.assertEqual(offered[-1], _("disktest.option.choose"))
            self.assertTrue(offered[0].startswith("~/.cache/silux · WD_BLACK SN850X"), offered)
            self.assertIn("btrfs", offered[0])
            self.assertTrue(any("/media/unidad2 · Samsung SSD 970 EVO Plus" in row and "ext4" in row
                                for row in offered), offered)
            # One row for each file system, not one for each btrfs subvolume.
            self.assertEqual(sum("btrfs" in row for row in offered), 1)
            self.assertEqual(tab.profile_box.count(), len(disktest.PROFILES))
            self.assertEqual(tab.profile_box.currentData(), "standard")

    def test_a_disk_with_nothing_measured_says_so_and_can_be_started(self):
        for design in DESIGNS:
            tab = self.tab(design)
            text = visible_texts(tab)
            self.assertIn(_("disktest.empty"), text)
            self.assertFalse(tab.history_card.isVisibleTo(tab))
            self.assertFalse(tab.rows.isVisibleTo(tab))
            self.assertTrue(tab.run_button.isEnabled())
            # What it will write, where and for how long, before starting.
            self.assertIn("1 GiB", tab.about.text())
            self.assertIn("~/.cache/silux", tab.about.text())
            self.assertIn("2 min", tab.about.text())
            plan = tab.plan()
            self.assertEqual((plan.folder, plan.disks, plan.filesystem, plan.write, plan.laps),
                             (OURS, ("nvme0n1",), "btrfs", True, 5))

    def test_the_options_change_the_plan_and_what_is_said_of_it(self):
        tab = self.tab("a")
        tab.write_box.setChecked(False)
        tab.size_box.setCurrentIndex(0)
        tab.laps_box.setCurrentIndex(2)
        tab._describe()
        plan = tab.plan()
        self.assertEqual((plan.write, plan.bytes_, plan.laps), (False, 64 * disktest.MIB, 3))
        self.assertEqual(tab.about.text(), _("disktest.about.read").format(
            size="64 MiB", folder="~/.cache/silux", writing="", total="1 min 40 s"))

    def test_a_folder_that_cant_be_measured_says_why_and_offers_another(self):
        for design in DESIGNS:
            tab = self.tab(design)
            with mock.patch.object(disktest, "where", return_value=disktest.Place(
                    "/tmp", "tmpfs", "tmpfs", refusal="in_memory")):
                tab.choose("/tmp/somewhere")
            text = visible_texts(tab)
            self.assertIn(_("disktest.note.in_memory"), text)
            self.assertIn(_("disktest.action.folder"), text)
            self.assertFalse(tab.run_button.isEnabled())
            self.assertFalse(tab.result_card.isVisibleTo(tab))
            self.assertFalse(tab.about.isVisibleTo(tab))
            self.assertNotIn(_("disktest.empty"), text)

    def test_a_hard_disk_is_said_to_be_one_before_starting(self):
        tab = self.tab("a")
        self.pick(tab, "unidad3")
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.rotational"), text)
        self.assertIn(_("disktest.empty"), text)
        self.assertTrue(tab.run_button.isEnabled())
        self.pick(tab, "unidad2")
        self.assertNotIn(_("disktest.note.rotational"), visible_texts(tab))


class TestWhatAResultShows(TabCase):
    def setUp(self):
        super().setUp()
        disktest.save_history([recorded("970-evo-plus-ext4"), recorded("sn850x-btrfs")])

    def test_the_disk_chosen_shows_its_own_last_result(self):
        for design in DESIGNS:
            tab = self.tab(design)
            text = visible_texts(tab)
            for expected in ("WD_BLACK SN850X HS 1000GB", "PCIe 4.0 × 4", "6 592", "3 946*",
                             "3 172", "268", "363", "63.3", "222"):
                self.assertIn(expected, text)
            # The file was kept out of btrfs's copies, and the result says so.
            self.assertIn(_("disktest.conditions.nocow").format(filesystem="btrfs"), text)
            self.assertNotIn("3 579", text.split(_("memtest.card.history"))[0])
            self.pick(tab, "unidad2")
            text = visible_texts(tab)
            for expected in ("Samsung SSD 970 EVO Plus 2TB", "PCIe 3.0 × 4", "3 579", "3 322",
                             "1 075", "48.1", "257"):
                self.assertIn(expected, text)
            self.assertNotIn("+C", text)
            self.pick(tab, "unidad3")
            text = visible_texts(tab)
            self.assertIn(_("disktest.empty"), text)
            self.assertFalse(tab.rows.isVisibleTo(tab))
            # The others are still in the history.
            self.assertIn("Samsung SSD 970 EVO Plus 2TB", text)
            self.assertIn("6 592", text)

    def test_each_test_is_said_in_words_with_its_code(self):
        for design in ("a", "b"):
            with self.subTest(design=design):
                text = visible_texts(self.tab(design))
                for words, code in ((_("disktest.kind.sequential"), "SEQ1M Q8T1"),
                                    (_("disktest.kind.single").format(
                                        kind=_("disktest.kind.sequential")), "SEQ1M Q1T1"),
                                    (_("disktest.kind.random").format(block="4K"), "RND4K Q32T1"),
                                    (_("disktest.kind.single").format(
                                        kind=_("disktest.kind.random").format(block="4K")),
                                     "RND4K Q1T1")):
                    self.assertIn(words, text.splitlines())
                    self.assertIn(code, text.splitlines())
                self.assertIn(_(disktest_page().COLUMNS["read"]) if design == "a"
                              else _("disktest.dir.read").capitalize(), text.splitlines())

    def test_the_single_request_the_link_and_the_heat(self):
        for design in ("a", "b"):
            with self.subTest(design=design):
                text = visible_texts(self.tab(design))
                self.assertIn("64.5 µs", text)
                self.assertIn("15 464 IOPS", text)
                self.assertIn("84 %", text)
                self.assertIn("7 877 MB/s", text)
                self.assertIn("62.9 °C", text)
        text = visible_texts(self.tab("now"))
        for expected in ("15 464 IOPS", "64.5 µs", "84 %", "62.9 °C"):
            self.assertIn(expected, text)

    def test_temperatures_follow_the_unit_chosen(self):
        from silux.settings import Preferences

        fahrenheit = dataclasses.replace(Preferences().normalized(), temperature_unit="f")
        for design in DESIGNS:
            text = visible_texts(self.tab(design, prefs=fahrenheit))
            self.assertIn("145.1 °F", text)
            self.assertNotIn("°C", text)

    def test_what_a_result_is_read_with_is_inside_its_own_card(self):
        for design in DESIGNS:
            tab = self.tab(design)
            inside = visible_texts(tab.result_card)
            self.assertIn(_("disktest.note.varied"), inside)
            self.assertIn("SEQ1M Q8T1 (" + _("disktest.dir.write") + ")", inside)
            self.assertEqual(tab._notices.count(), 0)
            self.pick(tab, "unidad2")
            self.assertNotIn(_("disktest.note.varied"), visible_texts(tab))

    def test_the_details_are_folded_until_asked_for(self):
        for design in DESIGNS:
            tab = self.tab(design)
            self.assertFalse(tab.detail.isVisibleTo(tab))
            self.assertNotIn(_("disktest.method"), visible_texts(tab))
            tab.detail_button.setChecked(True)
            text = visible_texts(tab)
            self.assertIn("6 584  6 586  6 608  6 616  6 592", text)
            self.assertIn(_("disktest.detail.note"), text)
            self.assertIn(_("disktest.method.direct"), text)
            self.assertIn(_("disktest.method.nocow"), text)
            self.assertIn(_("disktest.method.written").format(size="242 GB"), text)

    def test_the_history_lists_every_run_with_its_disk(self):
        tab = self.tab("a")
        rows = visible_texts(tab.history_card)
        for expected in ("WD_BLACK SN850X HS 1000GB", "Samsung SSD 970 EVO Plus 2TB", "6 592",
                         "3 946", "63.3", "3 579", "3 322", "48.1", "62.9 °C", "56.9 °C"):
            self.assertIn(expected, rows)

    def test_a_run_through_threads_is_named_for_what_it_is_and_says_why(self):
        disktest.save_history([recorded("sn850x-btrfs-threads")])
        for design in DESIGNS:
            tab = self.tab(design)
            text = visible_texts(tab)
            for expected in ("SEQ1M Q1T8", "RND4K Q1T32", _("disktest.engine.threads")):
                self.assertIn(expected, text)
            self.assertNotIn("RND4K Q32T1\n", text + "\n")
            self.assertIn(_("disktest.note.queue_of_threads"), visible_texts(tab.result_card))
            if design != "now":
                self.assertIn(_("disktest.kind.threads").format(
                    kind=_("disktest.kind.random").format(block="4K"), n=32), text)
            # It only read: no writing column, and nothing said of writing.
            self.assertNotIn(_(disktest_page().COLUMNS["write"]), text.splitlines())

    def test_it_fits_a_narrow_window(self):
        for design in DESIGNS:
            tab = self.tab(design)
            tab.resize(380, 800)
            for _turn in range(4):
                self.app.processEvents()
            self.assertLessEqual(tab.widget().minimumSizeHint().width(), 380)
            self.assertLessEqual(tab.widget().width(), tab.viewport().width())

    def test_it_reads_the_same_in_english(self):
        from silux import i18n

        before = i18n.current()
        self.addCleanup(i18n.set_language, before)
        i18n.set_language("en")
        for design in DESIGNS:
            tab = self.tab(design)
            tab.detail_button.setChecked(True)
            text = visible_texts(tab)
            for expected in ("Include writes", "Runs", "Some tests varied between runs",
                             "6 592", "▾ Details"):
                self.assertIn(expected, text)
            for spanish in ("Vueltas", "Lectura", "escritura", "Detalles", "Dónde"):
                self.assertNotIn(spanish, text)
        self.assertIn("84 % of the link's maximum", visible_texts(self.tab("now")))


class TestRunningAndFailing(TabCase):
    def setUp(self):
        super().setUp()
        disktest.save_history([recorded("sn850x-btrfs")])

    def test_a_tab_that_arrives_half_way_shows_the_run_under_way(self):
        from silux.ui.pages.disktest import DiskTestRun

        for design in DESIGNS:
            run = DiskTestRun()
            plan = disktest.make_plan(OURS)
            laps = {("SEQ1M Q8T1", "read"): 6_500_000_000, ("SEQ1M Q8T1", "write"): 3_900_000_000}
            with Running(run, plan, laps):
                tab = self.tab(design, run=run)
                text = visible_texts(tab)
                self.assertIn(_("bench.button.cancel"), text)
                self.assertFalse(tab.run_button.isEnabled())
                self.assertIn(_("disktest.conditions.running"), text)
                self.assertIn("6 500", text)
                self.assertIn("3 900", text)
                self.assertIn(_("disktest.phase.lap").format(
                    test="RND4K Q32T1", direction=_("disktest.dir.write"), lap=3, laps=5),
                    tab.progress.label.text())
                # Nothing of the result before it: neither its figures nor
                # its notes.
                self.assertNotIn("6 592", text.split(_("memtest.card.history"))[0])
                self.assertNotIn(_("disktest.note.varied"), text)
                tab._on_progress({"phase": "lapped", "test": "RND4K Q1T1", "direction": "read",
                                  "lap": 1, "laps": 5, "done": 0.9, "bytes_per_second": 61_000_000})
                self.assertIn("61.0", visible_texts(tab))

    def test_a_run_that_ends_shows_its_result_and_joins_the_history(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        tab = self.tab("a", run=run)
        states = []
        tab.running_changed.connect(states.append)
        run.model = "Another name"
        newer = dataclasses.replace(recorded("sn850x-btrfs"), timestamp=1_900_000_000.0)
        run._on_done(newer)
        self.assertEqual(states, [False])
        self.assertEqual(len(disktest.load_history()), 2)
        self.assertEqual(disktest.load_history()[0].model, "Another name")
        self.assertEqual(tab.result.timestamp, 1_900_000_000.0)
        self.assertFalse(tab.cancel_button.isVisibleTo(tab))

    def test_a_run_that_fails_says_what_happened_and_what_to_do(self):
        from silux.ui.pages.disktest import DiskTestRun

        for design in DESIGNS:
            run = DiskTestRun()
            tab = self.tab(design, run=run)
            failed = disktest.Result(reason="no_space", figures=(
                ("needed", 35_433_480_192), ("free", 21_300_000_000)))
            run._on_done(failed)
            text = visible_texts(tab)
            self.assertIn(_("disktest.note.no_space"), text)
            self.assertIn("35.4 GB", text)
            self.assertIn("21.3 GB", text)
            self.assertIn(_("disktest.action.smaller"), text)
            # Never a code on the screen.
            self.assertNotIn("errno", text)
            # The result before it is still there, and nothing was saved.
            self.assertIn("6 592", text)
            self.assertEqual(len(disktest.load_history()), 1)
            before = tab.size_box.currentIndex()
            tab._smaller_file()
            self.assertEqual(tab.size_box.currentIndex(), before - 1)
            self.assertNotIn(_("disktest.note.no_space"), visible_texts(tab))

    def test_every_error_and_every_note_has_its_words_in_both_languages(self):
        from silux import i18n
        from silux.ui.pages import disktest as page

        before = i18n.current()
        self.addCleanup(i18n.set_language, before)
        for language in ("es", "en"):
            i18n.set_language(language)
            for key, (title, body) in page.NOTES.items():
                self.assertNotEqual(_(title), title, key)
                self.assertNotEqual(_(body), body, key)
        # Every refusal `where` can give and every warning of a result has
        # a note of its own.
        for key in ("in_memory", "network", "not_a_disk", "read_only", "fuse_driver", "fuse",
                    "zfs", "overlay", "encrypted", "loop", "several_disks", "copy_on_write",
                    "through_the_cache", "queue_of_threads", "disk_moved_less", "disk_was_busy"):
            self.assertIn(key, page.NOTES)
        self.assertLessEqual(set(page.ERRORS), set(page.NOTES))

    def test_a_cancelled_run_leaves_no_error(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        tab = self.tab("a", run=run)
        run._on_done(disktest.Result(reason="cancelled"))
        self.assertEqual(tab._notices.count(), 0)
        self.assertIn("6 592", visible_texts(tab))


def disktest_page():
    from silux.ui.pages import disktest as page

    return page


class TestRecordedForThePage(unittest.TestCase):
    def test_the_run_through_threads_only_read(self):
        result = recorded("sn850x-btrfs-threads")
        self.assertEqual((result.engine, result.written_bytes, result.warnings),
                         ("threads", disktest.GIB, ("queue_of_threads",)))
        self.assertEqual([(m.name, m.stands_for, m.direction) for m in result.measures],
                         [("SEQ1M Q1T8", "SEQ1M Q8T1", "read"), ("SEQ1M Q1T1", "", "read"),
                          ("RND4K Q1T32", "RND4K Q32T1", "read"), ("RND4K Q1T1", "", "read")])
        self.assertEqual(json.loads(json.dumps(dataclasses.asdict(result)))["engine"], "threads")


if __name__ == "__main__":
    unittest.main()
