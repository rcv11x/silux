"""La cifra del pico de una gráfica no se monta encima de la curva.

Se ponía encima del punto si cabía y, si no, al lado y a su altura, dando por
hecho que «a los lados del máximo la curva ya ha bajado». Eso vale para una
aguja. En una meseta —la temperatura que sube y se queda, que es lo normal
bajo carga— la línea sigue justo ahí, y la cifra la tapaba en las fichas.
"""

import unittest

from silux import render
from silux.ui import theme
from tests import qt

try:
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

CAJA = (40.0, 12.0)        # lo que ocupa una cifra como «62.0 °C» en una ficha


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaCifraDelPico(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _grafica(self, valores, ancho=300, alto=40, capacidad=None):
        from silux.ui.widgets import Series, Sparkline

        g = Sparkline(theme.DARK, capacity=capacidad or len(valores))
        g.set_series(Series("prueba", "MHz"))
        g.resize(ancho, alto)
        g.set_formatter(render.temperature, 1.0)
        for v in valores:
            g.push(v)
        return g

    def _sitio(self, g):
        rect, puntos, _valores = g._trazado()
        caja = g._sitio_de_la_cifra(rect, puntos, g._indice_del_pico(), *CAJA)
        return rect, puntos, caja

    def _toca_la_curva(self, puntos, caja: QRectF) -> bool:
        """Si algún tramo de la línea pasa por dentro de la caja."""
        for a, b in zip(puntos, puntos[1:]):
            for paso in range(21):
                t = paso / 20
                x, y = a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t
                if caja.left() <= x <= caja.right() and caja.top() <= y <= caja.bottom():
                    return True
        return False

    MESETA = [40] * 15 + [41, 60, 60.5] + [60] * 20 + [45] * 10 + [44]
    AGUJA = [40, 41, 40, 41, 40, 41, 40, 90, 40, 41, 40, 41, 40, 41, 40, 41, 40]

    def test_en_una_meseta_no_tapa_la_linea(self):
        g = self._grafica(self.MESETA)
        self.assertIsNotNone(g._indice_del_pico())
        rect, puntos, caja = self._sitio(g)
        if caja is not None:
            self.assertFalse(self._toca_la_curva(puntos, caja), caja)
            self.assertTrue(rect.contains(caja), caja)

    def test_el_sitio_de_antes_si_la_tapaba(self):
        # Para que el test de arriba compruebe algo: al lado del punto y a su
        # altura, que es donde se ponía, la meseta pasa por dentro.
        g = self._grafica(self.MESETA)
        _rect, puntos, _caja = self._sitio(g)
        punto = puntos[g._indice_del_pico()]
        antes = QRectF(punto.x() + 6, punto.y() - CAJA[1] / 2, *CAJA)
        self.assertTrue(self._toca_la_curva(puntos, antes))

    def test_una_aguja_sigue_llevando_su_cifra(self):
        g = self._grafica(self.AGUJA)
        _rect, puntos, caja = self._sitio(g)
        self.assertIsNotNone(caja)
        self.assertFalse(self._toca_la_curva(puntos, caja))

    def test_en_ninguna_forma_de_curva_se_monta(self):
        import random

        azar = random.Random(7)
        for caso in range(200):
            n = azar.randint(8, 90)
            valores = [azar.uniform(20, 95) if azar.random() < 0.3 else 50.0 for _ in range(n)]
            valores[-1] = min(valores) - 1          # que el máximo no sea el último
            g = self._grafica(valores, ancho=azar.choice((160, 300, 520)),
                              alto=azar.choice((28, 40, 64)),
                              capacidad=azar.choice((n, 90)))
            if g._indice_del_pico() is None:
                continue
            rect, puntos, caja = self._sitio(g)
            if caja is None:
                continue
            with self.subTest(caso=caso):
                self.assertFalse(self._toca_la_curva(puntos, caja))
                self.assertTrue(rect.adjusted(-0.01, -0.01, 0.01, 0.01).contains(caja))

    def test_si_no_hay_sitio_no_se_pone_y_no_revienta(self):
        from PySide6.QtGui import QPixmap

        # Un diente de sierra que llena el cuadro: no queda hueco libre.
        valores = [20, 95] * 30 + [10]
        g = self._grafica(valores, ancho=120, alto=24)
        _rect, _puntos, caja = self._sitio(g)
        self.assertIsNone(caja)
        g.render(QPixmap(120, 24))


if __name__ == "__main__":
    unittest.main()
