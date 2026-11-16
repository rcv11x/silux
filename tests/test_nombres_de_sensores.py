"""Los nombres del árbol de sensores: los hilos, y los canales sin nombre.

Dos cosas del 5800X3D. Los relojes y el uso de cada hilo se llamaban
«Core #N» en Sensores y «CPU N» en la página del procesador, y son hilos:
dieciséis en ocho núcleos. Y las tensiones de la placa salen «Tensión 0, 1,
2…»: el driver del Super I/O (it87) solo nombra las que son del propio chip
—3VSB, Vbat—; qué llega a las demás entradas lo decidió Gigabyte y el
kernel no lo sabe. No se les pone nombre: se dice que el driver no lo da.
"""

import os
import tempfile
import unittest
from unittest import mock

from silux.model import SensorKind, thread_name
from tests import qt
from tests.test_equipos import EQUIPOS, foto, volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestLosHilos(unittest.TestCase):

    def test_en_el_arbol_se_llaman_como_en_la_pagina_cpu(self):
        for carpeta in volcados():
            f = foto(carpeta)[0]
            por_clave = {s.key: s.label for s in f.sensors}
            with self.subTest(equipo=carpeta.name):
                for hilo in f.cpu.logical:
                    self.assertEqual(por_clave[f"clock/cpu{hilo.index}"],
                                     thread_name(hilo.index))
                self.assertFalse([e for e in por_clave.values() if "Core #" in e])


class TestLosCanalesSinNombre(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def test_el_volcado_tiene_el_caso(self):
        tensiones = [s for s in self.foto.sensors
                     if s.chip.startswith("it8") and s.kind is SensorKind.VOLTAGE]
        self.assertTrue([s for s in tensiones if s.unnamed])
        # Las que el driver sí nombra no llevan la marca.
        con_nombre = {s.label for s in tensiones if not s.unnamed}
        self.assertIn("3VSB", con_nombre)

    def test_lo_que_trae_etiqueta_no_se_marca(self):
        k10temp = [s for s in self.foto.sensors if s.chip == "k10temp"]
        self.assertTrue(k10temp)
        self.assertFalse([s for s in k10temp if s.unnamed])

    @unittest.skipIf(QApplication is None, "sin PySide6")
    def test_sensores_dice_que_el_driver_no_las_nombra(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        qt.app()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            ventana = MainWindow(Preferences().normalized())
            self.addCleanup(ventana.close)
            ventana.show()
            ventana._on_sample(self.foto)
            ventana.select_section("Sensores")
            pie = ventana.monitor_page.absent
            self.assertTrue(pie.isVisible())
            chip = next(s.chip for s in self.foto.sensors if s.unnamed
                        and s.kind is SensorKind.VOLTAGE)
            self.assertIn(chip, pie.text())

    @unittest.skipIf(QApplication is None, "sin PySide6")
    def test_en_un_equipo_sin_canales_sin_nombre_no_dice_nada(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage
        from silux.tracking import Tracker
        import dataclasses

        app = qt.app()
        pagina = MonitorPage(theme.palette_for(app, "dark"), Preferences().normalized(),
                             Tracker())
        self.addCleanup(pagina.cancelar_ordenes)
        nombrados = tuple(s for s in self.foto.sensors if not s.unnamed)
        pagina.apply(dataclasses.replace(self.foto, sensors=nombrados))
        self.assertEqual(pagina.absent.text(), "")


if __name__ == "__main__":
    unittest.main()
