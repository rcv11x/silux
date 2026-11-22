"""`--samples`: una captura con las gráficas llenas, no en una esquina.

Con las diez muestras de siempre, la curva de cada ficha ocupa una esquina
del eje. Vale para ver una página; para enseñar cómo queda hace falta un
minuto de datos, y eso era lanzar el programa y esperar con la mano.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent

CONTAR = """
import sys
from silux.ui import app
vistas = []
original = app.MainWindow._on_sample
def contando(self, foto):
    vistas.append(1)
    return original(self, foto)
app.MainWindow._on_sample = contando
codigo = app.main(sys.argv[1:])
print("muestras:", len(vistas))
sys.exit(codigo)
"""


class TestLasMuestrasDeUnaCaptura(unittest.TestCase):

    def _capturar(self, *banderas):
        with tempfile.TemporaryDirectory() as tmp:
            destino = pathlib.Path(tmp) / "c.png"
            entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=tmp)
            hecho = subprocess.run(
                [sys.executable, "-c", CONTAR, "--screenshot", str(destino), *banderas],
                cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120)
            self.assertEqual(hecho.returncode, 0, hecho.stderr[-500:])
            self.assertTrue(destino.is_file())
            return int(hecho.stdout.split("muestras:")[1].split()[0])

    def test_sin_pedir_nada_son_las_diez_de_siempre(self):
        self.assertEqual(self._capturar(), 10)

    def test_se_toman_las_que_se_piden(self):
        self.assertEqual(self._capturar("--samples", "23"), 23)


ULTIMA = """
import sys
from silux.ui import app
vistas = []
original = app.MainWindow._on_sample
def guardando(self, foto):
    vistas.append(foto)
    return original(self, foto)
app.MainWindow._on_sample = guardando
codigo = app.main(sys.argv[1:])
foto = vistas[-1]
print("primera:", foto.first_reading, "vistas:", len(vistas))
print("ritmos:", all(d.io.read_rate_bps is not None for d in foto.disks))
sys.exit(codigo)
"""


class TestTheRatesOfACapture(unittest.TestCase):
    """A capture's rates check their window against the pause it takes, and
    `--samples 1` is the first reading. With a dump mounted, whose counters
    stand still, a valid window gives 0 B/s and a broken one nothing."""

    def _capturar(self, *banderas):
        with tempfile.TemporaryDirectory() as tmp:
            destino = pathlib.Path(tmp) / "c.png"
            entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=tmp)
            hecho = subprocess.run(
                [sys.executable, "tools/montar_equipo.py", "5800x3d",
                 sys.executable, "-c", ULTIMA, "--screenshot", str(destino), *banderas],
                cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=180)
            self.assertEqual(hecho.returncode, 0, hecho.stderr[-500:])
            return hecho.stdout

    def test_the_rates_come_out(self):
        salida = self._capturar("--page", "Almacenamiento")
        self.assertIn("primera: False vistas: 10", salida)
        self.assertIn("ritmos: True", salida)

    def test_one_sample_is_the_first_reading(self):
        self.assertIn("primera: True vistas: 1", self._capturar("--samples", "1"))


if __name__ == "__main__":
    unittest.main()
