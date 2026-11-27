"""In a narrow window the status bar keeps its words whole: the section
selector showed «Almacenam» and the text beside it «Se actualiza cad…»."""

import unittest

from tests import geometry, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestNarrowStatusBar(unittest.TestCase):
    def test_the_selector_and_the_texts_beside_it_are_whole(self):
        from silux import i18n
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        language = i18n.current()
        self.addCleanup(i18n.set_language, language)
        snapshot = shared_snapshot(EQUIPOS / "i5-10400")
        for code in ("es", "en"):
            for scale in ("normal", "grande"):
                i18n.set_language(code)
                prefs = Preferences(language=code, font_scale=scale).normalized()
                theme.apply(app, "dark", prefs.density, scale)
                window = MainWindow(prefs)
                self.addCleanup(window.deleteLater)
                window.show()
                # Read wide, then narrowed with no sample since: at once.
                window.resize(1100, 800)
                geometry.settle(app)
                window._on_sample(snapshot)
                window.resize(480, 800)
                geometry.settle(app)
                combo = window._compact_nav
                self.assertTrue(combo.isVisible())
                for index in range(combo.count()):
                    text = combo.itemText(index)
                    with self.subTest(language=code, scale=scale, section=text):
                        self.assertGreater(combo.width(),
                                           combo.fontMetrics().horizontalAdvance(text) + 20)
                for label in (window._status, window._blocked):
                    shown = label.text()
                    with self.subTest(language=code, scale=scale, text=shown):
                        self.assertTrue(shown)
                        self.assertFalse(shown.endswith(("…", "..")), shown)
                        self.assertGreaterEqual(
                            label.width(), label.fontMetrics().horizontalAdvance(shown))
                window.close()


if __name__ == "__main__":
    unittest.main()
