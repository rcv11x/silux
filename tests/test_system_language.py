"""Silux starts in the system's language: Spanish on a Spanish system,
English on any other. It always started in Spanish, and someone with the
system in English found it in Spanish."""

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import settings


class TestSystemLanguage(unittest.TestCase):

    def test_spanish_systems_get_spanish(self):
        for env in ({"LANG": "es_ES.UTF-8"}, {"LANG": "es_MX.UTF-8"},
                    {"LC_ALL": "es_AR.UTF-8", "LANG": "en_US.UTF-8"},
                    {"LANGUAGE": "es:en", "LANG": "en_US.UTF-8"}):
            with self.subTest(env=env):
                self.assertEqual(settings.system_language(env), "es")

    def test_anything_else_gets_english(self):
        for env in ({"LANG": "en_US.UTF-8"}, {"LANG": "de_DE.UTF-8"},
                    {"LANG": "C.UTF-8"}, {"LANG": "POSIX"}, {},
                    {"LANGUAGE": "fr", "LANG": "es_ES.UTF-8"}):
            with self.subTest(env=env):
                self.assertEqual(settings.system_language(env), "en")


class TestFirstStart(unittest.TestCase):
    """With no settings.json, the system decides; once saved, the setting."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = pathlib.Path(tmp.name)

    def load(self, system_lang):
        env = {"XDG_CONFIG_HOME": str(self.config), "LANG": system_lang,
               "LANGUAGE": "", "LC_ALL": "", "LC_MESSAGES": ""}
        with mock.patch.dict(os.environ, env):
            return settings.load().language

    def test_without_settings_it_follows_the_system(self):
        self.assertEqual(self.load("en_US.UTF-8"), "en")
        self.assertEqual(self.load("es_ES.UTF-8"), "es")

    def test_a_saved_language_wins(self):
        (self.config / "silux").mkdir()
        (self.config / "silux" / "settings.json").write_text(json.dumps({"language": "es"}))
        self.assertEqual(self.load("en_US.UTF-8"), "es")

    def test_an_unknown_saved_language_falls_back_to_the_system(self):
        (self.config / "silux").mkdir()
        (self.config / "silux" / "settings.json").write_text(json.dumps({"language": "xx"}))
        self.assertEqual(self.load("en_US.UTF-8"), "en")


if __name__ == "__main__":
    unittest.main()
