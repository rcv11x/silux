"""Cómo está repartida la página de Gráficos: lo importante arriba y una vez.

Tenía seis fichas de cifra, y dos de ellas —«VRAM ocupada» y «Bus de
memoria»— eran de la memoria, que tiene su tarjeta justo debajo con lo
mismo. La temperatura salía en su ficha y otra vez en «Sensores». Y la
tarjeta «Tarjeta» mezclaba qué gráfica es con los números con que la
identifica el sistema, que se buscan una vez.
"""

import unittest

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaPaginaDeGraficos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _ficha(self, equipo):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(self.fotos[equipo])
        self.app.processEvents()
        return pagina._sections[0]

    def test_cuatro_fichas_y_en_este_orden(self):
        from silux.ui.widgets import StatTile

        ficha = self._ficha("5800x3d")
        fichas = sorted((f for f in ficha.findChildren(StatTile) if f.isVisible()),
                        key=lambda f: f.mapTo(ficha, f.rect().topLeft()).x())
        self.assertEqual([f.caption.text() for f in fichas],
                         [_(c).upper() for c in ("gpu.tile.usage", "gpu.tile.clock",
                                                 "gpu.tile.temp", "gpu.tile.power")])

    def test_la_memoria_esta_entera_en_su_tarjeta(self):
        ficha = self._ficha("5800x3d")
        gpu = self.fotos["5800x3d"].gpus[0]
        self.assertTrue(ficha.memory_bar.isVisible())
        usado = ficha.memory._values[_("gpu.vram.used")].full_text()
        self.assertIn(f"{gpu.memory.used_percent:.0f} %", usado)
        bus = ficha.memory._values[_("gpu.vram.busy")].full_text()
        self.assertIn("GB/s", bus)
        # Y cada dato de la memoria, una sola vez en la página.
        textos = [e.text() for e in ficha.findChildren(QLabel) if e.isVisible()]
        self.assertEqual(sum(1 for t in textos if t == _("gpu.vram.busy")), 1)
        self.assertFalse([t for t in textos if t.upper() == "VRAM OCUPADA"])

    def test_la_temperatura_del_nucleo_sale_una_vez(self):
        ficha = self._ficha("5800x3d")
        self.assertTrue(ficha.tile_temp.isVisible())
        self.assertNotIn(_("gpu.sensor.temp"), ficha.sensors._values)
        # Las de dentro de la tarjeta siguen en la suya.
        self.assertIn("°C", ficha.sensors._values[_("gpu.sensor.hotspot")].full_text())
        self.assertIn("°C", ficha.sensors._values[_("gpu.sensor.memtemp")].full_text())

    def test_la_barra_del_consumo_dice_que_es(self):
        ficha = self._ficha("5800x3d")
        self.assertTrue(ficha.power_bar.isVisible())
        leyenda = " ".join(e.text() for e in ficha.power_bar.findChildren(QLabel))
        self.assertIn(_("gpu.bar.power.now"), leyenda)
        self.assertIn(_("gpu.bar.power.room"), leyenda)
        self.assertNotIn("Sin usar", leyenda)
        # El consumo es lo primero de su tarjeta, pegado a la barra.
        filas = ficha.sensors._filas
        self.assertEqual(filas[_("gpu.sensor.power")], min(filas.values()))

    def test_los_identificadores_van_plegados_y_se_abren(self):
        ficha = self._ficha("5800x3d")
        gpu = self.fotos["5800x3d"].gpus[0]
        ranura = ficha.inventory._values[_("gpu.field.slot")]
        self.assertFalse(ranura.isVisible())
        self.assertNotIn(_("gpu.field.slot"), ficha.card._values)
        self.assertIn(_("gpu.field.driver"), ficha.card._values)
        ficha.inventory_fold.boton.click()
        self.app.processEvents()
        self.assertTrue(ranura.isVisible())
        self.assertEqual(ranura.full_text(), gpu.pci_slot)
        ficha.inventory_fold.boton.click()
        self.assertFalse(ranura.isVisible())

    def test_en_la_integrada_no_queda_nada_de_una_memoria_que_no_tiene(self):
        ficha = self._ficha("i5-10400")
        self.assertFalse(ficha.memory._values[_("gpu.vram.busy")].isVisible())
        self.assertFalse(ficha.tile_temp.isVisible())
        self.assertTrue(ficha.tile_usage.isVisible())


if __name__ == "__main__":
    unittest.main()
