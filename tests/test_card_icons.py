"""Home's cards carry the icon of the section each leads to, small and grey
as the sidebar draws it. A section's own page doesn't: there every card
would repeat the same one."""

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

    def test_home_cards_carry_where_they_lead(self):
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            QApplication.processEvents()
            home = window.home_page
            for card, section in ((home.cpu, "nav.cpu"), (home.gpu, "nav.graphics"),
                                  (home.memoria, "nav.memory"), (home.discos, "nav.storage"),
                                  (home.temperaturas, "nav.sensors"), (home.red, "nav.network"),
                                  (home.placa, "nav.board")):
                with self.subTest(card=card._title_label.text()):
                    self.assertEqual(card.icon_section, section)
                    self.assertTrue(card._icon_label.isVisible())
                    self.assertFalse(card._icon_label.pixmap().isNull())
            self.assertEqual(home.memoria._title_label.text(), _("nav.memory"))

    def test_no_other_page_repeats_one(self):
        from silux.ui.app import SECTIONS
        from silux.ui.widgets import Card
        seen = 0
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "5800x3d")) as window:
            for section, _enabled in SECTIONS:
                if section in ("nav.home", "nav.battery"):
                    continue
                window.select_section(section)
                QApplication.processEvents()
                page = window.stack.currentWidget()
                titled = [c for c in page.findChildren(Card)
                          if c._title_label is not None and c.isVisible()]
                seen += len(titled)
                with self.subTest(section=section):
                    for card in titled:
                        self.assertIsNone(card.icon_section, card._title_label.text())
                        self.assertFalse(card._icon_label.isVisible())
        self.assertGreater(seen, 30)


if __name__ == "__main__":
    unittest.main()
