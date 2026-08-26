"""El color de acento y la lectura de las gráficas con el cursor.

Dos cosas que se ven pero no se miden solas: que el color elegido llegue a todo
—incluido lo que se pinta a mano, que fue justo lo que se quedó atrás la
primera vez— y que señalar un punto de una gráfica diga el valor correcto.
"""

import unittest

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from silux import render
from silux.settings import ACCENT_NAMES, Preferences
from silux.ui import theme
from silux.ui.widgets import Sparkline


class TestAcento(unittest.TestCase):
    def test_cada_acento_tiene_sus_tres_tonos_en_los_dos_temas(self):
        for nombre, temas in theme.ACCENTS.items():
            for tema in ("dark", "light"):
                tonos = temas[tema]
                self.assertEqual(len(tonos), 3, f"{nombre}/{tema}")
                for tono in tonos:
                    self.assertRegex(tono, r"^#[0-9A-Fa-f]{6}$", f"{nombre}/{tema}")

    def test_los_ajustes_y_el_tema_conocen_los_mismos_colores(self):
        # Están definidos en dos sitios porque los ajustes no cargan Qt; si se
        # desincronizan, elegir un color válido lo revertiría a naranja.
        self.assertEqual(set(ACCENT_NAMES), set(theme.ACCENTS))

    def test_tenir_cambia_los_tres_tonos(self):
        azul = theme.tinted(theme.DARK, "azul", dark=True)
        self.assertNotEqual(azul.accent, theme.DARK.accent)
        self.assertNotEqual(azul.accent_soft, theme.DARK.accent_soft)
        self.assertNotEqual(azul.accent_wash, theme.DARK.accent_wash)
        # Y no toca nada más: los fondos y el texto siguen siendo los del tema.
        self.assertEqual(azul.bg, theme.DARK.bg)
        self.assertEqual(azul.ink, theme.DARK.ink)

    def test_el_acento_por_omision_devuelve_la_paleta_tal_cual(self):
        self.assertIs(theme.tinted(theme.DARK, "naranja", dark=True), theme.DARK)

    def test_un_acento_inventado_no_rompe_nada(self):
        self.assertIs(theme.tinted(theme.LIGHT, "turquesa", dark=False), theme.LIGHT)

    def test_los_ajustes_rechazan_un_color_que_no_existe(self):
        self.assertEqual(Preferences(accent="fucsia").normalized().accent, "naranja")
        self.assertEqual(Preferences(accent="azul").normalized().accent, "azul")


class TestLecturaDeGraficas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _grafica(self, valores, ancho=100) -> Sparkline:
        chart = Sparkline(theme.DARK)
        chart.resize(ancho, 30)
        chart.set_formatter(render.percent, interval_s=1.0)
        for valor in valores:
            chart.push(valor)
        return chart

    def test_el_cursor_encuentra_el_punto_que_toca(self):
        chart = self._grafica([10, 20, 95, 30, 15])
        self.assertEqual(chart._index_at(0), 0)
        self.assertEqual(chart._index_at(50), 2)          # el pico, en el centro
        self.assertEqual(chart._index_at(100), 4)

    def test_fuera_del_widget_se_queda_en_los_extremos(self):
        chart = self._grafica([1, 2, 3])
        self.assertEqual(chart._index_at(-40), 0)
        self.assertEqual(chart._index_at(9999), 2)

    def test_una_grafica_vacia_no_tiene_nada_que_señalar(self):
        self.assertIsNone(self._grafica([]) ._index_at(50))
        self.assertIsNone(self._grafica([7])._index_at(50))

    def test_el_texto_lleva_el_valor_y_cuando_fue(self):
        chart = self._grafica([10, 20, 95, 30, 15])
        self.assertEqual(chart._hover_text(15, 4), "15.0 % · ahora")
        self.assertEqual(chart._hover_text(95, 2), "95.0 % · hace 2 s")

    def test_lo_viejo_se_cuenta_en_minutos(self):
        chart = self._grafica(range(200))
        chart.set_formatter(render.percent, interval_s=1.0)
        self.assertIn("min", chart._hover_text(3, 0))

    def test_el_intervalo_de_muestreo_cambia_la_antiguedad(self):
        chart = self._grafica([1, 2, 3, 4, 5])
        chart.set_formatter(render.percent, interval_s=5.0)
        self.assertEqual(chart._hover_text(1, 0), "1.0 % · hace 20 s")

    def test_sin_formateador_se_enseña_el_numero_pelado(self):
        chart = Sparkline(theme.DARK)
        chart.resize(100, 30)
        for valor in (1, 2, 3):
            chart.push(valor)
        self.assertIn("2", chart._hover_text(2, 1))

    def test_mover_el_raton_y_salir(self):
        chart = self._grafica([10, 20, 30])
        evento = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(50, 15),
                             QPointF(50, 15), Qt.MouseButton.NoButton,
                             Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        chart.mouseMoveEvent(evento)
        self.assertIsNotNone(chart._hover)
        chart.leaveEvent(None)
        self.assertIsNone(chart._hover)

    def test_pintar_con_el_cursor_puesto_no_revienta(self):
        chart = self._grafica([10, 20, 95, 30, 15])
        chart._hover = 2
        chart.grab()          # fuerza un paintEvent completo


if __name__ == "__main__":
    unittest.main()


class TestNucleosConLetraGrande(unittest.TestCase):
    """La rejilla de núcleos se pinta a mano, así que no la recoloca Qt.

    Con la letra al máximo el nombre del núcleo se comía la gráfica por
    arriba y quedaba un hueco por abajo: la caja del texto estaba fija en
    doce píxeles mientras las letras medían dieciocho.
    """

    def _celda(self, escala: str) -> int:
        from silux.ui.widgets import CoreMatrix
        app = QApplication.instance() or QApplication([])
        theme.set_density("normal", escala)
        return CoreMatrix(theme.palette_for(app, "dark"))._cell_h

    def test_la_celda_crece_con_la_letra(self):
        normal = self._celda("normal")
        maximo = self._celda("máximo")
        self.assertGreater(maximo, normal * 1.3,
                           "la celda no acompaña al texto")

    def test_y_el_hueco_del_historial_tambien(self):
        """El extra sobre la celda base iba en píxeles fijos."""
        alto_max = self._celda("máximo")
        extra_max = alto_max - theme.METRICS.cell_h
        alto_normal = self._celda("normal")
        extra_normal = alto_normal - theme.METRICS.cell_h
        self.assertGreater(extra_max, extra_normal)

    def tearDown(self):
        theme.set_density("normal", "normal")
