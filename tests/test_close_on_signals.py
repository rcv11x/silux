"""Ctrl+C and SIGTERM close Silux as its close button does.

Ctrl+C in the terminal raised a KeyboardInterrupt inside whatever Python ran
next (the charts' timer), the traceback went to the terminal and the window
stayed open. Python runs a signal's handler only between its own
instructions, and Qt's loop, idle, runs none.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestInTheWindow(unittest.TestCase):
    def test_a_signal_closes_it_through_its_close_button(self):
        from PySide6.QtCore import QTimer

        from silux.settings import Preferences
        from silux.ui import app as app_module

        application = qt.app()
        previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        old_fd = signal.set_wakeup_fd(-1)
        signal.set_wakeup_fd(old_fd)

        def restore():
            signal.set_wakeup_fd(old_fd)
            for number, handler in previous.items():
                signal.signal(number, handler)
        self.addCleanup(restore)

        with tempfile.TemporaryDirectory() as config, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
            window = app_module.MainWindow(Preferences().normalized())
            window.show()
            window._on_sample(shared_snapshot(EQUIPOS / "i5-10400"))
            app_module.close_on_signals(application, window)
            with mock.patch.object(window._memory_run, "cancel",
                                   wraps=window._memory_run.cancel) as cancel:
                QTimer.singleShot(100, lambda: os.kill(os.getpid(), signal.SIGINT))
                # Should the signal be lost, the test ends anyway.
                QTimer.singleShot(10_000, application.quit)
                started = time.monotonic()
                application.exec()
            self.assertLess(time.monotonic() - started, 9)
            self.assertFalse(window.isVisible())
            cancel.assert_called()
            self.assertTrue(os.path.isfile(os.path.join(config, "silux", "settings.json")))
            window.deleteLater()


# How the AppImage's AppRun starts it (`tools/build_appimage.py`).
APPRUN = ("import sys, runpy\nsys.path.pop(0)\n"
          "runpy.run_module(sys.argv.pop(1), run_name=\"__main__\", alter_sys=True)")


class TestTheProgram(unittest.TestCase):
    def run_and_stop(self, number: int,
                     command=("-m", "silux.ui.app")) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       XDG_CONFIG_HOME=os.path.join(home, "config"),
                       XDG_DATA_HOME=os.path.join(home, "data"),
                       XDG_CACHE_HOME=os.path.join(home, "cache"))
            process = subprocess.Popen([sys.executable, *command], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True)
            try:
                time.sleep(6)
                process.send_signal(number)
                out, err = process.communicate(timeout=30)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            return subprocess.CompletedProcess(process.args, process.returncode, out, err)

    def test_ctrl_c(self):
        done = self.run_and_stop(signal.SIGINT)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertNotIn("Traceback", done.stderr)
        self.assertNotIn("KeyboardInterrupt", done.stderr)

    def test_ctrl_c_as_the_appimage_starts_it(self):
        done = self.run_and_stop(signal.SIGINT, ("-c", APPRUN, "silux.ui.app"))
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertNotIn("Traceback", done.stderr)

    def test_sigterm(self):
        done = self.run_and_stop(signal.SIGTERM)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertNotIn("Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
