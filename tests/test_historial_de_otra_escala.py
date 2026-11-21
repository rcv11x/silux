"""Una prueba medida con otra escala dice por qué no tiene puntuación.

En el historial de Rendimiento, las pruebas de una escala anterior salían
con un «—» en la columna de la puntuación. Un guion es «no lo sé», y aquí sí
se sabe: se midieron con otra escala y su cifra no diría lo mismo. Hay una
nota debajo que lo cuenta para todas a la vez; la celda lo dice ahora para
la suya.

Las entradas son como las que guarda `history`: las de antes de la versión
no llevan `score_version`, y las de la v5 llevan un 5.
"""

import unittest

from silux import history, render, score
from tests import qt

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


def prueba(ts, version, **mas):
    return history.Entry(
        timestamp=ts, cpu="AMD Ryzen 7 5800X3D", threads=16,
        seconds=score.CANONICAL_SECONDS,
        scores={f"{carga}/{hilos}": 1000.0 * hilos
                for carga in score.SCORED_WORKLOADS for hilos in (1, 16)},
        score_version=version, **mas)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElHistorial(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _celdas(self, entradas):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.performance import PerformancePage

        theme.set_density("normal", "normal")
        self.pagina = PerformancePage(theme.palette_for(self.app, "dark"),
                                      Preferences().normalized())
        self.pagina._pintar_historial(entradas)
        etiquetas = self.pagina.history_card.findChildren(QLabel)
        return {e.text(): e for e in etiquetas}

    def test_la_de_otra_escala_dice_cual(self):
        celdas = self._celdas([prueba(100, score.VERSION - 1), prueba(200, score.VERSION)])
        self.assertIn(f"escala v{score.VERSION - 1}", celdas)
        celda = celdas[f"escala v{score.VERSION - 1}"]
        self.assertIn(f"v{score.VERSION}", celda.toolTip())

    def test_la_que_no_dice_su_escala_tampoco_se_queda_en_un_guion(self):
        celdas = self._celdas([prueba(100, None)])
        self.assertIn("otra escala", celdas)

    def test_la_de_esta_escala_lleva_su_cifra(self):
        celdas = self._celdas([prueba(200, score.VERSION)])
        puntos = score.compute(prueba(200, score.VERSION).scores, 16)
        self.assertIsNotNone(puntos)
        self.assertIn(render.thousands(puntos[1]), celdas)
        self.assertFalse([t for t in celdas if t.startswith("escala v")])

    def test_la_nota_de_debajo_sigue(self):
        self._celdas([prueba(100, score.VERSION - 1), prueba(200, score.VERSION)])
        self.assertFalse(self.pagina.history_note.isHidden())


if __name__ == "__main__":
    unittest.main()
