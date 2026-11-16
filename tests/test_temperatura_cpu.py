"""La temperatura del procesador, la misma en Inicio y en la página CPU.

Con los volcados del i5-10400: Inicio decía 33 °C —el sensor del
encapsulado— y la ficha de la página CPU 30, la media de los núcleos, con la
misma foto. Comprobado también con el del 5800X3D, donde el sensor del
encapsulado es Tctl (`k10temp`) y no hay uno por núcleo.

Lo que no se ha visto en ninguna pieza es un `k10temp` con Tdie: lo publican
solo los Ryzen a los que AMD les suma un desplazamiento a Tctl (los 1700X y
1800X, los Threadripper de las dos primeras generaciones). Ese caso sale de
la documentación del kernel y se dice en su test.
"""

import os
import pathlib
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

    def test_la_ficha_solo_dice_nucleos_donde_hay_sensores_por_nucleo(self):
        # El i5-10400 tiene uno por núcleo y la ficha da su media debajo de
        # la del encapsulado. El 5800X3D solo tiene Tctl: «núcleos 59 °C»
        # debajo de «59 °C» era la misma cifra con un nombre que no es el suyo.
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        for nombre, con_nucleos in (("i5-10400", True), ("5800x3d", False)):
            with self.subTest(equipo=nombre):
                f = self.fotos[nombre]
                self.assertEqual(any(l.temp_c is not None for l in f.cpu.logical),
                                 con_nucleos)
                ventana = MainWindow(Preferences().normalized())
                self.addCleanup(ventana.close)
                ventana._on_sample(f)
                ventana._on_sample(f)
                detalle = ventana.cpu_page.live.tile_temp.detail.full_text()
                self.assertEqual("núcleos" in detalle, con_nucleos, detalle)

    def test_en_amd_es_tctl_y_no_la_del_troquel_de_los_nucleos(self):
        # El 5800X3D publica Tctl y Tccd1. Sin desplazamiento, Tctl es la
        # del procesador; Tccd1 es la de uno de sus troqueles, y va por debajo.
        f = self.fotos["5800x3d"]
        sondas = {s.label: s.value for s in f.sensors if s.chip == "k10temp"}
        self.assertEqual(set(sondas), {"Tctl", "Tccd1"})
        self.assertEqual(f.cpu.package_temp_c, round(sondas["Tctl"], 1))
        self.assertEqual(f.cpu.temperature_c, f.cpu.package_temp_c)


class TestTdieAntesQueTctl(unittest.TestCase):
    """Un `k10temp` con las dos: la del procesador es Tdie.

    No se ha visto en una pieza. Sale de Documentation/hwmon/k10temp.rst:
    «Tdie is the real measured temperature, and Tctl is used for fan
    control», y Tdie solo existe donde Tctl lleva un desplazamiento —20 °C
    en un Ryzen 7 1800X, 27 en un Threadripper 1950X—. Ahí Tctl no es una
    temperatura de nada, y era la que salía por ser la más alta.
    """

    def _con_k10temp(self, **sondas):
        from silux import sysroot
        from silux.providers.base import Draft
        from silux.providers.hwmon import HwmonSensors

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chip = pathlib.Path(tmp.name) / "sys/class/hwmon/hwmon0"
        chip.mkdir(parents=True)
        (chip / "name").write_text("k10temp\n")
        for n, (etiqueta, grados) in enumerate(sondas.items(), 1):
            (chip / f"temp{n}_label").write_text(etiqueta + "\n")
            (chip / f"temp{n}_input").write_text(f"{int(grados * 1000)}\n")
        parche = mock.patch.dict(os.environ, {sysroot.VARIABLE: tmp.name})
        parche.start()
        sysroot.olvidar()
        self.addCleanup(sysroot.olvidar)
        self.addCleanup(parche.stop)
        borrador = Draft()
        HwmonSensors().collect(borrador)
        return borrador.cpu_extra.get("package_temp_c")

    def test_con_las_dos_sale_tdie(self):
        self.assertEqual(self._con_k10temp(Tctl=72.0, Tdie=45.0), 45.0)

    def test_con_tctl_sola_sale_tctl(self):
        self.assertEqual(self._con_k10temp(Tctl=57.8, Tccd1=55.5), 57.8)


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
