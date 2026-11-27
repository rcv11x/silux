"""The sidebar folds to its icons with a button, names each section when the
pointer is over it, and stays as it was left. A narrow window still swaps it
for the selector in the status bar."""

import unittest

from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-10400")

    def window(self, width: int = 1100):
        ventana = pantalla.Ventana(self.snapshot)
        window = ventana.__enter__()
        self.addCleanup(ventana.__exit__, None, None, None)
        window.resize(width, 760)
        geometry.settle(self.app)
        return window

    def fold(self, window) -> None:
        window.nav_toggle.click()
        geometry.settle(self.app)


class TestFolding(Case):
    def test_the_button_leaves_only_the_icons(self):
        window = self.window()
        open_width = window.nav_panel.width()
        names = window.section_names()
        self.fold(window)
        icon = window.nav.iconSize().width()
        self.assertLess(window.nav_panel.width(), icon * 4)
        self.assertLess(window.nav_panel.width(), open_width / 2)
        for row in range(window.nav.count()):
            item = window.nav.item(row)
            # Each one fits whole: no name cut to «Alm…».
            self.assertLessEqual(window.nav.visualItemRect(item).width(),
                                 window.nav.viewport().width())
        self.assertFalse(window.wordmark.isVisibleTo(window))
        self.assertEqual(window.section_names(), names)
        self.fold(window)
        self.assertEqual(window.nav_panel.width(), open_width)
        self.assertTrue(window.wordmark.isVisibleTo(window))

    def test_folded_each_icon_says_its_name(self):
        window = self.window()
        self.fold(window)
        for row in range(window.nav.count()):
            item = window.nav.item(row)
            if item.flags() & item.flags().ItemIsEnabled:
                self.assertEqual(item.toolTip(), item.text())
        self.fold(window)
        for row in range(window.nav.count()):
            item = window.nav.item(row)
            if item.flags() & item.flags().ItemIsEnabled:
                self.assertEqual(item.toolTip(), "")

    def test_sections_still_open_by_name(self):
        window = self.window()
        self.fold(window)
        self.assertTrue(window.select_section("Sensores"))
        self.assertIs(window.stack.currentWidget(), window.monitor_page)


class TestTheButton(Case):
    def test_it_sits_up_by_the_mark_open_or_folded(self):
        window = self.window()
        for _state in ("open", "folded"):
            toggle = window.nav_toggle.mapTo(window, window.nav_toggle.rect().bottomLeft())
            first = window.nav.mapTo(window, window.nav.rect().topLeft())
            with self.subTest(state=_state):
                self.assertTrue(window.nav_toggle.isVisibleTo(window))
                self.assertLess(toggle.y(), first.y())
                self.assertLessEqual(window.nav_toggle.width() + 1, window.nav_panel.width())
            self.fold(window)


class TestRemembered(Case):
    def test_it_starts_as_it_was_left(self):
        from silux import settings
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        window = self.window()
        self.fold(window)
        self.assertTrue(window.prefs.nav_folded)
        window.close()
        self.assertTrue(settings.load().nav_folded)
        again = MainWindow(Preferences(nav_folded=True).normalized())
        self.addCleanup(again.deleteLater)
        again.resize(1100, 760)
        again.show()
        geometry.settle(self.app)
        self.assertLess(again.nav_panel.width(), again.nav.iconSize().width() * 4)

    def test_a_theme_change_keeps_it_folded(self):
        window = self.window()
        self.fold(window)
        width = window.nav_panel.width()
        window._build_ui()
        geometry.settle(self.app)
        self.assertEqual(window.nav_panel.width(), width)


class TestNarrow(Case):
    def test_a_narrow_window_still_uses_the_selector(self):
        window = self.window()
        self.fold(window)
        window.resize(480, 760)
        geometry.settle(self.app)
        self.assertFalse(window.nav_panel.isVisible())
        self.assertTrue(window._compact_nav.isVisible())
        index = window._compact_nav.findText(window.nav.item(2).text())
        window._compact_nav.setCurrentIndex(index)
        geometry.settle(self.app)
        self.assertEqual(window.nav.currentRow(), 2)
        window.resize(1100, 760)
        geometry.settle(self.app)
        self.assertTrue(window.nav_panel.isVisible())
        self.assertLess(window.nav_panel.width(), window.nav.iconSize().width() * 4)


if __name__ == "__main__":
    unittest.main()
