"""Storage's tiles, one drive at a time: chosen in the tiles' box or by its
row in «Drives», with its own history since Silux opened, and remembered.

The dump has two drives of the same model and a third: the two alike are
told apart by their names, the third by its model and size.
"""

import dataclasses
import unittest

from silux.i18n import _
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

DUMP = "ryzen5-9600x"


def with_rates(snapshot, rates: dict):
    """The same machine, its drives moving `rates` (name -> read, write)."""
    disks = tuple(
        dataclasses.replace(d, io=dataclasses.replace(
            d.io, read_rate_bps=rates.get(d.name, (0.0, 0.0))[0],
            write_rate_bps=rates.get(d.name, (0.0, 0.0))[1]))
        for d in snapshot.disks)
    return dataclasses.replace(snapshot, disks=disks)


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / DUMP)

    def window(self):
        ventana = pantalla.Ventana(self.snapshot)
        window = ventana.__enter__()
        self.addCleanup(ventana.__exit__, None, None, None)
        window.resize(1400, 900)
        geometry.settle(self.app)
        return window

    def page(self, window):
        window.select_section("Almacenamiento")
        geometry.settle(self.app)
        return window.storage_page

    def key(self, page, name):
        from silux.ui.pages.storage import disk_choice_key

        disk = next(d for d in page._discos if d.name == name)
        return disk_choice_key(disk, page._discos)


class TestTheKey(Case):
    def test_model_and_size_and_the_name_only_between_two_alike(self):
        from silux.ui.pages.storage import disk_choice_key

        disks = self.snapshot.disks
        keys = {d.name: disk_choice_key(d, disks) for d in disks}
        self.assertEqual(keys["sda"], "SanDisk SSD PLUS 1000GB|1000204886016")
        self.assertEqual(keys["nvme0n1"], "KINGSTON SNV3S500G|500107862016|nvme0n1")
        self.assertNotEqual(keys["nvme0n1"], keys["nvme1n1"])


class TestChoosing(Case):
    def test_the_box_shows_one_drive_in_the_tiles(self):
        from silux import render

        window = self.window()
        page = self.page(window)
        window._on_sample(with_rates(self.snapshot, {"nvme1n1": (5e6, 2e6), "sda": (1e6, 0)}))
        geometry.settle(self.app)
        box = page.choice_box
        box.setCurrentIndex(box.findData(self.key(page, "nvme1n1")))
        box.activated.emit(box.currentIndex())
        geometry.settle(self.app)
        self.assertEqual(page.tile_read.value.text(), render.rate(5e6))
        self.assertEqual(page.tile_write.value.text(), render.rate(2e6))
        self.assertEqual(page.tile_read.chart.series.key, "disk:nvme1n1/read")
        self.assertIn("nvme1n1", page.choice_box.currentText())
        self.assertEqual(page.tile_temp.caption.text(), _("storage.tile.temperature"))

    def test_a_row_chooses_its_drive_and_again_every_drive(self):
        from silux.ui.pages.storage import ALL_DISKS

        window = self.window()
        page = self.page(window)
        row = next(i for i, d in enumerate(page._discos) if d.name == "sda")
        page.disks.row_picked.emit(row)
        geometry.settle(self.app)
        self.assertEqual(page._chosen, self.key(page, "sda"))
        self.assertEqual(page.disks.picked, row)
        self.assertEqual(page.choice_box.currentData(), self.key(page, "sda"))
        page.disks.row_picked.emit(row)
        geometry.settle(self.app)
        self.assertEqual(page._chosen, ALL_DISKS)
        self.assertIsNone(page.disks.picked)
        self.assertEqual(page.tile_temp.caption.text(), _("storage.tile.hottest"))


class TestOneList(Case):
    def test_a_single_list_above_the_tiles(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QComboBox

        window = self.window()
        page = self.page(window)
        boxes = [b for b in page.findChildren(QComboBox) if b.isVisibleTo(page)]
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        below = box.mapTo(page, QPoint(0, box.height())).y()
        for tile in (page.tile_read, page.tile_write, page.tile_free, page.tile_temp):
            with self.subTest(tile=tile.caption.text()):
                self.assertLessEqual(below, tile.mapTo(page, QPoint(0, 0)).y())


class TestItsHistory(Case):
    def test_chosen_later_it_draws_what_it_did_since_silux_opened(self):
        window = self.window()
        for second in range(6):
            window._on_sample(with_rates(self.snapshot, {"nvme0n1": (second * 1e6, 0)}))
        page = self.page(window)
        page.choose(self.key(page, "nvme0n1"))
        geometry.settle(self.app)
        chart = page.tile_read.chart
        self.assertEqual(chart.series.key, "disk:nvme0n1/read")
        # Every sample since the window opened, its own figures.
        self.assertGreaterEqual(chart.points, 6)
        self.assertEqual(chart._values[-1], 5e6)

    def test_every_drive_again_draws_the_sum_it_kept(self):
        from silux.ui.pages.storage import ALL_DISKS

        window = self.window()
        page = self.page(window)
        page.choose(self.key(page, "sda"))
        for second in range(4):
            window._on_sample(with_rates(self.snapshot, {"sda": (1e6, 0), "nvme0n1": (2e6, 0)}))
        page.choose(ALL_DISKS)
        geometry.settle(self.app)
        self.assertEqual(page.tile_read.chart.series.key, "disks/read")
        self.assertEqual(page.tile_read.chart._values[-1], 3e6)


class TestRemembered(Case):
    def test_the_window_keeps_it_and_opens_with_it(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        window = self.window()
        page = self.page(window)
        key = self.key(page, "nvme1n1")
        page.choose(key)
        self.assertEqual(window.prefs.storage_disk, key)
        again = MainWindow(Preferences(storage_disk=key).normalized())
        self.addCleanup(again.close)
        again.show()
        again._on_sample(self.snapshot)
        again.select_section("Almacenamiento")
        geometry.settle(self.app)
        self.assertEqual(again.storage_page.choice_box.currentData(), key)
        self.assertEqual(again.storage_page.tile_read.chart.series.key, "disk:nvme1n1/read")


class TestGone(Case):
    def test_a_drive_that_goes_while_shown_brings_back_every_drive_and_says_so(self):
        from silux.ui.pages.storage import ALL_DISKS

        window = self.window()
        page = self.page(window)
        page.choose(self.key(page, "sda"))
        without = dataclasses.replace(
            self.snapshot, disks=tuple(d for d in self.snapshot.disks if d.name != "sda"))
        window._on_sample(without)
        geometry.settle(self.app)
        self.assertEqual(page._chosen, ALL_DISKS)
        self.assertTrue(page.chosen_gone.isVisibleTo(page))
        self.assertIn("sda", page.chosen_gone.text())
        self.assertEqual(page.tile_read.chart.series.key, "disks/read")


class TestNarrow(Case):
    def test_with_a_drive_chosen_the_page_stays_in_its_view(self):
        window = self.window()
        page = self.page(window)
        page.choose(self.key(page, "nvme1n1"))
        window.resize(480, 900)
        geometry.settle(self.app)
        self.assertLessEqual(page.widget().width(), page.viewport().width())


if __name__ == "__main__":
    unittest.main()
