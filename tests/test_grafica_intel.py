"""Gráficos: lo que i915 publica de una integrada y antes no se leía.

Con el volcado del i5-10400 (UHD 630, kernel 7.3): las frecuencias del
silicio (RP0 1100, RP1 350 y RPn 350 MHz), `rc6_enable` y la falta de
`throttle_reason_*`, que en esta generación no existe. Lo que esta pieza no
da —unos límites cambiados, RC6 apagado, una Intel que sí dice por qué se
frena— se monta sobre la misma foto: son estados que otras piezas producen.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestLoQueLeeDelVolcado(unittest.TestCase):

    def test_las_frecuencias_del_silicio(self):
        gpu = foto(EQUIPOS / "i5-10400")[0].gpus[0]
        relojes = gpu.clocks
        self.assertEqual((relojes.silicon_min_hz, relojes.efficient_hz, relojes.silicon_max_hz),
                         (350_000_000, 350_000_000, 1_100_000_000))
        self.assertEqual((relojes.core_min_hz, relojes.core_max_hz),
                         (350_000_000, 1_100_000_000))
        self.assertIs(gpu.sleep_enabled, True)
        self.assertIsNone(gpu.throttled)

    def test_en_amd_no_hay_nada_de_esto(self):
        gpu = foto(EQUIPOS / "5800x3d")[0].gpus[0]
        self.assertIsNone(gpu.clocks.silicon_max_hz)
        self.assertIsNone(gpu.sleep_enabled)

    def test_los_limites_solo_si_alguien_los_cambio(self):
        relojes = foto(EQUIPOS / "i5-10400")[0].gpus[0].clocks
        self.assertIsNone(render.gpu_clock_limits(relojes))
        capado = dataclasses.replace(relojes, core_max_hz=900_000_000)
        self.assertEqual(render.gpu_clock_limits(capado), "350 MHz – 900 MHz")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.intel = foto(EQUIPOS / "i5-10400")[0]
        cls.amd = foto(EQUIPOS / "5800x3d")[0]

    def _seccion(self, muestra):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(muestra)
        self.app.processEvents()
        return pagina._sections[0]

    def _con_gpu(self, **cambios):
        gpu = dataclasses.replace(self.intel.gpus[0], **cambios)
        return dataclasses.replace(self.intel, gpus=(gpu,))

    def _visible(self, grid, clave):
        return grid._values[_(clave)].isVisibleTo(grid)

    def test_relojes_de_la_integrada(self):
        seccion = self._seccion(self.intel)
        relojes = seccion.clocks
        for clave, valor in (("gpu.clock.silmax", "1.10 GHz"),
                             ("gpu.clock.efficient", "350 MHz"),
                             ("gpu.clock.silmin", "350 MHz")):
            with self.subTest(clave=clave):
                self.assertTrue(self._visible(relojes, clave))
                self.assertEqual(relojes._values[_(clave)].full_text(), valor)
        # El máximo puesto es el del silicio: no se repite.
        self.assertFalse(self._visible(relojes, "gpu.clock.coremax"))
        self.assertFalse(self._visible(relojes, "gpu.clock.limits"))

    def test_unos_limites_cambiados_se_ven(self):
        relojes = dataclasses.replace(self.intel.gpus[0].clocks, core_max_hz=900_000_000)
        seccion = self._seccion(self._con_gpu(clocks=relojes))
        self.assertTrue(self._visible(seccion.clocks, "gpu.clock.limits"))
        self.assertEqual(seccion.clocks._values[_("gpu.clock.limits")].full_text(),
                         "350 MHz – 900 MHz")

    def test_sin_motivos_el_estado_se_esconde_y_se_dice(self):
        seccion = self._seccion(self.intel)
        self.assertFalse(self._visible(seccion.sensors, "gpu.sensor.state"))
        self.assertIn(_("gpu.na.intel.throttle"), seccion.sensors_pie.text())

    def test_una_intel_que_dice_por_que_se_frena(self):
        seccion = self._seccion(self._con_gpu(
            throttled=True, throttle_reasons=(_("gpu.throttle.intel.pl1"),)))
        self.assertTrue(self._visible(seccion.sensors, "gpu.sensor.state"))
        self.assertEqual(seccion.sensors._values[_("gpu.sensor.state")].full_text(),
                         _("gpu.throttle.why").format(motivos=_("gpu.throttle.intel.pl1")))
        self.assertNotIn(_("gpu.na.intel.throttle"), seccion.sensors_pie.text())

    def test_rc6_apagado(self):
        seccion = self._seccion(self._con_gpu(sleep_enabled=False, sleep_percent=0.0))
        self.assertEqual(seccion.engine_summary._values[_("gpu.engines.idle")].full_text(),
                         _("gpu.engines.rc6off"))

    def test_en_amd_siguen_como_estaban(self):
        seccion = self._seccion(self.amd)
        self.assertTrue(self._visible(seccion.clocks, "gpu.clock.coremax"))
        for clave in ("gpu.clock.silmax", "gpu.clock.efficient", "gpu.clock.silmin",
                      "gpu.clock.limits"):
            self.assertFalse(self._visible(seccion.clocks, clave), clave)
        self.assertTrue(self._visible(seccion.sensors, "gpu.sensor.state"))


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaTablaDeMotores(unittest.TestCase):
    """Revisión del autor: el uso que falta por permisos lleva candado."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.intel = foto(EQUIPOS / "i5-10400")[0]

    def _seccion(self, muestra):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(muestra)
        self.app.processEvents()
        return pagina._sections[0]

    def test_sin_permisos_el_uso_de_cada_motor_lleva_candado(self):
        self.assertTrue(self.intel.permission_note("gpus.0"))
        seccion = self._seccion(self.intel)
        motores = self.intel.gpus[0].engines
        self.assertTrue(motores)
        for fila in range(len(motores)):
            with self.subTest(motor=motores[fila].name):
                self.assertTrue(seccion.engines.is_cell_locked(fila, 2))
                self.assertNotEqual(seccion.engines._cells[fila][2].full_text(), render.DASH)

    def test_con_permisos_el_candado_se_va_y_sale_la_cifra(self):
        seccion = self._seccion(self.intel)
        gpu = self.intel.gpus[0]
        motores = tuple(dataclasses.replace(m, busy_percent=12.0) for m in gpu.engines)
        con = dataclasses.replace(self.intel, gpus=(dataclasses.replace(gpu, engines=motores),),
                                  notes=tuple(n for n in self.intel.notes
                                              if not n.path.startswith("gpus")))
        pagina = seccion.parentWidget()
        while not hasattr(pagina, "apply"):
            pagina = pagina.parentWidget()
        pagina.apply(con)
        self.app.processEvents()
        self.assertFalse(seccion.engines.is_cell_locked(0, 2))
        self.assertEqual(seccion.engines._cells[0][2].full_text(), "12.0 %")
        self.assertTrue(seccion.engines._cells[0][2].isVisibleTo(seccion))
