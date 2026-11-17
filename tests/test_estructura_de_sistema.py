"""Sistema empieza por lo suyo, y el uso de la memoria vive en Memoria.

La página de Sistema abría con la barra de memoria y su tabla entera: la
tercera vez que salían, después de Inicio y de Memoria. Y en una
distribución de publicación continua enseñaba «Versión —» y «Variante —»,
que no son datos que falten.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestSistemaYElUsoDeLaMemoria(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _abrir(self, ventana, seccion):
        ventana.select_section(seccion)
        for _vez in range(3):
            self.app.processEvents()
        return ventana.stack.currentWidget()

    def test_sistema_no_repite_la_memoria(self):
        from silux.ui.widgets import StackedBar

        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            pagina = self._abrir(ventana, "Sistema")
            self.assertEqual(pagina.findChildren(StackedBar), [])
            textos = pantalla.textos_de(pagina)
            self.assertNotIn(_("sys.mem.cache"), textos)
            # Y lo suyo sigue entero.
            for clave in ("sys.kernel.name", "sys.field.distro", "sys.field.uptime"):
                self.assertIn(_(clave), textos)

    def test_encendido_desde_va_en_el_formato_de_la_fecha_de_la_bios(self):
        """«17/11/2026 18:15» al lado de una BIOS del «2025-10-28»: dos
        formatos de fecha en el mismo programa, y uno de ellos ambiguo."""
        import re

        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                pagina = self._abrir(ventana, "Sistema")
                desde = pagina.activity._values[_("sys.field.since")].full_text()
                self.assertEqual(desde, f.system.boot_time)
                self.assertRegex(desde, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
                # El mismo orden que la BIOS: año, mes, día.
                bios = render.bios_date(f.board.bios_date)
                self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}$", bios), bios)

    def test_el_desglose_esta_en_memoria_plegado_y_completo(self):
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                pagina = self._abrir(ventana, "Memoria")
                memoria = f.system.memory
                self.assertIn(render.size(memoria.available_bytes), pagina.usage_line.text())
                compartida = pagina.usage._values[_("sys.mem.shared")]
                self.assertFalse(compartida.isVisible())
                pagina.usage_fold.boton.click()
                self.app.processEvents()
                self.assertTrue(compartida.isVisible())
                self.assertEqual(compartida.full_text(), render.size(memoria.shared_bytes))
                self.assertEqual(pagina.usage._values[_("sys.mem.total")].full_text(),
                                 render.size(memoria.total_bytes))

    def test_lo_que_la_distribucion_no_declara_se_esconde_y_se_nombra(self):
        f = self.fotos["5800x3d"]
        self.assertIsNone(f.system.version_id)
        with pantalla.Ventana(f) as ventana:
            pagina = self._abrir(ventana, "Sistema")
            self.assertFalse(pagina.os._values[_("sys.field.version")].isVisible())
            self.assertTrue(pagina.os_pie.isVisible())
            self.assertIn("versión", pagina.os_pie.text())
            self.assertTrue(pagina.os._values[_("sys.field.distro")].isVisible())

    def test_y_lo_que_si_declara_sale(self):
        f = self.fotos["i5-10400"]
        self.assertTrue(f.system.version_id)
        with pantalla.Ventana(f) as ventana:
            pagina = self._abrir(ventana, "Sistema")
            version = pagina.os._values[_("sys.field.version")]
            self.assertTrue(version.isVisible())
            self.assertEqual(version.full_text(), f.system.version_id)
            self.assertNotIn("versión", pagina.os_pie.text())

    def test_las_insignias_no_repiten_la_ficha_de_abajo(self):
        f = self.fotos["5800x3d"]
        with pantalla.Ventana(f) as ventana:
            pagina = self._abrir(ventana, "Sistema")
            insignias = pantalla.textos_de(pagina.badges)
            self.assertIn(f.system.kernel, insignias)
            self.assertNotIn(f.system.architecture, insignias)
            self.assertNotIn(f.system.init, insignias)


if __name__ == "__main__":
    unittest.main()
