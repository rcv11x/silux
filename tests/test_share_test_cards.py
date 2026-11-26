"""A disk or memory test's result as an image, to paste where people compare
them: its figures, never where it ran, and the mark that says so."""

import dataclasses
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import disktest, i18n, memtest, render
from silux.i18n import _
from tests.qt import app
from tests.test_disktest import recorded as disk_run
from tests.test_disktest_page import TabCase
from tests.test_memtest import recorded as memory_run

# Where a pen drive is mounted carries its owner's name and its label.
MOUNT = "/run/media/zoraida/Fotos de Zoraida"
LABEL = "El SSD de Zoraida"


def card_texts(summary: str, rows) -> str:
    return "\n".join([summary] + [" ".join(row) for row in rows])


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()

    def setUp(self):
        language = i18n.current()
        self.addCleanup(i18n.set_language, language)
        i18n.set_language("es")


class TestTheDiskCard(Case):
    def test_its_figures_are_the_tests(self):
        from silux.ui import tarjeta

        result = disk_run("970-evo-plus-ext4")
        rows = tarjeta.disk_rows(result)
        text = card_texts(tarjeta.disk_summary(result), rows)
        for measure in result.measures:
            self.assertIn(render.disk_rate(measure.median.bytes_per_second), text)
        self.assertEqual([row[0] for row in rows[:4]],
                         ["SEQ1M Q8T1", "SEQ1M Q1T1", "RND4K Q32T1", "RND4K Q1T1"])
        for expected in ("Samsung SSD 970 EVO Plus 2TB", "ext4",
                         _("disktest.profile.standard"), f"{render.thousands(262452)} IOPS"):
            self.assertIn(expected, text)

    def test_a_figure_that_varied_is_marked_as_on_the_page(self):
        from silux.ui import tarjeta

        result = disk_run("sn850x-btrfs")
        rows = {row[0]: row for row in tarjeta.disk_rows(result)}
        self.assertTrue(rows["SEQ1M Q8T1"][1].endswith("MB/s*"))
        self.assertNotIn("*", rows["SEQ1M Q1T1"][1])
        self.assertIn(_("disktest.note.varied"), rows[_("share.test.profile")][2])

    def test_its_file_system_as_the_page_says_it(self):
        from silux.ui import tarjeta

        self.assertIn(_("disktest.conditions.nocow").format(filesystem="btrfs"),
                      tarjeta.disk_summary(disk_run("sn850x-btrfs")))

    def test_never_where_it_ran(self):
        from silux.ui import tarjeta

        result = dataclasses.replace(disk_run("970-evo-plus-ext4"), mountpoint=MOUNT, label=LABEL)
        text = card_texts(tarjeta.disk_summary(result), tarjeta.disk_rows(result))
        self.assertNotIn("zoraida", text.lower())


class TestTheMemoryCard(Case):
    def test_its_figures_are_the_tests(self):
        from silux.ui import tarjeta

        result = memory_run("i5-10400-window")
        rows = tarjeta.memory_rows(result)
        text = card_texts(tarjeta.memory_summary(result, "Core i5-10400"), rows)
        for level in result.levels:
            self.assertIn(render.nanoseconds(level.nanoseconds), text)
        # As the page's grid: the fastest kind, which here skips the cache
        # for writing and copying, with every thread and then with one.
        for operation, every, one in (("read", "33.2", "22.8"), ("write", "34.7", "37.2"),
                                      ("copy", "25.9", "20.1")):
            row = next(row for row in rows if row[0] == _(f"memtest.op.{operation}"))
            self.assertEqual(row[1], f"{every} GB/s")
            self.assertIn(f"{one} GB/s", row[2])
            self.assertEqual(_("memtest.grid.nt") in row[2], operation != "read")
        share = render.whole_percent(memtest.share_of_theoretical(result))
        for expected in ("Core i5-10400", "2666 MT/s", share, "42.7 GB/s"):
            self.assertIn(expected, text)


class TestUnfinished(Case):
    def test_a_run_that_stopped_halfway_is_not_shared(self):
        from silux.ui import tarjeta

        for result in (disk_run("970-evo-plus-ext4"), memory_run("i5-10400-window")):
            self.assertTrue(tarjeta.shareable(result))
            self.assertFalse(tarjeta.shareable(dataclasses.replace(result, reason="cancelled")))


class TestTheImage(Case):
    def test_it_carries_the_mark(self):
        from silux.ui import tarjeta, theme
        from tools import comprobar_privacidad

        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "card.png"
            self.assertTrue(tarjeta.save_image(
                tarjeta.draw_disk_test(disk_run("970-evo-plus-ext4"), theme.DARK), str(path)))
            self.assertEqual(comprobar_privacidad._capturas_delatoras([path]), [])

    def test_no_label_reaches_its_value(self):
        """Each label's last pixel comes before its value's first, in both
        languages: «Escritura sin caché» ran into its figure."""
        from PySide6.QtGui import QColor

        from silux.ui import tarjeta, theme

        palette = theme.DARK
        accent, ink = QColor(palette.accent), QColor(palette.ink)

        def near(pixel, colour) -> bool:
            return (abs(pixel.red() - colour.red()) + abs(pixel.green() - colour.green())
                    + abs(pixel.blue() - colour.blue())) < 30

        for language in ("es", "en"):
            i18n.set_language(language)
            result = memory_run("i5-10400-window")
            rows = tarjeta.memory_rows(result)
            image = tarjeta.draw_memory_test(result, "Core i5-10400", palette).toImage()
            for index, (label, _value, _detail) in enumerate(rows):
                baseline = tarjeta.MARGEN + 96 + index * tarjeta.ALTO_FILA
                labels, values = [], []
                for y in range(baseline - 16, baseline + 4):
                    for x in range(tarjeta.MARGEN, tarjeta.ANCHO - tarjeta.MARGEN):
                        pixel = image.pixelColor(x, y)
                        if near(pixel, accent):
                            labels.append(x)
                        elif near(pixel, ink):
                            values.append(x)
                with self.subTest(language=language, label=label):
                    self.assertTrue(labels and values)
                    self.assertLess(max(labels) + 4, min(values))


class TestOnTheDiskPage(TabCase):
    def setUp(self):
        super().setUp()
        disktest.save_history([disk_run("sn850x-btrfs")])

    def test_copy_puts_the_card_on_the_clipboard(self):
        from PySide6.QtWidgets import QApplication

        tab = self.tab()
        self.assertTrue(tab.share_buttons.isVisibleTo(tab))
        QApplication.clipboard().clear()
        tab.share_buttons.copy_button.click()
        self.assertFalse(QApplication.clipboard().pixmap().isNull())
        # Its effect, on its page.
        self.assertEqual(tab.share_buttons.note.text(), _("share.copied"))
        self.assertTrue(tab.share_buttons.note.isVisibleTo(tab))

    def test_save_writes_the_marked_image(self):
        from PySide6.QtWidgets import QFileDialog

        from tools import comprobar_privacidad

        tab = self.tab()
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "disk.png"
            with mock.patch.object(QFileDialog, "getSaveFileName",
                                   return_value=(str(path), "")) as asked:
                tab.share_buttons.save_button.click()
            suggested = pathlib.Path(asked.call_args.args[2]).name
            self.assertTrue(suggested.startswith(_("share.test.file.disk")))
            self.assertEqual(comprobar_privacidad._capturas_delatoras([path]), [])
            self.assertIn(path.name, tab.share_buttons.note.text())

    def test_a_disk_without_a_result_has_nothing_to_share(self):
        tab = self.tab()
        self.pick(tab, "unidad3")
        self.assertFalse(tab.share_buttons.isVisibleTo(tab))

    def test_nor_one_that_stopped_halfway(self):
        tab = self.tab()
        tab.show_result(dataclasses.replace(disk_run("sn850x-btrfs"), reason="disconnected"))
        self.assertFalse(tab.share_buttons.isVisibleTo(tab))


class TestOnTheMemoryPage(Case):
    def setUp(self):
        super().setUp()
        memtest.clear_history()
        self.addCleanup(memtest.clear_history)
        memtest.save_history([memory_run("i5-10400-window")])

    def test_copy_puts_the_card_on_the_clipboard(self):
        from PySide6.QtWidgets import QApplication

        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memtest import MemoryTestTab
        from tests.test_equipos import EQUIPOS, shared_snapshot

        tab = MemoryTestTab(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(tab.deleteLater)
        tab.resize(900, 900)
        tab.show()
        tab.apply(shared_snapshot(EQUIPOS / "i5-10400"))
        self.assertTrue(tab.share_buttons.isVisibleTo(tab))
        QApplication.clipboard().clear()
        tab.share_buttons.copy_button.click()
        self.assertFalse(QApplication.clipboard().pixmap().isNull())
        self.assertEqual(tab.share_buttons.note.text(), _("share.copied"))


if __name__ == "__main__":
    unittest.main()
