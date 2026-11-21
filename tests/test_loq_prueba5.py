"""What a Lenovo LOQ 15IRH8 laptop's prueba5 report showed, on its dump.

A hybrid laptop: an Intel UHD inside the processor and an NVIDIA RTX 4050
with the proprietary driver, one battery the kernel calls BAT1 and held at
its charge limit, and a memory controller whose counters the helper could
not open.
"""

import unittest

from silux.i18n import _
from silux.model import Need
from silux.privileged.client import PmuUnsupported
from silux.providers import imc
from silux.providers.base import Draft
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

DUMP = EQUIPOS / "i5-12450h"


class TestOnItsPages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.foto = foto(DUMP)[0]

    def _texts(self, seccion):
        with pantalla.Ventana(self.foto) as ventana:
            ventana.select_section(seccion)
            return pantalla.textos_de(ventana.stack.currentWidget())

    def test_an_nvidia_without_modesetting_has_unpublished_outputs(self):
        textos = self._texts("Gráficos")
        self.assertIn(_("gpu.displays.unpublished"), textos)
        self.assertNotIn(_("gpu.displays.none"), textos)

    def test_an_integrated_card_no_api_uses(self):
        # Vulkan lists the NVIDIA and llvmpipe, OpenGL's context is the NVIDIA's.
        textos = self._texts("Gráficos")
        self.assertIn(_("gpu.apis.notseen"), textos)
        self.assertNotIn(_("gpu.apis.none"), textos)

    def test_a_battery_held_on_the_charger_has_no_runtime_dash(self):
        self.assertEqual(self.foto.batteries[0].status, "bat.status.held")
        textos = self._texts("Batería")
        self.assertIn(_("bat.left.oncharger"), textos)

    def test_its_only_battery_is_not_battery_2(self):
        aparatos = {s.device for s in self.foto.sensors if s.chip == "BAT1"}
        self.assertEqual(aparatos, {_("sensor.dev.battery")})


class TestItsModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foto = foto(DUMP)[0]


    def test_its_caches_go_p_before_e_within_a_level(self):
        qt.app()
        from silux.ui.pages.caches import CachesPage
        claves = list(CachesPage._group(self.foto))
        self.assertEqual([(nivel, tipo, nucleo) for nivel, tipo, nucleo, _tam in claves],
                         [(1, "data", "performance"), (1, "data", "efficiency"),
                          (1, "instruction", "performance"), (1, "instruction", "efficiency"),
                          (2, "unified", "performance"), (2, "unified", "efficiency"),
                          (3, "unified", "")])

class TestTheMemoryControllerItCouldNotOpen(unittest.TestCase):

    def test_it_says_so_with_the_helpers_reason(self):
        class Helper:
            def connected(self):
                return True

            def imc(self):
                raise PmuUnsupported("perf_event_open: Invalid argument")

        from tests.interval import fake_clock
        from silux import volcado
        with volcado.montado(DUMP), fake_clock():
            proveedor = imc.ImcTraffic(client=Helper())
            proveedor.collect(Draft())
            razon = proveedor.unavailable_reason()
        self.assertIs(razon[1], Need.ERROR)
        self.assertEqual(razon[2], _("prov.imc.unopened"))
        self.assertIn("Invalid argument", razon[5])


class TestTheSpdHint(unittest.TestCase):
    """Its SPD hub had spd5118 bound, and the hint said to load spd5118 for
    «the 1 modules» of a laptop with two."""

    def _hints(self, quitar_hwmon=False):
        import shutil
        import subprocess
        from unittest import mock
        from silux import volcado
        from silux.providers.privileged_memory import PrivilegedMemory

        hecho = subprocess.CompletedProcess([], 0, stdout="/lib/modules/spd5118.ko\n")
        with volcado.montado(DUMP) as raiz:
            if quitar_hwmon:
                # As before the driver binds: the bus lists the device alone.
                shutil.rmtree(raiz / "sys/bus/i2c/devices/0-0050/hwmon")
            with mock.patch("silux.system_deps.program_path", return_value="/usr/bin/modinfo"), \
                    mock.patch("subprocess.run", return_value=hecho):
                return list(PrivilegedMemory._spd_hint())

    def test_no_driver_to_load_when_it_is_bound(self):
        self.assertEqual(self._hints(), [])

    def test_one_device_without_its_driver_is_one_module(self):
        pistas = self._hints(quitar_hwmon=True)
        self.assertEqual([p.module for p in pistas], ["spd5118"])
        self.assertEqual(pistas[0].provides, _("prov.hint.spd.one"))


if __name__ == "__main__":
    unittest.main()
