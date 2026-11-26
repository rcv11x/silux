"""The Memory tab of Performance, mounted for real, and what the rest of the
window does with a test: Caches, Memory's small card and the way to the tab.

The run shown is the recorded one of `test_memtest`; the tab's own run is a
short one on whoever executes the suite."""

import dataclasses
import threading
import time
import unittest
from unittest import mock

from silux import memtest, render
from silux.i18n import _
from silux.memtest import KIB, MIB
from silux.ui.widgets import unbroken
from tests import pantalla
from tests.qt import app
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_memtest import recorded

DDR4_3200_TWO_CHANNELS = dict(theoretical_bytes_per_second=51_200_000_000,
                              channels=2, speed_mts=3200)


def texts(widget) -> str:
    return "\n".join(pantalla.textos_de(widget))


def visible_texts(widget) -> str:
    from PySide6.QtWidgets import QLabel

    # A notice added to a page already shown is shown on the next turn of
    # the event loop.
    for _turn in range(3):
        app().processEvents()
    return "\n".join(label.text() for label in widget.findChildren(QLabel)
                     if label.isVisibleTo(widget) and label.text())


def theme_palette(application):
    from silux.ui import theme

    return theme.palette_for(application, "dark")


class TabCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = app()
        theme.apply(cls.app, "dark", "normal")

    def setUp(self):
        memtest.clear_history()
        self.addCleanup(memtest.clear_history)

    def tab(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memtest import MemoryTestTab

        tab = MemoryTestTab(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(tab.deleteLater)
        tab.show()
        return tab


class TestWhatAResultShows(TabCase):
    def test_before_any_test_there_is_only_the_way_to_start(self):
        tab = self.tab()
        self.assertFalse(tab.result_card.isVisibleTo(tab))
        self.assertFalse(tab.history_card.isVisibleTo(tab))
        self.assertTrue(tab.run_button.isEnabled())
        # The main button, on the right, as the Disk tab's.
        self.assertEqual(tab.run_button.objectName(), "Primary")
        tab.resize(1200, 700)
        for _turn in range(3):
            self.app.processEvents()
        row = tab.run_button.parentWidget()
        self.assertLessEqual(row.width() - tab.run_button.geometry().right(), 2)

    def test_the_header_s_groups_have_air_between_them(self):
        """What it is and what to do took the same few pixels apart; the
        progress goes apart too, and its air with it when it is hidden."""
        from PySide6.QtWidgets import QLabel

        from silux.ui import theme
        from tests.test_disktest_page import vertical_gap

        tab = self.tab()
        tab.resize(900, 700)
        for _turn in range(3):
            self.app.processEvents()
        title = next(label for label in tab.findChildren(QLabel)
                     if label.text() == _("memtest.title"))
        inside = vertical_gap(tab, title, tab.intro)
        # «Start» right under the description: alone with a gap over it, it
        # looked lost.
        self.assertLessEqual(vertical_gap(tab, tab.intro, tab.run_button), inside + 4)
        header = tab.run_button.parentWidget()
        while header is not None and type(header).__name__ != "Card":
            header = header.parentWidget()
        bottom = header.height() - tab.run_button.mapTo(header, tab.run_button.rect().bottomLeft()).y()
        self.assertLessEqual(bottom, theme.METRICS.card_pad_v + 2)
        from silux.ui.widgets import Divider

        # The progress, under a line that goes with it.
        self.assertFalse(any(d.isVisibleTo(tab) for d in tab.progress.findChildren(Divider)))
        tab.progress.show()
        for _turn in range(3):
            self.app.processEvents()
        self.assertGreaterEqual(vertical_gap(tab, tab.run_button, tab.progress.label) - inside,
                                theme.METRICS.card_gap)
        line = tab.progress.findChildren(Divider)[0]
        self.assertTrue(line.isVisibleTo(tab))
        self.assertGreater(vertical_gap(tab, tab.run_button, line), 0)
        self.assertGreater(vertical_gap(tab, line, tab.progress.label), 0)

    def test_each_level_with_its_cycles_and_the_clock_it_ran_at(self):
        tab = self.tab()
        tab.show_result(recorded())
        seen = visible_texts(tab)
        for expected in ("0.90 ns", "2.72 ns", "11.3 ns", "77.4 ns",
                         _("memtest.grid.cycles").format(n="4.0"), "performance", "4.44 GHz"):
            self.assertIn(expected, seen)

    def test_a_latency_keeps_three_figures(self):
        """With one decimal, an i5-10400's 0.96 ns L1 read «1.0»."""
        tab = self.tab()
        tab.show_result(recorded("i5-10400"))
        seen = visible_texts(tab)
        for expected in ("0.96 ns", "2.82 ns", "9.09 ns", "64.2 ns"):
            self.assertIn(expected, seen)
        self.assertNotIn("1.0 ns", seen)

    def test_the_curve_is_said_to_match_the_caches_it_was_read_against(self):
        tab = self.tab()
        tab.show_result(recorded())
        self.assertIn(_("memtest.verdict.matches").format(
            sizes="L1 32 KiB, L2 512 KiB, L3 96 MiB"), visible_texts(tab))

    def test_a_cache_declared_at_another_size_is_said_with_its_figures(self):
        result = recorded()
        caches = tuple((n, 16 * MIB if n == "L3" else s) for n, s in result.caches)
        result = dataclasses.replace(
            result, caches=caches,
            levels=memtest.levels_from_curve(result.points, caches, result.ram_block))
        tab = self.tab()
        tab.show_result(result)
        self.assertIn(_("memtest.verdict.differs").format(
            level="L3", flat="64 MiB", rises="96 MiB", declared="16 MiB"), visible_texts(tab))

    def test_the_method_in_a_line(self):
        tab = self.tab()
        tab.show_result(recorded())
        for key, values in (("memtest.method.ram", {"block": "1 GiB"}),
                            ("memtest.method.pages", {"pct": "100"}),
                            ("memtest.method.cpu", {"cpu": 1}), ("memtest.method.cycles", {})):
            self.assertIn(_(key).format(**values), tab.method.text())

    def test_the_three_rates_and_every_pass_in_the_table(self):
        """Each cell with every thread, large, and the same kind with one
        under it; the fastest kind, and named when it skips the cache."""
        tab = self.tab()
        result = dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS)
        tab.show_result(result)
        tab.resize(1400, 900)
        for _turn in range(3):
            self.app.processEvents()
        one = render.counted("memtest.threads", 1).replace(" ", "\u00a0")
        for operation, every, single in (("read", "40.2", "43.9"), ("write", "25.4", "25.4"),
                                         ("copy", "38.5", "40.1")):
            with self.subTest(operation=operation):
                bar, figure, under = tab.grid.cells["RAM", operation]
                self.assertEqual(figure.text(), every)
                self.assertEqual(under.text(), f"{one}\u00a0{single}")
                self.assertTrue(bar.isVisibleTo(tab))
        _bar, figure, _under = tab.grid.cells["L1", "read"]
        self.assertFalse(figure.isVisibleTo(tab))
        tab.detail_button.setChecked(True)
        self.assertTrue(tab.chart.isVisibleTo(tab))
        table = visible_texts(tab.rates_table)
        for expected in (_("memtest.op.copynt"), "40.1 GB/s", "38.5 GB/s"):
            self.assertIn(expected, table)


class TestDesignA(TabCase):
    def test_a_result_s_notices_go_inside_its_card(self):
        tab = self.tab()
        tab.show_result(recorded("i5-10400-auto-cpufreq-curve"))
        title = _("memtest.notice.clock").format(percent=render.whole_percent(32))
        self.assertIn(title, visible_texts(tab.result_card))

    def test_each_bandwidth_column_has_its_own_colour(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS))
        tab.resize(1400, 900)
        for _turn in range(3):
            self.app.processEvents()
        colours = []
        for operation in ("read", "write", "copy"):
            bar = tab.grid.cells["RAM", operation][0]
            image = bar.grab().toImage()
            colours.append(image.pixelColor(4, image.height() // 2).name())
        self.assertEqual(len(set(colours)), 3, colours)

    def test_the_columns_colours_tell_apart_on_both_themes(self):
        """In the light theme the copy barely showed, and in the dark one
        writing and copying were two browns."""
        from PySide6.QtGui import QColor

        from silux.ui import theme
        from silux.ui.pages.memtest import GRID_COLUMNS

        def luminance(colour: QColor) -> float:
            def channel(value: float) -> float:
                return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
            return (0.2126 * channel(colour.redF()) + 0.7152 * channel(colour.greenF())
                    + 0.0722 * channel(colour.blueF()))

        for palette in (theme.LIGHT, theme.DARK):
            colours = [QColor(getattr(palette, name)) for _op, _key, name in GRID_COLUMNS]
            surface = luminance(QColor(palette.surface))
            for colour in colours:
                light, dark = sorted((luminance(colour), surface), reverse=True)
                self.assertGreaterEqual((light + 0.05) / (dark + 0.05), 4.5, colour.name())
                for warning in (palette.warn, palette.crit, palette.info):
                    self.assertNotEqual(colour.name().lower(), warning.lower())
            hues = sorted(colour.hslHue() for colour in colours)
            gaps = [b - a for a, b in zip(hues, hues[1:])] + [360 - hues[-1] + hues[0]]
            self.assertGreaterEqual(min(gaps), 60, hues)

    def test_the_bars_are_drawn_against_the_memory_s_maximum(self):
        """The read was 72 % of the maximum and its bar under half full."""
        result = recorded("i5-10400-window")
        tab = self.tab()
        tab.show_result(result)
        bar = tab.grid.cells["RAM", "read"][0]
        read = result.rate("read", 12)
        self.assertAlmostEqual(bar.fraction,
                               read.bytes_per_second / result.theoretical_bytes_per_second)
        self.assertIn(_("memtest.grid.bars").format(total="42.7 GB/s"), tab.grid.unit.text())

    def test_without_the_maximum_there_are_no_bars_and_it_says_so(self):
        tab = self.tab()
        tab.show_result(recorded())
        for operation in ("read", "write", "copy"):
            bar, figure, _under = tab.grid.cells["RAM", operation]
            self.assertFalse(bar.isVisibleTo(tab))
            self.assertTrue(figure.isVisibleTo(tab))
        self.assertIn(_("memtest.grid.nobars"), tab.grid.unit.text())

    def test_a_figure_that_skipped_the_cache_says_so_beside_it(self):
        """«sin caché» read as the one-thread figure's."""
        tab = self.tab()
        tab.show_result(recorded())
        for operation, skipped in (("read", False), ("write", True), ("copy", True)):
            with self.subTest(operation=operation):
                kind = tab.grid.kinds["RAM", operation]
                figure = tab.grid.cells["RAM", operation][1]
                self.assertEqual(kind.isVisibleTo(tab), skipped)
                if skipped:
                    self.assertEqual(kind.text(), _("memtest.grid.nt"))
                    left = kind.mapTo(tab, kind.rect().topLeft())
                    right = figure.mapTo(tab, figure.rect().topLeft())
                    self.assertEqual(left.y(), right.y())
                    self.assertLess(left.x(), right.x())

    def test_the_history_says_whose_read_it_shows(self):
        """It showed every thread's read under «Read» while the line above
        said one thread's."""
        memtest.append_history(recorded())
        tab = self.tab()
        seen = visible_texts(tab.history_card)
        self.assertIn(render.counted("memtest.col.read.threads", 16).upper(), seen)
        self.assertIn("40.2 GB/s", seen)
        self.assertNotIn("43.9 GB/s", seen)

    def test_a_narrow_window_shows_the_history_whole(self):
        """It was cut at the right, behind a scroll bar."""
        from silux.ui import theme

        memtest.append_history(recorded("i5-10400-window"))
        tab = self.tab()
        tab.resize(theme.METRICS.min_window_w, 900)
        # A title that breaks takes one more pass of the layout.
        for _turn in range(4):
            self.app.processEvents()
        self.assertEqual(tab.history.horizontalScrollBar().maximum(), 0)

    def narrowest(self, language: str):
        from silux import i18n
        from silux.ui import theme

        before = i18n.current()
        self.addCleanup(i18n.set_language, before)
        i18n.set_language(language)
        tab = self.tab()
        tab.show_result(recorded("i5-10400-window"))
        tab.resize(theme.METRICS.min_window_w, 900)
        for _turn in range(4):
            self.app.processEvents()
        return tab

    def test_it_fits_the_narrowest_window(self):
        """With «non-temporal» beside the large figures the grid outgrew it,
        and in English it asked for 483 px of 480."""
        from silux.ui import theme

        for language in ("es", "en"):
            with self.subTest(language=language):
                tab = self.narrowest(language)
                self.assertLessEqual(tab.widget().width(), tab.viewport().width())
                self.assertLessEqual(tab.widget().minimumSizeHint().width(),
                                     theme.METRICS.min_window_w)

    def test_in_the_narrowest_window_no_cache_goes_whole_under_its_figure(self):
        """Beside the figure it broke into two lines."""
        for language in ("es", "en"):
            tab = self.narrowest(language)
            for operation in ("write", "copy"):
                with self.subTest(language=language, operation=operation):
                    kind = tab.grid.kinds["RAM", operation]
                    _bar, figure, under = tab.grid.cells["RAM", operation]
                    self.assertTrue(kind.isVisibleTo(tab))
                    self.assertLessEqual(kind.fontMetrics().horizontalAdvance(kind.text()),
                                         kind.contentsRect().width())
                    # Under the figure, ending where it ends, and over the
                    # one-thread figure it also speaks for.
                    self.assertGreaterEqual(kind.mapTo(tab, kind.rect().topLeft()).y(),
                                            figure.mapTo(tab, figure.rect().bottomLeft()).y())
                    self.assertEqual(kind.mapTo(tab, kind.rect().topRight()).x(),
                                     figure.mapTo(tab, figure.rect().topRight()).x())
                    self.assertGreaterEqual(under.mapTo(tab, under.rect().topLeft()).y(),
                                            kind.mapTo(tab, kind.rect().bottomLeft()).y())

    def test_the_processor_is_named_over_the_result(self):
        tab = self.tab()
        tab.apply(shared_snapshot(EQUIPOS / "i5-10400"))
        tab.show_result(recorded("i5-10400"))
        self.assertIn("Core i5-10400", tab.cpu_name.text())
        self.assertTrue(tab.cpu_name.isVisibleTo(tab))


class TestFiguresKeepTheirUnits(TabCase):
    def test_a_figure_and_its_unit_stay_on_one_line(self):
        """«42.7 GB/» ended a line and «s.» began the next."""
        from PySide6.QtGui import QTextLayout

        def lines(text: str) -> int:
            layout = QTextLayout(text, self.app.font())
            layout.beginLayout()
            count = 0
            while (line := layout.createLine()).isValid():
                # Narrower than any figure: whatever can break does.
                line.setLineWidth(20)
                count += 1
            layout.endLayout()
            return count

        for figure in ("42.7 GB/s", "64.5 µs"):
            with self.subTest(figure=figure):
                self.assertGreater(lines(figure), 1)
                self.assertEqual(lines(unbroken(figure)), 1)


class TestShareOfTheMaximum(TabCase):
    def test_the_percentage_with_what_it_is_made_of(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS))
        self.assertEqual(tab.share.text(), _("memtest.share").format(
            rate=unbroken("43.9 GB/s"), threads=_("memtest.threads.one").format(n=1),
            channels=_("memtest.channels").format(n=2), mts=3200, total=unbroken("51.2 GB/s")))
        self.assertEqual(tab.share_value.text(), "86 %")
        self.assertTrue(tab.share_value.isVisibleTo(tab))

    def test_one_channel_is_said_in_the_singular(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(
            recorded(), theoretical_bytes_per_second=25_600_000_000, channels=1, speed_mts=3200))
        self.assertIn(_("memtest.channels.one").format(n=1), tab.share.text())

    def test_without_the_channels_it_says_why_there_is_none(self):
        tab = self.tab()
        tab.show_result(recorded())
        self.assertEqual(tab.share.text(), _("memtest.share.unknown"))
        self.assertFalse(tab.share_value.isVisibleTo(tab))

    def test_above_a_hundred_is_a_wrong_figure_and_is_said(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(
            recorded(), theoretical_bytes_per_second=25_600_000_000, channels=1, speed_mts=3200))
        self.assertIn(_("memtest.notice.over"), visible_texts(tab))
        self.assertEqual(tab.share_value.text(), "172 %")
        tab.show_result(dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS))
        self.assertNotIn(_("memtest.notice.over"), visible_texts(tab))


class TestEveryThread(TabCase):
    def test_less_with_every_thread_than_with_one_is_explained_with_its_figures(self):
        tab = self.tab()
        tab.show_result(recorded())
        tab.detail_button.setChecked(True)
        self.assertIn(_("memtest.threads.lower").format(every="40.2 GB/s", one="43.9 GB/s"),
                      visible_texts(tab))

    def test_not_when_every_thread_moves_more(self):
        result = recorded()
        rates = tuple(dataclasses.replace(r, bytes_per_second=r.bytes_per_second * 2)
                      if r.threads > 1 else r for r in result.rates)
        tab = self.tab()
        tab.show_result(dataclasses.replace(result, rates=rates))
        tab.detail_button.setChecked(True)
        self.assertFalse(tab.threads_note.isVisibleTo(tab))


class TestTheCurve(TabCase):
    def test_no_grid_line_runs_through_a_cache_name(self):
        """The size marks' lines crossed «L3 · 96 MiB» and the others."""
        import dataclasses as dc

        from PySide6.QtGui import QColor

        from silux.ui import theme
        from silux.ui.pages.memtest import CurveChart

        # A grid colour nothing else on the chart uses.
        palette = dc.replace(theme.palette_for(self.app, "dark"), line="#00ff00")
        result = recorded()
        for width in (1000, 700, 1400):
            with self.subTest(width=width):
                chart = CurveChart(palette)
                self.addCleanup(chart.deleteLater)
                chart.set_curve(result.points, result.caches)
                chart.resize(width, 220)
                image = chart.grab().toImage()
                self.assertEqual(len(chart.label_boxes), len(result.caches))
                for box in chart.label_boxes:
                    inside = box.toRect().adjusted(1, 1, -1, -1)
                    green = [(x, y) for x in range(inside.left(), inside.right() + 1)
                             for y in range(inside.top(), inside.bottom() + 1)
                             if QColor(image.pixel(x, y)).green() > 200
                             and QColor(image.pixel(x, y)).red() < 60]
                    self.assertEqual(green, [], box)


class TestTheChannelsWaitForPermissions(TabCase):
    """Rule 5: what is missing for want of permissions has its padlock and the
    way to give them, and giving them shows on the same tab."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.without = shared_snapshot(EQUIPOS / "5800x3d")

    def test_without_permissions_the_share_has_its_padlock_and_its_button(self):
        tab = self.tab()
        tab.apply(self.without)
        tab.show_result(recorded())
        self.assertEqual(tab.share.text(), _("memtest.share.locked"))
        self.assertTrue(tab.share_lock.isVisibleTo(tab))
        self.assertTrue(tab.share_button.isVisibleTo(tab))
        self.assertEqual(tab.share_button.text(), _("perm.button.read"))
        asked = []
        tab.elevation_requested.connect(lambda: asked.append(True))
        tab.share_button.click()
        tab.share_lock.clicked.emit()
        self.assertEqual(asked, [True, True])

    def locked_tab(self, width: int):
        tab = self.tab()
        tab.apply(self.without)
        tab.show_result(recorded())
        tab.resize(width, 900)
        for _turn in range(3):
            self.app.processEvents()
        return tab

    def test_the_button_looks_like_the_status_bar_one(self):
        """It read as plain text."""
        from PySide6.QtGui import QColor

        button = self.locked_tab(1000).share_button
        self.assertTrue(button.font().underline())
        self.assertGreaterEqual(button.font().weight(), 600)
        self.assertEqual(button.palette().buttonText().color().name(),
                         QColor(theme_palette(self.app).info).name())

    def test_the_padlock_sits_on_the_text_line_and_the_button_under_it(self):
        """The padlock rode above the words. In the share's card the button
        doesn't fit beside them: it goes under, where the text starts."""
        for width in (1400, 700):
            with self.subTest(width=width):
                tab = self.locked_tab(width)
                share, lock, button = tab.share, tab.share_lock, tab.share_button

                def top(widget):
                    return widget.mapTo(tab, widget.rect().topLeft())

                def middle(widget, height):
                    return top(widget).y() + height / 2

                text = middle(share, share.fontMetrics().height())
                self.assertLessEqual(abs(text - middle(lock, lock.height())), 1.5)
                self.assertGreaterEqual(top(button).y(), top(share).y() + share.height())
                self.assertLessEqual(top(button).x(), top(share).x())

    def test_as_root_there_is_nothing_to_give(self):
        from silux.model import PrivilegedState

        root = dataclasses.replace(self.without, privileged=PrivilegedState(
            supported=True, already_root=True))
        tab = self.tab()
        tab.apply(root)
        tab.show_result(recorded())
        self.assertEqual(tab.share.text(), _("memtest.share.unknown"))
        self.assertFalse(tab.share_lock.isVisibleTo(tab))
        self.assertFalse(tab.share_button.isVisibleTo(tab))

    def test_once_given_a_test_of_this_boot_gets_its_share_on_the_spot(self):
        from tests.test_al_momento import con_permisos

        just_now = dataclasses.replace(recorded(), timestamp=time.time() - 60)
        memtest.append_history(just_now)
        tab = self.tab()
        tab.apply(self.without)
        self.assertTrue(tab.share_lock.isVisibleTo(tab))
        measured = []
        tab.measured.connect(measured.append)
        tab.apply(con_permisos(self.without))
        self.assertFalse(tab.share_lock.isVisibleTo(tab))
        self.assertTrue(tab.share_value.isVisibleTo(tab))
        self.assertIn("%", tab.share_value.text())
        self.assertIsNotNone(memtest.load_history()[0].theoretical_bytes_per_second)
        self.assertEqual(len(measured), 1)

    def test_every_test_of_this_boot_gets_its_share_not_only_the_one_in_view(self):
        from tests.test_al_momento import con_permisos

        booted = time.time() - self.without.system.uptime_seconds
        earlier = dataclasses.replace(recorded(), timestamp=booted + 60)
        later = dataclasses.replace(recorded(), timestamp=booted + 420)
        before = dataclasses.replace(recorded(), timestamp=booted - 3600)
        for result in (before, earlier, later):
            memtest.append_history(result)
        tab = self.tab()
        tab.apply(self.without)
        tab.apply(con_permisos(self.without))
        filled = {r.timestamp: r.theoretical_bytes_per_second for r in memtest.load_history()}
        self.assertIsNotNone(filled[later.timestamp])
        self.assertIsNotNone(filled[earlier.timestamp])
        self.assertIsNone(filled[before.timestamp])
        from PySide6.QtWidgets import QLabel

        shares = [label.text() for label in tab.history.findChildren(QLabel)
                  if label.text().endswith(" %")]
        self.assertEqual(len(shares), 2)

    def test_a_test_from_before_the_machine_booted_is_left_as_it_was(self):
        """Its modules may not be today's."""
        from tests.test_al_momento import con_permisos

        booted = time.time() - self.without.system.uptime_seconds
        before = dataclasses.replace(recorded(), timestamp=booted - 3600)
        memtest.append_history(before)
        tab = self.tab()
        tab.apply(con_permisos(self.without))
        self.assertEqual(tab.share.text(), _("memtest.share.unknown"))
        self.assertIsNone(memtest.load_history()[0].theoretical_bytes_per_second)


class TestTitlesOverTheirFigures(TabCase):
    """Without the memory's maximum there are no bars, and each operation's
    title sat where its bar would start, far from its figure."""

    def text_edges(self, label, grid) -> tuple[int, int]:
        """Where the label's text starts and ends, in the grid."""
        from PySide6.QtCore import Qt

        width = label.fontMetrics().horizontalAdvance(label.text())
        inside = label.contentsRect()
        left = (inside.right() - width + 1 if label.alignment() & Qt.AlignmentFlag.AlignRight
                else inside.left())
        start = label.mapTo(grid, inside.topLeft()).x() + (left - inside.left())
        return start, start + width

    def test_without_bars_each_title_ends_over_its_figure(self):
        from silux.ui.pages.memtest import GRID_COLUMNS

        tab = self.tab()
        tab.show_result(recorded())
        tab.resize(1690, 1100)
        for _turn in range(3):
            self.app.processEvents()
        grid = tab.grid
        for head, (operation, _key, _colour) in zip(grid.heads, GRID_COLUMNS):
            with self.subTest(operation=operation):
                _bar, figure, _under = grid.cells["RAM", operation]
                end = figure.mapTo(grid, figure.rect().topRight()).x()
                self.assertLessEqual(abs(self.text_edges(head, grid)[1] - end), 2)

    def test_with_bars_each_title_starts_over_its_bar(self):
        from silux.ui.pages.memtest import GRID_COLUMNS

        tab = self.tab()
        tab.show_result(dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS))
        tab.resize(1690, 1100)
        for _turn in range(3):
            self.app.processEvents()
        grid = tab.grid
        for head, (operation, _key, _colour) in zip(grid.heads, GRID_COLUMNS):
            with self.subTest(operation=operation):
                bar, _figure, _under = grid.cells["RAM", operation]
                self.assertTrue(bar.isVisibleTo(grid))
                start = bar.mapTo(grid, bar.rect().topLeft()).x()
                self.assertLessEqual(abs(self.text_edges(head, grid)[0] - start), 2)


class TestWideScreens(TabCase):
    def test_the_content_takes_the_width_as_every_page(self):
        from silux.ui import theme

        tab = self.tab()
        tab.show_result(recorded())
        tab.resize(2560, 1300)
        for _turn in range(3):
            self.app.processEvents()
        root = tab.widget()
        card = tab.result_card
        left = card.mapTo(root, card.rect().topLeft()).x()
        right = root.width() - left - card.width()
        self.assertEqual((left, right), (theme.METRICS.page_margin,) * 2)

    def test_a_narrow_window_keeps_its_usual_margins(self):
        from silux.ui import theme

        tab = self.tab()
        tab.show_result(recorded())
        tab.resize(900, 700)
        for _turn in range(3):
            self.app.processEvents()
        self.assertEqual(tab.widget().column.contentsMargins().left(), theme.METRICS.page_margin)


class TestWhatWentOnWhileMeasuring(TabCase):
    def test_a_clock_that_changed_is_said_with_how_much(self):
        """A power manager switched the turbo on halfway through the curve:
        2.89 to 4.25 GHz."""
        tab = self.tab()
        tab.show_result(recorded("i5-10400-auto-cpufreq-curve"))
        title = _("memtest.notice.clock").format(percent=render.whole_percent(32))
        self.assertIn(title, visible_texts(tab))
        self.assertIn(render.hz(2_887_094_477), visible_texts(tab))

    def test_a_single_thread_pass_with_the_clock_down_is_said_too(self):
        tab = self.tab()
        tab.show_result(recorded("i5-10400-auto-cpufreq-rates"))
        self.assertIn(_("memtest.notice.clock").format(percent=render.whole_percent(32)),
                      visible_texts(tab))

    def test_the_turbo_s_own_steps_say_nothing(self):
        tab = self.tab()
        for result in (recorded("i5-10400-auto-cpufreq-curve"), recorded("i5-10400")):
            tab.show_result(result)
        clock = _("memtest.notice.clock").split("{")[0]
        self.assertNotIn(clock, visible_texts(tab))

    def test_without_the_module_it_says_the_measure_is_the_simple_one(self):
        plan = memtest.make_plan((("L1", 32 * KIB), ("L2", 256 * KIB)), (0,), cpu=0,
                                 available=4 * 1024 * MIB)
        with mock.patch.object(memtest, "native_module", return_value=None):
            result = memtest.run(plan)
        if not result.measured:
            self.skipTest("the simple measure gave nothing here")
        tab = self.tab()
        tab.show_result(result)
        tab.detail_button.setChecked(True)
        seen = visible_texts(tab)
        self.assertIn(_("memtest.notice.simple"), seen)
        self.assertIn(_("memtest.method.simple"), seen)
        self.assertFalse(tab.chart.isVisibleTo(tab))


@unittest.skipUnless(memtest.native_module(), "silux_bench is not installed")
class TestRunningIt(TabCase):
    def short_plan(self) -> memtest.Plan:
        cpus = tuple(memtest.native_module().allowed_cpus()[:1])
        return memtest.Plan(cpu=cpus[0], cpus=cpus, sizes=memtest.curve_sizes(64 * KIB),
                            ram_block=None, ram_block_limited=False, single_bytes=2 * MIB,
                            multi_bytes=None, caches=(("L1", 32 * KIB),))

    def wait(self, tab, seconds=60):
        deadline = time.monotonic() + seconds
        while (tab.running or tab.cancel_button.isVisibleTo(tab)) \
                and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def test_a_run_ends_on_the_page_and_in_the_history(self):
        tab = self.tab()
        states, results = [], []
        tab.running_changed.connect(states.append)
        tab.measured.connect(results.append)
        with mock.patch.object(tab, "plan", self.short_plan):
            tab.start()
            self.assertFalse(tab.run_button.isEnabled())
            self.assertTrue(tab.cancel_button.isVisibleTo(tab))
            self.wait(tab)
        self.assertEqual(states, [True, False])
        self.assertEqual(len(results), 1)
        self.assertTrue(tab.result_card.isVisibleTo(tab))
        self.assertTrue(tab.history_card.isVisibleTo(tab))
        self.assertEqual(memtest.load_history(), results)
        self.assertTrue(tab.run_button.isEnabled())
        self.assertFalse(tab.progress.isVisibleTo(tab))

    def test_the_last_result_stays_in_view_until_the_new_one(self):
        """And a cancelled run leaves it there."""
        memtest.append_history(recorded())
        tab = self.tab()
        with mock.patch.object(tab, "plan", self.short_plan):
            tab.start()
            self.assertTrue(tab.result_card.isVisibleTo(tab))
            self.assertIn("77.4 ns", visible_texts(tab))
            tab.cancel_button.click()
            self.wait(tab)
        self.assertTrue(tab.result_card.isVisibleTo(tab))
        self.assertIn("77.4 ns", visible_texts(tab))

    def test_the_progress_says_its_step_beside_the_bar(self):
        """«Measuring latency (1 of 3)», not «Latency · 12 %»."""
        tab = self.tab()
        caches = (("L1", 32 * KIB), ("L2", 256 * KIB), ("L3", 12 * MIB))
        tab._run.plan = memtest.make_plan(caches, tuple(range(12)), cpu=1,
                                          available=16 * 1024 * MIB)
        tab._on_progress("single", 0.55)
        self.assertFalse(tab.progress.bar.isTextVisible())
        self.assertEqual(tab.progress.label.text(), _("memtest.step").format(
            what=_("memtest.step.single"), n=2, of=3))
        self.assertEqual(tab.progress.value(), 55)
        tab._on_progress("multi", 0.8)
        self.assertEqual(tab.progress.label.text(), _("memtest.step").format(
            what=render.counted("memtest.step.multi", 12), n=3, of=3))
        self.assertNotIn("%", tab.progress.label.text())

    def test_cancelling_leaves_no_result_and_no_notice(self):
        tab = self.tab()
        with mock.patch.object(tab, "plan", self.short_plan):
            tab.start()
            tab.cancel_button.click()
            self.wait(tab)
        self.assertEqual(memtest.load_history(), [])
        self.assertFalse(tab.result_card.isVisibleTo(tab))
        self.assertNotIn(_("memtest.notice.failed"), visible_texts(tab))
        self.assertTrue(tab.run_button.isEnabled())


@unittest.skipUnless(memtest.native_module(), "silux_bench is not installed")
class TestATestOutlivesTheRebuild(unittest.TestCase):
    """F-M5: the window rebuilds its pages when the theme or the language
    changes. The test went on in its child process and was saved, but the new
    tab didn't know: no progress, «Start» enabled again, and the result only
    after reopening."""

    @classmethod
    def setUpClass(cls):
        cls.app = app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def setUp(self):
        memtest.clear_history()
        self.addCleanup(memtest.clear_history)

    def test_changing_the_theme_or_the_language_half_way(self):
        from silux import i18n
        from silux.ui import theme

        # The window changes both for the whole process.
        self.addCleanup(i18n.set_language, i18n.current())
        self.addCleanup(theme.apply, self.app, "dark", "normal")
        for change in (dict(theme="light"), dict(language="en")):
            with self.subTest(**change), pantalla.Ventana(self.snapshot) as window:
                memtest.clear_history()
                old = window.benchmarks_page.memory_tab
                # The real test, held until the new tab has been looked at:
                # however fast or loaded the machine, it outlasts the rebuild.
                release = threading.Event()
                self.addCleanup(release.set)
                real_run = memtest.run

                def held(*args, **kwargs):
                    release.wait(60)
                    return real_run(*args, **kwargs)

                with mock.patch.object(old, "plan", return_value=TestRunningIt.short_plan(self)), \
                        mock.patch.object(memtest, "run", held):
                    old.start()
                    window._on_preferences(dataclasses.replace(window.prefs, **change))
                    new = window.benchmarks_page.memory_tab
                    self.assertIsNot(new, old)
                    self.assertTrue(new.running)
                    self.assertTrue(new.cancel_button.isVisibleTo(new))
                    self.assertFalse(new.run_button.isEnabled())
                    self.assertFalse(window.benchmarks_page.cpu_tab.run_button.isEnabled())
                    release.set()
                deadline = time.monotonic() + 60
                while new.running and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.01)
                self.app.processEvents()
                self.assertEqual(len(memtest.load_history()), 1)
                self.assertIsNotNone(new.result)
                self.assertTrue(new.result_card.isVisibleTo(new))
                self.assertTrue(new.run_button.isEnabled())
                self.assertTrue(window.benchmarks_page.cpu_tab.run_button.isEnabled())


class TestOneTestAtATime(TabCase):
    def test_while_one_runs_the_other_cant_start_and_says_why(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.benchmarks import BenchmarksPage

        page = BenchmarksPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.show()
        page.cpu_tab.running_changed.emit(True)
        self.assertFalse(page.memory_tab.run_button.isEnabled())
        self.assertEqual(page.memory_tab.blocked_note.text(),
                         _("bench.tabs.busy").format(test=_("bench.tab.cpu")))
        page.cpu_tab.running_changed.emit(False)
        self.assertTrue(page.memory_tab.run_button.isEnabled())
        page.memory_tab.running_changed.emit(True)
        self.assertFalse(page.cpu_tab.run_button.isEnabled())
        self.assertFalse(page.cpu_tab.quick_button.isEnabled())
        page.memory_tab.running_changed.emit(False)
        self.assertTrue(page.cpu_tab.run_button.isEnabled())
        # And the third: while the disk test runs, neither of the others.
        page.disk_tab.running_changed.emit(True)
        self.assertFalse(page.cpu_tab.run_button.isEnabled())
        self.assertFalse(page.memory_tab.run_button.isEnabled())
        self.assertEqual(page.memory_tab.blocked_note.text(),
                         _("bench.tabs.busy").format(test=_("bench.tab.disk")))
        page.disk_tab.running_changed.emit(False)
        self.assertTrue(page.cpu_tab.run_button.isEnabled())
        self.assertTrue(page.memory_tab.run_button.isEnabled())
        page.memory_tab.running_changed.emit(True)
        self.assertEqual(page.disk_tab.blocked_note.text(),
                         _("bench.tabs.busy").format(test=_("bench.tab.memory")))
        self.assertFalse(page.disk_tab.run_button.isEnabled())
        page.memory_tab.running_changed.emit(False)

    def test_the_tabs_that_exist_and_no_other(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.benchmarks import BenchmarksPage

        page = BenchmarksPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        self.assertEqual([b.text() for b in page.buttons.values()],
                         [_("bench.tab.cpu"), _("bench.tab.memory"), _("bench.tab.disk")])
        self.assertEqual(page.tab, "cpu")
        self.assertTrue(page.select_tab("memory"))
        self.assertIs(page.stack.currentWidget(), page.memory_tab)
        self.assertTrue(page.select_tab("disk"))
        self.assertIs(page.stack.currentWidget(), page.disk_tab)
        self.assertFalse(page.select_tab("network"))


class TestTheRestOfTheWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def setUp(self):
        memtest.clear_history()
        self.addCleanup(memtest.clear_history)

    def test_a_test_reaches_memorys_small_card(self):
        """Caches gets its latencies too: `test_caches_latencia` looks there."""
        with pantalla.Ventana(self.snapshot) as window:
            self.assertIn(_("memory.lasttest.none"), texts(window.memory_page))
            window.benchmarks_page.memory_tab.measured.emit(recorded())
            memory = texts(window.memory_page)
            self.assertIn(" · ".join((
                _("memory.lasttest.ram").format(ns="77.4 ns"),
                _("memory.lasttest.read").format(rate="43.9 GB/s"))), memory)
            self.assertNotIn(_("memory.lasttest.none"), memory)

    def test_the_small_card_carries_the_percentage_too(self):
        with pantalla.Ventana(self.snapshot) as window:
            window.memory_page.set_last_test(
                dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS))
            self.assertIn(_("memory.lasttest.share").format(pct="86"),
                          texts(window.memory_page))

    def test_the_link_opens_performance_on_its_memory_tab_and_starts_nothing(self):
        with pantalla.Ventana(self.snapshot) as window:
            window.memory_page.test_link.click()
            self.assertIs(window.stack.currentWidget(), window.benchmarks_page)
            self.assertEqual(window.benchmarks_page.tab, "memory")
            self.assertEqual(window.nav.currentItem().text(), _("nav.benchmark"))
            self.assertIsNone(window.benchmarks_page.running())

    def test_a_saved_test_is_on_the_small_card_when_the_window_opens(self):
        memtest.append_history(recorded())
        with pantalla.Ventana(self.snapshot) as window:
            self.assertIn(_("memory.lasttest.open"), texts(window.memory_page))

    def test_the_tab_can_be_asked_for_from_the_command_line(self):
        from silux.ui.app import build_parser

        self.assertEqual(build_parser().parse_args(["--tab", "memory"]).tab, "memory")
        self.assertEqual(build_parser().parse_args(["--pestana", "cpu"]).tab, "cpu")


if __name__ == "__main__":
    unittest.main()
