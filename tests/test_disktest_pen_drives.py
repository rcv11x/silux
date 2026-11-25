"""Pen drives and cards in the Disk tab: FAT32's largest file, how long
writing the file takes on a slow disk, and a file system that went through
the page cache. On the dumps of machines that have them mounted."""

from silux import disktest
from silux.disktest import GIB, MIB
from silux.i18n import _
from tests.test_disktest_page import TabCase, visible_texts


class TestFat32(TabCase):
    """A SATA disk with a FAT32 partition."""

    DUMP = "i7-12700kf"

    def test_a_file_too_large_for_it_is_said_before_and_the_largest_offered(self):
        tab = self.tab()
        self.pick(tab, "/media/unidad1 ")
        self.assertEqual(tab.plan().filesystem, "vfat")
        self.assertTrue(tab.run_button.isEnabled())
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.too_big_for_fat"), text)
        self.assertIn("4 095 MiB", text)
        self.assertFalse(tab.run_button.isEnabled())

        notice = next(n for n in tab.findChildren(type(tab._note("too_big_for_fat", "fits",
                                                                 largest="", size="")))
                      if n.isVisibleTo(tab) and "4 095" in n.findChild(
                          type(tab.run_button)).text().replace(" ", " "))
        notice.findChild(type(tab.run_button)).click()
        self.assertEqual(tab.plan().bytes_, 4095 * MIB)
        self.assertEqual(tab.size_box.currentText().replace(" ", " "), "4 095 MiB")
        self.assertNotIn(_("disktest.note.too_big_for_fat"), visible_texts(tab))
        self.assertTrue(tab.run_button.isEnabled())
        self.assertIn("4 095 MiB", tab.about.text().replace(" ", " "))
        # The sizes stay in order, and it is offered only once.
        sizes = [tab.size_box.itemData(i) for i in range(tab.size_box.count())]
        self.assertEqual(sizes, sorted(sizes))
        tab._largest_that_fits()
        self.assertEqual(tab.size_box.count(), len(sizes))

    def test_elsewhere_the_same_size_is_no_trouble(self):
        tab = self.tab()
        self.pick(tab, "/media/unidad5 ")
        tab.size_box.setCurrentIndex(tab.size_box.findData(4 * GIB))
        tab._describe()
        self.assertNotIn(_("disktest.note.too_big_for_fat"), visible_texts(tab))
        self.assertTrue(tab.run_button.isEnabled())

    def test_a_file_the_engine_finds_too_large_is_not_a_failing_disk(self):
        from silux.ui.pages.disktest import DiskTestRun

        run = DiskTestRun()
        tab = self.tab(run=run)
        run._on_done(disktest.Result(reason="too_big", bytes_=16 * GIB,
                                     figures=(("bytes", 16 * GIB),)))
        text = visible_texts(tab)
        self.assertIn(_("disktest.note.too_big"), text)
        self.assertIn("16 GiB", text)
        self.assertIn(_("disktest.action.smaller"), text)
        self.assertNotIn(_("disktest.note.io"), text)
