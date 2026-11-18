"""Ningún texto de varias líneas se queda sin su última línea.

En Inicio, con el i5-10400, la tarjeta de Red decía «RTL8111/8168/8211/8411
PCI Express Gigabit Ethernet / Controller · 1 Gb/s · dúplex completo» en dos
líneas y la segunda salía cortada por abajo, en los dos temas. La fila medía
195 px y sus tarjetas pedían 214 y 221.

La causa estaba en `ResponsiveRow`: al cambiar de columnas sacaba a sus hijos
de la rejilla con `takeAt` y los volvía a meter. Desde Python eso no destruye
la celda vieja, y cada widget sigue avisando de sus cambios a la primera
celda que tuvo: la nueva se queda con la altura que calculó la primera vez
(con el texto de carga, de una línea) y no se entera de que el texto creció.

Aquí se monta la ventana con cada equipo volcado, se recorren las secciones
y se mide cada etiqueta que parte líneas contra lo que pide a su ancho.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux.settings import Preferences
from tests import qt
from tests.test_equipos import EQUIPOS, foto, volcados

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


def _asentar(app, veces=5):
    for _vuelta in range(veces):
        app.processEvents()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaFilaQueSeRecoloca(unittest.TestCase):

    def test_la_celda_nueva_se_entera_de_que_su_hijo_crece(self):
        from silux.ui.widgets import ResponsiveRow

        app = qt.app()
        fila = ResponsiveRow(min_item_width=110)
        self.addCleanup(fila.deleteLater)
        etiquetas = [QLabel("corto") for _n in range(3)]
        for etiqueta in etiquetas:
            etiqueta.setWordWrap(True)
            fila.add(etiqueta)
        fila.resize(400, 200)
        fila.show()
        _asentar(app)
        celda = fila.layout().itemAt(0)
        ancho = etiquetas[0].width()
        una_linea = celda.heightForWidth(ancho)

        etiquetas[0].setText("un texto bastante más largo, que a este ancho "
                             "ya no cabe en una línea ni en dos")
        _asentar(app)
        celda = fila.layout().itemAt(0)
        self.assertIs(celda.widget(), etiquetas[0])
        self.assertGreater(etiquetas[0].heightForWidth(ancho), una_linea)
        self.assertEqual(celda.heightForWidth(ancho), etiquetas[0].heightForWidth(ancho))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestNadaSeCortaPorAbajo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from silux.ui import theme
        from silux.ui.app import MainWindow

        cls.app = qt.app()
        prefs = Preferences(window_width=1440, window_height=900).normalized()
        theme.apply(cls.app, prefs.theme, prefs.density, prefs.font_scale, prefs.accent)
        cls.ventana = MainWindow(prefs)
        cls.ventana.resize(1440, 900)
        cls.ventana.show()

    @classmethod
    def tearDownClass(cls):
        cls.ventana.close()

    def _poner(self, equipo: str) -> None:
        muestra = foto(EQUIPOS / equipo)[0]
        for _vuelta in range(3):
            self.ventana._on_sample(muestra)
            _asentar(self.app)

    def _cortadas(self) -> list[str]:
        pagina = self.ventana.stack.currentWidget()
        cortadas = []
        for etiqueta in pagina.findChildren(QLabel):
            if not (etiqueta.isVisibleTo(self.ventana) and etiqueta.wordWrap()
                    and etiqueta.text()):
                continue
            pide = etiqueta.heightForWidth(etiqueta.width())
            if etiqueta.height() < pide:
                cortadas.append(f"«{etiqueta.text()[:50]}» mide {etiqueta.height()} "
                                f"y pide {pide}")
        return cortadas

    def test_la_tarjeta_de_red_de_inicio_con_un_nombre_de_dos_lineas(self):
        self._poner("i5-10400")
        self.ventana.select_section("Inicio")
        _asentar(self.app)
        red = self.ventana.home_page.red
        detalle = red.detalle
        self.assertIn("RTL8111/8168/8211/8411", detalle.text())
        una_linea = detalle.fontMetrics().lineSpacing()
        # El caso: a este ancho el nombre no cabe en una línea.
        self.assertGreater(detalle.heightForWidth(detalle.width()), una_linea * 1.5)
        self.assertGreaterEqual(detalle.height(), detalle.heightForWidth(detalle.width()))
        self.assertGreaterEqual(red.height(), red.heightForWidth(red.width()))

    def test_ninguna_seccion_con_ningun_volcado(self):
        for carpeta in volcados():
            self._poner(carpeta.name)
            for fila in range(self.ventana.nav.count()):
                self.ventana.nav.setCurrentRow(fila)
                _asentar(self.app)
                pagina = type(self.ventana.stack.currentWidget()).__name__
                with self.subTest(equipo=carpeta.name, pagina=pagina):
                    self.assertEqual(self._cortadas(), [])


    def _tablas_que_desplazan(self) -> list[str]:
        """Las tablas cuyo contenido no cabe en su alto y se desplaza dentro.

        En Gráficos, la de códecs: sus «✓» y «✗» van en una letra mayor que
        la de las cifras, cada fila medía más de lo que la tabla había
        calculado y lo que sobraba se desplazaba dentro de la tarjeta, con la
        cabecera fuera de la vista.
        """
        from silux.ui.widgets import Table

        pagina = self.ventana.stack.currentWidget()
        malas = []
        for tabla in pagina.findChildren(Table):
            if not tabla.isVisibleTo(self.ventana) or not tabla._rows:
                continue
            barra = tabla.verticalScrollBar()
            if barra.maximum() > 0:
                malas.append(f"{tabla._headers[0]}: {barra.maximum()} px fuera de la vista")
        return malas

    def test_ninguna_tabla_se_desplaza_por_dentro(self):
        for carpeta in volcados():
            self._poner(carpeta.name)
            for fila in range(self.ventana.nav.count()):
                self.ventana.nav.setCurrentRow(fila)
                _asentar(self.app)
                pagina = type(self.ventana.stack.currentWidget()).__name__
                with self.subTest(equipo=carpeta.name, pagina=pagina):
                    self.assertEqual(self._tablas_que_desplazan(), [])


if __name__ == "__main__":
    unittest.main()
