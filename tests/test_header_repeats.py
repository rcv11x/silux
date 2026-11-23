"""A page's header says each thing once.

Board's subtitle read «Intel H110 · UEFI (64 bits) · Sobremesa» over the
chips «Intel H110» and «UEFI (64 bits)», and the report wrote the same line
twice.
"""

import unittest

from silux.ui import app as appmod
from tests import pantalla, qt
from tests.test_equipos import foto, shared_snapshot, volcados

try:
    from PySide6.QtWidgets import QLabel
except ImportError:                                    # pragma: no cover
    QLabel = None


def _header(page):
    """The subtitle's pieces and the chips' texts of a page's header."""
    from silux.ui.widgets import ChipRow
    pieces = set()
    for label in page.findChildren(QLabel):
        if label.objectName() == "Subhead" and label.isVisibleTo(page):
            pieces.update(p.strip() for p in label.text().split("·") if p.strip())
    chips = set()
    for row in page.findChildren(ChipRow):
        if row.isVisibleTo(page):
            chips.update(label.text() for label in row.findChildren(QLabel)
                         if label.isVisibleTo(page) and label.text())
    return pieces, chips


@unittest.skipIf(QLabel is None, "sin PySide6")
class TestEveryHeader(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_the_subtitle_does_not_repeat_the_chips(self):
        for folder in volcados():
            with pantalla.Ventana(shared_snapshot(folder)) as window:
                for key, active in appmod.SECTIONS:
                    if not active or not window.select_section(key):
                        continue
                    for _vez in range(3):
                        self.app.processEvents()
                    pieces, chips = _header(window.stack.currentWidget())
                    with self.subTest(folder.name, section=key):
                        self.assertEqual(pieces & chips, set())


if __name__ == "__main__":
    unittest.main()
