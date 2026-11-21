"""One password window per request, and «Cancel» is final.

The collector runs for real on a recorded machine; only the command handed to
pkexec is replaced by one that exits as pkexec does when the user presses
«Cancel» (126). What the tests count is how many password windows would open.
"""

import itertools
import unittest
from unittest import mock

from silux.collector import Collector
from silux.privileged.client import PrivilegedClient
from tests import qt
from tests.test_equipos import EQUIPOS
from tests.test_volcar_equipo import _herramienta

CANCELLED = ["sh", "-c", "exit 126"]
# The password was right, and the helper did not start: still one window.
BROKEN = ["sh", "-c", "exit 1"]


class _Recorded(unittest.TestCase):
    """A collector on the 5800X3D, with pkexec answering «cancelled»."""

    answer = CANCELLED

    def setUp(self):
        self.windows = 0
        self.while_open = None          # what the user does with the window open

        def order(_client):
            self.windows += 1
            if self.while_open is not None:
                self.while_open()
            return list(self.answer)

        for patch in (mock.patch.object(PrivilegedClient, "_orden", order),
                      mock.patch.object(PrivilegedClient, "supported", return_value=True),
                      mock.patch("silux.providers.privileged_memory.already_root",
                                 return_value=False)):
            patch.start()
            self.addCleanup(patch.stop)
        mounted = _herramienta().mounted(EQUIPOS / "5800x3d")
        mounted.__enter__()
        self.addCleanup(mounted.__exit__, None, None, None)
        self.collector = Collector()
        self.addCleanup(self.collector.close)
        self.collector.snapshot()


class TestCancelIsFinal(_Recorded):

    def test_one_request_opens_one_window(self):
        self.collector.request_elevation()
        self.collector.snapshot()
        self.assertEqual(self.windows, 1)

    def test_after_a_cancel_nothing_asks_again(self):
        self.collector.request_elevation()
        for _sample in range(3):
            snapshot = self.collector.snapshot()
        self.assertEqual(self.windows, 1)
        # The padlocks stay where they were.
        for field in ("modules", "disks.health"):
            with self.subTest(field=field):
                self.assertIsNotNone(snapshot.permission_note(field))

    def test_asking_again_opens_one_more(self):
        for _request in range(2):
            self.collector.request_elevation()
            self.collector.snapshot()
        self.assertEqual(self.windows, 2)


class TestAFailureIsFinalToo(TestCancelIsFinal):
    answer = BROKEN


class TestAskingWhileTheWindowIsOpen(_Recorded):
    """A click while the password window is open asks for what that window
    is already asking: it does not open a second one after the cancel."""

    def test_the_open_window_answers_it(self):
        from silux.ui.sampler import Sampler

        qt.app()
        sampler = Sampler()
        self.while_open = sampler.request_elevation
        sampler.request_elevation()
        turns = itertools.count()
        with mock.patch.object(sampler, "_esperar", lambda _c: next(turns) < 3):
            sampler._loop(self.collector)
        self.assertEqual(self.windows, 1)


if __name__ == "__main__":
    unittest.main()
