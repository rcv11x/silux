"""Placa base: sin columnas de guiones y sin la tarjeta de un equipo que no hay.

En un sobremesa montado, la tarjeta «Equipo» eran cinco filas de códigos de
fábrica («-CF», «X570 MB», «MS-7D23») o de guiones, y en la de la placa
salían con guion los campos que el firmware no rellena.
"""

import dataclasses
import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaPaginaDeLaPlaca(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _pagina(self, ventana):
        ventana.select_section("Placa base")
        for _vez in range(3):
            self.app.processEvents()
        return ventana.board_page

    def test_en_una_placa_suelta_no_hay_tarjeta_de_equipo(self):
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                pagina = self._pagina(ventana)
                self.assertIsNone(f.board.system_display_name)
                self.assertFalse(pagina.system_card.isVisible())
                self.assertIn(_("board.nosystem"), pagina.board_pie.text())
                textos = pantalla.textos_de(pagina)
                self.assertNotIn("-CF", textos)

    def test_lo_que_el_firmware_no_rellena_se_esconde_y_se_nombra(self):
        f = self.fotos["5800x3d"]
        self.assertIsNone(f.board.version)
        with pantalla.Ventana(f) as ventana:
            pagina = self._pagina(ventana)
            self.assertFalse(pagina.board._values[_("board.field.revision")].isVisible())
            self.assertIn(_("board.field.revision").lower(), pagina.board_pie.text())
            # Una frase, no «El firmware no rellena: revisión, fabricante del chasis».
            self.assertTrue(pagina.board_pie.text().startswith(
                "El firmware de esta placa no dice su revisión ni el fabricante del chasis."),
                pagina.board_pie.text())
            self.assertTrue(pagina.board._values[_("storage.col.model")].isVisible())
            # Ni un guion en la tarjeta de la placa.
            self.assertFalse([e for e in pagina.board._values.values()
                              if e.isVisible() and e.full_text() == "—"])

    def test_lo_que_si_rellena_sale(self):
        f = self.fotos["i5-10400"]
        with pantalla.Ventana(f) as ventana:
            pagina = self._pagina(ventana)
            revision = pagina.board._values[_("board.field.revision")]
            self.assertTrue(revision.isVisible())
            self.assertEqual(revision.full_text(), f.board.version)

    def test_en_un_equipo_de_marca_la_tarjeta_esta_y_sin_guiones(self):
        # Como lo deja el proveedor en un OEM: la versión del sistema trae el
        # nombre comercial, y el SKU no viene.
        f = self.fotos["5800x3d"]
        marca = dataclasses.replace(f, board=dataclasses.replace(
            f.board, system_vendor="LENOVO", system_name="11DQS0KM00",
            system_version="ThinkCentre M80q", system_family="ThinkCentre M80q",
            system_sku=None, vendor="LENOVO", name="316C"))
        self.assertTrue(marca.board.system_display_name)
        with pantalla.Ventana(marca) as ventana:
            pagina = self._pagina(ventana)
            self.assertTrue(pagina.system_card.isVisible())
            self.assertEqual(pagina.system._values[_("sys.field.version")].full_text(),
                             "ThinkCentre M80q")
            self.assertFalse(pagina.system._values["SKU"].isVisible())
            self.assertNotIn(_("board.nosystem"), pagina.board_pie.text())


if __name__ == "__main__":
    unittest.main()
