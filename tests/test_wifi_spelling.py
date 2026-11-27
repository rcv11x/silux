"""«Wifi» is written «Wi-Fi», in Devices and in Motherboard."""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts

class TestWiFi(unittest.TestCase):
    def test_spelt_with_its_hyphen(self):
        self.assertEqual(_("board.pci.kind.wifi"), "Wi-Fi")
        qt.app()
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i7-4710hq")) as window:
            for page in ("Dispositivos", "Placa base"):
                window.select_section(page)
                qt.app().processEvents()
                texts = visible_texts(window.stack.currentWidget())
                with self.subTest(page=page):
                    self.assertFalse([t for t in texts if "Wifi" in t])
            window.select_section("Dispositivos")
            qt.app().processEvents()
            self.assertIn("Wi-Fi", visible_texts(window.stack.currentWidget()))


if __name__ == "__main__":
    unittest.main()
