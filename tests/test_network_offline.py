"""Without a connection, the loopback is not the machine's network.

Offline, the loopback was the only interface with an address, and Home and
Network headed with «lo · 127.0.0.1».
"""

import unittest

from silux.i18n import _
from silux.ui.pages.network import main_interface
from tests import pantalla, qt
from tests.test_interface_language import visible_texts
from tests.test_equipos import EQUIPOS, foto, volcados


class TestOffline(unittest.TestCase):

    def test_no_dump_heads_with_the_loopback(self):
        for folder in volcados():
            principal, _all = main_interface(foto(folder)[0].network)
            with self.subTest(folder.name):
                self.assertFalse(principal is not None and principal.kind == "loopback")

    def test_said_offline_on_home_and_network(self):
        qt.app()
        snapshot = foto(EQUIPOS / "celeron-560")[0]
        self.assertIsNone(main_interface(snapshot.network)[0])
        with pantalla.Ventana(snapshot) as window:
            for section in ("Inicio", "Red"):
                window.select_section(section)
                text = visible_texts(window.stack.currentWidget())
                with self.subTest(section):
                    self.assertIn(_("net.offline"), text)
                    self.assertNotIn("lo · 127.0.0.1", text)
            # No tiles of dashes under it.
            self.assertFalse(window.stack.currentWidget().tiles.isVisibleTo(window))


if __name__ == "__main__":
    unittest.main()
