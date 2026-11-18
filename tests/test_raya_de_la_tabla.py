"""Bajo la cabecera de cada tabla hay una raya, y se ve.

El commit `03ef40b` decía que la cabecera llevaba una raya. La regla estaba
en la hoja de estilos (`border-bottom` en `QLabel#ColumnTitle`) y en la
captura no había nada: un test que mirase la hoja habría pasado igual. Por
eso este no mira la hoja ni el widget suelto: monta la ventana, la pinta
como `--screenshot` y busca la raya en la imagen, en los dos temas.

La raya es una sola, de lado a lado de la tabla, entre los títulos y la
primera fila: también en el hueco entre dos columnas.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux.settings import Preferences
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaRayaDeLaTabla(unittest.TestCase):

    def _ventana(self, tema: str):
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        prefs = Preferences(theme=tema, window_width=1200, window_height=800).normalized()
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale)
        ventana = MainWindow(prefs)
        self.addCleanup(ventana.close)
        ventana.resize(1200, 800)
        ventana.show()
        muestra = foto(EQUIPOS / "5800x3d")[0]
        for _vuelta in range(3):
            ventana._on_sample(muestra)
            for _vez in range(5):
                app.processEvents()
        self.assertTrue(ventana.select_section("Cachés"))
        for _vez in range(5):
            app.processEvents()
        return ventana, theme.palette_for(app, tema)

    def test_se_ve_en_la_imagen_en_los_dos_temas(self):
        from silux.ui.widgets import Table

        for tema in ("dark", "light"):
            with self.subTest(tema=tema):
                ventana, paleta = self._ventana(tema)
                tabla = [t for t in ventana.stack.currentWidget().findChildren(Table)
                         if t.isVisibleTo(ventana)][0]
                titulos = sorted(
                    (e for e in tabla.findChildren(QLabel) if e.objectName() == "ColumnTitle"),
                    key=lambda e: e.mapTo(ventana, QPoint(0, 0)).x())
                fin_cabecera = max(e.mapTo(ventana, QPoint(0, e.height())).y() for e in titulos)
                primera_fila = tabla._cells[0][0].mapTo(ventana, QPoint(0, 0)).y()
                self.assertGreater(primera_fila, fin_cabecera)

                imagen = ventana.grab().toImage()
                escala = imagen.width() / ventana.width()
                raya = QColor(paleta.line).name()
                # Bajo el primer título, bajo el último y en el hueco entre
                # el primero y el segundo, que es donde un borde de cada
                # título se interrumpe.
                primero, segundo, ultimo = titulos[0], titulos[1], titulos[-1]
                hueco = (primero.mapTo(ventana, QPoint(primero.width(), 0)).x()
                         + segundo.mapTo(ventana, QPoint(0, 0)).x()) // 2
                self.assertGreater(segundo.mapTo(ventana, QPoint(0, 0)).x(),
                                   primero.mapTo(ventana, QPoint(primero.width(), 0)).x())
                for nombre, x in (("primer título", primero.mapTo(ventana, QPoint(4, 0)).x()),
                                  ("entre columnas", hueco),
                                  ("último título", ultimo.mapTo(ventana, QPoint(4, 0)).x())):
                    franja = [imagen.pixelColor(int(x * escala), int(y * escala)).name()
                              for y in range(fin_cabecera, primera_fila)]
                    self.assertEqual(franja.count(raya), 1,
                                     f"{nombre}: entre la cabecera y la primera fila "
                                     f"se ve {franja}, y la raya es {raya}")


if __name__ == "__main__":
    unittest.main()
