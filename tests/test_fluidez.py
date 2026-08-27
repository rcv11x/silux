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


class TestRitmoReal(unittest.TestCase):
    """La animación tiene que durar lo que dura el muestreo, no lo que se pidió.

    Recorrer sysfs, hwmon y los discos lleva su rato, así que entre muestra y
    muestra pasa más de lo configurado. Animando contra el intervalo pedido,
    la línea llegaba al final y se quedaba parada esperando el dato: eso es lo
    que se veía como un tirón.
    """

    def _ventana(self, **kwargs):
        from silux.ui.app import MainWindow
        _app()
        theme.set_density("normal", "normal")
        return MainWindow(Preferences(font_scale="normal", **kwargs).normalized())

    def test_arranca_con_lo_configurado(self):
        ventana = self._ventana(interval_s=2.0)
        self.assertEqual(ventana._intervalo_real, 2000.0)

    def test_y_se_ajusta_a_lo_que_de_verdad_tarda(self):
        import time
        from silux.collector import Collector

        ventana = self._ventana()
        muestra = Collector().sample()
        ventana._on_sample(muestra)
        for _ in range(6):
            time.sleep(0.05)
            ventana._on_sample(muestra)
        self.assertLess(ventana._intervalo_real, 1000.0,
                        "no ha seguido al ritmo de verdad")

    def test_una_pausa_larga_no_descoloca_el_ritmo(self):
        """Suspender el equipo no puede dejar la animación en horas."""
        from unittest import mock
        from silux.collector import Collector

        ventana = self._ventana()
        antes = ventana._intervalo_real
        muestra = Collector().sample()
        ventana._on_sample(muestra)
        # Como si el equipo hubiera estado dormido dos minutos.
        with mock.patch.object(ventana._desde_la_muestra, "restart",
                               return_value=120_000):
            ventana._on_sample(muestra)
        self.assertEqual(ventana._intervalo_real, antes,
                         "un salto absurdo tiene que descartarse")


class TestElAtajoSeVe(unittest.TestCase):
    def test_la_barra_de_estado_lo_dice(self):
        """Un atajo que no aparece en ningún sitio no existe."""
        from silux.collector import Collector
        from silux.ui.app import MainWindow
        _app()
        theme.set_density("normal", "normal")
        ventana = MainWindow(Preferences(font_scale="normal").normalized())
        ventana._on_sample(Collector().sample())
        self.assertIn("espacio", ventana._status.full_text().lower())
