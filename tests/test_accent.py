"""The accent colour, picked in Settings. One table decides it
(`theme.ACCENTS`), and everything painted in the accent takes it from the
palette: when it changes, every page shows the new one at once and nothing
of the old one stays. It once came out mixed, blue in some places and amber
in others, because a saved choice reached some paths and not others."""

import colorsys
import pathlib
import re
import unittest
from dataclasses import replace

from PySide6.QtGui import QColor

from silux import settings
from silux.i18n import _
from silux.ui import theme
from tests import geometry, pantalla, qt
from tests.per_dump import per_dump
from tests.test_equipos import EQUIPOS, shared_snapshot

UI = pathlib.Path(__file__).resolve().parent.parent / "silux" / "ui"


def _luminance(colour: str) -> float:
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _hue(colour: str) -> float:
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def _palettes():
    for name in theme.ACCENTS:
        for base in (theme.DARK, theme.LIGHT):
            yield name, base, theme.tinted(base, name)


class TestTheTable(unittest.TestCase):
    def test_the_same_names_as_the_preferences(self):
        self.assertEqual(tuple(theme.ACCENTS), settings.ACCENTS)
        self.assertEqual(settings.ACCENTS[0], "amber")
        self.assertEqual(settings.Preferences().accent, "amber")

    def test_every_one_reads_in_both_themes(self):
        # Normal text, WCAG's 4.5:1: the primary button's text on the accent
        # and on its hover, a badge's on its wash, the accent as text.
        for name, base, palette in _palettes():
            with self.subTest(accent=name, dark=base is theme.DARK):
                self.assertGreaterEqual(contrast(palette.bg, palette.accent), 4.5)
                self.assertGreaterEqual(contrast(palette.bg, palette.accent_soft), 4.5)
                self.assertGreaterEqual(contrast(palette.accent, palette.accent_wash), 4.5)
                self.assertGreaterEqual(contrast(palette.accent, palette.surface), 4.5)

    def test_what_is_actionable_never_looks_like_the_accent(self):
        # The padlocks and what has a fix go in blue: beside a blue accent
        # they take another hue. And a chart's second series too.
        for name, base, palette in _palettes():
            for other in ("info", "series_b"):
                with self.subTest(accent=name, dark=base is theme.DARK, colour=other):
                    gap = abs(_hue(getattr(palette, other)) - _hue(palette.accent)) % 360
                    self.assertGreaterEqual(min(gap, 360 - gap), 40)

    def test_an_old_name_is_the_default(self):
        # The accents had Spanish names once: a saved «azul» isn't a choice.
        self.assertEqual(settings.Preferences(accent="azul").normalized().accent, "amber")


class TestNoColourByHand(unittest.TestCase):
    """Colours come from the theme: none is written in a page or a widget."""

    LITERAL = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b"
                         r"|QColor\(\s*\d|GlobalColor\.(?!transparent)\w+")
    # The theme is the table; the icons draw the logo, which is the brand's.
    ALLOWED = {"theme.py", "icons.py"}

    def test_no_colour_literal_outside_the_theme(self):
        found = []
        for path in sorted(UI.rglob("*.py")):
            if path.name in self.ALLOWED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0] if not re.search(r"[\"']#", line) else line
                if self.LITERAL.search(code):
                    found.append(f"{path.relative_to(UI)}:{number}: {line.strip()}")
        self.assertEqual(found, [])


def _tones(palette) -> set:
    return {QColor(getattr(palette, key)).rgb()
            for key in ("accent", "accent_soft", "accent_wash")}


def _pixels(image) -> set:
    image = image.convertToFormat(image.Format.Format_RGB32)
    width, height = image.width(), image.height()
    return {image.pixel(x, y) for y in range(0, height, 2) for x in range(0, width, 2)}


class TestChangedAtOnce(unittest.TestCase):
    """Mounted in amber and changed to blue: no page keeps an amber pixel."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")

    def _no_amber_left(self, folder):
        amber = _tones(theme.DARK)
        with pantalla.Ventana(shared_snapshot(folder)) as window:
            geometry.settle(self.app)
            window._on_preferences(replace(window.prefs, theme="dark", accent="blue"))
            window._on_sample(shared_snapshot(folder))
            geometry.settle(self.app)
            blue = _tones(window._palette)
            self.assertTrue(blue.isdisjoint(amber))
            seen_blue = False
            for name in window.section_names():
                if not window.select_section(name):
                    continue
                geometry.settle(self.app)
                pixels = _pixels(window.stack.currentWidget().grab().toImage())
                with self.subTest(page=name):
                    self.assertEqual(pixels & amber, set())
                seen_blue = seen_blue or bool(pixels & blue)
            pixels = _pixels(window.nav.viewport().grab().toImage())
            self.assertEqual(pixels & amber, set())
            self.assertTrue(pixels & blue, "the open section's pill")
            self.assertTrue(seen_blue)


per_dump(TestChangedAtOnce, "no_amber_left", TestChangedAtOnce._no_amber_left)


class TestInSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")

    def test_picked_it_applies_at_once(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.select_section("Ajustes")
            geometry.settle(self.app)
            box = window.settings_page.accent_box
            self.assertEqual([box.itemData(i) for i in range(box.count())],
                             list(theme.ACCENTS))
            self.assertEqual(box.itemText(1), _("settings.accent.blue"))
            box.setCurrentIndex(box.findData("green"))
            geometry.settle(self.app)
            self.assertEqual(window.prefs.accent, "green")
            green = theme.tinted(theme.DARK, "green")
            self.assertEqual(window._palette.accent, green.accent)
            self.assertEqual(window.nav.pill, QColor(green.accent_wash))
            # Still on Settings, with the list showing the choice.
            self.assertIs(window.stack.currentWidget(), window.settings_page)
            self.assertEqual(window.settings_page.accent_box.currentData(), "green")


class TestTheShareCards(unittest.TestCase):
    def test_in_the_accent_picked(self):
        from silux.ui import tarjeta

        app = qt.app()
        palette = theme.tinted(theme.DARK, "purple")
        image = tarjeta.dibujar(shared_snapshot(EQUIPOS / "5800x3d"), palette)
        pixels = _pixels(image.toImage() if hasattr(image, "toImage") else image)
        self.assertEqual(pixels & (_tones(theme.DARK) - {QColor(theme.DARK.accent).rgb()}), set())
        self.assertTrue(pixels & _tones(palette))
        del app


if __name__ == "__main__":
    unittest.main()
