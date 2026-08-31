"""El mapa de cachés: qué núcleos comparten cada nivel.

Solo lo monta `pages/caches.py`. `_contiguous_runs` se viene con él: agrupa
los núcleos consecutivos para escribir «0-7» en vez de ocho números, y no lo
llama nadie más.
"""

from __future__ import annotations

from typing import Optional, Sequence
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget
from ..i18n import _
from . import theme
from .theme import Palette, mono_font, ui_font


def _contiguous_runs(positions: Sequence[int]) -> list[tuple[int, int]]:
    """Agrupa posiciones consecutivas: [0,1,4,5] -> [(0,1), (4,5)].

    Hace falta porque una instancia de caché puede tocar CPUs que no queden
    seguidas en el eje si la topología es rara; así se dibuja un bloque por
    tramo en vez de uno gigante que abarque huecos ajenos.
    """
    runs: list[tuple[int, int]] = []
    for value in positions:
        if runs and value == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], value)
        else:
            runs.append((value, value))
    return runs


class CacheMap(QWidget):
    """Mapa de la jerarquía de caché sobre el eje de CPUs lógicas.

    Enseña de un vistazo lo que una tabla de tamaños no dice: qué núcleos
    comparten cada instancia. Que la L2 sea privada por núcleo y la L3 común a
    los doce hilos se ve en la forma, no leyendo números.

    El eje va ordenado por núcleo físico, no por índice de CPU, para que los
    hermanos SMT queden juntos: en este equipo la CPU 0 y la 6 son el mismo
    núcleo, y de otro modo su L1 saldría partida en dos trozos.
    """

    GUTTER = 76
    ROW_H = 30
    ROW_GAP = 5
    AXIS_H = 18

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._axis: list[int] = []
        self._rows: list[dict] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(150)

    def set_data(self, axis: Sequence[int], rows: Sequence[dict]) -> None:
        """`axis` son las CPUs en orden de dibujo; cada fila lleva etiqueta,
        nivel e instancias como tuplas de CPUs con su tamaño ya formateado."""
        self._axis = list(axis)
        self._rows = list(rows)
        self.setFixedHeight(self.sizeHint().height())
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        rows = max(len(self._rows), 1)
        return QSize(320, rows * self.ROW_H + (rows - 1) * self.ROW_GAP + self.AXIS_H + 4)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._axis or not self._rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gutter = min(self.GUTTER, self.width() * 0.3)
        plot_left = gutter + 6
        plot_width = max(self.width() - plot_left - 2, 40)
        column = plot_width / len(self._axis)
        position = {cpu: i for i, cpu in enumerate(self._axis)}

        label_font = ui_font(max(7, theme.METRICS.small_pt - 1))
        value_font = mono_font(max(7, theme.METRICS.mono_pt - 1))
        max_level = max((row.get("level", 1) for row in self._rows), default=1)

        for index, row in enumerate(self._rows):
            top = index * (self.ROW_H + self.ROW_GAP)
            band = QRectF(plot_left, top, plot_width, self.ROW_H)

            painter.setFont(label_font)
            painter.setPen(self._p.q("muted"))
            painter.drawText(
                QRectF(0, top, gutter, self.ROW_H),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                row["label"],
            )

            # Cuanto más alto el nivel, más presencia: la L3 es la que manda.
            weight = 0.10 + 0.16 * (row.get("level", 1) / max_level)
            for cpus, text in row["instances"]:
                for start, end in _contiguous_runs(sorted(position[c] for c in cpus if c in position)):
                    rect = QRectF(band.left() + start * column, band.top(),
                                  (end - start + 1) * column, band.height())
                    inner = rect.adjusted(1.0, 1.0, -1.0, -1.0)
                    painter.setPen(QPen(self._p.q("accent", 0.55), 1))
                    painter.setBrush(QBrush(self._p.q("accent", weight)))
                    painter.drawRoundedRect(inner, 4, 4)

                    painter.setFont(value_font)
                    if painter.fontMetrics().horizontalAdvance(text) + 10 <= inner.width():
                        painter.setPen(self._p.q("ink"))
                        painter.drawText(inner, int(Qt.AlignmentFlag.AlignCenter), text)

        axis_top = len(self._rows) * (self.ROW_H + self.ROW_GAP)
        painter.setFont(value_font)
        painter.setPen(self._p.q("muted"))
        step = max(1, round(len(self._axis) * 26 / max(plot_width, 1)))
        for i, cpu in enumerate(self._axis):
            if i % step:
                continue
            painter.drawText(
                QRectF(plot_left + i * column, axis_top, column, self.AXIS_H),
                int(Qt.AlignmentFlag.AlignCenter), str(cpu),
            )
        painter.drawText(
            QRectF(0, axis_top, gutter, self.AXIS_H),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), _("nav.cpu"),
        )
        painter.end()
