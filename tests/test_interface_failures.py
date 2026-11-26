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
        from PySide6.QtCore import QTimer

        app = qt.app()
        recorded = failures.Failures()
        failures.install_hooks(recorded)
        QTimer.singleShot(0, _broken_slot)
        for _turn in range(5):
            app.processEvents()
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
        from PySide6.QtCore import QTimer

        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import full_report
        from silux.ui.app import MainWindow

        app = qt.app()
        window = MainWindow(Preferences().normalized())
        self.addCleanup(window.deleteLater)
        failures.install_hooks(window.failures)
        QTimer.singleShot(0, _broken_slot)
        for _turn in range(5):
            app.processEvents()
        snapshot = window.for_the_report(shared_snapshot(EQUIPOS / "i5-10400"))
        text = full_report.build(snapshot)
        self.assertIn(_("report.diag.failures"), text)
        self.assertIn("ui._broken_slot", text)
