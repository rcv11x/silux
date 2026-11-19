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
                         [_(c) for c in ("gpu.tile.usage", "gpu.tile.clock",
                                         "gpu.tile.temp", "gpu.tile.power")])

    def test_la_cifra_empieza_donde_su_etiqueta_y_lleva_la_unidad_pegada(self):
        """La cifra iba arrimada a su unidad por la derecha, con el hueco
        reservado delante: «0 MHz» de la gráfica parada empezaba tres cifras
        más allá que su etiqueta. Ahora empieza en el borde de la etiqueta, y
        el hueco queda detrás de la unidad."""
        from PySide6.QtGui import QFontMetrics
        from silux.ui import theme
        from silux.ui.widgets import StatTile

        ficha = self._ficha("5800x3d")
        for tile in (f for f in ficha.findChildren(StatTile) if f.isVisible()):
            with self.subTest(ficha=tile.caption.text()):
                cifra = tile.value.mapTo(tile, tile.value.contentsRect().topLeft()).x()
                etiqueta = tile.caption.mapTo(tile, tile.caption.contentsRect().topLeft()).x()
                self.assertEqual(cifra, etiqueta)
                from PySide6.QtCore import Qt
                self.assertTrue(tile.value.alignment() & Qt.AlignmentFlag.AlignLeft)
                # El ancho reservado lleva la unidad: lo que cabe detrás.
                numero = QFontMetrics(tile.value.font()).horizontalAdvance(tile.value.text())
                self.assertGreaterEqual(tile.value.width(),
                                        numero + tile.value.ancho_de_la_unidad())
                self.assertTrue(tile.unit.text())
                self.assertTrue(tile.unit.isHidden(), "la unidad la pinta la cifra")

    def test_sin_ficha_de_temperatura_las_otras_tres_no_dejan_hueco(self):
        """La integrada de Intel no publica temperatura y su ficha se esconde;
        su celda se quedaba reservada, vacía, entre Frecuencia y Consumo."""
        from silux.ui.widgets import StatTile

        ficha = self._ficha("i5-10400")
        self.assertFalse(ficha.tile_temp.isVisible())
        fichas = sorted((f for f in ficha.findChildren(StatTile) if f.isVisible()),
                        key=lambda f: f.mapTo(ficha, f.rect().topLeft()).x())
        self.assertEqual([f.caption.text() for f in fichas],
                         [_(c) for c in ("gpu.tile.usage", "gpu.tile.clock",
                                         "gpu.tile.power")])
        # En una fila, con el mismo hueco entre cada dos y hasta los bordes.
        self.assertEqual(len({f.mapTo(ficha, f.rect().topLeft()).y() for f in fichas}), 1)
        izquierdas = [f.mapTo(ficha, f.rect().topLeft()).x() for f in fichas]
        derechas = [x + f.width() for x, f in zip(izquierdas, fichas)]
        huecos = [b - a for a, b in zip(derechas, izquierdas[1:])]
        self.assertEqual(len(set(huecos)), 1, huecos)
        self.assertEqual(izquierdas[0], 0)
        self.assertEqual(derechas[-1], ficha.width())
        self.assertLessEqual(max(f.width() for f in fichas) - min(f.width() for f in fichas), 1)

    def test_la_ficha_que_vuelve_recupera_su_sitio(self):
        """La sección se reutiliza: tras una tarjeta sin temperatura puede
        venir una que la tiene."""
        from silux.ui.widgets import StatTile

        ficha = self._ficha("i5-10400")
        ficha.apply(self.fotos["5800x3d"].gpus[0])
        self.app.processEvents()
        fichas = sorted((f for f in ficha.findChildren(StatTile) if f.isVisible()),
                        key=lambda f: f.mapTo(ficha, f.rect().topLeft()).x())
        self.assertEqual([f.caption.text() for f in fichas],
                         [_(c) for c in ("gpu.tile.usage", "gpu.tile.clock",
                                         "gpu.tile.temp", "gpu.tile.power")])
        self.assertEqual(len({f.mapTo(ficha, f.rect().topLeft()).y() for f in fichas}), 1)

    def test_el_motor_parado_dice_en_reposo_y_no_cero_megahercios(self):
        """Una integrada de Intel en reposo profundo marca 0 MHz, y «Núcleo
        0 MHz» se leía como una lectura rota."""
        import dataclasses

        ficha = self._ficha("i5-10400")
        gpu = self.fotos["i5-10400"].gpus[0]
        self.assertEqual(ficha.clocks._values[_("gpu.clock.core")].full_text(),
                         render.hz(gpu.clocks.core_hz))
        parada = dataclasses.replace(
            gpu, clocks=dataclasses.replace(gpu.clocks, core_hz=0))
        ficha.apply(parada)
        self.app.processEvents()
        self.assertEqual(ficha.clocks._values[_("gpu.clock.core")].full_text(), _("gpu.clock.idle"))
        textos = [e.text() for e in ficha.findChildren(QLabel) if e.isVisible()]
        self.assertNotIn("0 MHz", textos)
        self.assertIn(_("gpu.clock.idle"), [e.text() for e in ficha.tile_clock.findChildren(QLabel)])

    def test_el_uso_del_motor_de_video_se_llama_igual_que_en_sensores(self):
        self.assertEqual(_("gpu.sensor.videouse"), "Uso del motor de video")
        self.assertEqual(_("gpu.sensor.videouse"), _("sensor.gpu.video"))

    def test_el_uso_del_video_sale_una_vez_y_es_una_barra(self):
        """En «Ahora mismo», con lo que cuenta en el nombre; la fila de
        «Consumo y temperaturas» que decía lo mismo se va."""
        from silux.ui.pages.graphics import BARRAS_DE_MOTOR
        ficha = self._ficha("5800x3d")
        visibles = [e.text() for e in ficha.findChildren(QLabel) if e.isVisible()]
        self.assertNotIn(_("gpu.sensor.videouse"), visibles)
        self.assertEqual(visibles.count(_(BARRAS_DE_MOTOR["engine.video"])), 1)

    def test_una_integrada_de_intel_no_ensena_guiones_de_lo_que_solo_cuenta_amd(self):
        """«Unidades de rasterizado —», «Motores de sombreado —», «SoC —»,
        «Perfil de rendimiento —», «Voltaje —» y «Voltaje del SoC —»: seis
        guiones de datos que en una UHD no existen. Se esconden y se nombran."""
        ficha = self._ficha("i5-10400")
        gpu = self.fotos["i5-10400"].gpus[0]
        self.assertEqual((gpu.driver, gpu.integrated), ("i915", True))
        for rejilla, pie, claves in (
                (ficha.card, ficha.card_pie, ("gpu.field.rops", "gpu.field.shaders")),
                (ficha.clocks, ficha.clocks_pie, ("SoC", "gpu.clock.profile",
                                                  "gpu.clock.link", "gpu.clock.linkmax")),
                # «Consumo y temperaturas» se va entera en esta pieza (no le
                # queda nada propio) y su pie pasa debajo de la fila.
                (ficha.sensors, ficha.sensors_outside, ("gpu.sensor.voltage", "gpu.sensor.vsoc"))):
            for clave in claves:
                with self.subTest(campo=clave):
                    self.assertFalse(rejilla._values[_(clave)].isVisible())
                    self.assertFalse(rejilla._names[_(clave)].isVisible())
            self.assertTrue(pie.isVisible())
        self.assertIn(_("gpu.na.intel.card"), ficha.card_pie.text())
        self.assertIn(_("gpu.na.intel.clocks"), ficha.clocks_pie.text())
        self.assertIn(_("gpu.na.intel.sensors"), ficha.sensors_outside.toolTip())
        # Lo que sí tiene se sigue viendo: sus unidades de ejecución.
        self.assertEqual(ficha.card._values[_("gpu.field.compute")].full_text(),
                         render.compute_units(gpu))
        self.assertIn("23", render.compute_units(gpu))
        # Y ningún guion queda en la tarjeta ni en los relojes.
        for rejilla in (ficha.card, ficha.clocks):
            visibles = [v.full_text() for v in rejilla._values.values() if v.isVisible()]
            self.assertNotIn(render.DASH, visibles)

    def test_en_la_amd_esas_filas_siguen_con_su_dato(self):
        ficha = self._ficha("5800x3d")
        for rejilla, clave in ((ficha.card, "gpu.field.rops"), (ficha.card, "gpu.field.shaders"),
                               (ficha.clocks, "SoC"), (ficha.clocks, "gpu.clock.profile"),
                               (ficha.sensors, "gpu.sensor.voltage"),
                               (ficha.sensors, "gpu.sensor.vsoc")):
            with self.subTest(campo=clave):
                valor = rejilla._values[_(clave)]
                self.assertTrue(valor.isVisible())
                self.assertNotEqual(valor.full_text(), render.DASH)
        self.assertFalse(ficha.card_pie.isVisible())

    def test_el_uso_del_motor_de_video_lleva_candado_si_falta_por_permisos(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        foto = self.fotos["i5-10400"]
        self.assertIsNotNone(foto.permission_note("gpus.0.usage"))
        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(foto)
        self.app.processEvents()
        ficha = pagina._sections[0]
        self.assertTrue(ficha.sensors.is_locked(_("gpu.sensor.videouse")))
        pedidos = []
        ficha.elevation_requested.connect(lambda: pedidos.append(1))
        ficha.sensors._candados[_("gpu.sensor.videouse")].clicked.emit()
        self.assertEqual(pedidos, [1])

    def test_el_tamano_de_cada_monitor_sale_de_sus_milimetros(self):
        """El AORUS de 27 salía «26.6"» y el LG «27.2"», de centímetros
        enteros. El EDID de los dos trae la medida al milímetro."""
        for equipo, esperado in (("5800x3d", ['26.7"', '27.0"']), ("i5-10400", ['21.5"'])):
            with self.subTest(equipo=equipo):
                ficha = self._ficha(equipo)
                self.assertEqual([fila[4].full_text() for fila in ficha.displays._cells],
                                 esperado)

    def test_ahora_mismo_junta_las_barras_cada_una_con_su_nombre(self):
        """Las tres de la memoria y el consumo, y debajo las de los motores
        que esta tarjeta deja medir (test_barras_de_motores)."""
        ficha = self._ficha("5800x3d")
        gpu = self.fotos["5800x3d"].gpus[0]
        self.assertTrue(ficha.now_card.isVisible())
        self.assertEqual(ficha.now.visible_rows(),
                         [_("gpu.now.vram"), _("gpu.now.power"), _("gpu.now.bus"),
                          _("gpu.now.engine.render"), _("gpu.now.engine.video")])
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
        # El consumo está en su ficha y en su barra, no otra vez en la tabla
        # de debajo; y la memoria ocupada, solo en su barra.
        self.assertNotIn(_("gpu.now.power"), ficha.sensors._values)
        self.assertNotIn(_("gpu.now.vram"), ficha.memory._values)
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
        # Sin VRAM propia no hay nada de la memoria «ahora mismo»: ni VRAM,
        # ni consumo de la tarjeta, ni bus. Lo que queda son los motores, una
        # barra cada uno, con candado sin permisos (test_barras_de_motores).
        for clave in ("gpu.now.vram", "gpu.now.power", "gpu.now.bus"):
            self.assertNotIn(_(clave), ficha.now.visible_rows())
        self.assertEqual(ficha.now.visible_rows(),
                         ["Render / 3D", "Video (codificar y decodificar)",
                          "Mejora de video", "Copia"])
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
