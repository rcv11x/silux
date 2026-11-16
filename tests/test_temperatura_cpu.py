"""La temperatura del procesador, la misma en Inicio y en la página CPU.

Con los volcados del i5-10400: Inicio decía 33 °C —el sensor del
encapsulado— y la ficha de la página CPU 30, la media de los núcleos, con la
misma foto. Solo comprobado en Intel: en AMD el sensor del encapsulado es
Tctl, y hasta el volcado del 5800X3D no hay con qué mirarlo.
"""

import os
import re
import tempfile
import unittest
from unittest import mock

from tests.test_equipos import EQUIPOS, foto, volcados
from tests import qt

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaTemperaturaDeLaCpu(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {d.name: foto(d)[0] for d in volcados()}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def test_inicio_y_la_ficha_dicen_lo_mismo(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                ventana = MainWindow(Preferences().normalized())
                self.addCleanup(ventana.close)
                ventana._on_sample(f)
                ventana._on_sample(f)
                inicio = re.search(r"([\d.]+)\s*°C", ventana.home_page.cpu.cifras.text())
                ficha = ventana.cpu_page.live.tile_temp.value.text()
                self.assertIsNotNone(inicio)
                self.assertEqual(round(float(inicio.group(1))), int(ficha))

    def test_es_la_del_encapsulado_cuando_la_hay(self):
        # La media de los núcleos esconde el más caliente; el sensor del
        # encapsulado es el que mira el control de los ventiladores.
        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                if f.cpu.package_temp_c is not None:
                    self.assertEqual(f.cpu.temperature_c, f.cpu.package_temp_c)


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElConsumoQueFaltaSeExplica(unittest.TestCase):
    """En un volcado el contador de RAPL no avanza: la página CPU lo dice."""

    def test_la_pagina_cpu_ensena_por_que(self):
        from PySide6.QtWidgets import QLabel

        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        app = qt.app()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            f = foto(EQUIPOS / "i5-10400")[0]
            ventana = MainWindow(Preferences().normalized())
            self.addCleanup(ventana.close)
            ventana._on_sample(f)
            app.processEvents()
            textos = [l.text() for l in ventana.cpu_page.findChildren(QLabel)]
            self.assertIn(_("prov.rapl.frozen"), textos)
            self.assertEqual(ventana.cpu_page.live.tile_power.value.text(), "—")
