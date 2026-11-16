"""La QApplication de la suite no depende de qué test corre antes.

Dos procesos de la suite en paralelo abortaban («Fatal Python error:
Aborted») al crear el primer widget, también con `tests/qt.py`. El instalador
del icono (`tools/install_desktop.py`) dibuja con una `QGuiApplication`, que
le basta. Si `test_desktop` es lo primero que toca Qt en un proceso, esa es
la aplicación que queda, `QApplication.instance()` la devuelve, y un widget
sin `QApplication` aborta. En serie no se veía: siempre había corrido antes
algún test de interfaz.

El orden se fuerza en un proceso aparte, que es la única forma de tener un Qt
sin estrenar.
"""

import os
import pathlib
import subprocess
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent

try:
    import PySide6.QtSvg  # noqa: F401
    HAY_QT = True
except ImportError:                                    # pragma: no cover
    HAY_QT = False


def _en_otro_proceso(*tests: str) -> subprocess.CompletedProcess:
    entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run([sys.executable, "-m", "unittest", *tests], cwd=RAIZ,
                          env=entorno, capture_output=True, text=True, timeout=120)


@unittest.skipUnless(HAY_QT, "hace falta PySide6")
class TestElOrdenNoImporta(unittest.TestCase):

    def test_un_widget_despues_de_dibujar_los_iconos(self):
        salida = _en_otro_proceso(
            "tests.test_desktop.TestInstalacion.test_instala_todos_los_tamanos",
            "tests.test_gpu.TestAnchoDeLasColumnas")
        self.assertEqual(salida.returncode, 0, salida.stderr[-600:])

    def test_el_proceso_sale_bien_con_ventanas_sin_cerrar(self):
        # Los tests de la página de Rendimiento sueltan la página sin
        # cerrarla. Pasaban, y el proceso salía con una violación de segmento
        # la mitad de las veces: por eso se repite.
        for vez in range(4):
            salida = _en_otro_proceso("tests.test_benchmark.TestDuracionTotal",
                                      "tests.test_benchmark.TestLoQueNoPuntuaSeVeQueNoPuntua")
            self.assertEqual(salida.returncode, 0,
                             f"a la {vez + 1}ª: código {salida.returncode}\n"
                             + salida.stderr[-400:])

    def test_una_aplicacion_que_no_es_de_widgets_se_dice(self):
        # Quien pida la aplicación con otra ya creada tiene que enterarse ahí,
        # con una frase, y no tres tests más tarde con un aborto.
        codigo = ("from PySide6.QtGui import QGuiApplication\n"
                  "otra = QGuiApplication([])\n"
                  "from tests import qt\n"
                  "try:\n"
                  "    qt.app()\n"
                  "except RuntimeError as error:\n"
                  "    print('dicho:', error)\n")
        entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        salida = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=entorno,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(salida.returncode, 0, salida.stderr[-600:])
        self.assertIn("dicho:", salida.stdout)


if __name__ == "__main__":
    unittest.main()
