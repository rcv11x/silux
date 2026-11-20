"""The home folder is shown as «~».

People share screenshots, and «/home/<name>» carries the user's name: in
Settings it was in the folder of the settings file and in the development
copy, both in plain sight.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import render
from tests import pantalla, qt

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestHomePath(unittest.TestCase):

    def test_the_home_folder_becomes_a_tilde(self):
        for shown, path in (("~/.config/silux/settings.json", "/home/ana/.config/silux/settings.json"),
                            ("~", "/home/ana"),
                            ("[Errno 13] Permission denied: '~/x.md'",
                             "[Errno 13] Permission denied: '/home/ana/x.md'")):
            with self.subTest(path=path):
                self.assertEqual(render.home_path(path, "/home/ana"), shown)

    def test_only_the_home_folder(self):
        for path in ("/home/anabel/x", "/srv/home/ana/x", "/opt/silux"):
            with self.subTest(path=path):
                self.assertEqual(render.home_path(path, "/home/ana"), path)
        self.assertEqual(render.home_path("/x", "/"), "/x")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestSettingsDoesNotShowIt(unittest.TestCase):

    def _texts_with(self, home: str, config: str) -> list[str]:
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        qt.app()
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}), \
             mock.patch.object(pathlib.Path, "home", return_value=pathlib.Path(home)):
            window = MainWindow(Preferences().normalized())
            self.addCleanup(window.deleteLater)
            window.settings_page.refresh_desktop()
            return pantalla.textos_de(window.settings_page)

    def test_neither_the_settings_file_nor_the_development_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            # The settings file inside the home folder, and the repository too.
            for home, config in ((tmp, os.path.join(tmp, ".config")),
                                 (str(ROOT.parent), os.path.join(tmp, ".config"))):
                with self.subTest(home=home):
                    texts = self._texts_with(home, config)
                    self.assertEqual([t for t in texts if home in t], [])
                    self.assertTrue([t for t in texts if "~/" in t])

    def test_the_settings_file_reads_as_in_the_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            texts = self._texts_with(tmp, os.path.join(tmp, ".config"))
        self.assertTrue([t for t in texts if "~/.config/silux/settings.json" in t])


if __name__ == "__main__":
    unittest.main()
