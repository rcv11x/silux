"""«Enviar mi informe»: saved in the data folder, copied and Discord opened,
for the person to paste it there. Nothing is sent by itself. After an update
the sidebar asks once for that version's report, under a new version's
notice and above «Comunidad»; the welcome explains it with the same button."""

import os
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from silux import __version__
from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "no PySide6")
class TestSendReport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = foto(EQUIPOS / "5800x3d")[0]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.tmp / "config"),
                                             "XDG_DATA_HOME": str(self.tmp / "data")})
        patch.start()
        self.addCleanup(patch.stop)
        opened = mock.patch("silux.system_env.open_path", return_value=True)
        self.open_path = opened.start()
        self.addCleanup(opened.stop)

    def window(self, **prefs):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        window = MainWindow(Preferences(**prefs).normalized())
        self.addCleanup(window.deleteLater)
        window.show()
        window._on_sample(self.snapshot)
        self.app.processEvents()
        return window

    def preview(self, window):
        dialog = window._report_preview
        self.addCleanup(dialog.close)
        # Before the window goes: a QThread destroyed while it runs aborts.
        self.addCleanup(dialog.cancel_annex)
        return dialog

    def wait_for_the_annex(self, dialog):
        deadline = time.monotonic() + 90
        while dialog.annex_pending() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertFalse(dialog.annex_pending())

    # -- the button and what it does ------------------------------------------

    def test_saved_copied_and_discord_opened(self):
        from silux import history
        from silux.ui.pages.settings import COMMUNITY_URL
        window = self.window(welcome_shown=True, last_run_version="2026.11.20")
        window._note_this_version()
        window.settings_page.send_report_requested.emit()
        self.app.processEvents()
        dialog = self.preview(window)
        self.assertTrue(dialog.isVisible())
        # Seen first, and «Mandar» is what Enter presses.
        self.assertFalse(dialog.send_button.isEnabled())
        self.wait_for_the_annex(dialog)
        self.assertTrue(dialog.send_button.isDefault())
        with mock.patch("PySide6.QtWidgets.QMessageBox.information") as told:
            dialog.send_button.click()
        saved = list(history.reports_dir().glob("informe-silux-*.md"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(encoding="utf-8"), dialog.report())
        self.assertEqual(QApplication.clipboard().text(), dialog.report())
        self.open_path.assert_called_once_with(COMMUNITY_URL)
        self.assertIn("#silux-app-chat", told.call_args.args[2])
        # Sent, the sidebar stops asking.
        self.assertEqual(window.prefs.report_pending, "")
        self.assertFalse(window.report_notice.isVisibleTo(window.nav_panel))

    def test_seeing_it_isnt_sending_it(self):
        window = self.window()
        window.settings_page.report_requested.emit()
        self.app.processEvents()
        dialog = self.preview(window)
        self.assertFalse(dialog.sending)
        self.open_path.assert_not_called()

    def test_the_two_data_folders(self):
        from silux import history, settings
        from silux.ui.widgets import Button
        window = self.window()
        buttons = {b.text(): b for b in window.settings_page.findChildren(Button)}
        buttons[_("settings.data.button")].click()
        buttons[_("settings.data.config")].click()
        self.assertEqual([c.args[0] for c in self.open_path.call_args_list],
                         [str(history.data_dir()), str(settings.config_path().parent)])

    # -- the sidebar ----------------------------------------------------------

    def asks(self, window) -> bool:
        return window.report_notice.isVisibleTo(window.nav_panel)

    def test_after_an_update_it_asks_once(self):
        from silux import settings
        window = self.window(welcome_shown=True, last_run_version="2026.11.20")
        window._note_this_version()
        self.assertTrue(self.asks(window))
        window.report_dismiss.click()
        self.assertFalse(self.asks(window))
        # Opened again, the same version doesn't ask.
        again = self.window(**{f: getattr(settings.load(), f)
                               for f in ("welcome_shown", "last_run_version", "report_pending")})
        again._note_this_version()
        self.assertFalse(self.asks(again))
        self.assertEqual(again.prefs.last_run_version, __version__)

    def test_settings_from_before_it_was_kept_are_an_update(self):
        window = self.window(welcome_shown=True)
        window._note_this_version()
        self.assertTrue(self.asks(window))

    def test_the_first_run_doesnt_ask(self):
        window = self.window()
        window._note_this_version()
        self.assertFalse(self.asks(window))

    def test_a_new_version_comes_first(self):
        from silux import updates
        window = self.window(welcome_shown=True)
        window._note_this_version()
        window._version_nueva = updates.Release(
            version=(2099, 1, 1), tag="2099.1.1", url="https://example.invalid")
        window._pintar_version_nueva()
        self.assertTrue(window.update_button.isVisibleTo(window.nav_panel))
        self.assertFalse(self.asks(window))

    def test_community_opens_discord(self):
        from silux.ui.pages.settings import COMMUNITY_URL
        window = self.window()
        self.assertEqual(window.community_button.text(), _("sidebar.community"))
        window.community_button.click()
        self.open_path.assert_called_once_with(COMMUNITY_URL)

    def test_the_foot_in_order_and_apart_open_and_folded(self):
        window = self.window(welcome_shown=True)
        window._note_this_version()
        for folded in (False, True):
            with self.subTest(folded=folded):
                window.set_nav_folded(folded)
                self.app.processEvents()
                window.nav_panel.layout().activate()
                foot = [window.report_notice, window.community_button, window.version_label]
                shown = [w for w in foot if w.isVisibleTo(window.nav_panel)]
                self.assertEqual(shown[:2], [window.report_notice, window.community_button])
                tops = [w.geometry().top() for w in shown]
                self.assertEqual(tops, sorted(tops))
                for upper, lower in zip(shown, shown[1:]):
                    self.assertLessEqual(upper.geometry().bottom(), lower.geometry().top())
                for widget in shown:
                    self.assertLessEqual(widget.geometry().right(), window.nav_panel.width())
                    self.assertGreaterEqual(widget.geometry().left(), 0)
                self.assertEqual(window.report_icon.isVisibleTo(window.nav_panel), folded)
                self.assertEqual(window.report_ask.isVisibleTo(window.nav_panel), not folded)
                self.assertEqual(window.community_button.toolButtonStyle(),
                                 Qt.ToolButtonStyle.ToolButtonIconOnly if folded
                                 else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                self.assertTrue(window.community_button.toolTip())

    # -- the welcome ----------------------------------------------------------

    def test_from_the_welcome_over_it_and_then_over_the_window(self):
        window = self.window()
        welcome = window.show_welcome(page=1)
        self.app.processEvents()
        welcome.report_button.click()
        self.app.processEvents()
        dialog = self.preview(window)
        # A dialog of the window would wait for the welcome to close.
        self.assertIs(dialog.parentWidget(), welcome)
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.sending)
        welcome.start_button.click()
        self.app.processEvents()
        self.assertIs(dialog.parentWidget(), window)
        self.assertTrue(dialog.isVisible())

    def test_the_welcome_picks_the_accent_and_updates(self):
        window = self.window()
        welcome = window.show_welcome()
        self.app.processEvents()
        welcome.accent_box.setCurrentIndex(welcome.accent_box.findData("green"))
        self.app.processEvents()
        self.assertEqual(window.prefs.accent, "green")
        welcome = window._welcome
        self.assertTrue(welcome.updates_switch.isChecked())
        welcome.updates_switch.setChecked(False)
        self.app.processEvents()
        self.assertFalse(window.prefs.check_updates)
        window._welcome.reject()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
