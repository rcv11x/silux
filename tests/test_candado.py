"""El candado: un dato que está, y lo guarda un permiso.

Había tres estados para un campo: el dato, el guion de «no lo sé» y el campo
escondido y nombrado al pie porque no existe. Un dato que falta por permisos
salía con el mismo guion que uno que no se pudo leer, y no son lo mismo: este
tiene arreglo. El candado es el cuarto estado, dice por qué al pasar el
ratón, y pulsarlo pide los permisos.

Con los volcados de los dos equipos, sin permisos: en los dos falta el
voltaje del procesador; en el i5-10400, además, el uso y el consumo de la
gráfica y lo que el SPD no sabe de cada módulo.
"""

import dataclasses
import os
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.model import Need, PrivilegedState
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

INTEL, AMD = "i5-10400", "5800x3d"


class TestQueNotaGuardaUnCampo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in (INTEL, AMD)}

    def test_la_del_campo_o_la_de_la_pieza_entera(self):
        f = self.fotos[INTEL]
        self.assertEqual(f.permission_note("cpu.voltage_v").path, "cpu.voltage_v")
        self.assertEqual(f.permission_note("gpus.0.usage").path, "gpus.0")
        self.assertEqual(f.permission_note("gpus.0").path, "gpus.0")

    def test_lo_que_falta_por_otro_motivo_no_tiene_candado(self):
        # En el 5800X3D el consumo falta porque el contador no avanza en un
        # volcado, y la gráfica no tiene nada guardado.
        f = self.fotos[AMD]
        self.assertIsNone(f.permission_note("cpu.power"))
        self.assertIsNone(f.permission_note("gpus.0.usage"))

    def test_un_nombre_que_empieza_igual_no_es_el_mismo_campo(self):
        self.assertIsNone(self.fotos[INTEL].permission_note("gpus.01.usage"))

    def test_sin_ayudante_no_hay_candado_que_abrir(self):
        f = dataclasses.replace(self.fotos[INTEL],
                                privileged=PrivilegedState(supported=False))
        self.assertIsNone(f.permission_note("cpu.voltage_v"))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElCandadoEnLasPaginas(unittest.TestCase):

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

    def _ventana(self, f):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences(window_width=1440, window_height=880).normalized())
        ventana.resize(1440, 880)
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(f)
        ventana._on_sample(f)
        for _vez in range(4):
            self.app.processEvents()
        return ventana

    # -- el voltaje del procesador -------------------------------------------------

    def _rejilla_del_procesador(self, ventana):
        ventana.select_section("CPU")
        for _vez in range(4):
            self.app.processEvents()
        return next(iter(ventana.cpu_page._sections.values())).processor

    def test_el_voltaje_lleva_candado_en_los_dos_equipos(self):
        from silux.i18n import _

        for nombre, f in self.fotos.items():
            with self.subTest(equipo=nombre):
                rejilla = self._rejilla_del_procesador(self._ventana(f))
                campo = _("cpu.field.voltage")
                self.assertTrue(rejilla.is_locked(campo))
                candado = rejilla._candados[campo]
                self.assertTrue(candado.isVisible())
                self.assertFalse(rejilla._values[campo].isVisible())
                # Dice por qué, con las palabras de la nota.
                self.assertIn(f.permission_note("cpu.voltage_v").message, candado.toolTip())

    def test_pulsarlo_pide_los_permisos(self):
        from silux.i18n import _

        from silux.privileged.client import PrivilegedClient
        ventana = self._ventana(self.fotos[AMD])
        rejilla = self._rejilla_del_procesador(ventana)
        with mock.patch.object(PrivilegedClient, "instalado", return_value=True), \
             mock.patch.object(PrivilegedClient, "al_dia", return_value=True), \
             mock.patch.object(ventana.sampler, "request_elevation") as pedir:
            rejilla._candados[_("cpu.field.voltage")].clicked.emit()
        pedir.assert_called_once()

    def test_con_el_dato_el_candado_se_va(self):
        from silux.i18n import _

        f = self.fotos[AMD]
        ventana = self._ventana(f)
        rejilla = self._rejilla_del_procesador(ventana)
        tipo = dataclasses.replace(f.cpu.types[0], voltage_v=1.212)
        con_voltaje = dataclasses.replace(
            f, cpu=dataclasses.replace(f.cpu, types=(tipo,)),
            notes=tuple(n for n in f.notes if n.path != "cpu.voltage_v"),
            privileged=PrivilegedState(supported=True, connected=True))
        ventana._on_sample(con_voltaje)
        campo = _("cpu.field.voltage")
        self.assertFalse(rejilla.is_locked(campo))
        self.assertEqual(rejilla._values[campo].full_text(), render.volts(1.212))

    def test_sin_ayudante_sigue_siendo_un_guion(self):
        from silux.i18n import _

        f = dataclasses.replace(self.fotos[AMD], privileged=PrivilegedState(supported=False))
        rejilla = self._rejilla_del_procesador(self._ventana(f))
        campo = _("cpu.field.voltage")
        self.assertFalse(rejilla.is_locked(campo))
        self.assertEqual(rejilla._values[campo].full_text(), render.DASH)

    # -- el uso y el consumo de la gráfica -----------------------------------------

    def _ficha(self, ventana):
        ventana.select_section("Gráficos")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.graphics_page._sections[0]

    def test_en_la_intel_el_uso_y_el_consumo_llevan_candado(self):
        from silux.i18n import _

        ficha = self._ficha(self._ventana(self.fotos[INTEL]))
        for tile in (ficha.tile_usage, ficha.tile_power):
            self.assertTrue(tile.is_locked())
            self.assertTrue(tile.lock.isVisible())
            self.assertFalse(tile.value.isVisible())
            self.assertFalse(tile.unit.isVisible(), "un candado no lleva unidad")
            self.assertEqual(tile.detail.full_text(), _("lock.detail"))
        # El reloj, que se lee sin pedir nada, sigue con su cifra.
        self.assertFalse(ficha.tile_clock.is_locked())

    def test_en_la_radeon_no_hay_ninguno(self):
        ficha = self._ficha(self._ventana(self.fotos[AMD]))
        for tile in (ficha.tile_usage, ficha.tile_power, ficha.tile_temp):
            self.assertFalse(tile.is_locked())
            self.assertTrue(tile.value.isVisible())

    def test_el_candado_de_la_ficha_pide_los_permisos(self):
        from silux.privileged.client import PrivilegedClient
        ventana = self._ventana(self.fotos[INTEL])
        ficha = self._ficha(ventana)
        with mock.patch.object(PrivilegedClient, "instalado", return_value=True), \
             mock.patch.object(PrivilegedClient, "al_dia", return_value=True), \
             mock.patch.object(ventana.sampler, "request_elevation") as pedir:
            ficha.tile_usage.lock.clicked.emit()
        pedir.assert_called_once()

    def test_inicio_dice_que_el_uso_va_con_permisos(self):
        from silux.i18n import _

        inicio = self._ventana(self.fotos[INTEL]).home_page
        self.assertEqual(inicio.gpu.pie.text(), _("home.gpu.locked"))
        inicio = self._ventana(self.fotos[AMD]).home_page
        self.assertEqual(inicio.gpu.pie.text(), "")

    # -- lo que el SPD no sabe de cada módulo --------------------------------------

    def test_en_memoria_la_velocidad_real_y_el_banco_llevan_candado(self):
        from silux.i18n import _

        ventana = self._ventana(self.fotos[INTEL])
        ventana.select_section("Memoria")
        for _vez in range(4):
            self.app.processEvents()
        rejillas = ventana.memory_page._slot_grids
        self.assertEqual(len(rejillas), 2)
        for rejilla in rejillas:
            self.assertTrue(rejilla.is_locked(_("memory.field.running")))
            self.assertTrue(rejilla.is_locked(_("memory.field.bank")))
            # Lo que sí trae el SPD sigue siendo un dato.
            self.assertFalse(rejilla.is_locked(_("memory.field.rated")))
            self.assertIn("3200", rejilla._values[_("memory.field.rated")].full_text())


if __name__ == "__main__":
    unittest.main()
