"""Los controles en reposo se distinguen del fondo, en los dos temas.

Lo que dice dónde está un control —el borde de un desplegable, el carril de
un interruptor apagado, la caja de una casilla— pide un contraste de 3:1
con lo que tiene al lado (WCAG 1.4.11), y el texto de una insignia, 4.5:1
(1.4.3). Con `line` de borde, en oscuro se quedaban en 1.2:1: el interruptor
apagado y el contorno de los desplegables casi no se veían en Ajustes.
"""

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import qt

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _luminancia(color) -> float:
    def canal(valor: int) -> float:
        c = valor / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return (0.2126 * canal(color.red()) + 0.7152 * canal(color.green())
            + 0.0722 * canal(color.blue()))


def contraste(a, b) -> float:
    """El cociente de WCAG 2 entre dos `QColor` opacos."""
    claro, oscuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def _sobre(color, fondo):
    """Un color translúcido ya posado sobre su fondo."""
    from PySide6.QtGui import QColor

    alfa = color.alphaF()
    return QColor(*(round(getattr(color, c)() * alfa + getattr(fondo, c)() * (1 - alfa))
                    for c in ("red", "green", "blue")))


def _regla(hoja: str, selector: str) -> str:
    """El cuerpo de la primera regla con ese selector exacto."""
    inicio = re.search(r"(^|\n)\s*" + re.escape(selector) + r"\s*\{", hoja)
    assert inicio, selector
    return hoja[inicio.end():hoja.index("}", inicio.end())]


def _color_del_borde(regla: str) -> str:
    encontrado = (re.search(r"border:\s*\d+px solid (#[0-9A-Fa-f]{6})", regla)
                  or re.search(r"border-color:\s*(#[0-9A-Fa-f]{6})", regla))
    assert encontrado, regla
    return encontrado.group(1)


# Los controles que se ven en reposo en Ajustes y en los diálogos, con el
# selector de la regla que les pone el borde.
CONTROLES = {
    "desplegable y selector": "QComboBox, QDoubleSpinBox, QSpinBox",
    "casilla": "QCheckBox::indicator",
    "botón secundario": "QPushButton",
    "botón de acompañar": "QPushButton#GhostButton",
}


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElContraste(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _paletas(self):
        from silux.ui import theme

        return {"oscuro": theme.DARK, "claro": theme.LIGHT}

    def test_el_borde_de_cada_control_se_distingue_de_lo_que_lo_rodea(self):
        from PySide6.QtGui import QColor

        from silux.ui import theme

        for tema, p in self._paletas().items():
            hoja = theme.stylesheet(p)
            for control, selector in CONTROLES.items():
                color = QColor(_color_del_borde(_regla(hoja, selector)))
                # Fuera, la tarjeta; dentro, el relleno del propio control.
                for fondo in ("surface", "surface_alt"):
                    with self.subTest(tema=tema, control=control, fondo=fondo):
                        self.assertGreaterEqual(contraste(color, p.q(fondo)), 3.0)

    def test_el_interruptor_apagado_se_ve_sobre_la_tarjeta(self):
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QWidget

        from silux.ui.pages.settings import Interruptor

        for tema, p in self._paletas().items():
            interruptor = Interruptor(p)
            interruptor.resize(interruptor.sizeHint())
            lienzo = QPixmap(interruptor.size())
            lienzo.fill(p.q("surface"))
            # Sin el fondo de la ventana: lo que se mide es lo que pinta él.
            interruptor.render(lienzo, renderFlags=QWidget.RenderFlag.DrawChildren)
            imagen = lienzo.toImage()
            maximo = max(contraste(imagen.pixelColor(x, y), p.q("surface"))
                         for x in range(imagen.width()) for y in range(imagen.height()))
            with self.subTest(tema=tema):
                self.assertGreaterEqual(maximo, 3.0)
            interruptor.deleteLater()

    def test_el_texto_de_cada_insignia_se_lee(self):
        from PySide6.QtGui import QColor

        from silux.ui.pages.settings import (ESTADOS_DE_PERMISOS, ESTADOS_DEL_MENU,
                                             Insignia)

        tonos = {tono for _clave, _ayuda, tono in
                 (*ESTADOS_DE_PERMISOS.values(), *ESTADOS_DEL_MENU.values())}
        for tema, p in self._paletas().items():
            for tono in sorted(tonos):
                insignia = Insignia(p)
                insignia.poner("Sin conceder", tono)
                estilo = insignia.styleSheet()
                texto = QColor(re.search(r"color: (#[0-9a-fA-F]{6})", estilo).group(1))
                r, g, b, a = re.search(r"background: rgba\((\d+), (\d+), (\d+), ([\d.]+)\)",
                                       estilo).groups()
                fondo = QColor(int(r), int(g), int(b))
                fondo.setAlphaF(float(a))
                fondo = _sobre(fondo, p.q("surface"))
                with self.subTest(tema=tema, tono=tono):
                    self.assertGreaterEqual(contraste(texto, fondo), 4.5)
                insignia.deleteLater()

    def test_las_flechas_del_selector_se_ven(self):
        """Medidas en la página montada con la hoja de la aplicación: el
        tamaño de la flecha lo decide la hoja, y fuera de ella no se aplica."""
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.settings import SettingsPage

        normales = Preferences().normalized()
        self.addCleanup(theme.apply, self.app, normales.theme, normales.density,
                        normales.font_scale)
        for tema in ("dark", "light"):
            p = theme.apply(self.app, tema, "normal")
            pagina = SettingsPage(normales, p)
            pagina.resize(1200, 900)
            pagina.show()
            self.app.processEvents()
            selector = pagina.interval
            imagen = selector.grab().toImage()
            flecha = p.q("muted")
            # Las dos flechas viven en la franja de los botones; el marco de
            # dos píxeles queda fuera, que también es de ese gris.
            ancho, alto = imagen.width(), imagen.height()
            pixeles = sum(
                1 for x in range(ancho - 22, ancho - 3) for y in range(3, alto - 3)
                if contraste(imagen.pixelColor(x, y), flecha) < 2.0)
            with self.subTest(tema=tema):
                # Dos triángulos de unos 8 × 4 px con su suavizado. Los de
                # antes, de 3 × 2, sumaban menos de una docena.
                self.assertGreaterEqual(pixeles, 40)
            pagina.close()
            pagina.deleteLater()


if __name__ == "__main__":
    unittest.main()
