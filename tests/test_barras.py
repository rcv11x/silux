"""Las barras de Inicio, Memoria y Almacenamiento, y su leyenda.

Tres cosas que se vieron en las capturas: en Inicio la caché iba con el color
del fondo de la barra y no se sabía dónde acababa; la leyenda de debajo no
decía de qué tramo era cada insignia, había que contarlos; y las insignias
de Almacenamiento, en compacto, iban pegadas a la barra.

Con el volcado del 5800X3D, que tiene memoria con caché y cinco discos.
"""

import os
import tempfile
import unittest
from unittest import mock

from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLasBarras(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana(self, **preferencias):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        prefs = Preferences(**preferencias).normalized()
        ventana = MainWindow(prefs)
        ventana.resize(prefs.window_width, prefs.window_height)
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(self.foto)
        ventana._on_sample(self.foto)
        for _vez in range(4):
            self.app.processEvents()
        return ventana

    def _barras(self, ventana):
        return {"Inicio, memoria": ventana.home_page.memoria.barra,
                "Inicio, discos": ventana.home_page.discos.barra,
                "Memoria": ventana.memory_page.bar,
                "Almacenamiento": ventana.storage_page.total_bar}

    def test_cada_insignia_lleva_el_color_de_su_tramo(self):
        ventana = self._ventana()
        for nombre, barra in self._barras(ventana).items():
            visibles = [s for s in barra._segments if s[1] > 0]
            insignias = barra._legend._widgets
            with self.subTest(barra=nombre):
                self.assertGreater(len(visibles), 1)
                self.assertEqual(len(insignias), len(visibles))
                for (etiqueta, _valor, token), insignia in zip(visibles, insignias):
                    self.assertIn(etiqueta, insignia.text())
                    self.assertIsNotNone(insignia.swatch(), etiqueta)
                    self.assertEqual(insignia.swatch().name(),
                                     barra._p.q(token).name(), etiqueta)

    def test_dos_tramos_no_comparten_color(self):
        ventana = self._ventana()
        for nombre, barra in self._barras(ventana).items():
            with self.subTest(barra=nombre):
                colores = [i.swatch().name() for i in barra._legend._widgets]
                self.assertEqual(len(colores), len(set(colores)), colores)

    def test_en_inicio_la_cache_no_es_del_color_del_fondo(self):
        from silux.i18n import _

        barra = self._ventana().home_page.memoria.barra
        fondo = barra._p.q("line").name()
        cache = [token for etiqueta, valor, token in barra._segments
                 if etiqueta == _("sys.mem.cache")]
        self.assertEqual(len(cache), 1)
        self.assertNotEqual(barra._p.q(cache[0]).name(), fondo)

    def test_inicio_y_memoria_reparten_la_memoria_igual(self):
        ventana = self._ventana()
        self.assertEqual(ventana.home_page.memoria.barra._segments,
                         ventana.memory_page.bar._segments)

    def test_el_tramo_libre_se_ve_en_la_leyenda(self):
        # Es del color de la barra vacía: sin borde, su cuadrado no se vería.
        from silux.i18n import _

        barra = self._ventana().memory_page.bar
        libre = next(i for i in barra._legend._widgets if _("sys.mem.free") in i.text())
        self.assertIsNotNone(libre._borde)

    def test_la_muestra_no_tapa_el_texto(self):
        from silux.ui.widgets import Badge

        sola, con_color = Badge("Caché  15.4 GB", quiet=True), Badge("Caché  15.4 GB", quiet=True)
        con_color.set_swatch(self.app.palette().window().color())
        self.assertGreater(con_color.sizeHint().width(), sola.sizeHint().width())

    def test_una_leyenda_de_dos_filas_va_entera_a_la_izquierda(self):
        # Con la muestra de color las insignias son más anchas y la leyenda de
        # la memoria pasa a dos filas en compacto. La de arriba se repartía
        # por todo el ancho: solo la última fila llevaba el muelle.
        #
        # La barra se monta sola y estrecha, para que las dos filas no
        # dependan de la densidad que haya dejado puesta otro test.
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        from silux import render
        from silux.ui import theme
        from silux.ui.widgets import StackedBar, memory_segments

        caja = QWidget()
        self.addCleanup(caja.close)
        barra = StackedBar(theme.palette_for(self.app, "dark"))
        QVBoxLayout(caja).addWidget(barra)
        caja.resize(300, 160)
        caja.show()
        memoria = self.foto.system.memory
        barra.set_segments(memory_segments(memoria), total=memoria.total_bytes,
                           formatter=render.size)
        for _vez in range(5):
            self.app.processEvents()
        leyenda = barra._legend
        self.assertGreater(leyenda.filas(), 1, "ya cabe en una fila: el test no mira nada")
        izquierdas = {}
        for insignia in leyenda._widgets:
            punto = insignia.mapTo(leyenda, QPoint(0, 0))
            izquierdas.setdefault(punto.y(), []).append(punto.x())
        self.assertGreater(len(izquierdas), 1)
        for fila, equis in izquierdas.items():
            self.assertEqual(min(equis), 0, f"la fila de y={fila} no empieza a la izquierda")

    def test_en_compacto_nada_se_monta_sobre_la_barra_de_almacenamiento(self):
        from PySide6.QtCore import QPoint

        ventana = self._ventana(density="compact", window_width=900, window_height=680)
        ventana.select_section("Almacenamiento")
        for _vez in range(4):
            self.app.processEvents()
        pagina = ventana.storage_page
        barra = pagina.total_bar

        def caja(widget):
            arriba = widget.mapTo(pagina, QPoint(0, 0)).y()
            return arriba, arriba + widget.height()

        _tipos_arriba, tipos_abajo = caja(pagina.badges)
        barra_arriba, _fin = caja(barra)
        tramo_abajo = barra_arriba + barra.BAR_HEIGHT
        leyenda_arriba, _fin = caja(barra._legend)
        self.assertGreaterEqual(barra_arriba - tipos_abajo, 6,
                                "las insignias de tipo van pegadas a la barra")
        self.assertGreaterEqual(leyenda_arriba - tramo_abajo, 4,
                                "la leyenda va pegada a la barra")


if __name__ == "__main__":
    unittest.main()
