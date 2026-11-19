"""El estilo de la interfaz: una marca, iconos en la barra y cifras sin aire de terminal.

Lo que aquí se vigila es lo que se decidió al elegir la dirección visual y
no puede deshacerse sin querer: que la marca es una sola, que cada sección
tiene su icono, que el ámbar no se gasta en cualquier cosa y que los títulos
de tarjeta no vuelven a gritar.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:                                    # pragma: no cover
    QApplication = None

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElEstilo(unittest.TestCase):

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

    def _ventana(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences().normalized())
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(self.foto)
        self.app.processEvents()
        return ventana

    def test_cada_seccion_tiene_su_icono_dibujado(self):
        from silux.ui import icons
        from silux.ui.app import SECTIONS

        self.assertEqual(set(icons.NAV), {clave for clave, _activa in SECTIONS})
        ventana = self._ventana()
        for fila in range(ventana.nav.count()):
            icono = ventana.nav.item(fila).icon()
            with self.subTest(seccion=SECTIONS[fila][0]):
                self.assertFalse(icono.isNull())
                # Dibujado de verdad: si el SVG no se lee sale transparente.
                imagen = icono.pixmap(18, 18).toImage()
                self.assertTrue(any(imagen.pixelColor(x, y).alpha() > 40
                                    for x in range(imagen.width())
                                    for y in range(imagen.height())))

    def test_el_icono_de_la_seccion_abierta_va_en_el_acento_y_los_demas_en_gris(self):
        from PySide6.QtGui import QColor, QIcon
        from silux.ui import icons

        paleta = self._ventana()._palette
        icono = icons.nav_icon("nav.cpu", paleta.muted, paleta.accent, 18)

        def color_dominante(modo):
            imagen = icono.pixmap(18, 18, modo).toImage()
            puntos = [imagen.pixelColor(x, y) for x in range(imagen.width())
                      for y in range(imagen.height())]
            return max(puntos, key=lambda c: c.alpha())

        def casi(pintado, pedido):
            # Al pintar con suavizado un canal puede bailar una unidad.
            pedido = QColor(pedido)
            return all(abs(a - b) <= 2 for a, b in (
                (pintado.red(), pedido.red()), (pintado.green(), pedido.green()),
                (pintado.blue(), pedido.blue())))
        self.assertTrue(casi(color_dominante(QIcon.Mode.Normal), paleta.muted))
        self.assertTrue(casi(color_dominante(QIcon.Mode.Selected), paleta.accent))
        self.assertFalse(casi(color_dominante(QIcon.Mode.Normal), paleta.accent))

    def test_la_marca_es_el_logo_y_no_un_emoji(self):
        import silux

        ventana = self._ventana()
        self.assertFalse(hasattr(silux, "EMOJI"))
        self.assertFalse(ventana.brand_mark.pixmap().isNull())
        textos = [e.text() for e in ventana.findChildren(QLabel)]
        self.assertIn("Silux", textos)
        self.assertFalse([t for t in textos if "🔎" in t])

    def test_el_icono_del_programa_y_la_marca_son_el_mismo_dibujo(self):
        # Uno solo para todo: el del paquete es el que usan la ventana, la
        # entrada de menú y el AppImage, y la marca suelta sale de él.
        assets = RAIZ / "silux" / "ui" / "assets"
        icono = (assets / "silux.svg").read_text()
        for archivo in ("silux-mark-dark.svg", "silux-mark-light.svg", "silux-symbolic.svg"):
            self.assertTrue((assets / archivo).is_file(), archivo)
        # La pista de la «S» con sus dos vías, sobre la ficha ámbar.
        self.assertIn("H40 L32 36 V40 L40 48 H56 L64 56 V60 L56 68", icono)
        self.assertIn("#E27F22", icono)
        self.assertIn("currentColor", (assets / "silux-symbolic.svg").read_text())

    def test_la_version_va_al_pie_de_la_barra_no_encima_de_la_navegacion(self):
        ventana = self._ventana()
        panel = ventana.nav.parentWidget()
        version = next(e for e in panel.findChildren(QLabel) if e.text().startswith("versión"))
        self.assertGreater(version.mapTo(panel, version.rect().topLeft()).y(),
                           ventana.nav.mapTo(panel, ventana.nav.rect().bottomLeft()).y() - 2)

    def test_los_titulos_de_tarjeta_y_de_ficha_no_van_en_mayusculas(self):
        ventana = self._ventana()
        for seccion in ("Inicio", "CPU", "Gráficos", "Almacenamiento"):
            ventana.select_section(seccion)
            self.app.processEvents()
            pagina = ventana.stack.currentWidget()
            titulos = [e.text() for e in pagina.findChildren(QLabel)
                       if e.objectName() in ("CardTitle", "TileLabel") and e.isVisible()
                       and len(e.text()) > 3 and any(c.isalpha() for c in e.text())]
            with self.subTest(pagina=seccion):
                self.assertTrue(titulos)
                self.assertFalse([t for t in titulos if t.isupper()], titulos)

    def test_las_cifras_no_van_en_monoespaciada_y_no_bailan(self):
        from silux.ui import theme

        cifras = theme.value_font()
        self.assertNotEqual(cifras.family(), theme.mono_font().family())
        from PySide6.QtGui import QFontMetrics
        medida = QFontMetrics(cifras)
        anchos = {medida.horizontalAdvance(str(n) * 4) for n in range(10)}
        self.assertEqual(len(anchos), 1, anchos)

    def test_las_tarjetas_no_llevan_un_borde_que_pese(self):
        from silux.ui import theme

        for tema in ("dark", "light"):
            paleta = theme.palette_for(self.app, tema)
            regla = theme.stylesheet(paleta).split("QFrame#Card {")[1].split("}")[0]
            self.assertIn(f"border: 1px solid {paleta.line_soft};", regla)
            self.assertNotEqual(paleta.line_soft, paleta.line)


if __name__ == "__main__":
    unittest.main()
