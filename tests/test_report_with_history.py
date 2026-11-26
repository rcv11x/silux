"""Each dump's full report with tests on record: a CPU benchmark, a memory
test and a disk test run on a pen drive.

The tests that walk every dump's report ran with an empty history, so the
sections that only exist with one were never checked: in English, for
Spanish left in them, and for what a pen drive's mount carries.
"""

import dataclasses
import re
import unittest
from unittest import mock

from silux import benchmark, disktest, history, i18n, memtest
from silux.i18n import _
from tests.per_dump import per_dump
from tests.test_disktest import recorded as disk_run
from tests.test_equipos import shared_snapshot
from tests.test_memtest import recorded as memory_run

SPANISH = re.compile(r"[áéíóúñ¿¡]", re.I)
OWNER, LABEL = "lucia", "VIAJE 2026"
_CPU_RUN: list = []


def cpu_entry():
    """A real CPU benchmark, short: the same work for less time. One per
    process."""
    if not _CPU_RUN:
        with mock.patch.object(benchmark, "MIN_SECONDS", 0.05):
            result = benchmark.run(seconds=0.05)
        _CPU_RUN.append(history.from_result(result, "CPU", 0.05))
    return _CPU_RUN[0]


class TestTheReportWithHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import qt

        qt.app()
        cls.previous = i18n.current()
        i18n.set_language("en")

    @classmethod
    def tearDownClass(cls):
        i18n.set_language(cls.previous)

    def setUp(self):
        for clear in (history.clear, memtest.clear_history, disktest.clear_history):
            clear()
            self.addCleanup(clear)
        history.append(cpu_entry())
        memtest.save_history([memory_run()])
        disktest.save_history([dataclasses.replace(disk_run("cruzer-blade-fat32"),
                                                   mountpoint=f"/run/media/{OWNER}/{LABEL}")])

    def _in_english(self, folder):
        from silux.ui import full_report

        text = full_report.build(shared_snapshot(folder), anonymous=True)
        self.assertEqual([line for line in text.splitlines() if SPANISH.search(line)], [])
        for title in ("## Memory test", "## Disk test"):
            self.assertIn(title, text)
        # The CPU benchmark on record, on the Performance page.
        self.assertIn(f"### {_('bench.card.history')}", text)
        self.assertNotIn(OWNER, text)
        self.assertNotIn(LABEL, text)


per_dump(TestTheReportWithHistory, "in_english", TestTheReportWithHistory._in_english)


if __name__ == "__main__":
    unittest.main()
