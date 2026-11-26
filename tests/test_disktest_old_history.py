"""A history written by an earlier version is still each disk's.

`history-v1-2026-11-24.json` is the file the first version with a disk test
wrote, by its own code, with two real runs: one on a WD_BLACK SN850X at
/home, one on a Samsung 970 EVO Plus. Opened on the machine they ran on,
each disk shows its own result, never «no measures yet», and the history
lists both. A change in the file's version, or in how a run is matched to
its disk, that forgets them fails here.
"""

import shutil
import unittest

from silux import disktest
from silux.i18n import _
from tests.test_disktest import FIXTURES
from tests.test_disktest_page import TabCase, visible_texts

OLD_HISTORY = FIXTURES / "history-v1-2026-11-24.json"


class TestAnOldHistory(TabCase):
    def setUp(self):
        super().setUp()
        disktest.history_path().parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OLD_HISTORY, disktest.history_path())

    def test_it_loads_whole(self):
        runs = disktest.load_history()
        self.assertEqual([r.model for r in runs],
                         ["WD_BLACK SN850X HS 1000GB", "Samsung SSD 970 EVO Plus 2TB"])
        self.assertTrue(all(r.measured for r in runs))

    def test_each_disk_shows_its_own_runs(self):
        tab = self.tab()
        for place, model, figure in (("", "WD_BLACK SN850X HS 1000GB", "6 592"),
                                     ("unidad2", "Samsung SSD 970 EVO Plus 2TB", "3 579")):
            if place:
                self.pick(tab, place)
            with self.subTest(disk=model):
                self.assertIsNotNone(tab.result)
                self.assertEqual(tab.result.model, model)
                text = visible_texts(tab)
                self.assertNotIn(_("disktest.empty"), text)
                self.assertIn(figure, text)


if __name__ == "__main__":
    unittest.main()
