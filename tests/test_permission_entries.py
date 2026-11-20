"""Without the helper installed, every way of asking for permissions warns first.

«Qué pasa al dar permisos» tells what the password window will show before it
shows it, so it has to open from every place that asks: the notice in Home,
the padlocks, the buttons in Memory, Storage and Settings, the status bar,
the notices with a button and the report preview. None of them may start
the request on its own.
"""

import os
import tempfile
import unittest
from unittest import mock

from silux.i18n import _
from tests import qt
from tests.test_equipos import foto, volcados

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEveryEntryWarnsFirst(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photos = {carpeta.name: foto(carpeta)[0] for carpeta in volcados()}

    def setUp(self):
        from silux.privileged.client import PrivilegedClient

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patch in (mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name}),
                      mock.patch.object(PrivilegedClient, "instalado", return_value=False),
                      mock.patch.object(PrivilegedClient, "al_dia", return_value=False)):
            patch.start()
            self.addCleanup(patch.stop)

    def _window(self, photo):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        window = MainWindow(Preferences().normalized())
        window.show()
        self.addCleanup(window.close)
        window._on_sample(photo)
        return window

    def _settle(self):
        for _turn in range(4):
            self.app.processEvents()

    def _entries(self, window) -> list[tuple[str, str, object]]:
        """(where, section, widget) for everything visible that asks."""
        from silux.ui import app as appmod
        from silux.ui.widgets import LockMark, Notice

        entries = [("Home notice", "Inicio", window.home_page.permission_notice.grant_button),
                   ("status bar", "Inicio", window._blocked),
                   ("Memory button", "Memoria", window.memory_page.elevation_button),
                   ("Storage button", "Almacenamiento", window.storage_page.elevation_button),
                   ("Settings button", "Ajustes", window.settings_page.permission_button)]
        for key, active in appmod.SECTIONS:
            if not active or not window.select_section(key):
                continue
            self._settle()
            page = window.stack.currentWidget()
            entries += [(f"padlock in {key}", key, lock) for lock in page.findChildren(LockMark)
                        if getattr(lock, "_pulsable", False) and lock.isVisibleTo(window)]
            # Loading a sensor driver is not asking for permissions to read:
            # it changes the system, and has its own warning (test_module_load).
            entries += [(f"notice in {key}", key, notice.action_button)
                        for notice in page.findChildren(Notice)
                        if notice.action_button is not None
                        and notice.action_button.isVisibleTo(window)
                        and notice.action_button.text() != _("sensors.driver.button")]
        window._on_report_requested()
        self.addCleanup(window._report_preview.close)
        entries.append(("report preview", None, window._report_preview.grant_button))
        return entries

    def test_every_entry_opens_the_warning_and_asks_nothing(self):
        from silux.ui.widgets import LockMark

        for name, photo in self.photos.items():
            window = self._window(photo)
            entries = self._entries(window)
            self.assertTrue([e for e in entries if e[0].startswith("padlock")],
                            f"{name}: no padlock to click")
            with mock.patch.object(window.sampler, "request_elevation") as ask:
                for where, section, widget in entries:
                    ask.reset_mock()
                    with self.subTest(machine=name, entry=where):
                        if section is not None:
                            window.select_section(section)
                            self._settle()
                        self.assertTrue(widget.isVisibleTo(window), f"{where} is not shown")
                        before = getattr(window, "_dialogo_permisos", None)
                        if isinstance(widget, LockMark):
                            QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
                        else:
                            widget.click()
                        dialog = getattr(window, "_dialogo_permisos", None)
                        self.assertIsNot(dialog, before, f"{where} opened no warning")
                        self.assertTrue(dialog.isVisible())
                        ask.assert_not_called()
                        dialog.close()

    def test_after_asking_and_cancelling_from_home_they_still_warn(self):
        """The sequence of the 20th: Home, «Dar permisos esta vez», «Cancelar»
        in the password window; then CPU and Memory must warn again."""
        from silux.ui.widgets import LockMark

        photo = self.photos["i5-10400"]
        window = self._window(photo)
        with mock.patch.object(window.sampler, "request_elevation") as ask:
            window.home_page.permission_notice.grant_button.click()
            window._dialogo_permisos.grant_button.click()
            ask.assert_called_once()
            # The window was cancelled: the next sample is the same, still locked.
            window._on_sample(photo)
            self._settle()
            for where, section, widget in self._entries(window):
                ask.reset_mock()
                with self.subTest(entry=where):
                    if section is not None:
                        window.select_section(section)
                        self._settle()
                    before = window._dialogo_permisos
                    if isinstance(widget, LockMark):
                        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
                    else:
                        widget.click()
                    self.assertIsNot(window._dialogo_permisos, before, f"{where} opened no warning")
                    self.assertTrue(window._dialogo_permisos.isVisible())
                    ask.assert_not_called()
                    window._dialogo_permisos.close()


if __name__ == "__main__":
    unittest.main()
