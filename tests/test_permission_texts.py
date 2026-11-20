"""What the permission texts promise is what happens.

Installing the helper was offered as «para siempre … no hace falta volver a
darlos cada vez que abres Silux», and Settings said «la contraseña se pide una
vez por sesión». Neither was true: the rule is `auth_admin_keep`, which polkit
keeps for a few minutes and for one process. What installing gives is a
password window that says what is read, in the user's language, and no
notice before it.
"""

import dataclasses
import json
import pathlib
import re
import unittest
from unittest import mock

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

LANG = pathlib.Path(__file__).resolve().parent.parent / "silux" / "db" / "lang"
# The name in prose; a path, a file or a command («silux/», «silux.conf»,
# «silux-helper») stays as it is.
LOWERCASE_NAME = re.compile(r"(?<![\w/.-])silux(?![\w/-]|\.\w)")


def texts(language: str) -> dict:
    return json.loads((LANG / f"{language}.json").read_text(encoding="utf-8"))


class TestNoTextPromisesMore(unittest.TestCase):

    def test_nothing_says_once_per_session_or_for_good(self):
        promises = {"es": ("una vez por sesión", "para siempre (recomendado)",
                           "no hace falta volver a darlos"),
                    "en": ("once per session", "for good (recommended)",
                           "do not have to grant them again")}
        for language, phrases in promises.items():
            for key, text in texts(language).items():
                for phrase in phrases:
                    with self.subTest(language=language, key=key):
                        self.assertNotIn(phrase, text.lower())

    def test_the_name_is_written_silux(self):
        for language in ("es", "en"):
            for key, text in texts(language).items():
                with self.subTest(language=language, key=key):
                    self.assertIsNone(LOWERCASE_NAME.search(text), text)


@unittest.skipIf(QApplication is None, "no PySide6")
class TestSettingsWithTheHelperInstalled(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = foto(EQUIPOS / "i5-10400")[0]

    def _page(self, connected: bool):
        from silux.privileged.client import PrivilegedClient
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.settings import SettingsPage

        page = SettingsPage(Preferences().normalized(), theme.palette_for(self.app, "dark"))
        self.addCleanup(page.deleteLater)
        photo = dataclasses.replace(self.photo, privileged=dataclasses.replace(
            self.photo.privileged, connected=connected, supported=True))
        with mock.patch.object(PrivilegedClient, "instalado", return_value=True), \
             mock.patch.object(PrivilegedClient, "al_dia", return_value=True):
            page.set_privileges(photo)
        return page

    def test_installed_and_reading(self):
        page = self._page(connected=True)
        self.assertEqual(page.permission_state, "installed_connected")
        self.assertEqual(page.permission_badge.text(), _("settings.perm.installed.connected"))
        self.assertNotIn(_("settings.perm.connected.help"), page.permission_row.explicacion.text())

    def test_installed_without_permissions_yet(self):
        page = self._page(connected=False)
        self.assertEqual(page.permission_state, "installed")
        self.assertEqual(page.permission_row.explicacion.text(), _("settings.perm.installed.help"))


if __name__ == "__main__":
    unittest.main()
