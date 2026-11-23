"""Home names a card by the link it reaches, like the Graphics header.

An idle card drops its link to save power: a laptop's RTX 4050 read
«PCIe 1.0 × 8» on Home, like a fault, while its Graphics header said
«PCIe 4.0 × 8».
"""

import unittest

from silux import render
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados


class TestTheSameLinkEverywhere(unittest.TestCase):

    def test_the_maximum_when_the_link_is_down(self):
        gpu = next(g for g in shared_snapshot(EQUIPOS / "i5-12450h").gpus if g.vendor == "NVIDIA")
        self.assertTrue(gpu.link.downgraded)
        self.assertEqual(render.gpu_link(gpu), "PCIe 4.0 × 8")

    def test_home_and_the_header_agree_on_every_dump(self):
        from tests import pantalla, qt
        from silux.ui.pages.graphics import GpuSection
        qt.app()
        for carpeta in volcados():
            f = shared_snapshot(carpeta)
            with self.subTest(equipo=carpeta.name), pantalla.Ventana(f) as ventana:
                ventana.select_section("Gráficos")
                cabeceras = [s.subtitle.text() for s in
                             ventana.stack.currentWidget().findChildren(GpuSection)]
                ventana.select_section("Inicio")
                inicio = "\n".join(pantalla.textos_de(ventana.stack.currentWidget()))
                for gpu, cabecera in zip(f.gpus, cabeceras):
                    enlace = render.gpu_link(gpu)
                    if enlace != render.DASH:
                        self.assertIn(enlace, cabecera)
                        if gpu.link.downgraded:
                            self.assertNotIn(render.pcie_link(gpu.link) + " ·", inicio)


if __name__ == "__main__":
    unittest.main()
