"""Where a bar ends shows, in light and in dark, without competing with it.

In dark, the empty part of a bar was nearly the colour of its card: where
the 100 % was couldn't be seen.
"""

import unittest

from tests.qt import app

try:
    from PySide6.QtGui import QColor
except ImportError:                                    # pragma: no cover
    QColor = None


def apart(first: str, second: str) -> int:
    a, b = QColor(first), QColor(second)
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())


@unittest.skipIf(QColor is None, "sin PySide6")
class TestTheTrack(unittest.TestCase):
    def test_it_stands_out_from_the_card_and_stays_below_the_bar(self):
        from silux.ui import theme

        for name, palette in (("light", theme.LIGHT), ("dark", theme.DARK)):
            with self.subTest(theme=name):
                self.assertGreaterEqual(apart(palette.track, palette.surface), 45)
                for colour in (palette.accent, palette.series_b, palette.series_c):
                    self.assertGreater(apart(palette.track, colour),
                                       2 * apart(palette.track, palette.surface))

    def test_a_bar_paints_its_empty_part_with_it(self):
        from silux.ui import theme
        from silux.ui.widgets import RateBar

        app()
        for palette in (theme.LIGHT, theme.DARK):
            bar = RateBar(palette, height=10)
            self.addCleanup(bar.deleteLater)
            bar.resize(200, 10)
            bar.set_fraction(0.5)
            image = bar.grab().toImage()
            self.assertEqual(image.pixelColor(190, 5).name(), QColor(palette.track).name())
