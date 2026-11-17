"""Borrar pruebas del historial de Rendimiento: todas, o las de otra escala.

«Borrar el historial» borraba el archivo y dejaba la tarjeta con las filas
viejas: llamaba a `self.history.set_rows([])`, y `self.history` no existe
(F-M6 de la quinta auditoría).
"""

import unittest
from unittest import mock

from silux import history, score
from tests import qt
from tests.test_historial_de_otra_escala import prueba

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestBorrarElHistorial(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def setUp(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.performance import PerformancePage

        self.addCleanup(history.clear)
        self.guardadas = [prueba(300, score.VERSION), prueba(200, score.VERSION - 1),
                          prueba(100, None)]
        history.save(self.guardadas)
        theme.set_density("normal", "normal")
        self.pagina = PerformancePage(theme.palette_for(self.app, "dark"),
                                      Preferences().normalized())
        self.pagina.show()
        self.addCleanup(self.pagina.close)
        self.pagina._pintar_historial(history.load())

    def _contestando(self, respuesta):
        return mock.patch.object(QMessageBox, "question", return_value=respuesta)

    def test_borrarlo_todo_vacia_el_archivo_y_la_tarjeta(self):
        self.assertTrue(self.pagina.history_card.isVisible())
        with self._contestando(QMessageBox.StandardButton.Yes):
            self.pagina.clear_history.click()
        self.assertEqual(history.load(), [])
        self.assertFalse(self.pagina.history_card.isVisible())

    def test_si_se_dice_que_no_no_se_borra_nada(self):
        with self._contestando(QMessageBox.StandardButton.Cancel):
            self.pagina.clear_history.click()
        self.assertEqual(len(history.load()), 3)
        self.assertTrue(self.pagina.history_card.isVisible())


if __name__ == "__main__":
    unittest.main()
