"""The welcome of the first time.

Only the first time Silux opens, and again from Settings. What it changes
are preferences, applied as they are picked; it touches nothing of the
system unless the menu switch is on and «Start» pressed, and it asks for no
password.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from silux import i18n, settings
from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestOnlyTheFirstTime(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def test_no_preferences_yet_is_the_first_time(self):
        self.assertFalse(settings.load().welcome_shown)

    def test_preferences_from_before_the_welcome_are_not(self):
        settings.config_path().parent.mkdir(parents=True, exist_ok=True)
        settings.config_path().write_text(json.dumps({"theme": "dark"}))
        self.assertTrue(settings.load().welcome_shown)

    def test_once_seen_it_stays_seen(self):
        import dataclasses
        settings.save(dataclasses.replace(settings.load(), welcome_shown=True))
        self.assertTrue(settings.load().welcome_shown)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestTheDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = foto(EQUIPOS / "i5-10400")[0]

    def setUp(self):
        from silux.ui.app import MainWindow

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(i18n.set_language, i18n.current() if hasattr(i18n, "current") else "es")
        i18n.set_language("es")
        prefs = settings.Preferences(language="es").normalized()
        self.window = MainWindow(prefs)
        self.window.show()
        self.addCleanup(self.window.close)
        self.window._on_sample(self.photo)

    def _settle(self, ms: int = 0):
        if ms:
            QTest.qWait(ms)
        for _turn in range(4):
            self.app.processEvents()

    def _texts(self, dialog):
        return [w.text() for w in dialog.findChildren(QLabel) if w.text()]

    def test_it_opens_on_the_first_start_and_not_after(self):
        with mock.patch.object(self.window.sampler, "start"):
            self.window.start()
            self._settle(400)
            self.assertIsNotNone(self.window._welcome)
            self.window._welcome.reject()
            self._settle()
            self.assertTrue(settings.load().welcome_shown)
            self.window.start()
            self._settle(400)
        self.assertIsNone(self.window._welcome)

    def test_skipping_touches_nothing_of_the_system(self):
        dialog = self.window.show_welcome()
        with mock.patch("silux.desktop.set_shortcuts") as written, \
                mock.patch.object(self.window.settings_page, "add_to_menu") as menu:
            dialog.skip_button.click()
            self._settle()
        written.assert_not_called()
        menu.assert_not_called()
        self.assertTrue(settings.load().welcome_shown)

    def test_start_with_the_menu_switch_adds_it(self):
        with mock.patch("silux.ui.welcome.can_add_to_menu", return_value=True):
            dialog = self.window.show_welcome(page=1)
        self.assertIsNotNone(dialog.menu_switch)
        with mock.patch.object(self.window.settings_page, "add_to_menu") as menu:
            dialog.menu_switch.setChecked(True)
            dialog.start_button.click()
            self._settle()
        menu.assert_called_once_with()

    def test_start_without_it_adds_nothing(self):
        with mock.patch("silux.ui.welcome.can_add_to_menu", return_value=True):
            dialog = self.window.show_welcome(page=1)
        with mock.patch.object(self.window.settings_page, "add_to_menu") as menu:
            dialog.start_button.click()
            self._settle()
        menu.assert_not_called()

    def test_no_menu_row_where_there_is_nothing_to_add(self):
        with mock.patch("silux.ui.welcome.can_add_to_menu", return_value=False):
            dialog = self.window.show_welcome(page=1)
        self.assertIsNone(dialog.menu_switch)
        self.assertNotIn(_("welcome.menu"), self._texts(dialog))
        dialog.reject()

    def test_a_choice_applies_at_once_and_speaks_its_language(self):
        dialog = self.window.show_welcome()
        dialog.language_box.setCurrentIndex(dialog.language_box.findData("en"))
        self._settle()
        self.assertEqual(self.window.prefs.language, "en")
        dialog = self.window._welcome
        self.assertIn("Welcome to Silux", self._texts(dialog))
        self.assertNotIn("Te damos la bienvenida a Silux", self._texts(dialog))
        dialog.theme_box.setCurrentIndex(dialog.theme_box.findData("dark"))
        self._settle()
        self.assertEqual(self.window.prefs.theme, "dark")
        dialog = self.window._welcome
        self.assertEqual(dialog.theme_box.currentData(), "dark")
        dialog.reject()
        self._settle()
        i18n.set_language("es")

    def test_each_screen_as_tall_as_what_it_holds(self):
        dialog = self.window.show_welcome(page=1)
        self._settle()
        second = dialog.height()
        dialog.back_button.click()
        self._settle()
        first = dialog.height()
        self.assertLess(first, second)
        dialog.next_button.click()
        self._settle()
        self.assertEqual(dialog.height(), second)
        dialog.reject()
        self._settle()
        dialog = self.window.show_welcome(page=0)
        self._settle()
        self.assertEqual(dialog.height(), first)
        dialog.reject()

    def test_the_explanations_follow_the_text_size(self):
        from silux.ui import theme

        dialog = self.window.show_welcome()
        dialog.font_box.setCurrentIndex(dialog.font_box.findData("large"))
        self._settle()
        dialog = self.window._welcome
        for page in (0, 1):
            dialog._go(page)
            muted = [w for w in dialog.findChildren(QLabel)
                     if w.objectName() == "Muted" and w.isVisible()]
            self.assertTrue(muted)
            for label in muted:
                self.assertEqual(label.font().pointSize(), theme.METRICS.base_pt,
                                 label.text())
        dialog.reject()

    def test_its_own_corners_only_where_a_compositor_draws_them(self):
        from PySide6.QtCore import Qt

        from silux.ui import welcome

        frameless = Qt.WindowType.FramelessWindowHint
        dialog = self.window.show_welcome()
        self.assertTrue(dialog.windowFlags() & frameless)
        dialog.reject()
        self._settle()
        with mock.patch.object(welcome.QGuiApplication, "platformName", return_value="xcb"):
            dialog = self.window.show_welcome()
        self.assertFalse(dialog.windowFlags() & frameless)
        dialog.reject()

    def test_settings_opens_it_again(self):
        self.window.settings_page.welcome_button.click()
        self._settle()
        self.assertIsNotNone(self.window._welcome)
        self.window._welcome.reject()


if __name__ == "__main__":
    unittest.main()
