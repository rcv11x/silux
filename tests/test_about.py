"""The end of Settings, About: the third-party list folded, Claude named as
what it is, and each name thanked in its own badge, as «DDR4»."""

import unittest

from PySide6.QtWidgets import QLabel

from silux import db
from silux.i18n import _
from silux.ui.widgets import Plegable
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts


class TestAbout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _page(self, window):
        window.select_section("Ajustes")
        geometry.settle(self.app)
        return window.settings_page

    def test_the_third_party_list_comes_folded(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            page = self._page(window)
            fold = page.third_party
            self.assertIsInstance(fold, Plegable)
            self.assertFalse(fold.abierto())
            self.assertNotIn("libcpuid", visible_texts(page))
            fold.boton.click()
            geometry.settle(self.app)
            self.assertIn("libcpuid", visible_texts(page))

    def test_claude_as_an_ai_assistant(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            texts = visible_texts(self._page(window))
            self.assertIn(_("about.claude.name"), texts)
            self.assertNotIn("Claude", [t for t in texts if t == "Claude"])

    def test_each_name_thanked_in_its_badge(self):
        names = db.thanks()
        self.assertTrue(names)
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            page = self._page(window)
            badges = [label.text() for label in page.thanks_names.findChildren(QLabel)
                      if label.objectName() == "Badge" and label.isVisibleTo(page)]
            self.assertEqual(badges, list(names))


if __name__ == "__main__":
    unittest.main()
