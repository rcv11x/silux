"""Detalles de cinco páginas que decían algo raro (lista del autor, 19 de
noviembre). Cada uno con la página montada de verdad y un volcado."""

import unittest

from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _texto(clave_de_seccion, f):
    """Lo que dice una página, como lo cuenta el informe completo."""
    from silux.ui import full_report
    with pantalla.Ventana(f) as ventana:
        ventana.select_section(clave_de_seccion)
        QApplication.processEvents()
        pagina = ventana.stack.currentWidget()
        full_report.abrir_plegables(pagina)
        QApplication.processEvents()
        return full_report.page_text(pagina)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestDetalles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.i5 = foto(EQUIPOS / "i5-10400")[0]
        cls.amd = foto(EQUIPOS / "5800x3d")[0]

    def test_la_tarjeta_de_red_empieza_por_su_marca(self):
        # «RTL8111/8168/8211/8411 PCI Express…» no decía que es una Realtek.
        for clave in ("nav.network", "nav.home", "nav.board"):
            with self.subTest(pagina=clave):
                texto = _texto(clave, self.i5)
                self.assertIn("Realtek RTL8111/8168/8211/8411", texto)
                self.assertNotIn("Semiconductor", texto)
        self.assertIn("Intel I211 Gigabit", _texto("nav.board", self.amd))

    def test_red_dice_el_tipo_traducido_y_cero_perdidos(self):
        from silux.i18n import _
        texto = _texto("nav.network", self.i5)
        self.assertIn(f"- {_('memory.field.type')}: Ethernet", texto)
        self.assertNotIn(": ethernet", texto)
        # La ficha decía «sin pérdidas» y la tabla «—».
        self.assertIn(_("net.nolost"), texto)
        fila = next(l for l in texto.splitlines() if l.startswith("| enp"))
        self.assertTrue(fila.rstrip(" |").endswith("0"), fila)

    def test_el_boton_de_la_unidad_elegida_se_ve_elegido(self):
        from silux.ui import theme
        hoja = theme.stylesheet(theme.palette_for(qt.app(), "dark"))
        self.assertIn("QPushButton:checked", hoja)
        with pantalla.Ventana(self.i5) as ventana:
            botones = ventana.network_page._unit_buttons
            self.assertTrue(botones["bytes"].isChecked())
            self.assertFalse(botones["bits"].isChecked())

    def test_la_gtt_sin_lo_usado_dice_hasta(self):
        # «Tomada del sistema 11.6 GB» era el máximo, no lo que usa.
        from silux.i18n import _
        texto = _texto("nav.graphics", self.i5)
        self.assertIn(f"{_('gpu.vram.shared')}: hasta ", texto)
        self.assertIn(f"{_('gpu.vram.shared')}: ", _texto("nav.graphics", self.amd))
        self.assertNotIn(f"{_('gpu.vram.shared')}: hasta ", _texto("nav.graphics", self.amd))

    def test_el_microfono_de_la_camara_se_llama_asi(self):
        # Tres «Audio USB» en Sonido frente a dos de audio en el árbol USB:
        # el tercero es el micrófono de la cámara.
        from silux.i18n import _
        texto = _texto("nav.devices", self.amd)
        self.assertEqual(texto.count("| Audio USB |"), 2)
        self.assertIn(f"| {_('sound.usb.camera')} |", texto)

    def test_la_cabecera_del_arbol_usb_va_como_las_de_las_tablas(self):
        from silux.ui import theme
        with pantalla.Ventana(self.amd) as ventana:
            ventana.select_section("nav.devices")
            QApplication.processEvents()
            arbol = ventana.devices_page.usb
            cabecera = arbol.headerItem()
            textos = [cabecera.text(c) for c in range(arbol.columnCount())]
            self.assertEqual(textos, [t.upper() for t in textos])
        hoja = theme.stylesheet(theme.palette_for(qt.app(), "dark"))
        regla = hoja.split("QTreeWidget#DeviceTree QHeaderView::section {")[1].split("}")[0]
        self.assertIn("background: transparent", regla)

    def test_cada_cifra_de_dispositivos_cuenta_lo_que_dice(self):
        # «9 dispositivos USB · 5 de sonido» se leía como cinco de sonido
        # por USB, y cuenta también la HDMI y la de la placa.
        with pantalla.Ventana(self.amd) as ventana:
            ventana.select_section("nav.devices")
            QApplication.processEvents()
            subtitulo = ventana.devices_page.subtitle.text()
        self.assertIn(f"{len(self.amd.sound_cards)} tarjetas de sonido", subtitulo)

    def test_el_arbol_usb_no_ensena_columnas_que_no_dicen_nada(self):
        # Sin marcas ni modelos, ni de su firmware ni de usb.ids, el
        # fabricante quedaba vacío y «Qué es» repetía el nombre: «Teclado /
        # teclado».
        import dataclasses
        sin_nombres = dataclasses.replace(self.amd, usb_devices=tuple(
            dataclasses.replace(d, ids_vendor=None, ids_product=None)
            for d in self.amd.usb_devices))
        with pantalla.Ventana(sin_nombres) as ventana:
            ventana.select_section("nav.devices")
            QApplication.processEvents()
            arbol = ventana.devices_page.usb
            self.assertTrue(arbol.isColumnHidden(1))
            self.assertTrue(arbol.isColumnHidden(2))
            # Con el nombre y la marca que da un aparato de verdad, salen.
            primero = dataclasses.replace(sin_nombres.usb_devices[0], product="G502 HERO",
                                          vendor="Logitech")
            con_nombre = dataclasses.replace(
                sin_nombres, usb_devices=(primero, *sin_nombres.usb_devices[1:]))
            ventana._on_sample(con_nombre)
            self.assertFalse(arbol.isColumnHidden(1))
            self.assertFalse(arbol.isColumnHidden(2))

    def test_renombrar_y_borrar_van_en_el_menu_de_su_fila(self):
        # Two buttons on every row made the table a column of buttons: one
        # «⋯» per run, no taller than its row's text.
        import os
        import tempfile
        from unittest import mock
        from PySide6.QtWidgets import QLabel
        from silux import history
        from silux.i18n import _
        from silux.ui.pages.performance import RunMenu
        from tests.test_historial import _resultado
        with tempfile.TemporaryDirectory() as datos, \
             mock.patch.dict(os.environ, {"XDG_DATA_HOME": datos}):
            history.append(history.from_result(_resultado(), "Ryzen 7 5800X3D", 2.0))
            with pantalla.Ventana(self.amd) as ventana:
                pagina = ventana.benchmarks_page.cpu_tab
                pagina._pintar_historial(history.load())
                menus = pagina.history_card.findChildren(RunMenu)
                self.assertEqual(len(menus), 1)
                menu = menus[0]
                self.assertEqual([a.text() for a in menu.menu().actions()],
                                 [_("bench.button.rename"), _("bench.button.delete")])
                fila = max(l.sizeHint().height() for l in pagina.history_card.findChildren(QLabel)
                           if l.objectName() == "FieldName")
                self.assertLessEqual(menu.sizeHint().height(), fila + 8)
                # Delete asks first: the page's own method gets the run.
                with mock.patch.object(type(pagina), "_borrar_una") as borrar:
                    pagina._pintar_historial(history.load())
                    pagina.history_card.findChildren(RunMenu)[-1].delete_action.trigger()
                borrar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
