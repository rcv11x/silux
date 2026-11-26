"""What breaks in the interface goes to the report, with its traceback.

A failure in a provider went to the report; one in the window (a slot, a
paint, a thread of ours) only to the terminal, which nobody sends. When a
tester's Performance page went blank, his report said nothing.
"""

import sys
import threading
import unittest

from silux import failures
from tests import qt
from tests.test_equipos import EQUIPOS, shared_snapshot


def _broken_slot():
    raise KeyError("a slot of the window")


def run_the_loop_with(slot) -> None:
    """`slot` called from Qt's loop, as Silux runs: `app.exec()`. Called
    from `processEvents`, PySide 6.9 raises the slot's exception out of it
    instead of handing it to the hook; inside the loop both 6.9 and 6.12 hand
    it over."""
    from PySide6.QtCore import QTimer

    app = qt.app()
    QTimer.singleShot(0, slot)
    QTimer.singleShot(100, app.quit)
    app.exec()


class Hooks(unittest.TestCase):
    def setUp(self):
        hook, thread_hook = sys.excepthook, threading.excepthook

        def restore():
            sys.excepthook, threading.excepthook = hook, thread_hook
        self.addCleanup(restore)
        # The terminal keeps getting them: here, a list.
        self.printed = []
        sys.excepthook = lambda *exc_info: self.printed.append(exc_info[0])
        threading.excepthook = lambda args: self.printed.append(args.exc_type)


class TestTheHooks(Hooks):
    def test_a_slot_that_breaks(self):
        recorded = failures.Failures()
        failures.install_hooks(recorded)
        run_the_loop_with(_broken_slot)
        [failure] = recorded.recent()
        self.assertEqual(failure.where, "ui._broken_slot")
        self.assertIn("a slot of the window", failure.error)
        self.assertIn("_broken_slot", failure.trace)
        self.assertEqual(self.printed, [KeyError])

    def test_a_thread_that_breaks(self):
        recorded = failures.Failures()
        failures.install_hooks(recorded)
        worker = threading.Thread(target=lambda: 1 / 0, name="measuring")
        worker.start()
        worker.join()
        [failure] = recorded.recent()
        self.assertEqual(failure.where, "thread measuring")
        self.assertIn("ZeroDivisionError", failure.error)

    def test_an_interrupt_is_not_a_failure(self):
        recorded = failures.Failures()
        failures.install_hooks(recorded)
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())
        self.assertEqual(recorded.recent(), ())


class TestTheWindowsReport(Hooks):
    def test_carries_them(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import full_report
        from silux.ui.app import MainWindow

        qt.app()
        window = MainWindow(Preferences().normalized())
        self.addCleanup(window.deleteLater)
        failures.install_hooks(window.failures)
        run_the_loop_with(_broken_slot)
        snapshot = window.for_the_report(shared_snapshot(EQUIPOS / "i5-10400"))
        text = full_report.build(snapshot)
        self.assertIn(_("report.diag.failures"), text)
        self.assertIn("ui._broken_slot", text)
