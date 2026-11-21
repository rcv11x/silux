"""El consumo «de los núcleos», que en AMD es el de uno solo.

RAPL tiene un dominio `core` debajo del paquete. En Intel es PP0, la suma de
todos los núcleos. En AMD el kernel lo saca de un contador que es de cada
núcleo (`MSR_AMD_CORE_ENERGY_STATUS`) y lo lee en uno: el primero.

Se vio en el Ryzen 7 5800X3D: «núcleos 3,7 W» con el paquete en 64 W. Medido
con una carga atada a un hilo: en el núcleo 0, el dominio sube de 3,4 a 5,9 W;
en el núcleo 5 se queda en 3,7; con seis núcleos cargados y el paquete 22 W
más arriba, en 5,1. Enseñarlo como «núcleos» es un dato que parece bueno y no
lo es.

Con los volcados de los dos equipos. El volcado guarda una lectura del
contador, así que entre las dos fotos se le hace avanzar, que es lo que hace
solo en el equipo de verdad.
"""

import os
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.model import SensorKind
from tests import qt
from tests.test_equipos import EQUIPOS
from tests.test_volcar_equipo import _herramienta

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None

INTEL, AMD = "i5-10400", "5800x3d"
# Lo que avanza cada contador entre las dos fotos, en microjulios.
PAQUETE, DOMINIO = 60_000_000, 4_000_000


def foto_con_el_contador_andando(nombre: str):
    """La foto de un volcado con RAPL avanzando entre los dos muestreos, un
    segundo después: 60 J and 4 J in a few milliseconds were thousands of
    watts, which the impossible-watts check now drops."""
    from unittest import mock
    from silux.collector import Collector
    from silux.providers import rapl

    reloj = [1000.0]
    with _herramienta().montado(EQUIPOS / nombre) as raiz, \
            mock.patch.object(rapl.time, "monotonic", lambda: reloj[0]):
        recolector = Collector()
        try:
            recolector.snapshot()
            for contador in (raiz / "sys/devices/virtual/powercap").rglob("energy_uj"):
                paquete = contador.parent.name.count(":") == 1
                contador.write_text(
                    f"{int(contador.read_text()) + (PAQUETE if paquete else DOMINIO)}\n")
            reloj[0] += 1.0
            return recolector.snapshot()
        finally:
            recolector.close()


class TestElDominioDeLosNucleos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fotos = {n: foto_con_el_contador_andando(n) for n in (INTEL, AMD)}

    def test_el_paquete_sale_en_los_dos(self):
        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                self.assertGreater(f.cpu.power.package_w or 0, 0)
                self.assertIn("rapl", f.capabilities)

    def test_en_intel_es_la_suma_y_se_ensena(self):
        f = self.fotos[INTEL]
        self.assertGreater(f.cpu.power.core_w or 0, 0)
        self.assertIn("rapl/core_w", [s.key for s in f.sensors])
        self.assertNotIn("cpu.power.core_w", [n.path for n in f.notes])

    def test_en_amd_es_el_de_un_nucleo_y_no_se_ensena(self):
        f = self.fotos[AMD]
        self.assertIsNone(f.cpu.power.core_w)
        vatios = [s.key for s in f.sensors
                  if s.kind == SensorKind.POWER and s.key.startswith("rapl/")]
        self.assertEqual(vatios, ["rapl/package_w"])

    def test_en_amd_se_dice_por_que_falta(self):
        avisos = [n for n in self.fotos[AMD].notes if n.path == "cpu.power.core_w"]
        self.assertEqual(len(avisos), 1)
        self.assertTrue(avisos[0].message and avisos[0].hint)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaFicha(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto_con_el_contador_andando(n) for n in (INTEL, AMD)}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana(self, nombre):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences().normalized())
        self.addCleanup(ventana.close)
        ventana._on_sample(self.fotos[nombre])
        ventana._on_sample(self.fotos[nombre])
        return ventana

    def test_la_ficha_de_consumo_solo_desglosa_en_intel(self):
        from silux.i18n import _

        for nombre, sale in ((INTEL, True), (AMD, False)):
            with self.subTest(equipo=nombre):
                ficha = self._ventana(nombre).cpu_page.live.tile_power
                potencia = self.fotos[nombre].cpu.power
                self.assertEqual(ficha.value.text(), f"{potencia.package_w:.0f}")
                textos = render.power_breakdown(potencia) + render.power_tooltip(potencia)
                self.assertEqual(_("power.cores") in textos, sale)

    def test_el_aviso_sale_en_la_pagina_del_procesador(self):
        ventana = self._ventana(AMD)
        aviso = next(n for n in self.fotos[AMD].notes if n.path == "cpu.power.core_w")
        textos = [e.text() for e in ventana.cpu_page.findChildren(QLabel)]
        self.assertTrue(any(aviso.message in t for t in textos))


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestUnDatoUnMotivo(unittest.TestCase):
    """Revisión del autor: con el 5800X3D en un 5.15, la ficha de Consumo
    decía «requiere permisos» y el aviso de abajo «el contador no avanza»:
    dos motivos para el mismo dato. La ficha solo pone candado si el motivo
    es un permiso; si es otro, no da uno suyo."""

    @classmethod
    def setUpClass(cls):
        from tests.test_equipos import foto

        cls.app = qt.app()
        cls.parado = foto(EQUIPOS / AMD)[0]     # volcado: el contador no avanza

    def _ficha(self, muestra):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            ventana = MainWindow(Preferences().normalized())
            self.addCleanup(ventana.close)
            ventana._on_sample(muestra)
            return ventana.cpu_page.live.tile_power

    def test_con_el_contador_parado_no_dice_permisos(self):
        from silux.i18n import _

        self.assertIn("cpu.power", [n.path for n in self.parado.notes])
        self.assertIsNone(self.parado.permission_note("cpu.power"))
        ficha = self._ficha(self.parado)
        self.assertFalse(ficha.is_locked())
        self.assertNotIn(_("lock.detail"), ficha.detail.text())

    def test_sin_permisos_para_leerlo_es_candado(self):
        """La nota que deja RaplPower cuando energy_uj es de root (desde 5.10)."""
        import dataclasses
        from silux.i18n import _
        from silux.model import Need, Note, PrivilegedState

        nota = Note("cpu.power", Need.ROOT, _("prov.rapl.denied"), _("prov.rapl.denied.hint"),
                    _("what.cpu.power"))
        sin = dataclasses.replace(
            self.parado, notes=tuple(n for n in self.parado.notes if n.path != "cpu.power")
            + (nota,), privileged=PrivilegedState(supported=True))
        self.assertIs(sin.permission_note("cpu.power"), nota)
        self.assertTrue(self._ficha(sin).is_locked())
