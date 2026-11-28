"""In a low window the sidebar's rows draw closer instead of the section list
scrolling, and the report's question at its foot takes one line. In three
lines it pushed the sections off a 760 px window, and even without it the
list scrolled below 712 px."""

import tempfile
import unittest
from unittest import mock

from silux import __version__
from tests import qt

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheSidebarFits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": folder.name})
        patch.start()
        self.addCleanup(patch.stop)

    def window(self, height, asking=True):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.app import MainWindow
        prefs = Preferences(welcome_shown=True, last_run_version=__version__,
                            report_pending=__version__ if asking else "").normalized()
        theme.apply(self.app, prefs.theme, prefs.density, prefs.font_scale)
        window = MainWindow(prefs)
        self.addCleanup(window.deleteLater)
        window.show()
        window.resize(1000, height)
        for _turn in range(3):
            self.app.processEvents()
        return window

    def test_the_question_takes_one_line(self):
        window = self.window(900)
        label = window.report_ask.label
        self.assertTrue(window.report_notice.isVisibleTo(window.nav_panel))
        self.assertLess(label.height(), 2 * label.fontMetrics().height())
        # Its × is inside it, not beside it.
        self.assertIs(window.report_dismiss.parentWidget(), window.report_ask)

    def test_a_low_window_draws_the_rows_closer_and_nothing_scrolls(self):
        window = self.window(640)
        self.assertTrue(window.report_notice.isVisibleTo(window.nav_panel))
        self.assertEqual(window.nav.verticalScrollBar().maximum(), 0)
        self.assertIsNotNone(window.nav.itemDelegate().row_cap)
        # Every section still shows whole, its text and icon.
        nav = window.nav
        for row in range(nav.count()):
            item = nav.item(row)
            if item.isHidden():
                continue
            with self.subTest(section=item.text()):
                rect = nav.visualItemRect(item)
                self.assertGreaterEqual(rect.height(), nav.fontMetrics().height())
                self.assertGreaterEqual(rect.height(), nav.iconSize().height())
                self.assertLessEqual(rect.bottom(), nav.viewport().height())

    def test_a_tall_window_keeps_their_own_height(self):
        window = self.window(1000)
        self.assertIsNone(window.nav.itemDelegate().row_cap)
        self.assertEqual(window.nav.verticalScrollBar().maximum(), 0)

    def test_back_to_their_height_when_the_window_grows(self):
        window = self.window(640)
        self.assertIsNotNone(window.nav.itemDelegate().row_cap)
        window.resize(1000, 1000)
        for _turn in range(3):
            self.app.processEvents()
        self.assertIsNone(window.nav.itemDelegate().row_cap)


if __name__ == "__main__":
    unittest.main()
