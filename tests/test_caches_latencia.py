"""Cachés: la latencia medida en Memoria, en la fila de su nivel.

Las cifras son una medida de verdad del 5800X3D (18 de noviembre de 2026):
0.9 ns la L1, 2.8 la L2, 12.0 la L3 y 76.6 la RAM.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

MEDIDA = {"L1": 0.9, "L2": 2.8, "L3": 12.0, "RAM": 76.6}


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaLatenciaEnSuNivel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = shared_snapshot(EQUIPOS / "5800x3d")

    def _abrir(self, ventana):
        ventana.select_section("Cachés")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.caches_page

    def _filas(self, pagina):
        return [[c.full_text() for c in fila] for fila in pagina.table._cells]

    def test_sin_medir_la_columna_no_existe(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._abrir(ventana)
            self.assertNotIn(_("caches.col.latency"), pagina.table._headers)
            self.assertFalse(pagina.latency_note.isVisible())
            self.assertEqual(len(self._filas(pagina)), 4)

    def test_al_medir_en_memoria_sale_en_cada_fila_sin_salir_de_caches(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._abrir(ventana)
            # Lo que emite Memoria al terminar su medida.
            ventana.memory_page.latencies_measured.emit(dict(MEDIDA))
            for _vez in range(4):
                self.app.processEvents()
            self.assertEqual(pagina.table._headers[-1], _("caches.col.latency"))
            ultimas = {fila[0]: fila[-1] for fila in self._filas(pagina)}
            self.assertEqual(ultimas, {"L1 datos": "0.9 ns", "L1 instr.": "", "L2": "2.8 ns",
                                       "L3": "12.0 ns", _("caches.row.ram"): "76.6 ns"})
            self.assertTrue(pagina.latency_note.isVisible())
            self.assertTrue(pagina.table.isVisible())

    def test_un_nivel_que_no_se_pudo_medir_deja_su_celda_vacia(self):
        """Con una L3 enorme la RAM se queda sin medida, y se dice en Memoria."""
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._abrir(ventana)
            pagina.set_latencies({"L1": 0.9, "L2": 2.8})
            ultimas = {fila[0]: fila[-1] for fila in self._filas(pagina)}
            self.assertEqual(ultimas["L3"], "")
            self.assertNotIn(_("caches.row.ram"), ultimas)

    def test_sin_ninguna_medida_la_columna_se_va(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._abrir(ventana)
            pagina.set_latencies(dict(MEDIDA))
            pagina.set_latencies({})
            self.assertNotIn(_("caches.col.latency"), pagina.table._headers)
            self.assertEqual(len(self._filas(pagina)), 4)


if __name__ == "__main__":
    unittest.main()
