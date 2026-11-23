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
        # With the app's stylesheet, as it runs: without it the first screen
        # came out shorter than the second, and the test said so; with it,
        # the first is the taller, and the order of the suite decided which.
        # What holds either way: the dialog asks for the screen on show, not
        # for the tallest, and is never shorter than it.
        from PySide6.QtGui import QPalette

        from silux.ui import theme

        saved = (theme.METRICS, self.app.styleSheet(), QPalette(self.app.palette()),
                 self.app.style().name())

        def restore():
            theme.METRICS = saved[0]
            self.app.setStyle(saved[3])
            self.app.setPalette(saved[2])
            self.app.setStyleSheet(saved[1])

        self.addCleanup(restore)
        prefs = settings.Preferences(language="es").normalized()
        theme.apply(self.app, prefs.theme, prefs.density, prefs.font_scale)

        needs = {}
        for page in (0, 1):
            dialog = self.window.show_welcome(page=page)
            self._settle()
            needs[page] = dialog.minimumSizeHint().height()
            dialog.reject()
            self._settle()
        self.assertNotEqual(needs[0], needs[1])
        dialog = self.window.show_welcome(page=1)
        for button, page in ((dialog.back_button, 0), (dialog.next_button, 1)):
            button.click()
            self._settle()
            self.assertEqual(dialog.minimumSizeHint().height(), needs[page])
            self.assertGreaterEqual(dialog.height(), needs[page])
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

    def test_a_dialog_of_the_window_with_its_title_bar(self):
        # Frameless, on Wayland it came out in a corner of a large window:
        # as the window's modal child, the compositor centres it over it.
        from PySide6.QtCore import Qt

        dialog = self.window.show_welcome()
        self._settle()
        self.assertIs(dialog.parentWidget(), self.window)
        self.assertIs(dialog.windowHandle().transientParent(), self.window.windowHandle())
        self.assertEqual(dialog.windowType(), Qt.WindowType.Dialog)
        self.assertFalse(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertFalse(dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertEqual(dialog.windowModality(), Qt.WindowModality.WindowModal)
        self.assertTrue(dialog.windowTitle())
        dialog.reject()

    def test_closing_it_from_its_bar_counts_as_seen(self):
        dialog = self.window.show_welcome()
        dialog.close()
        self._settle()
        self.assertIsNone(self.window._welcome)
        self.assertTrue(self.window.prefs.welcome_shown)

    def test_settings_opens_it_again(self):
        self.window.settings_page.welcome_button.click()
        self._settle()
        self.assertIsNotNone(self.window._welcome)
        self.window._welcome.reject()


if __name__ == "__main__":
    unittest.main()
