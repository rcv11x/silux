"""Each card's title has its section's icon, small and grey, as the sidebar
draws it: on Home, the one of the section the card leads to."""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "no PySide6")
class TestCardIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt.app()

    def same(self, card, section, window):
        return card.icon_section == section and not card._icon_label.pixmap().isNull()

    def test_every_titled_card_of_every_page(self):
        from silux.ui.app import SECTIONS
        from silux.ui.widgets import Card
        seen = 0
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            for section, _enabled in SECTIONS:
                if section == "nav.battery":
                    continue
                window.select_section(section)
                QApplication.processEvents()
                page = window.stack.currentWidget()
                titled = [c for c in page.findChildren(Card)
                          if c._title_label is not None and c.isVisible()]
                seen += len(titled)
                with self.subTest(section=section):
                    for card in titled:
                        self.assertTrue(card._icon_label.isVisible(), card._title_label.text())
                        if section != "nav.home":
                            self.assertTrue(self.same(card, section, window))
        self.assertGreater(seen, 30)

    def test_home_cards_carry_where_they_lead(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            home = window.home_page
            for card, section in ((home.cpu, "nav.cpu"), (home.gpu, "nav.graphics"),
                                  (home.memoria, "nav.memory"), (home.placa, "nav.board")):
                with self.subTest(card=card._title_label.text()):
                    self.assertTrue(self.same(card, section, window))
            self.assertEqual(home.memoria._title_label.text(), _("nav.memory"))


if __name__ == "__main__":
    unittest.main()
