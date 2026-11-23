"""What the report and the Sensors tree say around a list.

Two testers' reports (an Iris Xe and a UHD) had «… no publica su
temperatura.» glued to the last sensor: in Markdown a paragraph right after
a list is part of its last item. It happened on every page with a foot
under a list.
"""

import pathlib
import unittest

from silux import volcado
from tests.per_dump import per_dump
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

    def _on_any_page(self, folder):
        from silux.ui import full_report

        photo = volcado.snapshot_of(folder)
        text = full_report.build(photo, anonymous=True)
        self.assertEqual(_glued(text), [])


per_dump(TestNoParagraphGluedToAList, "on_any_page_of_any_dump",
         TestNoParagraphGluedToAList._on_any_page)


if __name__ == "__main__":
    unittest.main()
