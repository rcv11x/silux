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


class TestEscalaVertical(unittest.TestCase):
    """De aquí salía el tirón, y no del deslizamiento.

    Con 90 muestras en 300 píxeles la línea avanza 3,4 px por segundo: eso no
    se ve. Lo que se veía era la escala reajustándose de golpe cada vez que
    entraba un valor fuera de lo que había, aplastando la curva entera.
    """

    def _grafica(self, valores):
        from silux.ui.widgets import Sparkline
        g = Sparkline(theme.palette_for(_app(), "dark"))
        g.resize(300, 40)
        for v in valores:
            g.push(v)
        return g

    def _pintar(self, g):
        from PySide6.QtGui import QPixmap
        g.render(QPixmap(300, 40))
        return g._escala

    def test_crecer_es_inmediato(self):
        """Encoger un dato para que quepa sería dibujarlo donde no está."""
        g = self._grafica([800.0] * 10)
        self._pintar(g)
        g.push(3400.0)
        _, techo = self._pintar(g)
        self.assertGreaterEqual(techo, 3400.0)

    def test_si_cabe_en_el_eje_que_hay_no_se_toca(self):
        """Lo que quita el tirón: el eje no se mueve por medio grado."""
        # Arranca con un eje holgado y se mueve dentro de él: lo que no puede
        # pasar es que el eje se reajuste por unas décimas.
        g = self._grafica([40.0, 56.0])
        primero = self._pintar(g)
        for v in (47.5, 48.2, 48.9, 47.1, 50.0):
            g.push(v)
            self.assertEqual(self._pintar(g), primero,
                             f"el eje se ha movido por {v}")

    def test_encoger_es_progresivo(self):
        g = self._grafica([800.0] * 5 + [3400.0])
        self._pintar(g)
        alto_con_pico = g._escala[1]
        # El pico tiene que salirse de la ventana de verdad: la gráfica guarda
        # noventa muestras, así que con veinte seguía dentro y la escala hacía
        # bien en no bajar.
        for _ in range(100):
            g.push(800.0)
        _, tras_una_pintada = self._pintar(g)
        self.assertLess(tras_una_pintada, alto_con_pico, "no ha empezado a bajar")
        self.assertGreater(tras_una_pintada, 1500.0, "ha bajado de golpe")

    def test_y_acaba_llegando(self):
        g = self._grafica([800.0] * 5 + [3400.0])
        self._pintar(g)
        for _ in range(100):
            g.push(800.0)
        for _ in range(80):
            self._pintar(g)
        self.assertLess(g._escala[1], 1000.0, "se ha quedado a medias")

    def test_ningun_valor_se_sale_de_la_escala(self):
        """Lo que se dibuja tiene que caber, siempre."""
        import random
        random.seed(11)
        g = self._grafica([800.0])
        for _ in range(60):
            g.push(random.choice([800.0, 800.0, 2600.0, 4400.0]))
            suelo, techo = self._pintar(g)
            actuales = list(g._values)
            self.assertLessEqual(max(actuales), techo)
            self.assertGreaterEqual(min(actuales), suelo)

    def test_al_limpiar_se_olvida_la_escala(self):
        g = self._grafica([800.0, 3400.0])
        self._pintar(g)
        g.clear()
        self.assertIsNone(g._escala)
