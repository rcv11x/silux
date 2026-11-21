"""The Network page in the interface's language.

Its traffic headers and its four tiles were Spanish literals: in English
they still read «Bajando», «Subiendo», «Recibido» and «Enviado».
"""

import unittest

from silux import i18n
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

SPANISH = ("Interfaz", "Bajando", "Subiendo", "Recibido", "Enviado", "Paquetes", "Perdidos")


class TestTheNetworkPageInEnglish(unittest.TestCase):

    def test_its_headers_and_tiles_are_translated(self):
        qt.app()
        i18n.set_language("en")
        try:
            snapshot = foto(EQUIPOS / "i5-10400")[0]
            with pantalla.Ventana(snapshot) as ventana:
                ventana.select_section("Red")
                pagina = ventana.stack.currentWidget()
                textos = pantalla.textos_de(pagina)
                cabeceras = [pagina.traffic.horizontalHeaderItem(c).text()
                             for c in range(pagina.traffic.columnCount())] \
                    if hasattr(pagina.traffic, "horizontalHeaderItem") else []
            esperados = [_("net.col.down"), _("net.col.up"), _("net.col.received"), _("net.col.sent")]
        finally:
            i18n.set_language("es")
        self.assertEqual(esperados, ["Downloading", "Uploading", "Received", "Sent"])
        for texto in esperados:
            self.assertIn(texto, textos)
        self.assertFalse([t for t in textos + cabeceras if t in SPANISH])


if __name__ == "__main__":
    unittest.main()
