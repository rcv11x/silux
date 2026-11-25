"""A button that can't be pressed looks it."""

import unittest

from PySide6.QtWidgets import QPushButton

from silux.ui import theme
from tests import qt


class TestDisabledButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def test_a_disabled_button_is_drawn_differently_in_both_themes(self):
        """«Start» stayed looking pressable while the memory test ran: a
        colour from the sheet beats the palette's disabled one."""
        for choice in ("dark", "light"):
            theme.apply(self.app, choice, "normal")
            with self.subTest(choice):
                button = QPushButton("Empezar")
                self.addCleanup(button.deleteLater)
                button.resize(button.sizeHint())
                enabled = button.grab().toImage()
                button.setEnabled(False)
                disabled = button.grab().toImage()
                self.assertNotEqual(enabled, disabled)


if __name__ == "__main__":
    unittest.main()
