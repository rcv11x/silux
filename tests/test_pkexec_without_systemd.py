"""Without systemd, pkexec alone doesn't give permissions, and the notice
says what else to install, there and next to «Unavailable» in Settings."""

import unittest
from unittest import mock

from silux.i18n import _
from tests.test_equipos import EQUIPOS, foto


class TestOnAntiX(unittest.TestCase):
    """The P8400 runs antiX: Debian with runit and no pkexec."""

    @classmethod
    def setUpClass(cls):
        cls.snapshot = foto(EQUIPOS / "core2-p8400-antix")[0]

    def test_the_notice_names_what_polkit_needs(self):
        note = next(n for n in self.snapshot.notes if n.path == "privileged.pkexec")
        self.assertIn("pkexec", note.hint)
        self.assertIn(_("deps.pkexec.nosystemd.debian"), note.hint)

    def test_with_systemd_only_the_package(self):
        snapshot = foto(EQUIPOS / "i5-5200u")[0]
        notes = [n for n in snapshot.notes if n.path == "privileged.pkexec"]
        self.assertFalse(any(_("deps.pkexec.nosystemd.debian") in n.hint for n in notes))

    def test_settings_says_it_next_to_unavailable(self):
        import dataclasses

        from silux.model import PrivilegedState
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.settings import SettingsPage
        from tests import qt

        app = qt.app()
        snapshot = dataclasses.replace(
            self.snapshot, privileged=PrivilegedState(supported=False, connected=False,
                                                      already_root=False))
        page = SettingsPage(Preferences().normalized(), theme.palette_for(app, "dark"))
        self.addCleanup(page.deleteLater)
        with mock.patch("silux.privileged.client.PrivilegedClient.installed", return_value=False):
            page.set_privileges(snapshot)
        self.assertEqual(page.permission_state, "unsupported")
        text = page.permission_row.explicacion.text()
        self.assertIn(_("settings.perm.unsupported.help"), text)
        self.assertIn(_("deps.pkexec.nosystemd.debian"), text)


if __name__ == "__main__":
    unittest.main()
