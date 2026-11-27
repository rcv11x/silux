"""A change made in Settings says «Setting saved» in the status bar for a
moment, and the next sample doesn't write over it."""

import unittest
from unittest import mock

from silux import settings as prefs_module
from silux.i18n import _
from tests import qt


def _window():
    from silux.settings import Preferences
    from silux.ui.app import MainWindow

    qt.app()
    window = MainWindow(Preferences(check_updates=False).normalized())
    window.resize(1200, 800)
    window.show()
    return window


class TestSettingSaved(unittest.TestCase):
    def setUp(self):
        from tests.test_equipos import EQUIPOS, shared_snapshot

        self.snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        self.window = _window()
        self.addCleanup(self.window.close)
        self.window._on_sample(self.snapshot)
        qt.app().processEvents()

    def test_said_for_two_seconds_and_not_written_over_by_a_sample(self):
        window = self.window
        window.select_section("Ajustes")
        window.settings_page.fluid_charts.click()
        self.assertEqual(window._status.full_text(), _("settings.saved"))
        self.assertTrue(window._status_message.isActive())
        self.assertEqual(window._status_message.interval(), 2000)
        window._on_sample(self.snapshot)
        self.assertEqual(window._status.full_text(), _("settings.saved"))
        # Then the hint again.
        window._status_message.stop()
        window._message_gone()
        self.assertEqual(window._status.full_text(), window._hint)

    def test_a_save_that_fails_says_so(self):
        with mock.patch.object(prefs_module, "save", return_value=False):
            self.window.settings_page.fluid_charts.click()
        self.assertEqual(self.window._status.full_text(), _("settings.notsaved"))

    def test_not_for_what_is_kept_without_asking(self):
        # Folding the sidebar is remembered, and is no setting changed.
        before = self.window._status.full_text()
        self.window.set_nav_folded(True)
        self.assertEqual(self.window._status.full_text(), before)


if __name__ == "__main__":
    unittest.main()
