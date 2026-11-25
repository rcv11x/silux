"""Storage says, under each disk, its last disk test and the way to it.

On the dump of the machine the recorded runs were measured on, as the disk
tab's own tests: its disks, its mounts and its links.
"""

import dataclasses

from silux import disktest
from silux.i18n import _
from tests import pantalla
from tests.test_disktest import recorded
from tests.test_disktest_page import TabCase, visible_texts


def plain(text: str) -> str:
    """Without the spaces that keep a figure and its unit together."""
    return text.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2060", "")


def open_storage(window) -> None:
    """Storage open, as someone would: a page fills when it is visited."""
    from PySide6.QtWidgets import QApplication

    from silux.ui.app import SECTIONS

    window.nav.setCurrentRow(next(i for i, (key, _on) in enumerate(SECTIONS)
                                  if key == "nav.storage"))
    QApplication.processEvents()


class TestTheLastTestUnderItsDisk(TabCase):
    def test_each_measured_disk_says_its_last_and_opens_it(self):
        disktest.save_history([recorded("970-evo-plus-ext4"), recorded("sn850x-btrfs")])
        with pantalla.Ventana(self.snapshot) as window:
            open_storage(window)
            page = window.storage_page
            line, summary = page._tests["nvme0n1"]
            self.assertTrue(line.isVisibleTo(page))
            text = plain(summary.text())
            self.assertIn("6 592 MB/s", text)
            self.assertIn("3 946 MB/s", text)
            self.assertIn("3 579 MB/s", plain(page._tests["nvme1n1"][1].text()))
            # A disk never measured says nothing of another's.
            self.assertFalse(page._tests["sda"][0].isVisibleTo(page))

            line.findChild(type(window.benchmarks_page.disk_tab.run_button)).click()
            self.assertIs(window.stack.currentWidget(), window.benchmarks_page)
            tab = window.benchmarks_page.disk_tab
            self.assertIs(window.benchmarks_page.stack.currentWidget(), tab)
            self.assertEqual(tab.plan().disks, ("nvme0n1",))
            self.assertIn("6 592", visible_texts(tab))

    def test_a_test_that_ends_shows_on_the_spot(self):
        """Rule 9: the line appears without leaving Storage."""
        with pantalla.Ventana(self.snapshot) as window:
            open_storage(window)
            page = window.storage_page
            self.assertFalse(page._tests["nvme0n1"][0].isVisibleTo(page))
            run = window._disk_run
            run.model = "WD_BLACK SN850X HS 1000GB"
            run._on_done(dataclasses.replace(recorded("sn850x-btrfs"), timestamp=1_900_000_000.0))
            self.assertTrue(page._tests["nvme0n1"][0].isVisibleTo(page))
            self.assertIn(_("storage.lasttest").split("{")[0], page._tests["nvme0n1"][1].text())
