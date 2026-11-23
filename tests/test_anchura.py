"""Ninguna página se sale por la derecha en la ventana compacta.

A 900×680 con la densidad compacta —el tamaño de las capturas de la
documentación y el de una ventana a media pantalla en un portátil—,
Rendimiento y Ajustes pintaban sus botones y sus párrafos cortados contra el
borde: alguna fila pedía más ancho mínimo del que había, el área de
desplazamiento no tiene barra horizontal y lo que sobraba simplemente no se
veía. Nada fallaba ni avisaba; solo se notaba mirando la captura.

Aquí se monta la ventana de verdad, se le da una muestra, se recorren las
catorce secciones y se mide cada widget visible contra el borde de la ventana.
La muestra es la del equipo que ejecuta la suite, que es lo que da nombres y
listas de verdad, más una batería para que la sección de Batería exista
también en un sobremesa. Lo que se exige —que nada se salga— vale para
cualquier hardware: no depende de que haya algo concreto que encontrar.
"""

import dataclasses
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QWidget

from silux.model import Battery
from silux.settings import Preferences
from silux.ui import theme
from tests import muestras, qt
from tests.per_dump import per_dump

ANCHO, ALTO = 900, 680

BATERIA = Battery(
    name="BAT0", status="bat.status.discharging", percent=76.0,
    design_wh=57.0, full_wh=50.2, now_wh=38.1,
    voltage_v=11.9, design_voltage_v=11.55, power_w=8.4, cycles=212,
    manufacturer="SMP", model="5B10W13930", technology="Li-poly",
    charge_start_percent=75, charge_end_percent=80)


def _app():
    return qt.app()


def _asentar(app, veces=4):
    # Los layouts anidados dentro del área de desplazamiento necesitan más de
    # una pasada de eventos para asentarse, lo mismo que en `--screenshot`.
    for _vuelta in range(veces):
        app.processEvents()


class TestNadaSeSalePorLaDerecha(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        prefs = Preferences(density="compact", window_width=ANCHO,
                            window_height=ALTO).normalized()
        theme.apply(cls.app, prefs.theme, prefs.density, prefs.font_scale)

        from silux.ui.app import SECTIONS, MainWindow

        cls.secciones = SECTIONS
        cls.ventana = MainWindow(prefs)
        cls.ventana.resize(ANCHO, ALTO)
        cls.ventana.show()

        muestra = dataclasses.replace(muestras.foto_real(), batteries=(BATERIA,))
        for _vuelta in range(3):
            cls.ventana._on_sample(muestra)
            _asentar(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.ventana.close()

    @staticmethod
    def _se_alcanza_desplazando(widget: QWidget, pagina: QWidget) -> bool:
        """Si lo que sobra de este widget se ve moviendo una barra horizontal.

        `Table` va en su propia zona de desplazamiento para que una tabla
        ancha no arrastre a la página: lo que queda a la derecha no está
        cortado, está a un gesto. La página no tiene esa barra, y lo que se
        salga de ella sí se pierde. Se mira que la barra exista de verdad y
        no solo que pudiera: una zona que no se desplaza recorta igual.
        """
        padre = widget.parentWidget()
        while padre is not None and padre is not pagina:
            zona = padre.parentWidget()
            if (isinstance(zona, QAbstractScrollArea) and zona is not pagina
                    and padre is zona.viewport()
                    and zona.horizontalScrollBarPolicy()
                    != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                    and zona.horizontalScrollBar().maximum() > 0):
                return True
            padre = zona
        return False

    def _desbordados(self) -> list[str]:
        ventana = self.ventana
        pagina = ventana.stack.currentWidget()
        fuera = []
        for widget in [pagina, *pagina.findChildren(QWidget)]:
            if not widget.isVisibleTo(ventana) or widget.width() <= 0:
                continue
            if self._se_alcanza_desplazando(widget, pagina):
                continue
            izquierda = widget.mapTo(ventana, QPoint(0, 0)).x()
            derecha = izquierda + widget.width()
            if izquierda < 0 or derecha > ventana.width():
                nombre = widget.objectName() or type(widget).__name__
                texto = getattr(widget, "text", lambda: "")()
                fuera.append(f"{nombre} «{str(texto)[:40]}» "
                             f"x={izquierda}..{derecha}")
        return fuera

    def test_las_catorce_secciones_caben_a_lo_ancho(self):
        self.assertEqual(self.ventana.width(), ANCHO)
        self.assertEqual(len(self.secciones), 14)
        for fila, (clave, _activa) in enumerate(self.secciones):
            with self.subTest(seccion=clave):
                self.ventana.nav.setCurrentRow(fila)
                _asentar(self.app)
                self.assertIs(self.ventana.stack.currentWidget(),
                              self.ventana.stack.widget(fila),
                              f"la sección {clave} no se abrió")
                fuera = self._desbordados()
                self.assertEqual(fuera, [], f"{clave}: se sale por la derecha "
                                            f"de {ANCHO} px:\n  " + "\n  ".join(fuera[:12]))

    def test_la_comprobacion_ve_lo_que_se_sale(self):
        """Sin esto, un `_desbordados` que no mirara nada daría verde."""
        from PySide6.QtWidgets import QLabel

        self.ventana.nav.setCurrentRow(0)
        _asentar(self.app)
        intruso = QLabel("ancho de más", self.ventana.stack.currentWidget())
        intruso.setGeometry(0, 0, ANCHO * 2, 20)
        intruso.show()
        try:
            self.assertTrue(any("ancho de más" in f for f in self._desbordados()))
        finally:
            intruso.hide()
            intruso.setParent(None)
            intruso.deleteLater()
            _asentar(self.app)


    def test_una_tabla_ancha_se_desplaza_y_no_cuenta_como_cortada(self):
        """Una tabla con más columnas de las que caben tiene su propia barra.

        Se vio en un equipo con dos monitores: la tabla de pantallas de
        Gráficos no cabe a 900 px, se desplaza, y sus celdas contaban como
        salidas de la ventana. Sin barra, las mismas celdas sí cuentan.
        """
        from silux.ui.widgets import Table

        self.ventana.nav.setCurrentRow(0)
        _asentar(self.app)
        pagina = self.ventana.stack.currentWidget()
        tabla = Table([f"columna {n}" for n in range(12)], parent=pagina)
        tabla.setGeometry(0, 0, 300, 80)
        tabla.set_rows([[f"un valor bastante largo {n}" for n in range(12)]])
        tabla.show()
        _asentar(self.app)
        try:
            self.assertGreater(tabla.horizontalScrollBar().maximum(), 0)
            self.assertFalse(any("un valor bastante largo" in f for f in self._desbordados()))
            tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            _asentar(self.app)
            self.assertTrue(any("un valor bastante largo" in f for f in self._desbordados()))
        finally:
            tabla.hide()
            tabla.setParent(None)
            tabla.deleteLater()
            _asentar(self.app)


class TestLaFilaReparteSegunLoQuePidenSusHijos(unittest.TestCase):
    """`ResponsiveRow` cuenta con el mínimo de cada hijo, no solo con el suyo.

    Los números son los de Ajustes medidos en la ventana: la tarjeta de
    Muestreo pide 340 px y la de Apariencia 540. A 1280×800 la fila mide 1055
    y caben las dos (340 + 540 + el hueco); a 900×680 en compacto mide 713, no
    caben, y repartirlas en dos columnas era lo que empujaba la página fuera
    de la ventana.
    """

    class _Pide(QWidget):
        def __init__(self, ancho):
            super().__init__()
            self._ancho = ancho

        def minimumSizeHint(self):  # noqa: N802
            from PySide6.QtCore import QSize
            return QSize(self._ancho, 20)

    def _fila(self, ancho):
        from silux.ui.widgets import ResponsiveRow

        _app()
        fila = ResponsiveRow(min_item_width=110)
        fila.add(self._Pide(340))
        fila.add(self._Pide(540))
        fila.resize(ancho, 200)
        fila.show()
        _asentar(QApplication.instance())
        self.addCleanup(fila.close)
        return fila

    def test_si_caben_van_en_dos_columnas_aunque_no_midan_lo_mismo(self):
        self.assertEqual(self._fila(1055)._columns, 2)

    def test_si_no_caben_bajan_a_una(self):
        self.assertEqual(self._fila(713)._columns, 1)

    def test_y_no_le_pide_a_quien_la_contiene_mas_que_el_hijo_mas_ancho(self):
        # Si pidiera el ancho de la rejilla en dos columnas, la ensancharían
        # hasta él y su propia anchura le diría que caben.
        self.assertEqual(self._fila(713).minimumSizeHint().width(), 540)




class TestTheLargestFontInANarrowWindow(unittest.TestCase):
    """With the largest font, at the narrowest the window allows, no page of
    any dump runs off the right edge. Header lines that didn't wrap, rows of
    buttons, widths reserved as minimums and a row's column width scaled
    with the font pushed every page out at 760 px."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _check(self, folder, density: str = "normal"):
        from silux.ui.app import MainWindow
        from tests.test_equipos import shared_snapshot

        # Left exactly as found: the defaults aren't what other tests expect.
        from PySide6.QtGui import QPalette
        saved = (theme.METRICS, self.app.styleSheet(), QPalette(self.app.palette()),
                 self.app.style().name())

        def restore():
            theme.METRICS = saved[0]
            self.app.setStyle(saved[3])
            self.app.setPalette(saved[2])
            self.app.setStyleSheet(saved[1])

        self.addCleanup(restore)
        metrics = theme.set_density(density, "máximo")
        width = metrics.min_window_w
        prefs = Preferences(density=density, font_scale="máximo", window_width=width,
                            window_height=ALTO).normalized()
        theme.apply(self.app, prefs.theme, prefs.density, prefs.font_scale)
        window = MainWindow(prefs)
        self.addCleanup(window.close)
        window.resize(width, ALTO)
        window.show()
        snapshot = shared_snapshot(folder)
        for _vuelta in range(2):
            window._on_sample(snapshot)
            _asentar(self.app)
        probe = TestNadaSeSalePorLaDerecha.__new__(TestNadaSeSalePorLaDerecha)
        probe.ventana = window
        self.assertEqual(window.width(), width)
        for row in range(window.nav.count()):
            window.nav.setCurrentRow(row)
            _asentar(self.app)
            with self.subTest(dump=folder.name, density=density,
                              section=window.nav.item(row).text()):
                self.assertEqual(probe._desbordados()[:12], [])

    def _every_page(self, folder):
        self._check(folder)

    def test_compact_and_spacious_too(self):
        from tests.test_equipos import EQUIPOS

        for density in ("compact", "spacious"):
            self._check(EQUIPOS / "5800x3d", density)


per_dump(TestTheLargestFontInANarrowWindow, "every_page", TestTheLargestFontInANarrowWindow._every_page)


def _first_snapshot(folder):
    """A dump's first snapshot: its rates still unknown."""
    from silux import volcado
    from silux.collector import Collector

    with volcado.mounted(folder):
        collector = Collector()
        try:
            return collector.snapshot()
        finally:
            collector.close()


class TestAWordInABigTile(unittest.TestCase):
    """«Calculando…» in place of a figure, on the first reading: at figure
    size it came out cut in narrow tiles («Calculandc» in CPU, «Calculando..»
    in Storage). It must fit whole with the normal font and the largest, from
    the narrowest window to a wide one: in between, the tiles go four to a
    row with room for their figures, not for a word."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _check(self, font_scale: str, cases):
        from PySide6.QtGui import QFontMetricsF, QPalette

        from silux.ui.app import MainWindow
        from silux.ui.widgets import _Cifra
        from tests.test_equipos import EQUIPOS

        saved = (theme.METRICS, self.app.styleSheet(), QPalette(self.app.palette()),
                 self.app.style().name())

        def restore():
            theme.METRICS = saved[0]
            self.app.setStyle(saved[3])
            self.app.setPalette(saved[2])
            self.app.setStyleSheet(saved[1])

        self.addCleanup(restore)
        metrics = theme.set_density("normal", font_scale)
        prefs = Preferences(font_scale=font_scale, window_width=metrics.min_window_w,
                            window_height=ALTO).normalized()
        theme.apply(self.app, prefs.theme, prefs.density, prefs.font_scale)
        for dump, sections in cases:
            window = MainWindow(prefs)
            self.addCleanup(window.close)
            window.show()
            first = _first_snapshot(EQUIPOS / dump)
            self.assertTrue(first.first_reading)
            window._on_sample(first)
            seen = 0
            for width in (metrics.min_window_w, 900, 1000, 1100, 1300, 1600):
                window.resize(max(width, metrics.min_window_w), ALTO)
                _asentar(self.app)
                for section in sections:
                    window.select_section(section)
                    _asentar(self.app)
                    page = window.stack.currentWidget()
                    for label in page.findChildren(_Cifra):
                        if not (label.palabra and label.isVisibleTo(page)):
                            continue
                        seen += 1
                        font = getattr(label, "word_font", label.font)()
                        with self.subTest(dump=dump, font=font_scale, width=width,
                                          section=section, word=label.text()):
                            # In fractions, as the painter elides.
                            self.assertLessEqual(
                                QFontMetricsF(font).horizontalAdvance(label.text()),
                                label.contentsRect().width())
            self.assertGreater(seen, 0, f"no word on {sections} of {dump}")

    def test_normal_font(self):
        self._check("normal", (("5800x3d", ("CPU", "Almacenamiento")), ("i5-8350u", ("Batería",))))

    def test_largest_font(self):
        self._check("máximo", (("5800x3d", ("CPU", "Almacenamiento")), ("i5-8350u", ("Batería",))))
