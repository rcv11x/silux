"""«Start» comes after every choice of the disk test, in reading order, at
any width: at 480 px with the custom profile, the pattern, block and queue
went under it."""

import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QComboBox

from silux import disktest
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestStartLast(unittest.TestCase):
    def test_after_every_choice_at_any_width(self):
        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Rendimiento")
            page = window.benchmarks_page
            page.select_tab("disk")
            tab = page.disk_tab
            box = tab.profile_box
            for width in (1400, 480):
                for profile in (disktest.CUSTOM, "standard"):
                    window.resize(width, 900)
                    box.setCurrentIndex(box.findData(profile))
                    box.activated.emit(box.currentIndex())
                    geometry.settle(app, 8)
                    start = tab.run_button.mapTo(window, QPoint(0, 0))
                    for choice in tab.findChildren(QComboBox):
                        if not choice.isVisibleTo(window):
                            continue
                        where = choice.mapTo(window, QPoint(0, 0))
                        with self.subTest(width=width, profile=profile,
                                          choice=choice.currentText()):
                            # Lower down, or on the same line further right.
                            self.assertTrue(
                                start.y() >= where.y() + choice.height()
                                or (abs(start.y() - where.y()) < choice.height()
                                    and start.x() > where.x()),
                                f"«Start» at {start.x()},{start.y()}; "
                                f"the choice at {where.x()},{where.y()}")


class TestChoicesInAColumn(unittest.TestCase):
    """At 480 px each list started right after its own caption, «Cola» and
    «Archivo» at different places: in a column they start at the same one.
    In a row, each caption keeps its own width."""

    def test_aligned_when_folded_and_not_padded_in_a_row(self):
        app = qt.app()
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.select_section("Rendimiento")
            page = window.benchmarks_page
            page.select_tab("disk")
            tab = page.disk_tab
            box = tab.profile_box
            box.setCurrentIndex(box.findData(disktest.CUSTOM))
            box.activated.emit(box.currentIndex())
            window.resize(480, 900)
            geometry.settle(app, 8)
            starts = {choice.currentText(): choice.mapTo(window, QPoint(0, 0)).x()
                      for choice in tab.findChildren(QComboBox) if choice.isVisibleTo(window)}
            self.assertGreaterEqual(len(starts), 6)
            self.assertEqual(len(set(starts.values())), 1, starts)
            window.resize(1600, 900)
            geometry.settle(app, 8)
            self.assertFalse(tab.options.folded)
            for caption in tab.captions:
                self.assertEqual(caption.minimumWidth(), 0, caption.text())


if __name__ == "__main__":
    unittest.main()
