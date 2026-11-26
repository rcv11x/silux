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


def disk_texts(result) -> str:
    """Everything a disk card writes but its footer."""
    from silux.ui import tarjeta

    cells = [" ".join([name] + [" ".join(map(str, cell)) for cell in row.values()])
             for name, row in tarjeta.disk_cells(result)]
    return "\n".join([tarjeta.disk_title(result), tarjeta.disk_subtitle(result), *cells,
                      *tarjeta.disk_notes(result)])


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()

    def setUp(self):
        language = i18n.current()
        self.addCleanup(i18n.set_language, language)
        i18n.set_language("es")


class TestTheDiskCard(Case):
    def test_a_column_per_direction_and_each_figure_alone(self):
        """As CrystalDiskMark: the unit once, over the table, and in each
        cell only its figure, with the requests per second under a random
        test's."""
        from silux.ui import tarjeta

        result = disk_run("970-evo-plus-ext4")
        cells = dict(tarjeta.disk_cells(result))
        self.assertEqual(list(cells), ["SEQ1M Q8T1", "SEQ1M Q1T1", "RND4K Q32T1", "RND4K Q1T1"])
        for measure in result.measures:
            figure, fraction, iops = cells[measure.name][measure.direction]
            self.assertEqual(figure, render.rate_figure(measure.median.bytes_per_second, 1e6))
            self.assertGreater(fraction, 0)
            self.assertEqual(bool(iops), measure.pattern == "random")
        self.assertEqual(cells["RND4K Q32T1"]["read"][2], f"{render.thousands(262452)} IOPS")
        self.assertEqual(tarjeta.DISK_UNIT, "MB/s")
        self.assertNotIn("MB/s", disk_texts(result))

    def test_a_figure_reads_over_its_bar(self):
        """In both themes, a figure over its bar is at least 4:1 against it:
        the white ink over the dark theme's orange was 1.8."""
        from PySide6.QtGui import QColor

        from silux.ui import tarjeta, theme
        from silux.ui.pages.disktest import TONES

        self.assertAlmostEqual(tarjeta.contrast(QColor("#ffffff"), QColor("#000000")), 21)
        for palette in (theme.DARK, theme.LIGHT):
            for direction, tone in TONES.items():
                bar = tarjeta._blend(palette.q("accent"), tone, palette.q("track"))
                with self.subTest(theme=palette.bg, direction=direction):
                    self.assertGreaterEqual(
                        tarjeta.contrast(tarjeta._readable_on(bar, palette), bar), 4)

    def test_its_title_is_the_disk(self):
        from silux.ui import tarjeta

        result = disk_run("970-evo-plus-ext4")
        self.assertEqual(tarjeta.disk_title(result), "Samsung SSD 970 EVO Plus 2TB")
        subtitle = tarjeta.disk_subtitle(result)
        self.assertTrue(subtitle.startswith(_("share.test.disk")))
        self.assertIn("ext4", subtitle)
        self.assertIn(_("disktest.profile.standard"), tarjeta.disk_notes(result)[0])

    def test_a_figure_that_varied_is_marked_and_said_once_at_the_foot(self):
        from silux.ui import tarjeta

        varied = disk_run("sn850x-btrfs")
        cells = dict(tarjeta.disk_cells(varied))
        self.assertTrue(cells["SEQ1M Q8T1"]["write"][0].endswith("*"))
        self.assertNotIn("*", cells["SEQ1M Q1T1"]["write"][0])
        footnote = f"* {_('share.test.varied')}"
        self.assertIn(footnote, tarjeta.disk_notes(varied))
        self.assertNotIn(footnote, tarjeta.disk_notes(disk_run("970-evo-plus-ext4")))

    def test_its_file_system_as_the_page_says_it(self):
        from silux.ui import tarjeta

        self.assertIn(_("disktest.conditions.nocow").format(filesystem="btrfs"),
                      tarjeta.disk_subtitle(disk_run("sn850x-btrfs")))

    def test_never_where_it_ran(self):
        result = dataclasses.replace(disk_run("970-evo-plus-ext4"), mountpoint=MOUNT, label=LABEL)
        self.assertNotIn("zoraida", disk_texts(result).lower())


class TestTheMemoryCard(Case):
    def test_its_figures_are_the_tests(self):
        from silux.ui import tarjeta

        result = memory_run("i5-10400-window")
        rows = tarjeta.memory_rows(result)
        text = "\n".join([tarjeta.memory_subtitle(result)] + [" ".join(row) for row in rows])
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
        for expected in (_("share.test.memory"), "2666 MT/s", share, "42.7 GB/s"):
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
                top = tarjeta.BODY_TOP + index * tarjeta.ALTO_FILA
                labels, values = [], []
                for y in range(top, top + tarjeta.ALTO_FILA):
                    for x in range(tarjeta.MARGEN, tarjeta.ANCHO - tarjeta.MARGEN):
                        pixel = image.pixelColor(x, y)
                        if near(pixel, accent):
                            labels.append(x)
                        elif near(pixel, ink):
                            values.append(x)
                with self.subTest(language=language, label=label):
                    self.assertTrue(labels and values)
                    self.assertLess(max(labels) + 4, min(values))


class TestTheLayout(Case):
    """The three cards, the machine's and the tests', alike."""

    def cards(self):
        from silux.ui import tarjeta, theme
        from tests.test_equipos import EQUIPOS, shared_snapshot

        palette = theme.DARK
        return palette, {
            "machine": tarjeta.dibujar(shared_snapshot(EQUIPOS / "i5-10400"), palette),
            "disk": tarjeta.draw_disk_test(disk_run("sn850x-btrfs"), palette),
            "memory": tarjeta.draw_memory_test(memory_run("i5-10400-window"), "Core i5-10400",
                                               palette)}

    def test_the_footer_is_the_version_and_where_silux_is(self):
        from silux import __version__
        from silux.ui import tarjeta

        self.assertEqual(tarjeta.footer_text(),
                         f"Silux {render.version(__version__)} · github.com/rcv11x/silux")

    def test_bands_stay_inside_the_margins_and_rows_are_one_height(self):
        """A band is as tall as a row and the plain row between two bands is
        too; nothing of them is drawn in the margins."""
        from PySide6.QtGui import QColor

        from silux.ui import tarjeta

        palette, cards = self.cards()
        band, background = QColor(palette.surface), QColor(palette.bg)
        for name, pixmap in cards.items():
            image = pixmap.toImage()
            with self.subTest(card=name):
                for x in (tarjeta.MARGEN - 1, tarjeta.ANCHO - tarjeta.MARGEN):
                    self.assertTrue(all(image.pixelColor(x, y) == background
                                        for y in range(image.height())))
                inside = tarjeta.MARGEN + 2
                runs, start = [], None
                for y in range(image.height() + 1):
                    banded = y < image.height() and image.pixelColor(inside, y) == band
                    if banded and start is None:
                        start = y
                    elif not banded and start is not None:
                        runs.append((start, y))
                        start = None
                self.assertGreaterEqual(len(runs), 2)
                self.assertEqual({end - begin for begin, end in runs}, {tarjeta.ALTO_FILA})
                self.assertEqual({b[0] - a[1] for a, b in zip(runs, runs[1:])},
                                 {tarjeta.ALTO_FILA})


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
