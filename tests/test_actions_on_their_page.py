"""Every button that starts something, pressed, with a short run of the real
thing: its effect shows on its page, the page stays in its view and nothing
breaks in the window.

No test pressed the CPU benchmark's buttons, and a tester's Performance page
went blank after one. Each run here is the real one, made short: the same
work for less time.
"""

import dataclasses
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from silux import benchmark, disktest, history, memtest
from silux.memtest import KIB, MIB
from tests import geometry, pantalla, qt
from tests.test_disk_native import _base
from tests.test_equipos import EQUIPOS, shared_snapshot

try:
    import silux_bench
except ImportError:
    silux_bench = None


def wait_for(application, done, seconds: float = 120) -> None:
    deadline = time.monotonic() + seconds
    while not done() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    geometry.settle(application)


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-10400")

    def setUp(self):
        for clear in (history.clear, memtest.clear_history, disktest.clear_history):
            clear()
            self.addCleanup(clear)
        ventana = pantalla.Ventana(self.snapshot)
        self.window = ventana.__enter__()
        self.addCleanup(ventana.__exit__, None, None, None)
        self.window.resize(1100, 720)
        geometry.settle(self.app)

    def tab(self, key: str):
        self.window.select_section("Rendimiento")
        page = self.window.benchmarks_page
        page.select_tab(key)
        geometry.settle(self.app)
        return page._tabs[key]

    def after(self, area) -> None:
        geometry.stays_in_view(self, self.window, area, self.snapshot)
        self.assertEqual(self.window.failures.recent(), ())


class TestTheCpuBenchmark(Case):
    def run_it(self, button) -> None:
        tab = self.tab("cpu")
        button(tab).click()
        wait_for(self.app, lambda: not tab.running)
        self.assertTrue(tab.results_card.isVisibleTo(tab))
        self.assertTrue(tab.score_card.isVisibleTo(tab))
        self.assertEqual(len(history.load()), 1)
        self.after(tab)

    def test_the_quick_one(self):
        with mock.patch.object(benchmark, "QUICK_SECONDS", 0.05):
            self.run_it(lambda tab: tab.quick_button)

    def test_the_whole_one(self):
        tab = self.tab("cpu")
        other = tab.duracion.count() - 1
        self.assertIsNone(tab.duracion.itemData(other))
        tab.duracion.setCurrentIndex(other)
        tab._duracion_libre = 0.05
        with mock.patch.object(benchmark, "MIN_SECONDS", 0.05):
            self.run_it(lambda tab: tab.run_button)


@unittest.skipUnless(memtest.native_module(), "silux_bench is not installed")
class TestTheMemoryBenchmark(Case):
    def test_start(self):
        tab = self.tab("memory")
        cpus = tuple(memtest.native_module().allowed_cpus()[:1])
        short = memtest.Plan(cpu=cpus[0], cpus=cpus, sizes=memtest.curve_sizes(64 * KIB),
                             ram_block=None, ram_block_limited=False, single_bytes=2 * MIB,
                             multi_bytes=None, caches=(("L1", 32 * KIB),))
        with mock.patch.object(tab, "plan", return_value=short):
            tab.run_button.click()
            wait_for(self.app, lambda: not tab.running
                     and not tab.cancel_button.isVisibleTo(tab))
        self.assertTrue(tab.result_card.isVisibleTo(tab))
        self.after(tab)


@unittest.skipUnless(hasattr(silux_bench, "DiskFile"), "silux_bench has no disk benchmark")
class TestTheDiskBenchmark(Case):
    def test_start(self):
        tab = self.tab("disk")
        base = _base()
        base.mkdir(parents=True, exist_ok=True)
        folder = pathlib.Path(tempfile.mkdtemp(prefix="actions-", dir=base))
        self.addCleanup(lambda: [p.unlink() for p in folder.iterdir()] and None
                        or folder.rmdir())
        tab.choose(str(folder))
        geometry.settle(self.app)
        plan = tab.plan()
        self.assertIsNotNone(plan)
        short = dataclasses.replace(
            plan, tests=(disktest.Test("sequential", MIB, 1),), bytes_=16 * MIB,
            laps=1, lap_seconds=0.2, pause_seconds=0.0, write=False)
        with mock.patch.object(tab, "plan", return_value=short):
            tab.run_button.click()
            wait_for(self.app, lambda: not tab.running
                     and not tab.cancel_button.isVisibleTo(tab))
        self.assertFalse(tab.running)
        # A result, or what stopped it, on the page.
        failure = tab._failure
        if tab.result is None:
            self.assertIsNotNone(failure, "no result and nothing said")
            self.assertTrue(failure.isVisibleTo(tab))
        else:
            self.assertTrue(tab.result.measures)
        self.after(tab)


class TestTheReport(Case):
    def test_its_button_shows_it(self):
        self.window.select_section("Ajustes")
        geometry.settle(self.app)
        self.window.settings_page.report_requested.emit()
        geometry.settle(self.app)
        dialog = self.window._report_preview
        self.addCleanup(dialog.cancel_annex)
        self.assertTrue(dialog.isVisible())
        self.assertIn("# ", dialog.report())
        self.assertEqual(self.window.failures.recent(), ())


class TestTheImage(Case):
    def test_copy_puts_it_on_the_clipboard(self):
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().clear()
        self.window.settings_page.share_copy_requested.emit()
        geometry.settle(self.app)
        self.assertFalse(QApplication.clipboard().pixmap().isNull())
        self.assertEqual(self.window.failures.recent(), ())


if __name__ == "__main__":
    unittest.main()
