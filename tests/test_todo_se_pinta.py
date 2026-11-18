"""Todas las páginas se pintan sin reventar, con cada equipo volcado.

El mapa de cachés dejó de pintarse al cambiar de tipografía: en su
`paintEvent`, una variable local se llamaba igual que la función que la
construye (`value_font = value_font(…)`), y eso es un `UnboundLocalError` en
cada repintado. La página salía con el hueco del mapa en blanco y la suite
entera pasaba: sin pantalla Qt no pinta nada hasta que alguien se lo pide, y
ningún test se lo pedía. Se vio al sacar las capturas, que sí pintan.

Aquí se monta la ventana, se le da la foto de cada volcado y se pinta cada
sección como lo hace `--screenshot`. Lo que revienta dentro de un
`paintEvent` no siempre sube hasta quien pidió pintar (depende de la versión
de PySide6), así que además se escucha por donde Python avisa de las
excepciones que nadie recoge. Con PySide6 6.12 este fallo en concreto no
llega a ser un test en rojo: el pintor se queda abierto y Qt tumba el proceso
con una violación de segmento. Si este archivo mata a su trabajador, es eso.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux.settings import Preferences
from tests import qt
from tests.test_equipos import foto, volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestTodoSePinta(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from silux.ui import theme
        from silux.ui.app import SECTIONS, MainWindow

        cls.app = qt.app()
        prefs = Preferences(window_width=1200, window_height=800).normalized()
        theme.apply(cls.app, prefs.theme, prefs.density, prefs.font_scale)
        cls.secciones = SECTIONS
        cls.ventana = MainWindow(prefs)
        cls.ventana.resize(1200, 800)
        cls.ventana.show()

    @classmethod
    def tearDownClass(cls):
        cls.ventana.close()

    def setUp(self):
        self.fallos: list[str] = []
        ganchos = (sys.excepthook, sys.unraisablehook)
        sys.excepthook = lambda tipo, valor, traza: self.fallos.append(repr(valor))
        sys.unraisablehook = lambda aviso: self.fallos.append(repr(aviso.exc_value))

        def devolver():
            sys.excepthook, sys.unraisablehook = ganchos
        self.addCleanup(devolver)

    def _pintar(self) -> None:
        try:
            self.ventana.grab()
        except Exception as error:                     # noqa: BLE001
            self.fallos.append(repr(error))

    def test_cada_seccion_con_cada_volcado(self):
        for carpeta in volcados():
            muestra = foto(carpeta)[0]
            for _vuelta in range(2):
                self.ventana._on_sample(muestra)
                self.app.processEvents()
            for fila in range(self.ventana.nav.count()):
                self.ventana.nav.setCurrentRow(fila)
                self.app.processEvents()
                self.fallos.clear()
                self._pintar()
                pagina = type(self.ventana.stack.currentWidget()).__name__
                with self.subTest(equipo=carpeta.name, pagina=pagina):
                    self.assertEqual(self.fallos, [])


if __name__ == "__main__":
    unittest.main()
