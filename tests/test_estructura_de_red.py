"""Red: el titular es la conexión, y una interfaz sin enlace no enseña guiones.

La cabecera decía «RTL8125 2.5GbE Controller», el nombre de un chip, donde
se viene a mirar por dónde se sale y con qué dirección; y sus insignias
repetían el subtítulo. La ficha de una tarjeta sin cable eran cinco guiones.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaPaginaDeRed(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: shared_snapshot(EQUIPOS / n) for n in ("5800x3d", "i5-10400")}

    def _pagina(self, ventana):
        ventana.select_section("Red")
        for _vez in range(3):
            self.app.processEvents()
        return ventana.network_page

    def test_el_titular_es_la_interfaz_y_su_direccion(self):
        from silux.ui.pages.network import main_interface

        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                pagina = self._pagina(ventana)
                principal, _todas = main_interface(f.network)
                self.assertEqual(pagina.title.text(), f"{principal.name} · {principal.ipv4}")
                self.assertIn(principal.model, pagina.subtitle.text())
                self.assertIn(render.link_summary(principal), pagina.subtitle.text())
                # Las insignias no repiten ni el titular ni el subtítulo.
                insignias = pantalla.textos_de(pagina.badges)
                self.assertNotIn(principal.name, insignias)
                self.assertNotIn(render.link_summary(principal), insignias)
                self.assertTrue(insignias)

    def test_una_tarjeta_sin_cable_no_ensena_guiones(self):
        f = self.fotos["5800x3d"]
        sin_cable = next(i for i in f.network if i.name == "enp5s0")
        self.assertIsNone(sin_cable.ipv4)
        with pantalla.Ventana(f) as ventana:
            pagina = self._pagina(ventana)
            rejilla = pagina._grids["enp5s0"]
            for clave in ("net.field.ipv4", "net.field.mask", "net.field.gateway",
                          "net.field.ipv6", "net.field.speed"):
                self.assertFalse(rejilla._values[_(clave)].isVisible(), clave)
            self.assertFalse([e for e in rejilla._values.values()
                              if e.isVisible() and e.full_text() == "—"])
            # Lo que sí tiene sigue: el estado, la dirección física, el modelo.
            self.assertTrue(rejilla._values[_("net.field.mac")].isVisible())
            self.assertTrue(rejilla._values[_("gpu.sensor.state")].isVisible())
            # Y la que tiene enlace no pierde nada.
            con_cable = pagina._grids["enp6s0"]
            self.assertTrue(con_cable._values[_("net.field.ipv4")].isVisible())
            self.assertTrue(con_cable._values[_("net.field.speed")].isVisible())


if __name__ == "__main__":
    unittest.main()
