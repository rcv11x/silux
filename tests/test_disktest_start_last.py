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


if __name__ == "__main__":
    unittest.main()
