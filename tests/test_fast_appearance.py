"""A change of theme, density or font applies the style sheet with the old
pages already gone: Qt repolishes every widget alive when the style sheet
changes, and those are about to be thrown away (docs/rendimiento.md)."""

import unittest
from dataclasses import replace
from unittest import mock

import shiboken6
from PySide6.QtWidgets import QWidget

from silux.ui import theme
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

# The window's own widgets (its status bar and the compact list) and
# nothing of a page: a page alone has over a hundred.
FEW_WIDGETS = 100


class TestTheStyleSheetMeetsNoPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def _watch(self, window):
        seen = []
        real = theme.apply

        def watched(*args, **kwargs):
            seen.append(len(window.findChildren(QWidget)))
            return real(*args, **kwargs)

        return seen, mock.patch.object(theme, "apply", watched)

    def _check(self, change):
        with pantalla.Ventana(self.snapshot) as window:
            geometry.settle(self.app)
            old = window.graphics_page
            seen, patch = self._watch(window)
            with patch:
                change(window)
                geometry.settle(self.app)
            self.assertEqual(len(seen), 1)
            self.assertLess(seen[0], FEW_WIDGETS)
            self.assertFalse(shiboken6.isValid(old))
            # And the window works on: the new pages are there and fed.
            window.select_section("Gráficos")
            geometry.settle(self.app)
            self.assertTrue(window.graphics_page.isVisible())

    def test_from_the_code(self):
        self._check(lambda window: window._on_preferences(
            replace(window.prefs, theme="light")))

    def test_from_the_settings_page_that_goes_too(self):
        def pick_light(window):
            window.select_section("Ajustes")
            geometry.settle(self.app)
            box = window.settings_page.theme_box
            box.setCurrentIndex(box.findData("light"))

        self._check(pick_light)

    def test_the_font_too(self):
        self._check(lambda window: window._on_preferences(
            replace(window.prefs, font_scale="mayor")))


if __name__ == "__main__":
    unittest.main()
