"""Una tabla que no cabe cede su texto más largo antes que cortar sus cifras.

En compacto a 900 px, la tabla de unidades de Almacenamiento pedía más ancho
del que tiene su tarjeta: «Escribiendo», la última columna, quedaba cortada
contra el borde, detrás de un desplazamiento horizontal. Lo que sobra se le
quita al modelo del disco, que sale con puntos suspensivos y entero al pasar
el ratón.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux.settings import Preferences
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
except ImportError:                                    # pragma: no cover
    QApplication = None

FILAS = [("nvme0n1", "WD_BLACK SN850X HS 1000GB", "NVMe", "931.5 GB", "44.9 °C"),
         ("nvme1n1", "Samsung SSD 970 EVO Plus 2TB", "NVMe", "1.8 TB", "41.9 °C"),
         ("sda", "ST2000DM008-2FR1", "HDD", "1.8 TB", "—")]


def _asentar(app, veces=5):
    for _vez in range(veces):
        app.processEvents()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaTablaSuelta(unittest.TestCase):

    def _tabla(self, ancho):
        from silux.ui.widgets import Table

        self.app = qt.app()
        caja = QWidget()
        self.addCleanup(caja.close)
        layout = QVBoxLayout(caja)
        tabla = Table(["Unidad", "Modelo", "Tipo", "Capacidad", "Temperatura"],
                      numeric=(False, False, False, True, True), cede=(1,))
        layout.addWidget(tabla)
        caja.resize(ancho, 300)
        caja.show()
        tabla.set_rows(FILAS)
        _asentar(self.app)
        self.caja = caja
        return tabla

    def test_con_sitio_no_se_recorta_nada(self):
        tabla = self._tabla(900)
        for fila, valores in zip(tabla._cells, FILAS):
            self.assertEqual([c.text() for c in fila], list(valores))

    def test_sin_sitio_cede_el_modelo_y_no_las_cifras(self):
        tabla = self._tabla(900)
        natural = tabla.widget().sizeHint().width()
        self.caja.resize(natural - 40, 300)
        _asentar(self.app)
        self.assertEqual(tabla.horizontalScrollBar().maximum(), 0)
        modelos = [fila[1] for fila in tabla._cells]
        self.assertTrue(any(c.text() != c.full_text() for c in modelos))
        self.assertEqual(modelos[1].toolTip(), FILAS[1][1])
        for fila, valores in zip(tabla._cells, FILAS):
            for columna in (0, 2, 3, 4):
                self.assertEqual(fila[columna].text(), valores[columna])
        ultima = tabla._cells[0][-1]
        self.assertLessEqual(ultima.mapTo(tabla, QPoint(ultima.width(), 0)).x(),
                             tabla.viewport().width())

    def test_al_volver_el_sitio_vuelve_el_texto(self):
        tabla = self._tabla(900)
        natural = tabla.widget().sizeHint().width()
        self.caja.resize(natural - 40, 300)
        _asentar(self.app)
        self.caja.resize(900, 300)
        _asentar(self.app)
        self.assertEqual([c.text() for c in tabla._cells[1]], list(FILAS[1]))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasUnidadesEnCompacto(unittest.TestCase):

    def test_la_tabla_de_unidades_cabe_a_900_con_cinco_discos(self):
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        normales = Preferences().normalized()
        self.addCleanup(theme.apply, app, normales.theme, normales.density,
                        normales.font_scale, normales.accent)
        prefs = Preferences(density="compact", window_width=900, window_height=680).normalized()
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale, prefs.accent)
        ventana = MainWindow(prefs)
        self.addCleanup(ventana.close)
        ventana.resize(900, 680)
        ventana.show()
        muestra = foto(EQUIPOS / "5800x3d")[0]
        self.assertEqual(len(muestra.disks), 5)
        for _vuelta in range(3):
            ventana._on_sample(muestra)
            _asentar(app)
        ventana.select_section("Almacenamiento")
        _asentar(app)
        tabla = ventana.storage_page.disks
        self.assertEqual(tabla.horizontalScrollBar().maximum(), 0)
        ultima = tabla._cells[0][-1]
        self.assertEqual(ultima.text(), ultima.full_text())
        self.assertLessEqual(ultima.mapTo(tabla, QPoint(ultima.width(), 0)).x(),
                             tabla.viewport().width())


if __name__ == "__main__":
    unittest.main()
