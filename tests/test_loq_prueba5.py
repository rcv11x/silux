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


if __name__ == "__main__":
    unittest.main()
