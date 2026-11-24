"""The suite draws with DejaVu Sans whether the system has it or not."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests import qt

ROOT = pathlib.Path(__file__).resolve().parent.parent
# A fontconfig with a single font directory: one where DejaVu isn't.
FONTS_CONF = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>{directory}</dir><cachedir>{cache}</cachedir></fontconfig>
"""
ASK = ("from tests import qt; app = qt.app(); "
       "from PySide6.QtGui import QFontInfo; "
       "print(app.font().family(), '|', QFontInfo(app.font()).family(), '|', "
       "app.font().pointSize())")


class TestTheSuitesFont(unittest.TestCase):
    def test_here_it_is_the_cis(self):
        from PySide6.QtGui import QFontInfo

        app = qt.app()
        qt.reset_font()
        self.assertEqual(QFontInfo(app.font()).family(), qt.CI_FONT)
        self.assertEqual(app.font().pointSize(), qt.CI_FONT_POINTS)

    def test_on_a_system_without_it_the_one_in_the_repository_is_used(self):
        """Another process, since fontconfig is read once: with no font of
        the system's at all, what Qt resolves is still DejaVu Sans."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = pathlib.Path(tmp, "fonts")
            empty.mkdir()
            conf = pathlib.Path(tmp, "fonts.conf")
            conf.write_text(FONTS_CONF.format(directory=empty, cache=pathlib.Path(tmp, "cache")),
                            encoding="utf-8")
            env = dict(os.environ, FONTCONFIG_FILE=str(conf), QT_QPA_PLATFORM="offscreen",
                       XDG_DATA_HOME=tmp, XDG_CONFIG_HOME=tmp)
            done = subprocess.run([sys.executable, "-c", ASK], cwd=ROOT, env=env,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertEqual(done.stdout.strip().splitlines()[-1],
                         f"{qt.CI_FONT} | {qt.CI_FONT} | {qt.CI_FONT_POINTS}")

    def test_the_fonts_come_with_their_licence(self):
        licence = (qt.FONTS / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Bitstream Vera Fonts Copyright", licence)
        self.assertIn("DejaVu changes are in public domain", licence)
        self.assertEqual(sorted(f.name for f in qt.FONTS.glob("*.ttf")),
                         ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"])


if __name__ == "__main__":
    unittest.main()
