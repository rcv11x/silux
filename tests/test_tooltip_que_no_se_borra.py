"""Un tooltip puesto desde fuera a un `ElidingLabel` sobrevive a un redimensionado.

`_refresh` corre en cada `resizeEvent` y terminaba poniendo el tooltip del
recorte: el texto entero si no cabía, o ninguno. Con eso borraba la
explicación que le había puesto la página —de dónde sale un dato, por qué
falta— en cuanto la ventana cambiaba de tamaño. Los de cada módulo de memoria
no volvían nunca, porque se ponen una sola vez.
"""

import unittest

from tests import qt

try:
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElTooltipDeFuera(unittest.TestCase):

    def setUp(self):
        from silux.ui.widgets import ElidingLabel

        self.app = qt.app()
        self.etiqueta = ElidingLabel("DDR4-3200")
        self.addCleanup(self.etiqueta.deleteLater)

    def _redimensionar(self, ancho: int) -> None:
        anterior = self.etiqueta.size()
        self.etiqueta.resize(ancho, 20)
        self.app.sendEvent(self.etiqueta, QResizeEvent(QSize(ancho, 20), anterior))

    def test_sobrevive_a_un_redimensionado(self):
        self.etiqueta.setToolTip("DDR4-3200\n\nLo que dice el SPD del módulo.")
        for ancho in (400, 30, 400):
            self._redimensionar(ancho)
            self.assertIn("SPD", self.etiqueta.toolTip(), ancho)

    def test_sin_explicacion_sigue_enseñando_el_texto_que_no_cabe(self):
        self._redimensionar(400)
        self.assertEqual(self.etiqueta.toolTip(), "")
        self._redimensionar(20)
        self.assertEqual(self.etiqueta.toolTip(), "DDR4-3200")

    def test_la_explicacion_es_del_valor_y_se_va_con_el(self):
        # Quien cambia el valor pone después su explicación, si la tiene. La
        # del anterior no puede quedarse pegada al nuevo.
        self.etiqueta.setToolTip("—\n\nEste disco no publica su temperatura.")
        self.etiqueta.set_full_text("31.0 °C")
        self._redimensionar(400)
        self.assertEqual(self.etiqueta.toolTip(), "")

    def test_y_se_puede_quitar(self):
        self.etiqueta.setToolTip("algo")
        self.etiqueta.setToolTip("")
        self._redimensionar(400)
        self.assertEqual(self.etiqueta.toolTip(), "")


if __name__ == "__main__":
    unittest.main()
