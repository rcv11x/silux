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


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestBorrarLasDeOtraEscala(TestBorrarElHistorial):
    """Tras cambiar de escala, el historial se queda con pruebas que ya no
    se pueden comparar con nada. Borrarlas una a una eran trece diálogos."""

    def test_el_modulo_deja_solo_las_de_esta(self):
        quedan = history.remove_other_scales(score.VERSION)
        self.assertEqual([e.timestamp for e in quedan], [300])
        self.assertEqual([e.timestamp for e in history.load()], [300])

    def test_el_boton_esta_mientras_haya_alguna(self):
        self.assertTrue(self.pagina.clear_other_scales.isVisible())
        self.pagina._pintar_historial([prueba(300, score.VERSION)])
        self.assertFalse(self.pagina.clear_other_scales.isVisible())

    def test_pregunta_diciendo_cuantas_y_borra_solo_esas(self):
        with self._contestando(QMessageBox.StandardButton.Yes) as pregunta:
            self.pagina.clear_other_scales.click()
        self.assertIn("2", pregunta.call_args.args[2])
        self.assertEqual([e.timestamp for e in history.load()], [300])
        # La tarjeta sigue, con la que queda, sin la nota y sin el botón.
        self.assertTrue(self.pagina.history_card.isVisible())
        self.assertFalse(self.pagina.history_note.isVisible())
        self.assertFalse(self.pagina.clear_other_scales.isVisible())

    def test_si_todas_eran_de_otra_escala_la_tarjeta_se_va(self):
        history.save([prueba(200, score.VERSION - 1)])
        self.pagina._pintar_historial(history.load())
        with self._contestando(QMessageBox.StandardButton.Yes):
            self.pagina.clear_other_scales.click()
        self.assertEqual(history.load(), [])
        self.assertFalse(self.pagina.history_card.isVisible())

    def test_si_se_dice_que_no_se_quedan(self):
        with self._contestando(QMessageBox.StandardButton.Cancel):
            self.pagina.clear_other_scales.click()
        self.assertEqual(len(history.load()), 3)


if __name__ == "__main__":
    unittest.main()
