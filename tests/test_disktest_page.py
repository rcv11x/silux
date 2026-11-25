"""The Disk tab of Performance, mounted for real.

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
    # Thousands are set apart with a narrow space, and a figure is kept with
    # its unit by a space that doesn't break; here, plain ones.
    text = "\n".join(text for text in found if text)
    return text.replace("\u202f", " ").replace("\u00a0", " ").replace("\u2060", "")


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
    """Each test, on the dump of the machine the recorded runs came from,
    or on another's."""

    DUMP = "5800x3d"

    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = app()
        theme.apply(cls.app, "dark", "normal")
        cls.snapshot = shared_snapshot(EQUIPOS / cls.DUMP)

    def setUp(self):
        self.clear()
        self.addCleanup(self.clear)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        # The dump's copy, which a test may mount and unmount things in.
        self.root = stack.enter_context(_herramienta().mounted(EQUIPOS / self.DUMP))
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

    def tab(self, prefs=None, run=None):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.disktest import DiskTestTab

        tab = DiskTestTab(theme.palette_for(self.app, "dark"),
                          prefs or Preferences().normalized(), run=run)
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
        tab = self.tab()
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
        tab = self.tab()
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
        tab = self.tab()
        tab.write_box.setChecked(False)
        tab.size_box.setCurrentIndex(0)
        tab.laps_box.setCurrentIndex(2)
        tab._describe()
        plan = tab.plan()
        self.assertEqual((plan.write, plan.bytes_, plan.laps), (False, 64 * disktest.MIB, 3))
        self.assertEqual(tab.about.text(), _("disktest.about.read").format(
            size="64 MiB", folder="~/.cache/silux", writing="", total="1 min 40 s"))

    def test_a_folder_that_cant_be_measured_says_why_and_offers_another(self):
        tab = self.tab()
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
        tab = self.tab()
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
        tab = self.tab()
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
        # Nor are the others' runs in the history.
        self.assertFalse(tab.history_card.isVisibleTo(tab))
        self.assertNotIn("Samsung SSD 970 EVO Plus 2TB", text)
        self.assertNotIn("6 592", text)

    def test_each_test_is_said_in_words_with_its_code(self):
        text = visible_texts(self.tab())
        for words, code in ((_("disktest.kind.sequential"), "SEQ1M Q8T1"),
                            (_("disktest.kind.single").format(
                                kind=_("disktest.kind.sequential")), "SEQ1M Q1T1"),
                            (_("disktest.kind.random").format(block="4K"), "RND4K Q32T1"),
                            (_("disktest.kind.single").format(
                                kind=_("disktest.kind.random").format(block="4K")),
                             "RND4K Q1T1")):
            self.assertIn(words, text.splitlines())
            self.assertIn(code, text.splitlines())
        self.assertIn(_(disktest_page().COLUMNS["read"]), text.splitlines())

    def test_each_name_on_one_line_and_every_row_as_tall(self):
        """The names took three lines, in English too, and each row was of
        its own height."""
        from PySide6.QtWidgets import QLabel

        from silux import i18n

        before = i18n.current()
        self.addCleanup(i18n.set_language, before)
        for language in ("es", "en"):
            with self.subTest(language=language):
                i18n.set_language(language)
                tab = self.tab()
                for _turn in range(3):
                    self.app.processEvents()
                heights = set()
                for name in tab.rows.names:
                    words = name.findChildren(QLabel)[0]
                    self.assertEqual(words.height(), words.fontMetrics().height(), words.text())
                    heights.add(name.height())
                self.assertEqual(len(heights), 1, heights)

    def test_the_single_request_the_link_and_the_heat(self):
        tab = self.tab()
        text = visible_texts(tab)
        self.assertIn("64.5 µs", text)
        self.assertIn("15 464 IOPS", text)
        self.assertIn(_("disktest.fact.link"), text)
        self.assertIn("84 %", text)
        self.assertIn("7 877 MB/s", text)
        self.assertIn("62.9 °C", text)

    def test_a_single_request_reads_on_one_line_and_writes_on_another(self):
        """In one line the card was crammed and «µs» parted from its figure."""
        detail = self.tab().facts["single"].detail.text()
        lines = detail.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith(_("disktest.dir.read").capitalize()), lines)
        self.assertTrue(lines[1].startswith(_("disktest.dir.write").capitalize()), lines)
        self.assertIn("64.5\u00a0µs", lines[0])
        self.assertNotIn(" µs", detail)
        # Nor a temperature from its unit, in a narrow window.
        heat = self.tab().facts["heat"].detail.text()
        self.assertIn("50.9\u00a0°C", heat)
        self.assertNotIn(" °C", heat)

    def test_the_heat_is_coloured_by_the_disk_s_own_limits(self):
        from silux import thermal
        from silux.ui import theme

        tab = self.tab()
        heat = tab.facts["heat"].value
        self.assertEqual(heat.property("level") or "", "")
        # The SN850X declares 89.85 °C as high and 93.85 °C as critical.
        for peak, level in ((90.0, thermal.HIGH), (94.0, thermal.CRITICAL), (62.85, thermal.OK)):
            with self.subTest(peak=peak):
                tab.show_result(dataclasses.replace(recorded("sn850x-btrfs"),
                                                    temperature_peak_c=peak))
                self.assertEqual(heat.property("level") or "",
                                 theme.LEVEL_PROPERTY.get(level, ""))

    def test_temperatures_follow_the_unit_chosen(self):
        from silux.settings import Preferences

        fahrenheit = dataclasses.replace(Preferences().normalized(), temperature_unit="f")
        text = visible_texts(self.tab(prefs=fahrenheit))
        self.assertIn("145.1 °F", text)
        self.assertNotIn("°C", text)

    def test_what_a_result_is_read_with_is_inside_its_own_card(self):
        tab = self.tab()
        inside = visible_texts(tab.result_card)
        self.assertIn(_("disktest.note.varied"), inside)
        self.assertIn("SEQ1M Q8T1 (" + _("disktest.dir.write") + ")", inside)
        self.assertEqual(tab._notices.count(), 0)
        self.pick(tab, "unidad2")
        self.assertNotIn(_("disktest.note.varied"), visible_texts(tab))

    def test_the_details_are_folded_until_asked_for(self):
        tab = self.tab()
        self.assertFalse(tab.detail.isVisibleTo(tab))
        self.assertNotIn(_("disktest.method"), visible_texts(tab))
        tab.detail_button.setChecked(True)
        text = visible_texts(tab)
        self.assertIn("6 584  6 586  6 608  6 616  6 592", text)
        self.assertIn(_("disktest.detail.note"), text)
        self.assertIn(_("disktest.method.direct"), text)
        self.assertIn(_("disktest.method.nocow"), text)
        self.assertIn(_("disktest.method.written").format(size="242 GB"), text)

    def test_the_history_lists_the_runs_of_the_disk_chosen_only(self):
        tab = self.tab()
        sn850x = ("WD_BLACK SN850X HS 1000GB", "6 592", "3 946", "63.3", "62.9 °C")
        evo = ("Samsung SSD 970 EVO Plus 2TB", "3 579", "3 322", "48.1", "56.9 °C")
        for pick, shown, hidden in ((None, sn850x, evo), ("unidad2", evo, sn850x)):
            if pick:
                self.pick(tab, pick)
            rows = visible_texts(tab.history_card)
            for expected in shown:
                self.assertIn(expected, rows)
            for other in hidden:
                self.assertNotIn(other, rows)

    def test_the_history_never_puts_another_engine_s_test_in_a_column(self):
        """The run through threads (SEQ1M Q1T8) sat under SEQ1M Q8T1."""
        threads = recorded("sn850x-btrfs-threads")
        disktest.save_history([threads, recorded("sn850x-btrfs")])
        tab = self.tab()
        self.assertEqual(len(tab.history_tables), 2)
        headings = [heading.text() for heading, _table in tab.history_tables]
        self.assertIn(_("disktest.engine.threads"), headings[0])
        self.assertIn(_("disktest.engine.uring"), headings[1])
        for heading in headings:
            self.assertIn(_("disktest.profile.standard"), heading)
        through, ring = (table for _heading, table in tab.history_tables)
        tips = [[through._grid.itemAtPosition(0, c).widget().toolTip() for c in range(1, 3)],
                [ring._grid.itemAtPosition(0, c).widget().toolTip() for c in range(1, 4)]]
        self.assertTrue(tips[0][0].startswith("SEQ1M Q1T8"), tips)
        self.assertTrue(all("Q8T1" not in tip for tip in tips[0]), tips)
        self.assertTrue(tips[1][0].startswith("SEQ1M Q8T1"), tips)
        # Named in words, as the table above: «Sequential, 8 threads, read».
        self.assertIn(_("disktest.kind.threads").format(
            kind=_("disktest.kind.sequential"), n=8).upper(), visible_texts(through))
        ring = visible_texts(ring)
        sequential = threads.measure("SEQ1M Q1T8", "read").median.bytes_per_second
        self.assertNotIn(disktest_page().megabytes(sequential), ring)

    def test_a_narrow_window_shows_the_history_whole(self):
        """It was cut at the right, behind a scroll bar. With its titles in
        words it fits from 520 px; narrower, down to the narrowest window,
        it leaves out the hottest temperature, and takes it back."""
        tab = self.tab()
        hottest = _("disktest.col.hottest").upper()

        def at(width: int) -> str:
            tab.resize(width, 900)
            for _turn in range(5):
                self.app.processEvents()
            for _heading, table in tab.history_tables:
                self.assertEqual(table.horizontalScrollBar().maximum(), 0, width)
            return visible_texts(tab)

        for width in (900, 520):
            self.assertIn(hottest, at(width))
            self.assertIn("62.9", at(width))
        for width in (500, 480, 400):
            text = at(width)
            self.assertNotIn(hottest, text)
            self.assertNotIn("62.9", text.split(_("memtest.card.history"))[-1])
        self.assertIn(hottest, at(900))

    def test_on_a_wide_screen_both_tabs_keep_to_the_same_width(self):
        """At 1920 px the cards went from side to side of the page."""
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memtest import MemoryTestTab
        from tests.test_memtest import recorded as memory_run

        disktest.save_history([recorded("sn850x-btrfs")])
        disk = self.tab()
        memory = MemoryTestTab(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(memory.deleteLater)
        memory.show()
        memory.show_result(memory_run())
        for tab in (disk, memory):
            tab.resize(1690, 1100)
        for _turn in range(5):
            self.app.processEvents()
        from PySide6.QtGui import QFontMetrics

        character = QFontMetrics(theme.ui_font(theme.METRICS.base_pt)).averageCharWidth()
        widths = []
        for tab, card in ((disk, disk.result_card), (memory, memory.result_card)):
            root = tab.widget()
            self.assertLess(root.content_width(), 1690 - 2 * theme.METRICS.page_margin)
            self.assertLessEqual(card.width(), root.content_width())
            # No wider than a long line of text, whatever the letter.
            self.assertLessEqual(card.width() / character, 120)
            widths.append(card.width())
        self.assertEqual(widths[0], widths[1])
        self.assertLessEqual(disk.place_box.width(), disk.widget().content_width())

    def test_start_ends_the_row_of_choices_on_the_right_as_the_main_button(self):
        tab = self.tab()
        tab.resize(1200, 900)
        for _turn in range(5):
            self.app.processEvents()
        button = tab.run_button
        self.assertEqual(button.objectName(), "Primary")
        row = button.parentWidget()
        self.assertIs(tab.profile_box.parentWidget().parentWidget(), row)
        self.assertLessEqual(row.width() - button.geometry().right(), 2)
        # Every control of the row as tall as the others, and level with
        # its caption.
        boxes = (tab.profile_box, tab.size_box, tab.laps_box, button)
        self.assertEqual(len({box.height() for box in boxes}), 1)
        middles = {box.mapTo(row, box.rect().center()).y() for box in boxes}
        middles.add(tab.write_box.mapTo(row, tab.write_box.rect().center()).y())
        for box in (tab.profile_box, tab.size_box, tab.laps_box):
            caption = box.parentWidget().layout().itemAt(0).widget()
            middles.add(caption.mapTo(row, caption.rect().center()).y())
        self.assertLessEqual(max(middles) - min(middles), 1, middles)

    def test_a_narrow_window_cuts_the_place_with_an_ellipsis(self):
        """It was cut halfway through a word: «457 GB fre»."""
        tab = self.tab()
        box = tab.place_box
        for width, whole in ((1400, True), (480, False)):
            tab.resize(width, 900)
            for _turn in range(5):
                self.app.processEvents()
            shown = box.shown_text()
            if whole:
                self.assertEqual(shown, box.currentText())
                continue
            self.assertTrue(shown.endswith("…"), shown)
            self.assertTrue(box.currentText().startswith(shown[:-1]))
            from PySide6.QtWidgets import QStyle, QStyleOptionComboBox

            option = QStyleOptionComboBox()
            box.initStyleOption(option)
            room = box.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                              QStyle.SubControl.SC_ComboBoxEditField, box)
            self.assertLessEqual(box.fontMetrics().horizontalAdvance(shown), room.width())

    def test_the_axis_says_the_same_figures_or_none(self):
        """Reading only, «10 000» met «100 000»; and each screenshot showed
        the figures it had room for."""
        from silux.ui import theme
        from silux.ui.pages.disktest import Axis

        axis = Axis(theme.palette_for(self.app, "dark"))
        self.addCleanup(axis.deleteLater)
        seen = set()
        for width in range(40, 1600, 7):
            labels = axis.labels(width)
            texts = tuple(text.replace("\u202f", " ") for _box, text in labels)
            with self.subTest(width=width):
                self.assertIn(texts, {(), ("1", "100", "10 000")})
                boxes = [box for box, _text in labels]
                for left, right in zip(boxes, boxes[1:]):
                    self.assertGreaterEqual(right.left() - left.right(), Axis.GAP)
                if boxes:
                    self.assertLessEqual(boxes[-1].right(), width)
                    self.assertGreaterEqual(boxes[0].left(), 0)
            seen.add(texts)
        self.assertEqual(seen, {(), ("1", "100", "10 000")})

    def test_a_run_through_threads_is_named_for_what_it_is_and_says_why(self):
        disktest.save_history([recorded("sn850x-btrfs-threads")])
        tab = self.tab()
        text = visible_texts(tab)
        for expected in ("SEQ1M Q1T8", "RND4K Q1T32", _("disktest.engine.threads")):
            self.assertIn(expected, text)
        self.assertNotIn("RND4K Q32T1\n", text + "\n")
        self.assertIn(_("disktest.note.queue_of_threads"), visible_texts(tab.result_card))
        self.assertIn(_("disktest.kind.threads").format(
            kind=_("disktest.kind.random").format(block="4K"), n=32), text)
        # It only read: no writing column, and nothing said of writing.
        self.assertNotIn(_(disktest_page().COLUMNS["write"]), text.splitlines())

    def test_it_fits_the_narrowest_window(self):
        from silux.ui import theme

        narrowest = theme.METRICS.min_window_w
        tab = self.tab()
        tab.resize(narrowest, 800)
        for _turn in range(4):
            self.app.processEvents()
        self.assertLessEqual(tab.widget().minimumSizeHint().width(), narrowest)
        self.assertLessEqual(tab.widget().width(), tab.viewport().width())

    def test_it_reads_the_same_in_english(self):
        from silux import i18n

        before = i18n.current()
        self.addCleanup(i18n.set_language, before)
        i18n.set_language("en")
        tab = self.tab()
        tab.detail_button.setChecked(True)
        text = visible_texts(tab)
        for expected in ("Include writes", "Runs", "Some tests varied between runs",
                         "6 592", "▾ Details"):
            self.assertIn(expected, text)
        for spanish in ("Vueltas", "Lectura", "escritura", "Detalles", "Dónde"):
            self.assertNotIn(spanish, text)
        self.assertIn("Of the link's maximum", text)
        self.assertIn(_("disktest.kind.single").format(kind="Sequential"), text)


class TestRunningAndFailing(TabCase):
    def setUp(self):
        super().setUp()
        disktest.save_history([recorded("sn850x-btrfs")])

    def test_a_tab_that_arrives_half_way_shows_the_run_under_way(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        plan = disktest.make_plan(OURS)
        laps = {("SEQ1M Q8T1", "read"): 6_500_000_000, ("SEQ1M Q8T1", "write"): 3_900_000_000}
        with Running(run, plan, laps):
            tab = self.tab(run=run)
            text = visible_texts(tab)
            self.assertIn(_("bench.button.cancel"), text)
            self.assertFalse(tab.run_button.isEnabled())
            self.assertIn(_("disktest.conditions.running"), text)
            self.assertIn("6 500", text)
            self.assertIn("3 900", text)
            words = _("disktest.kind.random").format(block="4K")
            self.assertEqual(tab.progress.label.text(), _("disktest.step").format(
                what=_("disktest.step.test").format(
                    test=words[:1].lower() + words[1:], direction=_("disktest.dir.write")),
                n=7, of=9))
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
        tab = self.tab(run=run)
        states = []
        tab.running_changed.connect(states.append)
        # The child doesn't know the model: the run that started it does.
        run.model = "WD_BLACK SN850X HS 1000GB"
        newer = dataclasses.replace(recorded("sn850x-btrfs"), model=None,
                                    timestamp=1_900_000_000.0)
        run._on_done(newer)
        self.assertEqual(states, [False])
        self.assertEqual(len(disktest.load_history()), 2)
        self.assertEqual(disktest.load_history()[0].model, run.model)
        self.assertEqual(tab.result.timestamp, 1_900_000_000.0)
        self.assertFalse(tab.cancel_button.isVisibleTo(tab))

    def test_a_run_that_fails_says_what_happened_and_what_to_do(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        tab = self.tab(run=run)
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
        tab = self.tab(run=run)
        run._on_done(disktest.Result(reason="cancelled"))
        self.assertEqual(tab._notices.count(), 0)
        self.assertIn("6 592", visible_texts(tab))


class TestWhereTheFileLay(TabCase):
    """A hard disk with ext4 on a partition, as the home's."""

    DUMP = "athlon-3000g"

    def on_the_hard_disk(self, **changes) -> str:
        model = next(d for d in self.snapshot.disks if d.name == "sda").model
        disktest.save_history([dataclasses.replace(
            recorded("970-evo-plus-ext4"), disks=("sda",), model=model, **changes)])
        tab = self.tab()
        self.assertEqual(tab.plan().disks, ("sda",))
        return visible_texts(tab)

    def test_where_it_lay_is_said_with_the_result(self):
        text = self.on_the_hard_disk(placement=(0.6123, 0.6271))
        self.assertIn(_("disktest.note.placement").format(first="61", last="63"), text)
        self.assertNotIn(_("disktest.note.placement_unknown"), text)

    def test_where_it_couldn_t_be_known_it_says_why(self):
        for changes, body in (
                ({}, "disktest.unplaced.unsaid"),
                (dict(layers=("crypt",)), "disktest.unplaced.crypt"),
                (dict(layers=("lvm",)), "disktest.unplaced.lvm"),
                (dict(layers=("raid",)), "disktest.unplaced.raid"),
                (dict(filesystem="btrfs"), "disktest.unplaced.filesystem")):
            with self.subTest(**changes):
                text = self.on_the_hard_disk(**changes)
                self.assertIn(_("disktest.note.placement_unknown"), text)
                self.assertIn(_(body).format(filesystem="btrfs"), text)
                # The rest are other disks' causes, and the platter's speed
                # is said once, above.
                for other in ("unsaid", "crypt", "lvm", "raid", "filesystem"):
                    if not body.endswith("." + other):
                        self.assertNotIn(_("disktest.unplaced." + other)
                                         .format(filesystem="btrfs"), text)
                self.assertEqual(text.count("doble"), 1)


class TestNoPlatterNoPlace(TabCase):
    def test_a_solid_state_disk_says_nothing_of_it(self):
        """Not even where its file lay, which ext4 tells on any disk."""
        for placement in (None, (0.1, 0.2)):
            with self.subTest(placement=placement):
                disktest.save_history([dataclasses.replace(recorded("sn850x-btrfs"),
                                                           placement=placement)])
                text = visible_texts(self.tab())
                self.assertIn("6 592", text)
                self.assertNotIn(_("disktest.note.placement_unknown"), text)
                self.assertNotIn(_("disktest.note.placement").split("{")[0], text)


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
