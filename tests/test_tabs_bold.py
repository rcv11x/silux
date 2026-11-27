"""Each of Performance's tabs is as wide as its name in the bold it takes
when open: the open one lost the edges of its letters («M», «o»)."""

import unittest

from tests import geometry, qt


class TestTabs(unittest.TestCase):
    def test_each_tab_fits_its_name_in_bold(self):
        from PySide6.QtGui import QFont, QFontMetrics

        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.benchmarks import TABS, BenchmarksPage

        app = qt.app()
        for density in ("compact", "normal", "spacious"):
            theme.apply(app, "dark", density)
            page = BenchmarksPage(theme.palette_for(app, "dark"), Preferences().normalized())
            self.addCleanup(page.deleteLater)
            page.show()
            geometry.settle(app)
            for key, name in TABS:
                button = page.buttons[key]
                bold = QFont(button.font())
                bold.setWeight(QFont.Weight.DemiBold)
                needed = QFontMetrics(bold).horizontalAdvance(_(name)) + 2 * theme.TAB_PAD_X
                with self.subTest(density=density, tab=key):
                    self.assertGreaterEqual(button.width(), needed)


if __name__ == "__main__":
    unittest.main()
