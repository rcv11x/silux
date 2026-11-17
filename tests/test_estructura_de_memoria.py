"""El orden de la página de Memoria: los datos primero, lo que falta al final.

Sin permisos, la página era: cabecera, una tarjeta que pide permisos, una
que ofrece medir, y dos avisos. No había un dato hasta el tercer bloque, y
con módulos leídos por SPD la tarjeta de permisos iba delante de ellos.
"""

import unittest

from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElOrdenDeMemoria(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in ("5800x3d", "i5-10400")}

    def _alturas(self, ventana):
        ventana.select_section("Memoria")
        for _vez in range(3):
            self.app.processEvents()
        pagina = ventana.memory_page
        raiz = pagina.widget()

        def alto(widget):
            return widget.mapTo(raiz, widget.rect().topLeft()).y()
        return pagina, alto

    def test_lo_que_pide_permisos_va_despues_de_los_datos(self):
        for equipo, f in self.fotos.items():
            with self.subTest(equipo=equipo), pantalla.Ventana(f) as ventana:
                pagina, alto = self._alturas(ventana)
                self.assertTrue(pagina.elevation.isVisible())
                for bloque in (pagina.title.parentWidget(), pagina._slots_host,
                               pagina.timings_card):
                    if bloque.isVisible():
                        self.assertLess(alto(bloque), alto(pagina.elevation))
                # La cabecera sigue siendo lo primero.
                self.assertEqual(alto(pagina.title.parentWidget()),
                                 pagina.widget().layout().contentsMargins().top())

    def test_en_el_intel_los_modulos_van_justo_debajo_de_la_cabecera(self):
        # Sus módulos se leen por SPD sin permisos: son el primer dato.
        with pantalla.Ventana(self.fotos["i5-10400"]) as ventana:
            pagina, alto = self._alturas(ventana)
            self.assertTrue(self.fotos["i5-10400"].modules or pagina._slot_grids)
            self.assertTrue(pagina._slots_host.isVisible())
            visibles = sorted(
                (alto(w), w) for w in (pagina._slots_host, pagina.timings_card,
                                       pagina.elevation) if w.isVisible())
            self.assertIs(visibles[0][1], pagina._slots_host)

    def test_los_avisos_cierran_la_pagina(self):
        from silux.ui.widgets import Notice

        with pantalla.Ventana(self.fotos["5800x3d"]) as ventana:
            pagina, alto = self._alturas(ventana)
            avisos = [a for a in pagina.findChildren(Notice) if a.isVisible()]
            self.assertTrue(avisos)
            self.assertGreater(min(alto(a) for a in avisos), alto(pagina.elevation))


if __name__ == "__main__":
    unittest.main()
