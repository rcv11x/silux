"""Performance's processor tab on a wide screen: the table of earlier runs
across the card, its text at a comfortable width, and its row buttons as
every other button of Silux.

At 2560 px the table stayed narrow at the left, the description ran in one
line of two hundred characters, and Rename and Delete were larger than the
other buttons, Delete with a red border.
"""

import unittest

from silux import history, score
from tests import geometry, qt
from tests.test_historial_de_otra_escala import prueba


class TestWide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")

    def setUp(self):
        history.clear()
        self.addCleanup(history.clear)
        history.save([prueba(200, score.VERSION), prueba(100, score.VERSION)])
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.performance import PerformancePage

        self.page = PerformancePage(theme.palette_for(self.app, "dark"),
                                    Preferences().normalized())
        self.addCleanup(self.page.deleteLater)
        self.page.resize(2560, 1300)
        self.page.show()
        geometry.settle(self.app)

    def row_buttons(self):
        from silux.ui.pages.performance import RunMenu

        return self.page.history_card.findChildren(RunMenu)

    def test_the_table_goes_across_the_card(self):
        card = self.page.history_card
        buttons = self.row_buttons()
        self.assertTrue(buttons)
        right = max(b.mapTo(card, b.rect().topRight()).x() for b in buttons)
        self.assertGreater(right, card.width() * 0.8)

    def test_its_text_keeps_to_a_comfortable_width(self):
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtGui import QFontMetrics

        from silux.ui import theme
        from silux.ui.theme import ui_font

        character = QFontMetrics(ui_font(theme.METRICS.base_pt)).averageCharWidth()
        for label in (self.page.intro, self.page.history_note_text):
            with self.subTest(text=label.text()[:30]):
                self.assertTrue(label.isVisibleTo(self.page))
                self.assertLessEqual(label.width(), character * 110)
                # And whole: a layout gave it the height for the whole width,
                # and its last lines were cut.
                needed = label.fontMetrics().boundingRect(
                    QRect(0, 0, label.width(), 10 ** 6), Qt.TextFlag.TextWordWrap,
                    label.text()).height()
                self.assertGreaterEqual(label.height(), needed)

    def test_each_run_has_its_menu(self):
        self.assertTrue(self.row_buttons())
        for menu in self.row_buttons():
            self.assertEqual(menu.text(), "⋯")
            self.assertEqual(len(menu.menu().actions()), 2)


class TestNarrow(TestWide):
    def test_the_table_scrolls_on_its_own_and_the_page_stays_in_view(self):
        """At 480 px the table, five columns and its buttons, made the whole
        page wider than the window, its text cut at the right."""
        self.page.resize(440, 900)
        geometry.settle(self.app)
        self.assertLessEqual(self.page.widget().width(), self.page.viewport().width())
        buttons = self.row_buttons()
        self.assertTrue(buttons)


if __name__ == "__main__":
    unittest.main()
