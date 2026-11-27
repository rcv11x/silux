"""About Silux says where its community is: UniversoLinux on Discord,
opened in the browser with the system's environment."""

import unittest
from unittest import mock

from silux import system_env
from silux.i18n import _
from tests import qt

class TestCommunity(unittest.TestCase):
    def test_about_links_to_the_discord_channel(self):
        from silux.settings import Preferences
        from silux.ui.pages.settings import COMMUNITY_URL, SettingsPage

        qt.app()
        with mock.patch.object(system_env, "open_path") as opened:
            page = SettingsPage(Preferences().normalized())
            self.addCleanup(page.deleteLater)
            link = page.community_link
            self.assertIn(_("about.community.discord"), link.text())
            self.assertIn(f'href="{COMMUNITY_URL}"', link.text())
            link.linkActivated.emit(COMMUNITY_URL)
        opened.assert_called_once_with("https://discord.gg/YEctcwHZCQ")


if __name__ == "__main__":
    unittest.main()
