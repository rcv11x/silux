"""A checked box has a tick in it, in light and in dark.

With the sheet, a checked box was only a square filled with the accent:
nothing in it said it was ticked.
"""

import unittest

from tests.qt import app

try:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton
except ImportError:                                    # pragma: no cover
    QCheckBox = None


@unittest.skipIf(QCheckBox is None, "sin PySide6")
class TestTheTick(unittest.TestCase):
    def tick_pixels(self, choice: str) -> int:
        """How many pixels of the box are of the colour written on the accent."""
        from silux.ui import theme

        application = app()
        palette = theme.apply(application, choice, "normal")
        self.addCleanup(theme.apply, application, "dark", "normal")
        box = QCheckBox("También la escritura")
        self.addCleanup(box.deleteLater)
        box.setChecked(True)
        box.show()
        application.processEvents()
        option = QStyleOptionButton()
        option.initFrom(box)
        square = box.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, box)
        # Inside its border and rounded corners, where the window shows.
        square = square.adjusted(3, 3, -3, -3)
        image = box.grab().toImage()
        ink = QColor(palette.bg)
        found = 0
        for x in range(square.left(), square.right() + 1):
            for y in range(square.top(), square.bottom() + 1):
                pixel = image.pixelColor(x, y)
                if (abs(pixel.red() - ink.red()) + abs(pixel.green() - ink.green())
                        + abs(pixel.blue() - ink.blue())) < 60:
                    found += 1
        return found

    def test_a_checked_box_has_a_tick_in_both_themes(self):
        for choice in ("light", "dark"):
            with self.subTest(choice=choice):
                self.assertGreater(self.tick_pixels(choice), 6)
