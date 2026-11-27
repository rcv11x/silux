"""One size system for the whole interface.

Text, controls, their heights, margins and gaps come from `theme.METRICS`
and the style sheet, never written by hand on a page, and they all grow
with the font size chosen in Settings. Controls without a size of their own
took the desktop's (9 pt on the CI, 10 on KDE) against the 11 of the rest,
and never grew with the font: Performance, made mostly of controls, read
smaller than the other pages.

The pages fitting at 720 px with every font size is `test_anchura`'s
`TestEveryFontAt720`.
"""

import pathlib
import re
import unittest

from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import QAbstractButton, QComboBox

from silux.ui import theme
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

UI = pathlib.Path(__file__).resolve().parent.parent / "silux" / "ui"
# The image to share is drawn at a fixed width so that two compare without
# scaling: it is a picture, not the interface.
NOT_THE_INTERFACE = {"tarjeta.py"}
# A link inside a line of text is sized by that line's rule.
LINKS = {"LinkAction", "StatusAction"}

HAND_WRITTEN = (
    ("a font size", re.compile(
        r"(setPointSize|setPointSizeF|setPixelSize|ui_font|value_font|mono_font)"
        r"\(\s*[\d.]+\s*[,)]")),
    ("a font size in a style sheet", re.compile(r"font-size:\s*\d")),
    # A one-pixel line is a line, not a size.
    ("a height", re.compile(r"set(Fixed|Minimum|Maximum)Height\(\s*([2-9]|\d\d+)\s*\)")),
)


def size(widget) -> int:
    widget.ensurePolished()
    return QFontInfo(widget.font()).pointSize()


class TestNothingSizedByHand(unittest.TestCase):
    def test_no_page_writes_a_font_size_or_a_height(self):
        found = []
        for path in sorted(UI.rglob("*.py")):
            if path.name in NOT_THE_INTERFACE:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for what, pattern in HAND_WRITTEN:
                    if pattern.search(line):
                        found.append(f"{path.relative_to(UI)}:{number}: {what}: {line.strip()}")
        self.assertEqual(found, [])


class TestEveryControlAtTheTextSize(unittest.TestCase):
    """Every button, list and box of every page is the size of the program's
    text, at every font size."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.saved = theme.METRICS

    def tearDown(self):
        theme.METRICS = self.saved
        theme.apply(self.app, "dark", "normal")

    def test_on_every_page(self):
        for dump in ("i5-10400", "5800x3d"):
            snapshot = shared_snapshot(EQUIPOS / dump)
            for scale in ("normal", "máximo"):
                metrics = theme.set_density("normal", scale)
                theme.apply(self.app, "dark", "normal", scale)
                with pantalla.Ventana(snapshot) as window:
                    for section, page in pantalla.recorrer(window):
                        tabs = getattr(page, "_tabs", None) or {"": page}
                        for key, tab in tabs.items():
                            if key:
                                page.select_tab(key)
                            geometry.settle(self.app)
                            controls = [w for w in tab.findChildren(QComboBox)
                                        + tab.findChildren(QAbstractButton)
                                        if w.objectName() not in LINKS]
                            for widget in controls:
                                with self.subTest(dump=dump, scale=scale, section=section,
                                                  tab=key, widget=type(widget).__name__):
                                    self.assertEqual(size(widget), metrics.base_pt)

    def test_performance_captions_too(self):
        """The labels beside Performance's lists and the line of how long a
        test takes, as the controls they go with."""
        theme.apply(self.app, "dark", "normal")
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Rendimiento")
            page = window.benchmarks_page
            cpu, disk = page.cpu_tab, page.disk_tab
            for widget in (cpu.each_caption, cpu.duracion_total, disk.about, *disk.captions):
                with self.subTest(text=widget.text()):
                    self.assertEqual(size(widget), theme.METRICS.base_pt)

    def test_a_check_box_and_a_list_s_arrow_grow_with_the_font(self):
        normal = theme.set_density("normal", "normal")
        largest = theme.set_density("normal", "máximo")
        self.assertGreater(largest.indicator_px, normal.indicator_px)
        self.assertGreater(largest.arrow_px, normal.arrow_px)
        sheet = theme.stylesheet(theme.DARK, largest)
        self.assertIn(f"width: {largest.indicator_px}px; height: {largest.indicator_px}px", sheet)


if __name__ == "__main__":
    unittest.main()
