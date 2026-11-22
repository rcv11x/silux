"""Las zonas térmicas de ACPI que no miden nada, y las temperaturas sin nombre.

En muchas placas de sobremesa el firmware declara zonas térmicas que no están
conectadas a ningún sensor y devuelve siempre el mismo número: 16.8 °C las
tres del X570 AORUS ELITE, 27.8 °C la del H510M. Salían en el árbol como una
temperatura más de la placa, y 16.8 °C dentro de una caja no lo ha medido
nadie. No se esconden —el equipo las publica— pero se dice que no son una
medida, y no cuentan como temperatura de nada.

Y las temperaturas de la placa que el driver numera sin decir dónde están
(`it87`, `gigabyte_wmi`) tenían el mismo problema que las tensiones y ningún
pie que lo dijera.
"""

import dataclasses
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from silux.model import SensorKind
from silux.providers.base import Draft
from silux.providers.hwmon import HwmonSensors
from tests import qt
from tests.test_equipos import EQUIPOS, foto, volcados
from tests.test_volcar_equipo import _herramienta

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _acpitz(f):
    return [s for s in f.sensors if s.chip == "acpitz"]


# Whether each dump's firmware fills its ACPI zone with a fixed number. Not
# every acpitz is filler: the author's T14 measures with it (33 °C, with the
# CPU), and «every acpitz is filler» came from our desktops. A new dump with
# a zone has to say which it is.
FILLER = {"5800x3d": True, "i5-10400": True, "i5-10400-turbo": True,
          "i5-1135g7": False, "i5-12450h": True, "i7-10700f": True,
          # 16.8 °C on both zones, flat, as on our desktops.
          "ryzen3-4100": True,
          # 27.8 and 29.8 °C, the Intel firmware's usual pair.
          "i5-3330": True,
          # Each follows its processor: 35.5 °C with the cores at 35, and
          # 74 °C with thinkpad_acpi's CPU at 74.
          "core2-p8400": False, "i5-8350u": False,
          # 67.5 °C with the core at 67, and 55 °C with ASUS's sensor at 55.
          "celeron-560": False, "i7-4710hq": False,
          # 27.8 and 29.8 °C again, with the package at 39.
          "celeron-g3900": True}


class TestLasZonasQueNoMiden(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fotos = {c.name: foto(c)[0] for c in volcados()}

    def test_los_volcados_tienen_el_caso(self):
        self.assertEqual({s.value for s in _acpitz(self.fotos["5800x3d"])}, {16.8})
        self.assertEqual({s.value for s in _acpitz(self.fotos["i5-10400"])}, {27.8})

    def test_se_marcan_y_solo_ellas(self):
        # A virtual machine has no thermal zone.
        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                zonas = _acpitz(f)
                if zonas:
                    self.assertIn(nombre, FILLER, "a new dump with acpitz: say if it measures")
                    self.assertEqual({s.placeholder for s in zonas}, {FILLER[nombre]})
                self.assertFalse([s.key for s in f.sensors
                                  if s.placeholder and s.chip != "acpitz"])

    def test_el_informe_lo_dice_al_lado_del_numero(self):
        from silux import report

        texto = report.build(self.fotos["5800x3d"])
        self.assertEqual(texto.count("16.8 °C (relleno del firmware"), 3, texto[-3000:])
        self.assertNotIn("47.6 °C (relleno", texto)

    def test_no_se_avisa_de_ellas(self):
        # A zone that measures keeps its limits, and its heat with them.
        for f in self.fotos.values():
            for sensor in (s for s in _acpitz(f) if s.placeholder):
                self.assertEqual(sensor.alarm_level, "ok")
                self.assertIsNone(sensor.heat)


class TestUnaZonaQueSiMide(unittest.TestCase):
    """En un portátil la zona de ACPI es un sensor de verdad, y puede pasar
    por 27.8 °C como por cualquier otro valor."""

    def _leer(self, proveedor, raiz, miligrados, critica=None):
        zona = raiz / "sys/class/hwmon/hwmon0"
        zona.mkdir(parents=True, exist_ok=True)
        (zona / "name").write_text("acpitz\n")
        (zona / "temp1_input").write_text(f"{miligrados}\n")
        if critica is not None:
            (zona / "temp1_crit").write_text(f"{critica}\n")
        draft = Draft()
        with mock.patch.dict(os.environ, {"SILUX_SYSROOT": str(raiz)}):
            from silux import sysroot
            sysroot.forget()
            self.addCleanup(sysroot.forget)
            proveedor.collect(draft)
        return next(s for s in draft.sensors if s.chip == "acpitz")

    def test_la_que_se_ha_visto_moverse_ya_no_se_marca(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            proveedor = HwmonSensors()
            self.assertFalse(self._leer(proveedor, raiz, 45000).placeholder)
            # Pasa por el valor de relleno después de haber marcado otro.
            self.assertFalse(self._leer(proveedor, raiz, 27800).placeholder)

    def test_la_de_relleno_pierde_sus_limites(self):
        # ACPI zones usually declare a critical trip point, filler or not.
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            relleno = self._leer(HwmonSensors(), raiz, 16800, critica=105000)
            self.assertTrue(relleno.placeholder)
            self.assertIsNone(relleno.heat)
            self.assertEqual(relleno.alarm_level, "ok")
            self.assertEqual(self._leer(HwmonSensors(), raiz, 35500, critica=105000).heat, 0.0)

    def test_y_la_que_arranca_en_el_valor_deja_de_marcarse_al_moverse(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            proveedor = HwmonSensors()
            self.assertTrue(self._leer(proveedor, raiz, 27800).placeholder)
            self.assertFalse(self._leer(proveedor, raiz, 31000).placeholder)
            self.assertFalse(self._leer(proveedor, raiz, 27800).placeholder)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPaginaDeSensores(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _pagina(self, f):
        from silux.settings import Preferences
        from silux.tracking import Tracker
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage

        app = qt.app()
        pagina = MonitorPage(theme.palette_for(app, "dark"), Preferences().normalized(),
                             Tracker())
        self.addCleanup(pagina.cancelar_ordenes)
        pagina.apply(f)
        return pagina

    def test_el_pie_dice_que_no_son_una_medida(self):
        for nombre, valor in (("5800x3d", "16.8"), ("i5-10400", "27.8")):
            with self.subTest(equipo=nombre):
                pie = self._pagina(self.fotos[nombre]).absent.text()
                self.assertIn("acpitz", pie)
                self.assertIn(valor, pie)

    def test_la_fila_lo_dice_al_pasar_el_raton_y_va_apagada(self):
        pagina = self._pagina(self.fotos["5800x3d"])
        arbol = pagina.tree
        fila = arbol._rows["acpitz/temp1"]
        buena = arbol._rows["k10temp/temp1"]
        self.assertIn("16.8", fila.toolTip(1))
        self.assertIn("firmware", fila.toolTip(1))
        self.assertNotIn("firmware", buena.toolTip(1))
        self.assertEqual(fila.foreground(1).color(), arbol._p.q("muted"))
        self.assertNotEqual(buena.foreground(1).color(), arbol._p.q("muted"))

    def test_el_pie_nombra_los_chips_con_temperaturas_sin_nombre(self):
        pie = self._pagina(self.fotos["5800x3d"]).absent.text()
        frase = next(f for f in pie.split("\n") if "temperatura" in f.lower()
                     and "gigabyte_wmi" in f)
        self.assertIn("it8688", frase)
        # El de relleno tiene su propia frase, y una tarjeta de red con una
        # sola temperatura no tiene nada que distinguir.
        self.assertNotIn("acpitz", frase)
        self.assertNotIn("r8169", frase)

    def test_en_el_intel_no_hay_nada_que_decir_de_temperaturas_sin_nombre(self):
        pie = self._pagina(self.fotos["i5-10400"]).absent.text()
        self.assertNotIn("drivetemp", pie)
        self.assertNotIn("coretemp", pie)

    def test_cada_cosa_en_su_renglon(self):
        # Tres explicaciones seguidas en un párrafo no las lee nadie.
        pie = self._pagina(self.fotos["5800x3d"]).absent.text()
        self.assertGreaterEqual(len(pie.split("\n")), 3, pie)


class TestNoCuentaComoTemperaturaDeNada(unittest.TestCase):

    def test_un_procesador_sin_sensor_propio_no_toma_la_de_relleno(self):
        # Sin coretemp ni k10temp, la temperatura del procesador caía a la
        # zona de ACPI: 27.8 °C clavados, con pinta de dato bueno.
        volcar = _herramienta()
        with volcar.mounted(EQUIPOS / "i5-10400") as raiz:
            # Como en un kernel sin el módulo `coretemp` cargado.
            for enlace in list((raiz / "sys/class/hwmon").iterdir()):
                if (enlace / "name").read_text().strip() == "coretemp":
                    shutil.rmtree(enlace.resolve())
                    enlace.unlink()
            from silux.collector import Collector
            recolector = Collector()
            try:
                recolector.snapshot()
                f = recolector.snapshot()
            finally:
                recolector.close()
        self.assertTrue(_acpitz(f))
        self.assertIsNone(f.cpu.temperature_c)


if __name__ == "__main__":
    unittest.main()
