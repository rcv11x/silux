"""Lo que enseña `tools/volcar_gpu.py` de cada gráfica, y lo que no toca."""

import contextlib
import importlib.util
import io
import pathlib
import unittest

# El módulo entero y no sus nombres: así no se recogen dos veces sus tests.
from tests import test_volcar_equipo as equipo


def _herramienta():
    ruta = pathlib.Path(__file__).resolve().parent.parent / "tools" / "volcar_gpu.py"
    spec = importlib.util.spec_from_file_location("volcar_gpu", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


volcar_gpu = _herramienta()


def _salida(**estado) -> str:
    with equipo._montado(**estado), contextlib.redirect_stdout(io.StringIO()) as salida:
        volcar_gpu.main()
    return salida.getvalue()


class TestUnaGraficaDormida(unittest.TestCase):
    """B-1: lo primero es su estado de energía, y si duerme no se pasa de ahí."""

    def test_dormida_solo_su_estado_y_quien_es(self):
        texto = _salida(estado="suspended", power_state="D3cold")
        self.assertIn("power/runtime_status = suspended", texto)
        self.assertIn("power_state = D3cold", texto)
        self.assertIn("device = 0x7550", texto)
        self.assertIn("dormida", texto)
        self.assertNotIn("GT/s", texto)
        self.assertNotIn("temp1_input", texto)
        self.assertNotIn("gpu_busy_percent", texto)

    def test_despierta_entera(self):
        texto = _salida(estado="active", power_state="D0")
        self.assertIn("power/runtime_status = active", texto)
        self.assertIn("current_link_speed = 32.0 GT/s PCIe", texto)
        self.assertIn("temp1_input = 38000", texto)


if __name__ == "__main__":
    unittest.main()
