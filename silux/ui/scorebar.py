"""La barra de puntuación de la página de Rendimiento.

Solo la monta `pages/performance.py`. Es la única de las cuatro que sale de
`widgets.py` sin arrastrar nada.
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget
from . import theme


class ScoreBar(QWidget):
    """Dónde cae una puntuación entre las conocidas de la misma pieza.

    Un número solo no dice nada: 9130 puntos no significa si es mucho o poco
    hasta que se sabe qué sacan los demás con el mismo procesador. La barra
    pone los extremos de lo registrado y una marca donde cae este equipo.

    No se dibuja cuando no hay con qué comparar. Es lo normal al principio
    —la tabla arranca casi vacía— y situar a alguien respecto de dos medidas
    sueltas sería peor que callar.
    """

    ALTO_BARRA = 10
    ALTO_MARCA = 16

    def __init__(self, palette: theme.Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._comparacion = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self.ALTO_MARCA + 4)

    def set_comparacion(self, comparacion) -> None:
        self._comparacion = comparacion
        self.setVisible(comparacion is not None)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._comparacion is None:
            return
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

        alto = self.ALTO_BARRA
        arriba = (self.height() - alto) / 2
        ancho = max(1, self.width() - 2)

        # El recorrido de lo registrado, en gris: es el contexto, no el dato.
        fondo = QRectF(1, arriba, ancho, alto)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(QColor(self._p.surface_alt)))
        pintor.drawRoundedRect(fondo, alto / 2, alto / 2)

        # La mediana, para que se vea respecto de qué se está lejos o cerca.
        comp = self._comparacion
        if comp.maximo > comp.minimo:
            centro = (comp.mediana - comp.minimo) / (comp.maximo - comp.minimo)
            x = 1 + centro * ancho
            pintor.setPen(QPen(QColor(self._p.muted), 1, Qt.PenStyle.DashLine))
            pintor.drawLine(QPointF(x, arriba), QPointF(x, arriba + alto))

        # Y la marca de este equipo, en el color de acento, que es el que el
        # programa usa para lo que le pertenece a quien mira.
        x = 1 + comp.fraccion * ancho
        marca = QRectF(x - 2, arriba - (self.ALTO_MARCA - alto) / 2,
                       4, self.ALTO_MARCA)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(QColor(self._p.accent)))
        pintor.drawRoundedRect(marca, 2, 2)
        pintor.end()
