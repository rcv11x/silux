"""La ficha de cada disco: qué es y cómo está, y lo del kernel plegado.

Eran catorce filas seguidas, con la temperatura y la salud al final, detrás
del sector lógico y del planificador; y un disco SATA enseñaba «Enlace —»,
que no es un dato que falte: no tiene enlace PCIe propio.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaFichaDeUnDisco(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def _pagina(self, ventana):
        ventana.select_section("Almacenamiento")
        for _vez in range(3):
            self.app.processEvents()
        return ventana.storage_page

    def test_la_salud_va_arriba_y_el_firmware_plegado(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            rejilla, detalle = pagina._grids["nvme0n1"], pagina._details["nvme0n1"]
            self.assertEqual(len(rejilla._filas), 10)
            self.assertIn(_("gpu.sensor.temp"), rejilla._filas)
            self.assertNotIn(_("storage.field.scheduler"), rejilla._filas)
            planificador = detalle._values[_("storage.field.scheduler")]
            self.assertFalse(planificador.isVisible())
            pagina._folds["nvme0n1"].boton.click()
            self.app.processEvents()
            self.assertTrue(planificador.isVisible())
            disco = next(d for d in self.foto.disks if d.name == "nvme0n1")
            self.assertEqual(planificador.full_text(), disco.scheduler)
            self.assertEqual(detalle._values[_("storage.field.firmware")].full_text(),
                             disco.firmware)

    def test_un_sata_no_ensena_un_enlace_que_no_tiene(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            enlace = _("gpu.clock.link")
            self.assertFalse(pagina._grids["sda"]._values[enlace].isVisible())
            self.assertTrue(pagina._grids["nvme0n1"]._values[enlace].isVisible())
            self.assertIn("PCIe", pagina._grids["nvme0n1"]._values[enlace].full_text())

    def test_en_la_ficha_no_queda_un_guion_que_no_sea_no_lo_se(self):
        # Sin permisos, lo del diagnóstico lleva candado; lo demás tiene dato.
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            for nombre, rejilla in pagina._grids.items():
                guiones = [n for n, e in rejilla._values.items()
                           if e.isVisible() and e.full_text() == "—"]
                self.assertEqual(guiones, [], nombre)


if __name__ == "__main__":
    unittest.main()
