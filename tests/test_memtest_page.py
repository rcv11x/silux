"""The Memory tab of Performance, mounted for real, and what the rest of the
window does with a test: Caches, Memory's small card and the way to the tab.

The run shown is the recorded one of `test_memtest`; the tab's own run is a
short one on whoever executes the suite."""

import dataclasses
import time
import unittest
from unittest import mock

from silux import memtest
from silux.i18n import _
from silux.memtest import KIB, MIB
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

    def test_each_level_with_its_cycles_and_the_clock_it_ran_at(self):
        tab = self.tab()
        tab.show_result(recorded())
        seen = visible_texts(tab)
        for expected in ("0.9 ns", "2.7 ns", "11.3 ns", "77.4 ns",
                         _("memtest.tile.cycles").format(n="4.0", freq="4.44 GHz"),
                         "performance", _("memtest.conditions.at").format(freq="4.44 GHz")):
            self.assertIn(expected, seen)

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
        """The line says the three are one thread's."""
        tab = self.tab()
        tab.show_result(recorded())
        self.assertEqual(tab.rates.text(), _("memtest.rates.one").format(rates="  ·  ".join((
            f"{_('memtest.op.read')} 43.9 GB/s", f"{_('memtest.op.write')} 20.6 GB/s",
            f"{_('memtest.op.copy')} 27.7 GB/s"))))
        tab.detail_button.setChecked(True)
        self.assertTrue(tab.chart.isVisibleTo(tab))
        table = visible_texts(tab.rates_table)
        for expected in (_("memtest.op.copynt"), "40.1 GB/s", "38.5 GB/s"):
            self.assertIn(expected, table)


class TestShareOfTheMaximum(TabCase):
    def test_the_percentage_with_what_it_is_made_of(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(recorded(), **DDR4_3200_TWO_CHANNELS))
        self.assertEqual(tab.share.text(), _("memtest.share").format(
            pct="86", rate="43.9 GB/s", threads=_("memtest.threads.one").format(n=1),
            channels=_("memtest.channels").format(n=2), mts=3200, total="51.2 GB/s"))
        self.assertEqual(tab.share_bar.value(), 85)
        self.assertTrue(tab.share_bar.isVisibleTo(tab))

    def test_one_channel_is_said_in_the_singular(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(
            recorded(), theoretical_bytes_per_second=25_600_000_000, channels=1, speed_mts=3200))
        self.assertIn(_("memtest.channels.one").format(n=1), tab.share.text())

    def test_without_the_channels_it_says_why_there_is_none(self):
        tab = self.tab()
        tab.show_result(recorded())
        self.assertEqual(tab.share.text(), _("memtest.share.unknown"))
        self.assertFalse(tab.share_bar.isVisibleTo(tab))

    def test_above_a_hundred_is_a_wrong_figure_and_is_said(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(
            recorded(), theoretical_bytes_per_second=25_600_000_000, channels=1, speed_mts=3200))
        self.assertIn(_("memtest.notice.over"), visible_texts(tab))
        self.assertEqual(tab.share_bar.value(), 100)
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
        self.assertTrue(tab.share_bar.isVisibleTo(tab))
        self.assertIn("%", tab.share.text())
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


class TestWideScreens(TabCase):
    def test_the_content_keeps_to_a_readable_width_and_stays_centred(self):
        tab = self.tab()
        tab.show_result(recorded())
        tab.resize(2560, 1300)
        for _turn in range(3):
            self.app.processEvents()
        root = tab.widget()
        card = tab.result_card
        self.assertLessEqual(card.width(), root.content_width())
        left = card.mapTo(root, card.rect().topLeft()).x()
        right = root.width() - left - card.width()
        self.assertLessEqual(abs(left - right), 2)

    def test_a_narrow_window_keeps_its_usual_margins(self):
        from silux.ui import theme

        tab = self.tab()
        tab.show_result(recorded())
        tab.resize(900, 700)
        for _turn in range(3):
            self.app.processEvents()
        self.assertEqual(tab.widget().column.contentsMargins().left(), theme.METRICS.page_margin)


class TestWhatWentOnWhileMeasuring(TabCase):
    def test_points_taken_with_the_clock_down_are_said(self):
        """A core that was still coming up to speed for the first blocks."""
        result = recorded()
        slow = tuple(dataclasses.replace(p, frequency_hz=int(p.frequency_hz * 0.65))
                     if index < 3 else p for index, p in enumerate(result.points))
        tab = self.tab()
        tab.show_result(dataclasses.replace(result, points=slow))
        self.assertIn(_("memtest.notice.clock"), visible_texts(tab))
        tab.show_result(result)
        self.assertNotIn(_("memtest.notice.clock"), visible_texts(tab))

    def test_without_the_module_it_says_the_measure_is_the_simple_one(self):
        plan = memtest.make_plan((("L1", 32 * KIB), ("L2", 256 * KIB)), (0,), cpu=0,
                                 available=4 * 1024 * MIB)
        with mock.patch.object(memtest, "native_module", return_value=None):
            result = memtest.run(plan)
        if not result.measured:
            self.skipTest("the simple measure gave nothing here")
        tab = self.tab()
        tab.show_result(result)
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

    def test_the_progress_is_said_beside_the_bar_and_not_on_it(self):
        tab = self.tab()
        tab._on_progress("write", 0.55)
        self.assertFalse(tab.progress.bar.isTextVisible())
        self.assertEqual(tab.progress.label.text(), f"{_('memtest.phase.write')}  ·  55 %")
        self.assertEqual(tab.progress.value(), 55)

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
                # Long enough to outlast the rebuild on a loaded machine.
                plan = dataclasses.replace(TestRunningIt.short_plan(self),
                                           sizes=memtest.curve_sizes(32 * MIB))
                with mock.patch.object(old, "plan", return_value=plan):
                    old.start()
                window._on_preferences(dataclasses.replace(window.prefs, **change))
                new = window.benchmarks_page.memory_tab
                self.assertIsNot(new, old)
                self.assertTrue(new.running)
                self.assertTrue(new.cancel_button.isVisibleTo(new))
                self.assertFalse(new.run_button.isEnabled())
                self.assertFalse(window.benchmarks_page.cpu_tab.run_button.isEnabled())
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

    def test_the_tabs_that_exist_and_no_other(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.benchmarks import BenchmarksPage

        page = BenchmarksPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        self.assertEqual([b.text() for b in page.buttons.values()],
                         [_("bench.tab.cpu"), _("bench.tab.memory")])
        self.assertEqual(page.tab, "cpu")
        self.assertTrue(page.select_tab("memory"))
        self.assertIs(page.stack.currentWidget(), page.memory_tab)
        self.assertFalse(page.select_tab("disk"))


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
