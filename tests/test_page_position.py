"""A page stays where the user left it.

A button that disables itself while it has the focus («Buscar ahora», «Dar
permisos», «Quitar») made Qt hand the focus on, and the page scrolled to
wherever it landed: in Settings, from the updates card to the bottom.
"""

import os
import tempfile
import unittest
from unittest import mock

from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestButtonsDoNotMoveThePage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = foto(EQUIPOS / "i5-10400")[0]

    def setUp(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.window = MainWindow(Preferences().normalized())
        self.window.resize(1000, 700)
        self.window.show()
        self.addCleanup(self.window.close)
        self.window._on_sample(self.photo)

    def _settle(self):
        for _turn in range(4):
            self.app.processEvents()

    def _bring(self, page, widget):
        """Scrolls until the widget is in the middle of the page, if it can."""
        page.ensureWidgetVisible(widget, 0, page.viewport().height() // 2)
        self._settle()

    def test_a_button_that_disables_itself_keeps_the_page_still(self):
        from silux.ui import app as appmod

        tried = 0
        for key, active in appmod.SECTIONS:
            if not active or not self.window.select_section(key):
                continue
            self._settle()
            page = self.window.stack.currentWidget()
            bar = page.verticalScrollBar()
            for button in page.findChildren(QPushButton):
                if not (button.isVisibleTo(self.window) and button.isEnabled()):
                    continue
                with self.subTest(page=key, button=button.text()):
                    self._bring(page, button)
                    before = bar.value()
                    # What clicking it does: the window becomes the active one
                    # (pages an earlier test left open can have taken that),
                    # and the button takes the focus.
                    self.window.activateWindow()
                    self._settle()
                    button.setFocus()
                    self._settle()
                    if not button.hasFocus():
                        continue
                    button.setEnabled(False)
                    self._settle()
                    self.assertEqual(bar.value(), before)
                    button.setEnabled(True)
                    tried += 1
        self.assertGreater(tried, 10)

    def test_search_now_and_its_answer(self):
        self.window.select_section("Ajustes")
        self._settle()
        page = self.window.settings_page
        bar = page.verticalScrollBar()
        self._bring(page, page.update_now)
        before = bar.value()
        self.assertGreater(before, 0, "the page must be scrolled for this to mean anything")
        with mock.patch.object(type(self.window), "_lanzar"):
            QTest.mouseClick(page.update_now, Qt.MouseButton.LeftButton)
            self._settle()
            self.assertFalse(page.update_now.isEnabled())
            self.assertEqual(bar.value(), before)
            page.set_update_status("Ninguna versión más nueva.")
            self._settle()
        self.assertEqual(bar.value(), before)


if __name__ == "__main__":
    unittest.main()
