"""Las gráficas de las tarjetas de Inicio dibujan lo que se midió.

Una curva pequeña sin eje ni cifras no se puede contrastar a ojo: si
dibujara otra cosa —la muestra anterior, un valor repetido, el reloj donde
dice uso— no se notaría. Aquí se le dan a la ventana tres fotos seguidas de
este equipo y se mira que cada gráfica haya guardado, en orden, justo el
dato de cada foto.

Lee el hardware de quien ejecuta la suite y no exige nada concreto: lo que
una foto no trae no se compara.
"""

import os
import tempfile
import time
import unittest
from unittest import mock

from tests import qt

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasGraficasDeInicio(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from silux.collector import Collector

        cls.app = qt.app()
        recolector = Collector()
        try:
            cls.fotos = [recolector.sample()]
            for _vez in range(2):
                time.sleep(0.2)
                cls.fotos.append(recolector.snapshot())
        finally:
            recolector.close()

    def setUp(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)
        self.ventana = MainWindow(Preferences().normalized())
        self.addCleanup(self.ventana.close)
        for f in self.fotos:
            self.ventana._on_sample(f)
        self.inicio = self.ventana.home_page

    def _comparar(self, grafica, esperados):
        esperados = [float(v) for v in esperados if v is not None]
        if not esperados:
            self.skipTest("este equipo no publica ese dato")
        self.assertEqual(list(grafica._values), esperados)

    def test_la_del_procesador_es_su_uso(self):
        self._comparar(self.inicio.cpu.grafica, [f.cpu.usage_percent for f in self.fotos])

    def test_la_de_la_grafica_es_su_uso_o_su_reloj(self):
        if not self.fotos[0].gpus:
            self.skipTest("este equipo no tiene gráfica")
        gpus = [f.gpus[0] for f in self.fotos]
        if all(g.busy_percent is not None for g in gpus):
            self._comparar(self.inicio.gpu.grafica, [g.busy_percent for g in gpus])
        elif all(g.busy_percent is None and g.temp_c is None and g.power_w is None
                 for g in gpus):
            self._comparar(self.inicio.gpu.grafica,
                           [g.clocks.core_hz / 1e6 if g.clocks.core_hz else None for g in gpus])
        else:
            self.skipTest("el uso de la gráfica va y viene entre fotos")

    def test_la_de_temperaturas_es_la_de_la_pieza_que_encabeza(self):
        # La curva es de la misma pieza que la cifra grande de encima: la más
        # caliente, que no cede el sitio por décimas (MARGEN_DEL_TITULAR).
        from silux.ui.pages.home import MARGEN_DEL_TITULAR

        def lecturas(f):
            todas = {"cpu": f.cpu.temperature_c,
                     "gpu": f.gpus[0].temp_c if f.gpus else None}
            discos = [d.temp_c for d in f.disks if d.temp_c is not None]
            todas["disco"] = max(discos) if discos else None
            return {k: v for k, v in todas.items() if v is not None}

        esperadas, titular = [], None
        for f in self.fotos:
            ahora = lecturas(f)
            if not ahora:
                self.skipTest("este equipo no publica temperaturas")
            lider = max(ahora, key=ahora.get)
            if titular not in ahora or ahora[lider] - ahora[titular] >= MARGEN_DEL_TITULAR:
                titular = lider
            esperadas.append(ahora[titular])
        self._comparar(self.inicio.temperaturas.grafica, esperadas)

    def test_la_de_red_es_lo_que_mueve_la_interfaz_principal(self):
        from silux.ui.pages.network import main_interface

        ritmos = []
        for f in self.fotos:
            principal, _todas = main_interface(f.network)
            ritmos.append(principal.traffic.total_rate_bps if principal else None)
        self._comparar(self.inicio.red.grafica, ritmos)

    def test_una_muestra_por_foto_y_no_mas(self):
        for tarjeta in (self.inicio.cpu, self.inicio.temperaturas):
            self.assertLessEqual(len(tarjeta.grafica._values), len(self.fotos))


if __name__ == "__main__":
    unittest.main()
