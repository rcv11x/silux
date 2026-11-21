"""What the report and the Sensors tree say around a list.

Two testers' reports (an Iris Xe and a UHD) had «… no publica su
temperatura.» glued to the last sensor: in Markdown a paragraph right after
a list is part of its last item. It happened on every page with a foot
under a list.
"""

import pathlib
import unittest

from silux import volcado
from tests import qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


def _glued(text: str) -> list[str]:
    """The paragraphs that follow a list item or a table row directly. An
    indented line is the item's own continuation (a command under its
    module in Diagnóstico), as Markdown means it."""
    lines = text.splitlines()
    return [line for before, line in zip(lines, lines[1:])
            if before.lstrip().startswith(("- ", "|")) and line.strip()
            and not line.startswith((" ", "-", "|", "#", ">"))]


class TestNoParagraphGluedToAList(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_on_any_page_of_any_dump(self):
        from silux.ui import full_report
        for dump in sorted(p.name for p in EQUIPOS.iterdir() if (p / "manifiesto.json").is_file()):
            with self.subTest(dump=dump):
                photo = volcado.snapshot_of(EQUIPOS / dump)
                text = full_report.build(photo, anonymous=True)
                self.assertEqual(_glued(text), [])


if __name__ == "__main__":
    unittest.main()
