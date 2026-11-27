"""Silux is a rolling release: each version is the day it was published,
«AAAA.M.D», and there are no channels. The updater still reads the pruebas'
«0.4.0rcN» to compare with them, and only normal releases count."""

import datetime
import io
import json
import re
import unittest

from silux import __version__, render, updates


def release(tag: str, prerelease: bool = False, draft: bool = False) -> dict:
    base = f"https://github.com/rcv11x/silux/releases/download/{tag}/"
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "html_url": f"https://github.com/rcv11x/silux/releases/tag/{tag}",
            "assets": [{"name": n, "browser_download_url": base + n}
                       for n in (updates.NORMAL, updates.COMPAT, updates.SUMS)]}


class TestTheVersion(unittest.TestCase):
    def test_a_day_with_no_leading_zeros(self):
        # The last prueba stays until the first date is published.
        if __version__ == "0.4.0rc14":
            self.skipTest("the prueba14 until the first release by date")
        match = re.fullmatch(r"(\d{4})\.([1-9]\d?)\.([1-9]\d?)", __version__)
        self.assertIsNotNone(match, f"{__version__} isn't AAAA.M.D")
        datetime.date(*(int(n) for n in match.groups()))

    def test_one_release_a_day(self):
        # The version is the day: two entries with one version would be two
        # releases the same day, which has no format (ask the author).
        import pathlib
        changelog = (pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
            encoding="utf-8")
        versions = re.findall(r"^## (\d{4}\.\d{1,2}\.\d{1,2})\b", changelog, re.MULTILINE)
        self.assertEqual(len(versions), len(set(versions)), versions)

    def test_shown_as_it_is(self):
        self.assertEqual(render.version("2026.11.28"), "2026.11.28")
        self.assertEqual(render.version("2026.12.5"), "2026.12.5")


class TestTheUpdater(unittest.TestCase):
    def test_the_latest_normal_release(self):
        listing = [release("2026.12.2"), release("2026.12.10"), release("2026.11.28"),
                   release("0.4.0rc14", prerelease=True), release("v0.3.0")]
        self.assertEqual(updates.latest(listing).tag, "2026.12.10")

    def test_prereleases_and_drafts_do_not_count(self):
        listing = [release("2026.12.10", prerelease=True), release("2026.12.11", draft=True),
                   release("2026.11.28")]
        self.assertEqual(updates.latest(listing).tag, "2026.11.28")

    def test_a_date_is_ahead_of_every_prueba(self):
        found = updates.latest([release("2026.11.28")])
        for running in ("0.4.0rc1", "0.4.0rc14", "0.3.0", "2026.11.27"):
            with self.subTest(running=running):
                self.assertTrue(updates.is_newer(found, running))
        self.assertFalse(updates.is_newer(found, "2026.11.28"))
        self.assertTrue(updates.is_current(found, "2026.11.28"))
        self.assertFalse(updates.is_newer(found, "2026.12.1"))

    def test_no_channels(self):
        self.assertFalse(hasattr(updates, "channel_for"))
        self.assertFalse(hasattr(updates, "CHANNELS"))

    def test_check_reads_the_listing(self):
        listing = json.dumps([release("2026.11.28"), release("0.4.0rc14", True)]).encode()
        found = updates.check(lambda url, timeout: io.BytesIO(listing))
        self.assertEqual(found.version_text, "2026.11.28")
        self.assertEqual(set(found.assets), {updates.NORMAL, updates.COMPAT, updates.SUMS})


class TestTheSettings(unittest.TestCase):
    def test_a_saved_channel_is_ignored(self):
        import os
        import tempfile
        from unittest import mock

        from silux import settings
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": folder.name}):
            settings.config_dir().mkdir(parents=True)
            settings.config_path().write_text(json.dumps(
                {"update_channel": "stable", "check_updates_migrated": True,
                 "check_updates": False}), encoding="utf-8")
            loaded = settings.load()
            self.assertFalse(hasattr(loaded, "update_channel"))
            self.assertFalse(loaded.check_updates)
            settings.save(loaded)
            self.assertNotIn("update_channel", settings.config_path().read_text())

    def test_settings_has_no_channel_row(self):
        from silux.settings import Preferences
        from silux.ui.pages.settings import SettingsPage
        from tests import qt
        qt.app()
        page = SettingsPage(Preferences().normalized())
        self.addCleanup(page.deleteLater)
        self.assertFalse(hasattr(page, "update_channel"))


if __name__ == "__main__":
    unittest.main()
