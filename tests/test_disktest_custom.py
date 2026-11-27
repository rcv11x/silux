"""The «Custom» disk test profile: the pattern, block and queue chosen, one
thread until there are several rings; and its runs compared, and listed in
the history, only with runs of the same tests."""

import dataclasses
import unittest

from silux import disktest
from silux.disktest import KIB, MIB
from silux.disktest import Test as DiskTest
from tests.test_disktest import recorded
from tests.test_disktest_page import TabCase


def custom(result, test: DiskTest, when: float):
    """A recorded run as if it had measured `test` alone, at `when`."""
    measures = tuple(dataclasses.replace(m, pattern=test.pattern, block=test.block,
                                         depth=test.depth, threads=test.threads)
                     for m in result.measures if m.name == "SEQ1M Q8T1")
    return dataclasses.replace(result, profile="custom", measures=measures, timestamp=when)


class TestComparing(unittest.TestCase):
    def test_a_run_compares_only_with_one_of_the_same_tests(self):
        base = recorded("sn850x-btrfs")
        rnd16 = DiskTest("random", 16 * KIB, 4)
        older = custom(base, rnd16, base.timestamp - 100)
        other = custom(base, DiskTest("sequential", MIB, 2), base.timestamp - 50)
        newer = custom(base, rnd16, base.timestamp)
        standard = dataclasses.replace(base, timestamp=base.timestamp - 10)
        history = [newer, standard, other, older]
        self.assertIs(disktest.previous(newer, history), older)
        self.assertIsNone(disktest.previous(other, history))
        # And a standard one never with a custom one.
        self.assertNotEqual(disktest.previous(base, [newer, other]), newer)


class TestTheTab(TabCase):
    def test_its_choices_show_only_with_it_and_reach_the_plan(self):
        tab = self.tab()
        self.assertFalse(tab.custom_row.isVisibleTo(tab))
        tab.profile_box.setCurrentIndex(tab.profile_box.findData("custom"))
        tab.profile_box.activated.emit(tab.profile_box.currentIndex())
        self.assertTrue(tab.custom_row.isVisibleTo(tab))
        tab.pattern_box.setCurrentIndex(tab.pattern_box.findData("random"))
        tab.block_box.setCurrentIndex(tab.block_box.findData(16 * KIB))
        tab.depth_box.setCurrentIndex(tab.depth_box.findData(4))
        plan = tab.plan()
        self.assertEqual(plan.profile, "custom")
        self.assertEqual(plan.tests, (DiskTest("random", 16 * KIB, 4),))
        self.assertEqual(plan.tests[0].name, "RND16K Q4T1")

    def test_the_history_keeps_it_apart(self):
        base = recorded("sn850x-btrfs")
        run = custom(base, DiskTest("random", 16 * KIB, 4), base.timestamp + 10)
        disktest.save_history([run, base])
        tab = self.tab()
        self.assertEqual(len(tab.history_tables), 2)
        headers = [" ".join(table._headers) for _heading, table in tab.history_tables]
        self.assertTrue(any("16" in h for h in headers), headers)


if __name__ == "__main__":
    unittest.main()
