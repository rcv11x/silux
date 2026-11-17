"""Cómo está repartida la página de Gráficos: lo importante arriba y una vez.

Tenía seis fichas de cifra, y dos de ellas —«VRAM ocupada» y «Bus de
memoria»— eran de la memoria, que tiene su tarjeta justo debajo con lo
mismo. La temperatura salía en su ficha y otra vez en «Sensores». Y la
tarjeta «Tarjeta» mezclaba qué gráfica es con los números con que la
identifica el sistema, que se buscan una vez.
"""

import unittest

from silux import render
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

    def test_ahora_mismo_junta_las_tres_barras_cada_una_con_su_nombre(self):
        ficha = self._ficha("5800x3d")
        gpu = self.fotos["5800x3d"].gpus[0]
        self.assertTrue(ficha.now_card.isVisible())
        self.assertEqual(ficha.now.visible_rows(),
                         [_("gpu.now.vram"), _("gpu.now.power"), _("gpu.now.bus")])
        vram = ficha.now.text_of(_("gpu.now.vram"))
        self.assertIn(f"{gpu.memory.used_percent:.0f} %", vram)
        self.assertIn(render.size(gpu.memory.total_bytes), vram)
        self.assertIn(render.watts(gpu.power_cap_w), ficha.now.text_of(_("gpu.now.power")))
        self.assertIn("GB/s", ficha.now.text_of(_("gpu.now.bus")))
        # La barra mide lo que dice su cifra.
        barra = ficha.now._rows[_("gpu.now.power")][1]
        self.assertAlmostEqual(barra.fraction(), gpu.power_w / gpu.power_cap_w, places=3)

    def test_va_justo_debajo_de_las_fichas_y_ocupa_poco(self):
        ficha = self._ficha("5800x3d")
        def alto(w):
            return w.mapTo(ficha, w.rect().topLeft()).y()
        self.assertGreater(alto(ficha.now_card), alto(ficha.tile_usage))
        self.assertLess(alto(ficha.now_card), alto(ficha.card))
        # Tres renglones y un título: menos que una ficha de cifra y media.
        self.assertLess(ficha.now_card.height(), ficha.tile_usage.height() * 1.5)

    def test_las_tarjetas_de_abajo_no_repiten_lo_que_dicen_las_barras(self):
        ficha = self._ficha("5800x3d")
        textos = [e.text() for e in ficha.findChildren(QLabel) if e.isVisible()]
        for repetido in ("En uso", "Límite de consumo"):
            self.assertNotIn(repetido, textos)
        self.assertEqual(textos.count(_("gpu.now.power")), 1)
        self.assertEqual(textos.count(_("gpu.now.vram")), 1)
        from silux.ui.widgets import StackedBar
        self.assertEqual([b for b in ficha.findChildren(StackedBar) if b.isVisible()], [])
        # Lo que no está en las barras sigue en su tarjeta.
        self.assertIn(_("gpu.vram.type"), ficha.memory._values)
        self.assertIn(_("gpu.sensor.state"), ficha.sensors._values)

    def test_la_temperatura_del_nucleo_sale_una_vez(self):
        ficha = self._ficha("5800x3d")
        self.assertTrue(ficha.tile_temp.isVisible())
        self.assertNotIn(_("gpu.sensor.temp"), ficha.sensors._values)
        # Las de dentro de la tarjeta siguen en la suya.
        self.assertIn("°C", ficha.sensors._values[_("gpu.sensor.hotspot")].full_text())
        self.assertIn("°C", ficha.sensors._values[_("gpu.sensor.memtemp")].full_text())

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
        # Sin VRAM propia y sin permisos no hay nada que medir «ahora
        # mismo»: la tarjeta entera no sale.
        self.assertEqual(ficha.now.visible_rows(), [])
        self.assertFalse(ficha.now_card.isVisible())
        self.assertFalse(ficha.tile_temp.isVisible())
        self.assertTrue(ficha.tile_usage.isVisible())


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaTablaDeCodecs(unittest.TestCase):
    """Era un bloque más oscuro que su tarjeta, con un punto gris donde la
    tarjeta no acelera un códec: había que mirar dos veces para verlo."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def _ficha(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        self.paleta = theme.palette_for(self.app, "dark")
        pagina = GraphicsPage(self.paleta, Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(self.foto)
        self.app.processEvents()
        return pagina._sections[0]

    def test_el_volcado_tiene_de_los_dos(self):
        codecs = self.foto.gpus[0].codecs
        self.assertTrue([c for c in codecs if c.encode])
        self.assertTrue([c for c in codecs if not c.encode])

    def test_si_y_no_son_dos_simbolos_distintos_con_su_tono_y_su_texto(self):
        ficha = self._ficha()
        for fila, codec in enumerate(self.foto.gpus[0].codecs):
            for columna, puede in ((1, codec.decode), (2, codec.encode)):
                celda = ficha.codecs._cells[fila][columna]
                with self.subTest(codec=codec.name, columna=columna):
                    self.assertEqual(celda.full_text(), "✓" if puede else "✗")
                    self.assertEqual(celda.property("tone"), "yes" if puede else "no")
                    # Y dicho con palabras, para quien no distinga el color.
                    self.assertEqual(celda.toolTip(),
                                     _("gpu.codec.yes" if puede else "gpu.codec.no"))

    def test_el_no_no_lleva_el_color_de_un_fallo_ni_el_de_un_aviso(self):
        from silux.ui import theme

        hoja = theme.stylesheet(self.paleta if hasattr(self, "paleta")
                                else theme.palette_for(self.app, "dark"))
        regla = hoja.split('QLabel#FieldName[tone="no"]')[1].split("}")[0]
        paleta = theme.palette_for(self.app, "dark")
        self.assertNotIn(paleta.warn, regla)
        self.assertNotIn(f"color: {paleta.crit};", regla)
        self.assertIn("rgba(", regla)
        si = hoja.split('QLabel#FieldName[tone="yes"]')[1].split("}")[0]
        self.assertIn(paleta.ok, si)

    def test_la_tabla_no_es_un_bloque_del_color_de_la_pagina(self):
        ficha = self._ficha()
        self.assertEqual(ficha.codecs.widget().objectName(), "TableBody")
        from silux.ui import theme
        self.assertIn("QWidget#TableBody { background: transparent; }",
                      theme.stylesheet(theme.palette_for(self.app, "dark")))


if __name__ == "__main__":
    unittest.main()
