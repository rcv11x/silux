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
        tab = self.tab()
        tab.show_result(recorded())
        self.assertEqual(tab.rates.text(), "  ·  ".join((
            f"{_('memtest.op.read')} 43.9 GB/s", f"{_('memtest.op.write')} 20.6 GB/s",
            f"{_('memtest.op.copy')} 27.7 GB/s")))
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
            pct="86", channels=_("memtest.channels").format(n=2), mts=3200, total="51.2 GB/s"))
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
