"""pkexec without a polkit agent in the session: said, with the agent to install.

A bare window manager (Hyprland, Sway, i3) runs no agent, and pkexec then
fails with «No authentication agent found» and the same exit code as a
refusal. It was taken for «cancelled or denied».
"""

import sys
import unittest
from unittest import mock

from silux import system_deps, volcado
from silux.i18n import _
from silux.privileged import client
from tests.test_equipos import EQUIPOS


def _pkexec_saying(words: str, code: int) -> list[str]:
    """A pkexec that fails as the real one does: its words, its code."""
    return [sys.executable, "-c",
            f"import sys; sys.stderr.write({words!r}); sys.exit({code})"]


class _Client(client.PrivilegedClient):

    def __init__(self, command):
        super().__init__()
        self._fake = command

    @staticmethod
    def supported():
        return True

    def _command(self):
        return self._fake


class TestTheClient(unittest.TestCase):

    def test_no_agent_is_not_a_refusal(self):
        words = "Error executing command as another user: No authentication agent found.\n"
        with self.assertRaises(client.HelperNoAgent):
            _Client(_pkexec_saying(words, 127)).connect()

    def test_a_cancel_is_still_a_cancel(self):
        with self.assertRaises(client.HelperDenied) as caught:
            _Client(_pkexec_saying("", 126)).connect()
        self.assertNotIsInstance(caught.exception, client.HelperNoAgent)


class TestTheAgentToInstall(unittest.TestCase):

    def test_by_desktop_and_family(self):
        cases = {("KDE", "debian"): "polkit-kde-agent-1", ("KDE", "fedora"): "polkit-kde",
                 ("Hyprland", "arch"): "hyprpolkitagent", ("Hyprland", "debian"): "mate-polkit",
                 ("sway", "debian"): "mate-polkit", ("i3", "gentoo"): "mate-extra/mate-polkit",
                 ("LXQt", "ubuntu"): "lxqt-policykit", (None, None): "mate-polkit"}
        for (desktop, family), package in cases.items():
            with self.subTest(desktop=desktop, family=family):
                self.assertEqual(system_deps.polkit_agent(desktop, family), package)


class TestOnTheMemoryPage(unittest.TestCase):

    def _note(self, machine: str, desktop: str):
        from silux.collector import Collector
        from silux.providers.privileged_memory import PrivilegedMemory
        from tests.interval import second_snapshot

        words = "Error executing command as another user: No authentication agent found.\n"
        with volcado.mounted(EQUIPOS / machine), \
                mock.patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": desktop}):
            collector = Collector()
            try:
                provider = next(p for p in collector.providers
                                if isinstance(p, PrivilegedMemory))
                provider.client = _Client(_pkexec_saying(words, 127))
                provider.requested = True
                snapshot = second_snapshot(collector)
            finally:
                collector.close()
        return snapshot, next(n for n in snapshot.notes if n.path == "privileged.agent")

    def test_a_debian_with_sway(self):
        _snapshot, note = self._note("celeron-n4000", "sway")
        self.assertEqual(note.message, _("deps.polkitagent"))
        self.assertEqual(note.hint, _("deps.polkitagent.hint").format(paquete="mate-polkit"))

    def test_an_arch_with_hyprland_in_settings_and_the_report(self):
        from silux import report
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.settings import SettingsPage
        from tests import qt

        snapshot, note = self._note("i5-3330", "Hyprland")
        self.assertIn("hyprpolkitagent", note.hint)
        app = qt.app()
        page = SettingsPage(Preferences().normalized(), theme.palette_for(app, "dark"))
        self.addCleanup(page.deleteLater)
        with mock.patch("silux.privileged.client.PrivilegedClient.installed",
                        return_value=False):
            page.set_privileges(snapshot)
        self.assertIn("hyprpolkitagent", page.permission_row.explicacion.text())
        self.assertIn("hyprpolkitagent", report._diagnosis(snapshot))


if __name__ == "__main__":
    unittest.main()
