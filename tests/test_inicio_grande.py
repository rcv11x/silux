"""Inicio con la ventana grande: las tres tarjetas de abajo y lo que cambió.

Con los volcados de los dos equipos, que son la otra cara el uno del otro:
el i5-10400 con su gráfica integrada, que no publica temperatura, y el
5800X3D con una dedicada que sí.
"""

import os
import re
import tempfile
import unittest
from unittest import mock

from silux import render
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

INTEL, AMD = "i5-10400", "5800x3d"


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestInicioConLaVentanaGrande(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in (INTEL, AMD)}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _inicio(self, nombre, **preferencias):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        prefs = Preferences(window_width=1440, window_height=880,
                            **preferencias).normalized()
        ventana = MainWindow(prefs)
        ventana.resize(prefs.window_width, prefs.window_height)
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(self.fotos[nombre])
        ventana._on_sample(self.fotos[nombre])
        for _vez in range(4):
            self.app.processEvents()
        return ventana, ventana.home_page

    # -- temperaturas ----------------------------------------------------------

    def test_cada_temperatura_lleva_el_nombre_de_lo_que_mide(self):
        from silux.i18n import _

        for nombre in (INTEL, AMD):
            with self.subTest(equipo=nombre):
                _ventana, inicio = self._inicio(nombre)
                tarjeta = inicio.temperaturas
                texto = f"{tarjeta.nombre.text()} · {tarjeta.cifras.text()}"
                cifras = re.findall(r"([^·\d]+?)\s+([\d.]+)\s*°C", texto)
                self.assertTrue(cifras, texto)
                # Ninguna cifra suelta: tantas temperaturas como nombres.
                self.assertEqual(len(cifras), texto.count("°C"), texto)
                nombres = {n.strip() for n, _g in cifras}
                self.assertIn(_("home.temp.cpu"), nombres)

    def test_arriba_va_la_mas_caliente(self):
        f = self.fotos[AMD]
        _ventana, inicio = self._inicio(AMD)
        todas = [t for t in (f.cpu.temperature_c, f.gpus[0].temp_c,
                             *(d.temp_c for d in f.disks)) if t is not None]
        self.assertGreater(len(todas), 2)
        self.assertIn(render.temperature(max(todas), False), inicio.temperaturas.nombre.text())

    def test_la_del_procesador_es_la_misma_que_en_su_tarjeta(self):
        f = self.fotos[INTEL]
        _ventana, inicio = self._inicio(INTEL)
        grados = render.temperature(f.cpu.temperature_c, False)
        self.assertIn(grados, inicio.cpu.cifras.text())
        self.assertIn(grados, f"{inicio.temperaturas.nombre.text()} {inicio.temperaturas.cifras.text()}")

    def test_lleva_a_sensores(self):
        from silux.i18n import _

        ventana, inicio = self._inicio(AMD)
        inicio.temperaturas.pulsada.emit(inicio.temperaturas._seccion)
        self.assertIs(ventana.stack.currentWidget(), ventana.monitor_page)
        self.assertEqual(inicio.temperaturas._seccion, _("nav.sensors"))

    # -- red ---------------------------------------------------------------------

    def test_la_red_es_la_misma_interfaz_que_en_su_pagina(self):
        for nombre in (INTEL, AMD):
            with self.subTest(equipo=nombre):
                ventana, inicio = self._inicio(nombre)
                self.assertEqual(inicio.red.nombre.text(), ventana.network_page.title.text())
                self.assertNotIn("full", inicio.red.detalle.text())

    def test_la_red_dice_el_enlace_y_las_dos_direcciones(self):
        _ventana, inicio = self._inicio(AMD)
        self.assertIn("Gb/s", inicio.red.detalle.text())
        # En un volcado el tráfico no avanza: sale, y sale a cero.
        self.assertIn("↓", inicio.red.cifras.text())
        self.assertIn("↑", inicio.red.cifras.text())

    # -- placa -------------------------------------------------------------------

    def test_la_placa_dice_modelo_bios_y_arranque(self):
        for nombre in (INTEL, AMD):
            with self.subTest(equipo=nombre):
                f = self.fotos[nombre]
                _ventana, inicio = self._inicio(nombre)
                self.assertEqual(inicio.placa.nombre.text(), f.board.display_name)
                self.assertIn(f.board.bios_version, inicio.placa.detalle.text())
                # La fecha, sin el orden americano del firmware.
                self.assertIn(render.bios_date(f.board.bios_date), inicio.placa.detalle.text())
                self.assertNotIn(f.board.bios_date, inicio.placa.detalle.text())
                self.assertIn(f.board.firmware, inicio.placa.cifras.text())
                self.assertNotIn("TPM TPM", inicio.placa.cifras.text())

    def test_las_tres_llevan_a_su_seccion(self):
        ventana, inicio = self._inicio(AMD)
        for tarjeta, pagina in ((inicio.red, ventana.network_page),
                                (inicio.placa, ventana.board_page)):
            tarjeta.pulsada.emit(tarjeta._seccion)
            self.assertIs(ventana.stack.currentWidget(), pagina)

    # -- lo que cambió arriba ------------------------------------------------------

    def test_el_boton_de_copiar_va_en_la_fila_de_las_insignias(self):
        from PySide6.QtCore import QPoint

        _ventana, inicio = self._inicio(AMD)
        cabecera = inicio.title.parentWidget()
        boton = inicio.share.mapTo(cabecera, QPoint(0, 0))
        insignias = inicio.badges.mapTo(cabecera, QPoint(0, 0))
        self.assertLess(abs(boton.y() - insignias.y()), inicio.share.height())
        self.assertGreater(boton.x(), insignias.x())

    def test_la_grafica_dice_que_es_y_no_cuanta_ram_coge(self):
        from silux.i18n import _

        _ventana, inicio = self._inicio(INTEL)
        detalle = inicio.gpu.detalle.text()
        self.assertIn(_("gpu.chip.integrated"), detalle)
        self.assertNotIn("RAM", f"{detalle} {inicio.gpu.cifras.text()}")
        _ventana, inicio = self._inicio(AMD)
        self.assertNotIn(_("gpu.chip.integrated"), inicio.gpu.detalle.text())
        self.assertIn(render.compute_units(self.fotos[AMD].gpus[0]), inicio.gpu.detalle.text())

    def test_el_reloj_de_la_integrada_lleva_su_techo(self):
        # Sin permisos, de la UHD 630 solo se sabe a cuánto va: con el tope
        # al lado se sabe además si es mucho.
        f = self.fotos[INTEL]
        _ventana, inicio = self._inicio(INTEL)
        gpu = f.gpus[0]
        self.assertIsNone(gpu.busy_percent)
        self.assertIn(render.hz(gpu.clocks.core_hz), inicio.gpu.cifras.text())
        self.assertIn(render.hz(gpu.clocks.core_max_hz), inicio.gpu.cifras.text())

    def test_con_uso_y_vatios_la_grafica_los_ensena(self):
        _ventana, inicio = self._inicio(AMD)
        gpu = self.fotos[AMD].gpus[0]
        self.assertIn(render.percent(gpu.busy_percent), inicio.gpu.cifras.text())
        self.assertIn(render.watts(gpu.power_w), inicio.gpu.cifras.text())

    def test_repintar_no_crea_widgets(self):
        ventana, inicio = self._inicio(AMD)
        antes = len(inicio.findChildren(object))
        for _vez in range(10):
            ventana._on_sample(self.fotos[AMD])
        self.assertEqual(len(inicio.findChildren(object)), antes)

    def test_en_compacto_nada_se_sale(self):
        ventana, inicio = self._inicio(AMD, density="compact")
        ventana.resize(900, 680)
        for _vez in range(4):
            self.app.processEvents()
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QWidget

        fuera = [type(w).__name__ for w in inicio.findChildren(QWidget)
                 if w.isVisibleTo(ventana)
                 and w.mapTo(ventana, QPoint(0, 0)).x() + w.width() > ventana.width()]
        self.assertEqual(fuera, [])


if __name__ == "__main__":
    unittest.main()
