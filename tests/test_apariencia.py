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
        # desincronizan, elegir un color válido lo revertiría al de serie.
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
        self.assertEqual(Preferences(accent="fucsia").normalized().accent,
                         Preferences().accent)
        self.assertEqual(Preferences(accent="azul").normalized().accent, "azul")


class TestLecturaDeGraficas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _grafica(self, valores, ancho=100, capacidad=None) -> Sparkline:
        """Por defecto, una gráfica ya llena: es como se usa el 99 % del rato.

        La capacidad importa porque el ancho se reparte entre ella y no entre
        las muestras que haya, para que la curva no se recoloque cada vez que
        entra una. Mientras se llena, la serie ocupa solo la parte derecha.
        """
        chart = Sparkline(theme.DARK, capacity=capacidad or max(2, len(valores)))
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

    def test_fuera_del_widget_no_señala_nada(self):
        chart = self._grafica([1, 2, 3])
        self.assertIsNone(chart._index_at(-40))
        self.assertIsNone(chart._index_at(9999))

    def test_sobre_el_hueco_de_una_grafica_a_medio_llenar_tampoco(self):
        """Mientras se llena, la mitad izquierda está vacía: ahí no hay nada
        que leer, y antes el cursor señalaba una muestra que estaba en el
        otro extremo."""
        chart = self._grafica([10, 20, 30], capacidad=90)
        self.assertIsNone(chart._index_at(5))
        self.assertEqual(chart._index_at(99), 2)

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
        from silux.ui.corematrix import CoreMatrix
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


class TestCurvaSuave(unittest.TestCase):
    """Una gráfica de datos no puede dibujar lo que no midió.

    Unir las muestras con curvas se lee mucho mejor que con rectas, pero una
    curva mal hecha se abomba entre dos puntos y enseña un pico de temperatura
    que nunca ocurrió. La de aquí pasa por todas las muestras y no se sale del
    tramo entre cada dos.
    """

    def _puntos(self, alturas):
        from PySide6.QtCore import QPointF
        return [QPointF(i * 10.0, y) for i, y in enumerate(alturas)]

    def _recorrer(self, camino, pasos=200):
        """Las alturas por las que pasa la curva, muestreadas."""
        return [camino.pointAtPercent(i / pasos).y() for i in range(pasos + 1)]

    def test_pasa_por_todas_las_muestras(self):
        from silux.ui.widgets import curva_suave
        alturas = [50.0, 20.0, 80.0, 35.0]
        camino = curva_suave(self._puntos(alturas))
        recorrido = self._recorrer(camino)
        for altura in alturas:
            self.assertTrue(any(abs(y - altura) < 0.6 for y in recorrido),
                            f"la curva no pasa por {altura}")

    def test_no_se_sale_por_arriba_ni_por_abajo(self):
        """Es lo que evita el pico inventado entre dos muestras iguales."""
        from silux.ui.widgets import curva_suave
        alturas = [40.0, 40.0, 10.0, 40.0, 40.0]
        recorrido = self._recorrer(curva_suave(self._puntos(alturas)))
        self.assertGreaterEqual(min(recorrido), 10.0 - 0.5)
        self.assertLessEqual(max(recorrido), 40.0 + 0.5)

    def test_una_linea_plana_se_queda_plana(self):
        from silux.ui.widgets import curva_suave
        recorrido = self._recorrer(curva_suave(self._puntos([30.0] * 6)))
        self.assertLess(max(recorrido) - min(recorrido), 0.01)

    def test_con_una_sola_muestra_no_revienta(self):
        from silux.ui.widgets import curva_suave
        self.assertEqual(curva_suave(self._puntos([12.0])).elementCount(), 1)

    def test_sin_ninguna_tampoco(self):
        from silux.ui.widgets import curva_suave
        self.assertEqual(curva_suave([]).elementCount(), 0)

    def test_el_relleno_baja_hasta_el_suelo_y_cierra(self):
        from silux.ui.widgets import curva_suave
        camino = curva_suave(self._puntos([20.0, 50.0, 30.0]), cerrar_en=100.0)
        self.assertTrue(any(abs(y - 100.0) < 0.6 for y in self._recorrer(camino)))


class TestJerarquiaVisual(unittest.TestCase):
    """Que cada cosa pese lo que le toca en la pantalla."""

    def test_el_titulo_de_una_tarjeta_pesa_mas_que_una_cabecera(self):
        """Un título nombra la tarjeta entera; una cabecera, una columna.

        Compartían estilo, así que agrandar el primero agrandaba la segunda y
        las tablas acababan gritando tanto como las secciones que las
        contienen.
        """
        app = QApplication.instance() or QApplication([])
        hoja = theme.stylesheet(theme.palette_for(app, "dark"))
        self.assertIn("QLabel#CardTitle", hoja)
        self.assertIn("QLabel#ColumnTitle", hoja)

    def test_la_tabla_usa_su_propio_estilo(self):
        from silux.ui.widgets import Table
        app = QApplication.instance() or QApplication([])
        tabla = Table(("Uno", "Dos"), numeric=(False, True))
        from PySide6.QtWidgets import QLabel
        nombres = {e.objectName() for e in tabla.findChildren(QLabel)}
        self.assertIn("ColumnTitle", nombres)
        self.assertNotIn("CardTitle", nombres)


class TestTodosLosBotonesReaccionanAlRaton(unittest.TestCase):
    """Un botón que no responde al ratón parece desactivado.

    Los de cancelar la prueba y borrar el historial se quedaban quietos, y el
    motivo estaba en la especificidad de las hojas de Qt: un selector con id
    —`QPushButton#Danger`— gana a uno con pseudo-clase —`QPushButton:hover`—,
    así que el color y el borde del hover general nunca llegaban a ellos. El
    único hover propio que tenía `#Danger` ponía el fondo que ya tenía puesto.

    Se comprueba sobre la hoja y no sobre un widget pintado: fuera de una
    ventana de verdad el estilo no se aplica igual, y esa prueba diría que
    todo está bien pase lo que pase.
    """

    # Los nombres que llevan los botones con estilo propio.
    CON_ESTILO_PROPIO = ("Danger", "GhostButton")

    @staticmethod
    def _bloque(hoja: str, selector: str) -> str:
        """Lo que declara una regla, o cadena vacía si no está."""
        import re

        encaje = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", hoja)
        return encaje.group(1) if encaje else ""

    def test_cada_boton_con_estilo_propio_tiene_su_hover(self):
        from silux.ui import theme

        for paleta in (theme.DARK, theme.LIGHT):
            hoja = theme.stylesheet(paleta)
            for nombre in self.CON_ESTILO_PROPIO:
                with self.subTest(nombre=nombre, oscuro=paleta is theme.DARK):
                    reglas = self._bloque(hoja, f"QPushButton#{nombre}:hover")
                    self.assertTrue(reglas,
                                    f"#{nombre} no declara ningún hover")

    def test_y_ese_hover_cambia_algo_que_se_ve(self):
        """Poner el fondo que ya tenía es no tener hover.

        No basta con comparar las dos reglas: la mala declaraba `background` y
        la normal `color`, así que eran distintas y aun así el botón se quedaba
        igual. Lo que hay que mirar es cada propiedad del hover contra el valor
        que ya tiene el botón, heredando del `QPushButton` de base lo que su
        propia regla no diga.
        """
        from silux.ui import theme

        for paleta in (theme.DARK, theme.LIGHT):
            hoja = theme.stylesheet(paleta)
            base = _declaraciones(self._bloque(hoja, "QPushButton"))
            for nombre in self.CON_ESTILO_PROPIO:
                with self.subTest(nombre=nombre, oscuro=paleta is theme.DARK):
                    normal = base | _declaraciones(
                        self._bloque(hoja, f"QPushButton#{nombre}"))
                    encima = _declaraciones(
                        self._bloque(hoja, f"QPushButton#{nombre}:hover"))
                    cambian = [k for k, v in encima.items()
                               if normal.get(k) != v]
                    self.assertTrue(
                        cambian,
                        f"#{nombre} declara un hover que deja todo como estaba: "
                        f"{encima}")

    def test_el_boton_normal_sigue_teniendo_el_suyo(self):
        from silux.ui import theme

        reglas = self._bloque(theme.stylesheet(theme.DARK), "QPushButton:hover")
        self.assertIn("border-color", reglas)
        self.assertIn("color", reglas)


def _declaraciones(bloque: str) -> dict:
    """Las propiedades de una regla, para poder compararlas."""
    salida = {}
    for trozo in bloque.split(";"):
        if ":" in trozo:
            clave, valor = trozo.split(":", 1)
            salida[clave.strip()] = valor.strip()
    return salida
