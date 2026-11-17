"""Ningún nombre de sección sale cortado en la barra lateral.

En compacto la barra medía 140 px fijos y «Almacenamiento», con su icono
delante, no cabía: «Almacenamien…». El ancho escrito a mano es un suelo; lo
que manda es lo que pide el nombre más largo con la letra, la densidad y el
idioma que haya, y con la seminegrita de la sección abierta.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux import i18n
from silux.settings import Preferences
from tests import qt

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontMetricsF
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaBarraLateral(unittest.TestCase):

    def _ventana(self, **preferencias):
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        normales = Preferences().normalized()
        self.addCleanup(theme.apply, app, normales.theme, normales.density,
                        normales.font_scale, normales.accent)
        prefs = Preferences(**preferencias).normalized()
        theme.apply(app, prefs.theme, prefs.density, prefs.font_scale, prefs.accent)
        ventana = MainWindow(prefs)
        self.addCleanup(ventana.close)
        ventana.resize(900, 680)
        ventana.show()
        for _vez in range(4):
            app.processEvents()
        return ventana

    def _sobra(self, ventana) -> list[str]:
        """Los nombres que no caben, abiertos o no."""
        lista = ventana.nav
        gruesa = QFont(lista.font())
        gruesa.setWeight(QFont.Weight.DemiBold)
        normal, gruesa = QFontMetricsF(lista.font()), QFontMetricsF(gruesa)
        cortados = []
        for fila in range(lista.count()):
            item = lista.item(fila)
            caja = lista.visualItemRect(item)
            pide = lista.sizeHintForIndex(lista.indexFromItem(item)).width() + (
                gruesa.horizontalAdvance(item.text()) - normal.horizontalAdvance(item.text()))
            if pide > caja.width() or caja.right() > lista.viewport().width():
                cortados.append(f"{item.text()}: pide {pide:.0f} y tiene {caja.width()}")
        return cortados

    def test_caben_todos_en_cada_densidad_y_tamano_de_letra(self):
        for densidad in ("compact", "normal", "spacious"):
            for letra in ("normal", "máximo"):
                with self.subTest(densidad=densidad, letra=letra):
                    ventana = self._ventana(density=densidad, font_scale=letra)
                    self.assertEqual(self._sobra(ventana), [])

    def test_y_con_la_interfaz_en_ingles(self):
        self.addCleanup(i18n.set_language, "es")
        i18n.set_language("en")
        self.assertEqual(self._sobra(self._ventana(density="compact")), [])


if __name__ == "__main__":
    unittest.main()
