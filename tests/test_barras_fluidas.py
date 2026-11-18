"""Con «Movimiento fluido», las barras llegan a su dato en un momento; las
cifras, en el acto.

Cada barra sale del largo que se ve ahora y llega al dato nuevo en
`Deslizador.DURACION` (entre 150 y 200 ms), frenando al final. Un dato que
llega a media animación sigue desde donde esté la barra. El primer dato, y el
de una barra que no está a la vista, se ponen sin animar. La cifra de al lado
salta al dato real. Apagado, la barra salta también. Con la barra espaciadora
se congela todo: el temporizador se para.

El tiempo es un reloj de mentira que el test adelanta a mano
(`Deslizador.reloj`): con el de verdad, el resultado dependería de lo
cargada que esté la máquina.
"""

import dataclasses
import unittest
from unittest import mock

from tests import qt


class Reloj:
    """Un reloj que solo avanza cuando se le dice."""

    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora

    def pasar(self, segundos):
        self.ahora += segundos


def con_reloj(test):
    """Pone el reloj de mentira y el ajuste encendido, y los deja como
    estaban al acabar."""
    from silux.ui.widgets import Deslizador
    reloj = Reloj()
    test.addCleanup(setattr, Deslizador, "reloj", Deslizador.__dict__["reloj"])
    test.addCleanup(setattr, Deslizador, "fluido", Deslizador.fluido)
    Deslizador.reloj = staticmethod(reloj)
    Deslizador.fluido = True
    return reloj


class TestElDeslizador(unittest.TestCase):
    def setUp(self):
        from silux.ui.widgets import Deslizador
        self.D = Deslizador
        self.reloj = con_reloj(self)

    def test_dura_lo_que_un_parpadeo(self):
        self.assertGreaterEqual(self.D.DURACION, 0.15)
        self.assertLessEqual(self.D.DURACION, 0.20)

    def test_apagado_salta(self):
        self.D.fluido = False
        d = self.D(0.2)
        d.fijar(0.8)
        self.assertAlmostEqual(d.valor(), 0.8)
        self.assertFalse(d.moviendose())

    def test_sale_de_donde_se_ve_y_no_de_cero(self):
        d = self.D(0.2)
        d.fijar(0.8)
        self.assertAlmostEqual(d.valor(), 0.2)

    def test_frena_al_final(self):
        """En la primera mitad del tiempo hace mucho más de la mitad del camino."""
        d = self.D(0.0)
        d.fijar(1.0)
        self.reloj.pasar(self.D.DURACION / 2)
        self.assertGreater(d.valor(), 0.8)
        self.assertLess(d.valor(), 1.0)

    def test_llega_y_se_para(self):
        d = self.D(0.2)
        d.fijar(0.8)
        self.assertTrue(d.avanzar())
        self.reloj.pasar(self.D.DURACION)
        self.assertAlmostEqual(d.valor(), 0.8)
        # Un último fotograma para pintarla en su sitio, y quieta.
        self.assertTrue(d.avanzar())
        self.assertFalse(d.moviendose())
        self.assertFalse(d.avanzar())

    def test_un_dato_a_media_animacion_sigue_desde_donde_esta(self):
        d = self.D(0.0)
        d.fijar(1.0)
        self.reloj.pasar(self.D.DURACION / 3)
        a_medias = d.valor()
        self.assertTrue(0.0 < a_medias < 1.0)
        d.fijar(0.0)
        self.assertAlmostEqual(d.valor(), a_medias)
        self.reloj.pasar(self.D.DURACION)
        self.assertAlmostEqual(d.valor(), 0.0)

    def test_el_primer_dato_no_se_anima(self):
        d = self.D()
        d.fijar(0.6)
        self.assertAlmostEqual(d.valor(), 0.6)
        self.assertFalse(d.moviendose())

    def test_fuera_de_la_vista_no_se_anima(self):
        d = self.D(0.2)
        d.fijar(0.6, animar=False)
        self.assertAlmostEqual(d.valor(), 0.6)

    def test_el_mismo_dato_no_reinicia_nada(self):
        d = self.D(0.2)
        d.fijar(0.8)
        self.reloj.pasar(self.D.DURACION / 3)
        antes = d.valor()
        self.assertFalse(d.fijar(0.8))
        self.assertAlmostEqual(d.valor(), antes)


class TestLasBarrasDeVerdad(unittest.TestCase):
    def setUp(self):
        from silux.ui import theme
        self.app = qt.app()
        self.paleta = theme.palette_for(self.app, "dark")
        self.reloj = con_reloj(self)

    def a_la_vista(self, widget):
        self.addCleanup(widget.deleteLater)
        widget.resize(400, 120)
        widget.show()
        self.app.processEvents()
        return widget

    def test_la_cifra_salta_y_la_barra_sale_de_donde_esta(self):
        from silux.ui.widgets import Deslizador
        lista = self.a_la_vista(lista_con(self.paleta, "Render"))
        lista.set("Render", 0.2)
        barra = lista._rows["Render"][1]
        self.assertAlmostEqual(barra.shown_fraction(), 0.2, msg="el primer dato, sin animar")
        lista.set("Render", 0.8)
        self.assertEqual(lista.text_of("Render"), "80 %")
        self.assertAlmostEqual(barra.fraction(), 0.8)
        self.assertAlmostEqual(barra.shown_fraction(), 0.2)
        self.reloj.pasar(Deslizador.DURACION)
        barra.advance(0.2)
        self.assertFalse(barra.advance(0.2), "llegó: ya no pide fotogramas")
        self.assertAlmostEqual(barra.shown_fraction(), 0.8)

    def test_un_renglon_que_vuelve_no_se_desliza_desde_lo_que_ya_no_se_veia(self):
        lista = self.a_la_vista(lista_con(self.paleta, "Consumo"))
        lista.set("Consumo", 0.7)
        lista.set("Consumo", None)
        lista.set("Consumo", 0.1)
        self.assertAlmostEqual(lista._rows["Consumo"][1].shown_fraction(), 0.1)

    def test_la_de_memoria_tambien(self):
        from silux.ui.widgets import StackedBar
        barra = self.a_la_vista(StackedBar(self.paleta))
        barra.set_segments([("Aplicaciones", 2.0, "accent")], 10.0)
        barra.set_segments([("Aplicaciones", 6.0, "accent")], 10.0)
        self.assertAlmostEqual(barra._largos["Aplicaciones"].valor(), 0.2)
        self.assertTrue(barra.advance(0.1))
        self.reloj.pasar(1.0)
        barra.advance(0.2)
        self.assertAlmostEqual(barra._largos["Aplicaciones"].valor(), 0.6)
        self.assertFalse(barra.advance(0.3))

    def test_la_de_cada_hilo_tambien(self):
        from silux.ui.corematrix import CoreMatrix
        matriz = self.a_la_vista(CoreMatrix(self.paleta))
        matriz.set_cores([{"name": "CPU 0", "usage": 10.0, "history": ()}])
        uso = matriz._usos[0]
        matriz.set_cores([{"name": "CPU 0", "usage": 90.0, "history": ()}])
        self.assertIs(matriz._usos[0], uso, "se reutiliza, no se recrea")
        self.assertAlmostEqual(uso.valor(), 10.0)
        self.reloj.pasar(1.0)
        matriz.advance(0.5)
        self.assertAlmostEqual(uso.valor(), 90.0)

    def test_mientras_se_mueven_las_barras_no_se_rehace_el_historial(self):
        """Las curvas de cada hilo cambian con cada muestra; las barras, entre
        medias. Rehacer dieciséis curvas en cada fotograma de una barra era la
        mitad de lo que gastaba la página CPU con el movimiento fluido."""
        from PySide6.QtGui import QPixmap

        from silux.ui import corematrix
        from silux.ui.corematrix import CoreMatrix
        matriz = self.a_la_vista(CoreMatrix(self.paleta))
        historia = tuple(float(v % 50) for v in range(30))

        def hilos(uso, historia):
            # Lo que manda la página CPU (cpulive.py) para cada hilo.
            return [{"name": f"CPU {n}", "detail": "4.45 GHz  52°", "detail_short": "4.45 GHz",
                     "usage": uso, "history": historia, "starred": False} for n in range(4)]

        matriz.set_cores(hilos(10.0, historia))
        matriz.set_cores(hilos(90.0, historia))
        lienzo = QPixmap(matriz.size())
        matriz.render(lienzo)
        with mock.patch.object(corematrix, "curva_suave", wraps=corematrix.curva_suave) as curva:
            for _vez in range(5):
                self.reloj.pasar(0.03)
                matriz.advance(0.1)
                matriz.render(lienzo)
            self.assertEqual(curva.call_count, 0)
            matriz.set_cores(hilos(50.0, historia + (5.0,)))
            matriz.render(lienzo)
            self.assertEqual(curva.call_count, 8, "con la muestra nueva, dos por hilo")

    def test_la_de_cada_hilo_no_repinta_lo_fijo_en_cada_fotograma(self):
        """Celdas, nombres, curvas y estrellas se pintan una vez por muestra;
        en cada fotograma, solo el relleno de las barras."""
        from PySide6.QtGui import QPixmap

        from silux.ui.corematrix import CoreMatrix
        matriz = self.a_la_vista(CoreMatrix(self.paleta))
        hilos = lambda uso: [{"name": f"CPU {n}", "detail": "4.45 GHz", "detail_short": "4.45 GHz",
                              "usage": uso, "history": (1.0, 5.0, 3.0), "starred": n == 0}
                             for n in range(8)]
        matriz.set_cores(hilos(10.0))
        matriz.set_cores(hilos(90.0))
        lienzo = QPixmap(matriz.size())
        matriz.render(lienzo)
        with mock.patch.object(matriz, "_pintar_fondo", wraps=matriz._pintar_fondo) as fondo:
            for _vez in range(5):
                self.reloj.pasar(0.03)
                matriz.advance(0.1)
                matriz.render(lienzo)
            self.assertEqual(fondo.call_count, 0)
            matriz.set_cores(hilos(40.0))
            matriz.render(lienzo)
            self.assertEqual(fondo.call_count, 1, "con la muestra nueva, una vez")

    def test_la_de_memoria_no_repinta_su_leyenda_en_cada_fotograma(self):
        """La leyenda va debajo de la barra, dentro del mismo widget. Repintar
        el widget entero repintaba sus insignias en cada fotograma: casi cien
        por segundo en Inicio."""
        from PySide6.QtCore import QEvent, QObject

        from silux.ui.widgets import Badge, StackedBar
        barra = self.a_la_vista(StackedBar(self.paleta))
        barra.set_segments([("Aplicaciones", 2.0, "accent"), ("Libre", 8.0, "line")], 10.0)
        self.app.processEvents()

        class Contador(QObject):
            pintados = 0

            def eventFilter(self, objeto, evento):  # noqa: N802
                if evento.type() == QEvent.Type.Paint and isinstance(objeto, Badge):
                    Contador.pintados += 1
                return False

        contador = Contador()
        self.app.installEventFilter(contador)
        self.addCleanup(self.app.removeEventFilter, contador)
        barra.set_segments([("Aplicaciones", 6.0, "accent"), ("Libre", 4.0, "line")], 10.0)
        self.app.processEvents()
        Contador.pintados = 0
        for _vez in range(5):
            self.reloj.pasar(0.03)
            barra.advance(0.1)
            self.app.processEvents()
        self.assertEqual(Contador.pintados, 0)

    def test_parar_el_movimiento_la_pone_en_su_sitio(self):
        """Al congelar o apagar el ajuste, la ventana pide la fase 1: una barra
        a medio camino no se queda ahí hasta la muestra siguiente."""
        from silux.ui.widgets import StackedBar
        barra = self.a_la_vista(StackedBar(self.paleta))
        barra.set_segments([("Aplicaciones", 2.0, "accent")], 10.0)
        barra.set_segments([("Aplicaciones", 6.0, "accent")], 10.0)
        self.assertFalse(barra.advance(1.0))
        self.assertAlmostEqual(barra._largos["Aplicaciones"].valor(), 0.6)


def lista_con(paleta, *nombres):
    from silux.ui.widgets import LevelList
    lista = LevelList(paleta)
    for nombre in nombres:
        lista.add(nombre)
    return lista


class TestLaVentana(unittest.TestCase):
    """La ventana entera, con el volcado del 5800X3D y su RX 9070 XT."""

    @classmethod
    def setUpClass(cls):
        from tests.test_equipos import EQUIPOS, foto
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def setUp(self):
        self.reloj = con_reloj(self)

    def ventana(self, pagina):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        ventana = MainWindow(dataclasses.replace(Preferences(), fluid_charts=True).normalized())
        self.addCleanup(ventana.deleteLater)
        ventana.resize(1440, 900)
        ventana.show()
        ventana.select_section(pagina)
        self.app.processEvents()
        return ventana

    def con_consumo(self, vatios):
        grafica = dataclasses.replace(self.foto.gpus[0], power_w=vatios)
        return dataclasses.replace(self.foto, gpus=(grafica,) + self.foto.gpus[1:])

    def barra_de_consumo(self, ventana):
        from silux.i18n import _
        return ventana.graphics_page._sections[0].now._rows[_("gpu.now.power")][1]

    def test_la_animacion_empieza_en_el_valor_actual_y_no_en_cero(self):
        from silux.ui.widgets import Deslizador
        ventana = self.ventana("Gráficos")
        tope = self.foto.gpus[0].power_cap_w
        self.assertTrue(tope, "el volcado tiene el tope de consumo")
        ventana._on_sample(self.con_consumo(tope * 0.30))
        barra = self.barra_de_consumo(ventana)
        self.assertAlmostEqual(barra.shown_fraction(), 0.30, places=3,
                               msg="la primera muestra, en su sitio y no desde cero")
        self.reloj.pasar(1.0)
        ventana._on_sample(self.con_consumo(tope * 0.60))
        self.assertIs(self.barra_de_consumo(ventana), barra, "la barra no se recrea")
        self.assertAlmostEqual(barra.shown_fraction(), 0.30, places=3)
        self.reloj.pasar(Deslizador.DURACION / 2)
        self.assertGreater(barra.shown_fraction(), 0.30)
        self.assertLess(barra.shown_fraction(), 0.60)
        self.reloj.pasar(Deslizador.DURACION / 2)
        self.assertAlmostEqual(barra.shown_fraction(), 0.60, places=3)

    def test_la_de_una_pagina_que_se_abre_despues_esta_en_su_sitio(self):
        """El dato llega con Inicio abierto; al abrir Gráficos, la barra ya
        está donde dice su cifra, sin subir desde cero."""
        ventana = self.ventana("Inicio")
        tope = self.foto.gpus[0].power_cap_w
        ventana._on_sample(self.con_consumo(tope * 0.30))
        self.reloj.pasar(1.0)
        ventana._on_sample(self.con_consumo(tope * 0.50))
        ventana.select_section("Gráficos")
        self.app.processEvents()
        self.assertAlmostEqual(self.barra_de_consumo(ventana).shown_fraction(), 0.50, places=3)

    def test_mientras_una_barra_se_mueve_va_al_ritmo_de_la_pantalla(self):
        from silux.ui.app import LATIDO_GRAFICAS_MS
        from silux.ui.widgets import Deslizador
        ventana = self.ventana("Gráficos")
        tope = self.foto.gpus[0].power_cap_w
        ventana._on_sample(self.con_consumo(tope * 0.30))
        self.reloj.pasar(1.0)
        ventana._on_sample(self.con_consumo(tope * 0.60))
        self.assertTrue(ventana._latido.isActive())
        self.assertLess(ventana._latido.interval(), LATIDO_GRAFICAS_MS)
        self.reloj.pasar(Deslizador.DURACION)
        ventana._avanzar_graficas()
        ventana._avanzar_graficas()
        self.assertEqual(ventana._latido.interval(), LATIDO_GRAFICAS_MS,
                         "quietas las barras, vuelve al ritmo de las gráficas")

    def test_en_una_pagina_sin_nada_que_mover_no_late(self):
        """Placa base no tiene gráficas ni barras: latir treinta veces por
        segundo ahí era 1,8 puntos de un núcleo para nada."""
        ventana = self.ventana("Placa base")
        ventana._on_sample(self.foto)
        self.assertFalse(ventana._latido.isActive())
        ventana.select_section("Gráficos")
        ventana._on_sample(self.foto)
        self.assertTrue(ventana._latido.isActive(), "vuelve con la muestra siguiente")

    def test_sin_verse_no_late(self):
        """Minimizada o en otro escritorio no llega nada a la pantalla. Sin
        pantalla, Qt solo deja de exponer una ventana escondida."""
        ventana = self.ventana("Gráficos")
        ventana._on_sample(self.foto)
        self.assertTrue(ventana._latido.isActive())
        ventana.hide()
        self.app.processEvents()
        ventana._avanzar_graficas()
        self.assertFalse(ventana._latido.isActive())
        ventana._on_sample(self.foto)
        self.assertFalse(ventana._latido.isActive())
        ventana.show()
        self.app.processEvents()
        ventana._on_sample(self.foto)
        self.assertTrue(ventana._latido.isActive())

    def test_el_espacio_lo_congela(self):
        ventana = self.ventana("Gráficos")
        ventana._on_sample(self.foto)
        self.assertTrue(ventana._latido.isActive())
        ventana.alternar_congelado()
        self.assertFalse(ventana._latido.isActive())


if __name__ == "__main__":
    unittest.main()
