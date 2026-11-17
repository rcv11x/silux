"""Cómo está repartida la página CPU: lo que se busca arriba, lo demás a un clic.

«Procesador» eran quince filas seguidas: entre el encapsulado y el voltaje
había que pasar por familia, modelo, stepping, firma CPUID y microcódigo,
que hacen falta para un informe y casi nunca para otra cosa. Y la leyenda de
los mejores núcleos eran dos renglones de letra pequeña a todo el ancho.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaPaginaCpu(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _seccion(self, ventana):
        from silux.ui.pages.cpu import TypeSection

        ventana.select_section("CPU")
        self.app.processEvents()
        return ventana.cpu_page.findChildren(TypeSection)[0]

    def test_la_identificacion_va_plegada_y_no_se_pierde(self):
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                seccion = self._seccion(ventana)
                tipo = f.cpu.types[0]
                microcodigo = seccion.identity._values[_("cpu.field.microcode")]
                self.assertFalse(microcodigo.isVisible())
                self.assertNotIn(_("cpu.field.family"), seccion.processor._values)
                seccion.identity_fold.boton.click()
                self.app.processEvents()
                self.assertTrue(microcodigo.isVisible())
                self.assertEqual(microcodigo.full_text(), tipo.microcode)
                self.assertTrue(seccion.identity._values[_("cpu.field.signature")].full_text())

    def test_arriba_queda_lo_que_se_busca_con_el_voltaje(self):
        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            seccion = self._seccion(ventana)
            filas = seccion.processor._filas
            self.assertEqual(len(filas), 10)
            for clave in ("cpu.field.package", "cpu.field.cores", "cpu.field.threads",
                          "cpu.field.voltage"):
                self.assertIn(_(clave), filas)
            # Sin permisos el voltaje sigue llevando su candado, a la vista.
            self.assertTrue(seccion.processor.is_locked(_("cpu.field.voltage")))
            self.assertTrue(seccion.processor._candados[_("cpu.field.voltage")].isVisible())

    def test_la_leyenda_de_los_mejores_nucleos_es_una_frase(self):
        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            ventana.select_section("CPU")
            self.app.processEvents()
            leyenda = ventana.cpu_page.live.calidad
            self.assertTrue(leyenda.isVisible())
            self.assertIn("Núcleo 1", leyenda.text())
            self.assertNotIn("oblea", leyenda.text())
            # El porqué no se pierde: está al pasar el ratón.
            self.assertIn("oblea", leyenda.toolTip())
            self.assertIn("85 %", leyenda.toolTip())
            self.assertLessEqual(leyenda.height(), 2 * leyenda.fontMetrics().lineSpacing())


if __name__ == "__main__":
    unittest.main()
