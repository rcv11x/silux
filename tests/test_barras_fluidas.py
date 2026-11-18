"""Con «Movimiento fluido», las barras se deslizan; las cifras, no.

Cada barra va del largo que se ve al del dato nuevo durante el intervalo,
movida por el mismo temporizador que las gráficas. La cifra de al lado salta
al dato real. Apagado, la barra salta también. Con la barra espaciadora se
congela todo: el temporizador se para.
"""

import unittest

from tests import qt


class TestElDeslizador(unittest.TestCase):
    def setUp(self):
        from silux.ui.widgets import Deslizador
        self.D = Deslizador
        self.addCleanup(setattr, Deslizador, "fluido", Deslizador.fluido)

    def test_apagado_salta(self):
        self.D.fluido = False
        d = self.D(0.2)
        d.fijar(0.8)
        self.assertAlmostEqual(d.valor(), 0.8)

    def test_encendido_se_desliza_durante_el_intervalo(self):
        self.D.fluido = True
        d = self.D(0.2)
        d.fijar(0.8)
        self.assertAlmostEqual(d.valor(), 0.2)
        self.assertTrue(d.avanzar(0.5))
        self.assertAlmostEqual(d.valor(), 0.5)
        d.avanzar(1.0)
        self.assertAlmostEqual(d.valor(), 0.8)

    def test_un_dato_a_media_animacion_sale_de_donde_se_ve(self):
        self.D.fluido = True
        d = self.D(0.0)
        d.fijar(1.0)
        d.avanzar(0.5)
        d.fijar(0.0)
        self.assertAlmostEqual(d.valor(), 0.5)


class TestLasBarrasDeVerdad(unittest.TestCase):
    def setUp(self):
        from silux.ui import theme
        from silux.ui.widgets import Deslizador
        self.app = qt.app()
        self.paleta = theme.palette_for(self.app, "dark")
        self.addCleanup(setattr, Deslizador, "fluido", Deslizador.fluido)
        Deslizador.fluido = True

    def test_la_cifra_salta_y_la_barra_se_desliza(self):
        from silux.ui.widgets import LevelList
        lista = LevelList(self.paleta)
        self.addCleanup(lista.deleteLater)
        lista.add("Render")
        lista.set("Render", 0.2)
        lista._rows["Render"][1].advance(1.0)
        lista.set("Render", 0.8)
        barra = lista._rows["Render"][1]
        self.assertEqual(lista.text_of("Render"), "80 %")
        self.assertAlmostEqual(barra.fraction(), 0.8)
        self.assertAlmostEqual(barra.shown_fraction(), 0.2)
        barra.advance(0.5)
        self.assertAlmostEqual(barra.shown_fraction(), 0.5)

    def test_la_de_memoria_tambien(self):
        from silux.ui.widgets import StackedBar
        barra = StackedBar(self.paleta)
        self.addCleanup(barra.deleteLater)
        barra.set_segments([("Aplicaciones", 2.0, "accent")], 10.0)
        barra.set_segments([("Aplicaciones", 6.0, "accent")], 10.0)
        self.assertAlmostEqual(barra._largos["Aplicaciones"].valor(), 0.2)
        barra.advance(0.5)
        self.assertAlmostEqual(barra._largos["Aplicaciones"].valor(), 0.4)

    def test_la_de_cada_hilo_tambien(self):
        from silux.ui.corematrix import CoreMatrix
        matriz = CoreMatrix(self.paleta)
        self.addCleanup(matriz.deleteLater)
        matriz.set_cores([{"name": "CPU 0", "usage": 10.0, "history": ()}])
        matriz.set_cores([{"name": "CPU 0", "usage": 90.0, "history": ()}])
        self.assertAlmostEqual(matriz._usos[0].valor(), 10.0)
        matriz.advance(0.5)
        self.assertAlmostEqual(matriz._usos[0].valor(), 50.0)


class TestLaVentana(unittest.TestCase):
    def test_el_ajuste_mueve_las_barras_y_el_espacio_las_congela(self):
        import dataclasses
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        from silux.ui.widgets import Deslizador, LevelBar
        qt.app()
        self.addCleanup(setattr, Deslizador, "fluido", Deslizador.fluido)
        ventana = MainWindow(dataclasses.replace(Preferences(), fluid_charts=True).normalized())
        self.addCleanup(ventana.deleteLater)
        self.assertTrue(Deslizador.fluido)
        from tests import muestras
        ventana._on_sample(muestras.foto_real())
        self.assertTrue(any(isinstance(w, LevelBar) for w in ventana._graficas()))
        self.assertTrue(ventana._latido.isActive())
        ventana.alternar_congelado()
        self.assertFalse(ventana._latido.isActive())


if __name__ == "__main__":
    unittest.main()
