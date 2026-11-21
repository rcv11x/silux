"""An installed helper from an earlier version says so, everywhere.

It is not used (the client only uses the installed helper when it is this
version's), so what brings the data back is updating it, not giving
permissions. It was only said in Settings: Home, the notices and the
padlocks offered to give permissions as if it were not installed.
"""

import os
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.collector import Collector
from silux.i18n import _
from silux.privileged.client import PrivilegedClient
from tests import qt
from tests.test_equipos import EQUIPOS
from tests.test_volcar_equipo import _herramienta

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _photo(outdated: bool):
    """The collector for real on the i5-10400, with the installed helper old or not."""
    with mock.patch.object(PrivilegedClient, "necesita_reinstalar", return_value=outdated), \
         mock.patch("silux.providers.privileged_memory.already_root", return_value=False), \
         mock.patch.object(PrivilegedClient, "supported", return_value=True), \
         _herramienta().mounted(EQUIPOS / "i5-10400"):
        collector = Collector()
        try:
            collector.snapshot()
            return collector.snapshot()
        finally:
            collector.close()


class TestTheSnapshotSaysIt(unittest.TestCase):

    def test_every_permission_note_says_update_the_helper(self):
        photo = _photo(outdated=True)
        self.assertTrue(photo.privileged.outdated)
        self.assertTrue(photo.permission_notes)
        for note in photo.permission_notes:
            with self.subTest(note=note.path):
                self.assertTrue(note.helper_outdated)
                self.assertEqual(note.message, _("perm.outdated.body"))
                self.assertIn(_("lock.tip.outdated"), render.lock_tooltip(note))

    def test_with_this_versions_helper_nothing_changes(self):
        photo = _photo(outdated=False)
        self.assertFalse(photo.privileged.outdated)
        self.assertFalse([n for n in photo.permission_notes if n.helper_outdated])


@unittest.skipIf(QApplication is None, "no PySide6")
class TestInTheWindow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = _photo(outdated=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def _window(self, dismissed: bool = False):
        import dataclasses
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        prefs = dataclasses.replace(Preferences(), permission_notice_dismissed=dismissed)
        window = MainWindow(prefs.normalized())
        window.show()
        self.addCleanup(window.close)
        window._on_sample(self.photo)
        for _turn in range(4):
            self.app.processEvents()
        return window

    def test_home_says_it_with_update_and_not_now(self):
        notice = self._window().home_page.permission_notice
        self.assertTrue(notice.isVisible())
        self.assertEqual(notice.title.text(), _("perm.outdated.home"))
        self.assertEqual(notice.grant_button.text(), _("perm.replace.button"))
        self.assertTrue(notice.snooze_button.isVisible())
        self.assertFalse(notice.explain_button.isVisible())
        self.assertFalse(notice.dismiss_button.isVisible())

    def test_the_status_bar_too(self):
        self.assertEqual(self._window()._blocked.text(), _("status.blocked.outdated"))

    def test_even_if_the_permissions_notice_was_put_away_for_good(self):
        notice = self._window(dismissed=True).home_page.permission_notice
        self.assertTrue(notice.isVisible())
        self.assertEqual(notice.title.text(), _("perm.outdated.home"))

    def test_every_entry_updates_the_helper_and_asks_nothing_else(self):
        from tests.test_permission_entries import TestEveryEntryWarnsFirst
        from silux.ui.widgets import LockMark

        window = self._window()
        entries = TestEveryEntryWarnsFirst._entries(self, window)
        cpu = [w for where, _s, w in entries if where == "notice in nav.cpu"]
        self.assertTrue(cpu)
        self.assertEqual(cpu[0].text(), _("perm.replace.button"))
        from tests import pantalla
        self.assertIn(_("perm.outdated.title"), pantalla.textos_de(window.cpu_page))
        with mock.patch.object(type(window), "_on_permanent_requested") as update, \
             mock.patch.object(window.sampler, "request_elevation") as ask:
            tried = 0
            for where, section, widget in entries:
                if where in ("Memory button", "Storage button"):
                    continue          # hidden: «Actualizar el ayudante» is the one left
                with self.subTest(entry=where):
                    update.reset_mock()
                    if section is not None:
                        window.select_section(section)
                        for _turn in range(4):
                            self.app.processEvents()
                    self.assertTrue(widget.isVisibleTo(window), where)
                    tried += 1
                    if isinstance(widget, LockMark):
                        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
                    else:
                        widget.click()
                    update.assert_called_once()
            ask.assert_not_called()
        self.assertGreater(tried, 20)

    def _settle(self):
        for _turn in range(4):
            self.app.processEvents()

    def test_memory_and_storage_leave_only_update(self):
        window = self._window()
        window.select_section("Memoria")
        self._settle()
        self.assertEqual(window.memory_page.elevation_text.text(), _("perm.outdated.body"))
        self.assertFalse(window.memory_page.elevation_button.isVisible())
        window.select_section("Almacenamiento")
        self._settle()
        self.assertEqual(window.storage_page.elevation_text.text(), _("perm.outdated.body"))
        self.assertFalse(window.storage_page.elevation_button.isVisible())

    def test_after_updating_the_static_part_is_read_again(self):
        window = self._window()
        done = mock.Mock(error=None, returncode=0, stderr="")
        with mock.patch.object(window.sampler, "refresh_static") as refresh:
            window._instalacion_terminada(done)
        refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
