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
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

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

    @staticmethod
    def _justo(tabla) -> int:
        """Lo que ocupa la tabla con sus columnas pegadas, sin holgura."""
        columnas = len(tabla._headers)
        return (sum(max(a, tabla._ancho_de_cabecera(c)) for c, a in enumerate(tabla._anchos))
                + tabla._grid.horizontalSpacing() * (columnas - 1))

    def test_con_sitio_no_se_recorta_nada(self):
        tabla = self._tabla(900)
        for fila, valores in zip(tabla._cells, FILAS):
            self.assertEqual([c.text() for c in fila], list(valores))

    def test_sin_sitio_cede_el_modelo_y_no_las_cifras(self):
        tabla = self._tabla(900)
        self.caja.resize(self._justo(tabla) - 20, 300)
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
        self.caja.resize(self._justo(tabla) - 20, 300)
        _asentar(self.app)
        self.caja.resize(900, 300)
        _asentar(self.app)
        self.assertEqual([c.text() for c in tabla._cells[1]], list(FILAS[1]))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestFilasCortas(TestLaTablaSuelta):
    """«Ningún monitor conectado» traía seis valores para siete columnas."""

    def test_una_fila_corta_no_deja_el_dato_de_la_anterior(self):
        tabla = self._tabla(900)
        tabla.set_rows([("nada", "—"), ("sda", "—"), ("sdb", "—")])
        _asentar(self.app)
        self.assertEqual([c.full_text() for c in tabla._cells[0]], ["nada", "—", "", "", ""])

    def test_y_al_volver_la_fila_entera_cabe(self):
        tabla = self._tabla(900)
        tabla.set_rows([("nada", "—")])
        tabla.set_rows([FILAS[0]])
        _asentar(self.app)
        self.assertEqual([c.full_text() for c in tabla._cells[0]], list(FILAS[0]))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestConSitioDeSobra(TestLaTablaSuelta):
    """En una ventana de 2560 px las tablas se quedaban en el tercio
    izquierdo de su tarjeta. Las columnas se separan, con tope."""

    def _fin_de_la_ultima(self, tabla) -> int:
        ultima = tabla._cells[0][-1]
        return ultima.mapTo(tabla, QPoint(ultima.width(), 0)).x()

    def test_las_columnas_se_separan_cuando_sobra(self):
        tabla = self._tabla(900)
        justo = self._justo(tabla)
        self.assertGreater(self._fin_de_la_ultima(tabla), justo + 100)
        self.assertLessEqual(self._fin_de_la_ultima(tabla), tabla.viewport().width())
        self.assertEqual(tabla.horizontalScrollBar().maximum(), 0)

    def test_pero_no_sin_limite(self):
        from PySide6.QtGui import QFontMetrics
        from silux.ui.theme import value_font

        tabla = self._tabla(2400)
        tope = QFontMetrics(value_font()).averageCharWidth() * tabla.HOLGURA_MAXIMA
        columnas = len(tabla._headers)
        self.assertLessEqual(self._fin_de_la_ultima(tabla),
                             self._justo(tabla) + tope * columnas + columnas)
        self.assertLess(self._fin_de_la_ultima(tabla), tabla.viewport().width() - 200)

    def test_y_justa_de_sitio_no_cambia(self):
        tabla = self._tabla(900)
        self.caja.resize(self._justo(tabla) + 30, 300)
        _asentar(self.app)
        self.assertEqual(tabla.horizontalScrollBar().maximum(), 0)
        for fila, valores in zip(tabla._cells, FILAS):
            self.assertEqual([c.text() for c in fila], list(valores))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasPaginasCortasEnUnaVentanaGrande(unittest.TestCase):
    """A 2560×1440, Placa base y Sistema eran dos tarjetas a medio llenar y
    otra debajo, a todo lo ancho, con el resto de la ventana vacío."""

    def _ventana(self, ancho, alto, densidad="normal"):
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        normales = Preferences().normalized()
        self.addCleanup(theme.apply, app, normales.theme, normales.density,
                        normales.font_scale)
        prefs = Preferences(density=densidad, font_scale="normal",
                            window_width=ancho, window_height=alto).normalized()
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale)
        ventana = MainWindow(prefs)
        self.addCleanup(ventana.close)
        ventana.resize(ancho, alto)
        ventana.show()
        muestra = shared_snapshot(EQUIPOS / "5800x3d")
        for _vuelta in range(3):
            ventana._on_sample(muestra)
            _asentar(app)
        self.app = app
        return ventana

    def _tarjetas(self, ventana, seccion, rejillas):
        ventana.select_section(seccion)
        _asentar(self.app)
        pagina = ventana.stack.currentWidget()
        tarjetas = [getattr(pagina, r).parentWidget() for r in rejillas]
        return pagina, [(t.mapTo(pagina, QPoint(0, 0)).x(), t.mapTo(pagina, QPoint(0, 0)).y(),
                         t.width()) for t in tarjetas if t.isVisible()]

    def test_a_2560_van_todas_en_una_fila(self):
        ventana = self._ventana(2560, 1440)
        for seccion, rejillas in (("Placa base", ("board", "firmware", "chipset", "platform")),
                                  ("Sistema", ("os", "kernel", "activity"))):
            with self.subTest(seccion=seccion):
                pagina, cajas = self._tarjetas(ventana, seccion, rejillas)
                self.assertEqual(len(cajas), len(rejillas))
                self.assertEqual(len({y for _x, y, _w in cajas}), 1, cajas)
                anchos = [w for _x, _y, w in cajas]
                self.assertLessEqual(max(anchos) - min(anchos), 2)
                self.assertGreater(cajas[-1][0] + cajas[-1][2], pagina.viewport().width() * 0.95)

    def _comprobar_compacto(self, ventana):
        """De dos en dos con la que sobra a lo ancho, o de una en una.

        Cuántas caben depende de la tipografía: con la del CI (DejaVu, más
        ancha) a 900 px van de una en una, y con la de aquí de dos en dos.
        Las dos cosas están bien; lo que no puede pasar es que una fila quede
        a medias con un hueco a su derecha, ni que algo se salga.
        """
        for seccion, rejillas in (("Placa base", ("board", "firmware", "chipset", "platform")),
                                  ("Sistema", ("os", "kernel", "activity"))):
            with self.subTest(seccion=seccion):
                pagina, cajas = self._tarjetas(ventana, seccion, rejillas)
                filas: dict[int, list] = {}
                for x, y, ancho in cajas:
                    filas.setdefault(y, []).append((x, ancho))
                self.assertGreater(len(filas), 1)       # a 900 no caben en una
                borde = max(x + ancho for x, _y, ancho in cajas)
                self.assertLessEqual(borde, pagina.viewport().width())
                for y, fila in filas.items():
                    fila.sort()
                    # Cada fila llega al mismo borde derecho: ninguna a medias.
                    self.assertAlmostEqual(fila[-1][0] + fila[-1][1], borde, delta=2, msg=str(filas))
                    self.assertEqual(fila[0][0], min(x for x, _y, _a in cajas))

    def test_en_compacto_a_900_ninguna_fila_queda_a_medias(self):
        self._comprobar_compacto(self._ventana(900, 680, densidad="compact"))

    def test_y_tampoco_con_la_letra_del_ci(self):
        from PySide6.QtGui import QFont, QFontDatabase

        app = qt.app()
        ancha = "DejaVu Sans"
        if ancha not in QFontDatabase.families():
            self.skipTest(f"no está instalada {ancha}")
        de_antes = app.font()
        self.addCleanup(app.setFont, de_antes)
        letra = QFont(de_antes)
        letra.setFamily(ancha)
        app.setFont(letra)
        self._comprobar_compacto(self._ventana(900, 680, densidad="compact"))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasUnidadesEnCompacto(unittest.TestCase):

    def test_la_tabla_de_unidades_cabe_a_900_con_cinco_discos(self):
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        normales = Preferences().normalized()
        self.addCleanup(theme.apply, app, normales.theme, normales.density,
                        normales.font_scale)
        prefs = Preferences(density="compact", window_width=900, window_height=680).normalized()
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale)
        ventana = MainWindow(prefs)
        self.addCleanup(ventana.close)
        ventana.resize(900, 680)
        ventana.show()
        muestra = shared_snapshot(EQUIPOS / "5800x3d")
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
