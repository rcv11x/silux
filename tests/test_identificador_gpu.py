"""Un identificador único todo a ceros no se enseña.

En Gráficos salía «Identificador único  0000000000000000». Eso es lo que da
un driver que no lo tiene, y lo que deja una captura anónima, que tapa con
ceros para que la ventana mida lo mismo. Ninguno de los dos identifica nada.

Con el volcado del 5800X3D, donde el identificador de la Radeon está a ceros
porque el volcado lo tapa.
"""

import dataclasses
import unittest

from silux import render
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestQueEsUnIdentificador(unittest.TestCase):

    def test_todo_ceros_no_lo_es(self):
        for nada in (None, "", "0", "0000000000000000", " 0000 \n"):
            self.assertIsNone(render.unique_id(nada), repr(nada))

    def test_uno_de_verdad_sale_entero(self):
        self.assertEqual(render.unique_id("a1b2c3d4e5f60708\n"), "a1b2c3d4e5f60708")
        self.assertEqual(render.unique_id("0000000000000001"), "0000000000000001")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaFicha(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def _ficha(self, gpu):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GpuSection

        theme.set_density("normal", "normal")
        self.ficha = GpuSection(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.ficha.show()
        self.addCleanup(self.ficha.close)
        self.ficha.apply(gpu)
        self.app.processEvents()
        campo = _("gpu.field.uuid")
        return self.ficha.card._names[campo], self.ficha.card._values[campo]

    def test_el_del_volcado_esta_a_ceros_y_la_fila_no_sale(self):
        gpu = self.foto.gpus[0]
        self.assertTrue(gpu.unique_id and not gpu.unique_id.strip("0"))
        nombre, valor = self._ficha(gpu)
        self.assertFalse(nombre.isVisible())
        self.assertFalse(valor.isVisible())

    def test_con_uno_de_verdad_la_fila_vuelve(self):
        gpu = dataclasses.replace(self.foto.gpus[0], unique_id="a1b2c3d4e5f60708")
        nombre, valor = self._ficha(gpu)
        self.assertTrue(nombre.isVisible())
        self.assertEqual(valor.full_text(), "a1b2c3d4e5f60708")


if __name__ == "__main__":
    unittest.main()
