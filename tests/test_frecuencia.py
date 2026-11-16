"""La frecuencia del procesador, igual en todas partes y dibujada donde está.

Con los dos volcados del i5-10400: uno con el turbo apagado y otro con el
turbo encendido, que es el vaivén real que hace `auto-cpufreq` en ese equipo
en cuanto hay carga. Comprobado solo en Intel: el techo del silicio en AMD
sale de CPPC (`providers/cppc.py`), y hasta que esté el volcado del 5800X3D
no hay con qué mirarlo.
"""

import dataclasses
import os
import tempfile
import unittest
from unittest import mock

from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

APAGADO, ENCENDIDO = "i5-10400", "i5-10400-turbo"


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaGraficaDeFrecuencia(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in (APAGADO, ENCENDIDO)}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ficha(self, secuencia):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.cpulive import CpuLiveSection

        vivo = CpuLiveSection(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(vivo.deleteLater)
        escalas = []
        for i, nombre in enumerate(secuencia):
            f = self.fotos[nombre]
            vivo.apply(dataclasses.replace(f, monotonic_ns=f.monotonic_ns + i * 10**9))
            grafica = vivo.tile_freq.chart
            escalas.append(grafica._escala_visible(list(grafica._values))
                           if len(grafica._values) > 1 else None)
        return vivo.tile_freq, escalas

    def test_con_el_turbo_apagado_la_curva_no_va_pegada_al_techo(self):
        # Era la barra vertical: con el gobernador `performance` la frecuencia
        # está siempre en el techo que aplica el kernel, y si ese es el techo
        # del eje, el relleno ocupa todo el alto.
        ficha, escalas = self._ficha([APAGADO] * 4)
        suelo, techo = escalas[-1]
        actual = self.fotos[APAGADO].cpu.types[0].clocks.current_hz / 1e9
        self.assertLess((actual - suelo) / (techo - suelo), 0.9)

    def test_el_eje_no_cambia_cuando_el_turbo_va_y_viene(self):
        ficha, escalas = self._ficha([APAGADO] * 3 + [ENCENDIDO] * 3 + [APAGADO] * 3)
        self.assertEqual(len(set(e for e in escalas if e)), 1, escalas)

    def test_las_muestras_con_turbo_no_se_recortan_al_techo_sin_turbo(self):
        # Con el eje siguiendo al techo del momento, al volver a apagarse el
        # turbo las muestras de 4,0 GHz se dibujaban a la altura de las de 2,9.
        ficha, escalas = self._ficha([ENCENDIDO] * 3 + [APAGADO] * 3)
        suelo, techo = escalas[-1]
        self.assertGreaterEqual(techo, max(ficha.chart._values))

    def test_la_cifra_del_rango_es_la_del_eje(self):
        from silux import render

        ficha, escalas = self._ficha([APAGADO] * 3)
        suelo, techo = escalas[-1]
        self.assertEqual(ficha.detail.full_text(),
                         f"{render.hz(suelo * 1e9)} – {render.hz(techo * 1e9)}")


if __name__ == "__main__":
    unittest.main()
