"""El deslizamiento de las gráficas y el poder congelarlas.

Van juntos a propósito: cuanto más fluida se mueve una gráfica, más falta
hace poder pararla para leer un pico antes de que se vaya por la izquierda.
"""

import unittest

from PySide6.QtWidgets import QApplication

from silux.settings import Preferences
from silux.ui import theme
from silux.ui.widgets import Sparkline


def _app():
    return QApplication.instance() or QApplication([])


class TestDeslizamiento(unittest.TestCase):
    def setUp(self):
        self.grafica = Sparkline(theme.palette_for(_app(), "dark"))
        for valor in (10.0, 20.0, 30.0):
            self.grafica.push(valor)

    def test_una_muestra_nueva_empieza_el_recorrido(self):
        """Al llegar el dato la línea está a un paso de su sitio."""
        self.assertEqual(self.grafica._phase, 0.0)

    def test_avanzar_la_lleva_a_su_sitio(self):
        self.grafica.advance(1.0)
        self.assertEqual(self.grafica._phase, 1.0)

    def test_no_se_pasa_ni_se_queda_corto(self):
        self.grafica.advance(4.0)
        self.assertEqual(self.grafica._phase, 1.0)
        self.grafica.push(40.0)
        self.grafica.advance(-2.0)
        self.assertEqual(self.grafica._phase, 0.0)

    def test_los_movimientos_imperceptibles_no_repintan(self):
        """A treinta por segundo, repintar por medio píxel es gasto tonto."""
        self.grafica.advance(0.50)
        antes = self.grafica._phase
        self.grafica.advance(0.505)
        self.assertEqual(self.grafica._phase, antes)

    def test_dibujar_no_revienta_a_medio_recorrido(self):
        from PySide6.QtGui import QPixmap
        self.grafica.resize(200, 40)
        self.grafica.advance(0.4)
        lienzo = QPixmap(200, 40)
        self.grafica.render(lienzo)


class TestAjuste(unittest.TestCase):
    def test_apagado_de_serie(self):
        """Gasta procesador: quien lo quiera que lo encienda."""
        self.assertFalse(Preferences().fluid_charts)

    def test_se_guarda_y_se_recupera(self):
        prefs = Preferences(fluid_charts=True).normalized()
        self.assertTrue(prefs.fluid_charts)

    def test_un_valor_raro_no_lo_rompe(self):
        self.assertIsInstance(
            Preferences(fluid_charts="sí").normalized().fluid_charts, bool)


class TestCongelado(unittest.TestCase):
    def _ventana(self):
        from silux.ui.app import MainWindow
        _app()
        theme.set_density("normal", "normal")
        return MainWindow(Preferences(font_scale="normal").normalized())

    def test_empieza_descongelada(self):
        self.assertFalse(self._ventana()._congelado)

    def test_el_espacio_alterna(self):
        ventana = self._ventana()
        ventana.alternar_congelado()
        self.assertTrue(ventana._congelado)
        ventana.alternar_congelado()
        self.assertFalse(ventana._congelado)

    def test_congelada_no_reparte_la_muestra(self):
        """Lo que se para es lo que se pinta, no lo que se recoge."""
        from silux.collector import Collector
        ventana = self._ventana()
        ventana.alternar_congelado()
        muestra = Collector().sample()
        repartidas = []
        ventana._distribute = lambda s: repartidas.append(s)
        ventana._on_sample(muestra)
        self.assertEqual(repartidas, [])
        self.assertIs(ventana._last_snapshot, muestra,
                      "el dato tiene que llegar igual: los máximos no se pierden")

    def test_al_soltar_se_pone_al_dia(self):
        from silux.collector import Collector
        ventana = self._ventana()
        ventana.alternar_congelado()
        ventana._on_sample(Collector().sample())
        repartidas = []
        ventana._distribute = lambda s: repartidas.append(s)
        ventana.alternar_congelado()
        self.assertEqual(len(repartidas), 1)


if __name__ == "__main__":
    unittest.main()
