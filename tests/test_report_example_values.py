"""The report says which of its values are examples.

What identifies a machine goes in as values that look real («silux-pc»,
«192.168.1.120»): a tester took the address for a fault of the program. The
full report says it in its header, and the preview and the terminal no
longer say those values were left out: they are replaced.
"""

import contextlib
import io
import pathlib
import tempfile
import unittest

from silux import i18n, privacidad
from silux.i18n import _
from tests.test_equipos import EQUIPOS, shared_snapshot


def header(text: str) -> str:
    return text.split("\n## ", 1)[0]


class TestTheFullReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import qt

        qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def test_its_header_names_the_example_values(self):
        from silux.ui import full_report

        head = header(full_report.build(self.snapshot, anonymous=True))
        line = next(line for line in head.splitlines()
                    if line.startswith(f"- **{_('report.head.covered')}:**"))
        for value in (privacidad.HOST_NAME, privacidad.IPV4, privacidad.IPV6):
            self.assertIn(value, line)

    def test_with_the_identifiers_there_is_nothing_to_say(self):
        from silux.ui import full_report

        head = header(full_report.build(self.snapshot, anonymous=False))
        self.assertNotIn(f"**{_('report.head.covered')}:**", head)

    def test_in_english_too(self):
        from silux.ui import full_report

        previous = i18n.current()
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, previous)
        head = header(full_report.build(self.snapshot, anonymous=True))
        self.assertIn("- **Covered:**", head)
        self.assertIn(privacidad.IPV4, head)


class TestWhatTheyAreToldBeforehand(unittest.TestCase):
    def test_the_preview_says_they_are_replaced(self):
        for language, word in (("es", "de ejemplo"), ("en", "example")):
            previous = i18n.current()
            i18n.set_language(language)
            try:
                self.assertIn(word, _("report.preview.intro"))
            finally:
                i18n.set_language(previous)

    def test_the_terminal_says_they_are_replaced(self):
        from silux import cli

        with tempfile.TemporaryDirectory() as folder:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                cli.main(["--report", str(pathlib.Path(folder) / "informe.md"),
                          "--without-permissions", "--sections", "home"])
        said = out.getvalue()
        self.assertNotIn("omitido", said)
        self.assertIn("de ejemplo", said)
