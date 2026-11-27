"""A window that is closed goes, with its pages.

A lambda holding the window, connected to a signal of one of its own
widgets, kept every closed window alive: about 22 MB each, and a suite that
opens one per dump and page filled 31 GB.
"""

import gc
import unittest

from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


def windows_alive() -> int:
    from silux.ui.app import MainWindow

    gc.collect()
    return sum(1 for o in gc.get_objects() if isinstance(o, MainWindow))


class TestClosedWindowsGo(unittest.TestCase):
    def test_three_windows_opened_and_closed_leave_none(self):
        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        before = windows_alive()
        for _turn in range(3):
            with pantalla.Ventana(snapshot) as window:
                window.set_nav_folded(True)
                geometry.settle(app)
            del window
            geometry.settle(app)
        self.assertEqual(windows_alive(), before)


if __name__ == "__main__":
    unittest.main()
