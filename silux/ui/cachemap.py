"""El mapa de cachés: qué núcleos comparten cada nivel.

Solo lo monta `pages/caches.py`. `_contiguous_runs` se viene con él: agrupa
los núcleos consecutivos para escribir «0-7» en vez de ocho números, y no lo
llama nadie más.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .. import render
from ..i18n import _
from . import theme
from .theme import Palette, ui_font, value_font


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
    # Room a figure leaves inside its block, on each side, and a pill around
    # the figure of a run of blocks.
    TEXT_PAD = 3
    PILL_PAD = 4

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._axis: list[int] = []
        self._rows: list[dict] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(150)

    def set_data(self, axis: Sequence[int], rows: Sequence[dict]) -> None:
        """`axis` is the CPUs in drawing order; each row has its label, level
        and instances as (CPUs, size, short size, tooltip), already written."""
        self._axis = list(axis)
        self._rows = list(rows)
        self.setFixedHeight(self.sizeHint().height())
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        rows = max(len(self._rows), 1)
        return QSize(320, rows * self.ROW_H + (rows - 1) * self.ROW_GAP + self.AXIS_H + 4)

    def _geometry(self) -> tuple[float, float, float]:
        """The gutter's width, where the plot starts and one CPU's width."""
        gutter = min(self.GUTTER, self.width() * 0.3)
        plot_left = gutter + 6
        plot_width = max(self.width() - plot_left - 2, 40)
        return gutter, plot_left, plot_width / max(len(self._axis), 1)

    def blocks(self) -> list[tuple[int, QRectF, tuple]]:
        """Each drawn block: its row, its rectangle and its instance. An
        instance over CPUs that aren't together on the axis is one block per
        run."""
        _gutter, plot_left, column = self._geometry()
        position = {cpu: i for i, cpu in enumerate(self._axis)}
        found = []
        for index, row in enumerate(self._rows):
            top = index * (self.ROW_H + self.ROW_GAP)
            for instance in row["instances"]:
                for start, end in _contiguous_runs(
                        sorted(position[c] for c in instance[0] if c in position)):
                    rect = QRectF(plot_left + start * column, top,
                                  (end - start + 1) * column, self.ROW_H)
                    found.append((index, rect.adjusted(1.0, 1.0, -1.0, -1.0), instance))
        return found

    def _fitting(self, width: float, *texts: str):
        """The first text that fits `width`, with its font: at the figures'
        size, or a point smaller."""
        normal = value_font(max(7, theme.METRICS.mono_pt - 1))
        smaller = value_font(max(7, theme.METRICS.mono_pt - 2))
        for text in texts:
            for font in (normal, smaller):
                if QFontMetricsF(font).horizontalAdvance(text) <= width - 2 * self.TEXT_PAD:
                    return text, font
        return None

    def plan(self) -> list[tuple[int, QRectF, str, object, bool]]:
        """What text goes where: (row, area, text, font, on a pill).

        Each block with its size, the short one if the size doesn't fit. A
        row whose blocks can't all hold theirs is labelled once per run of
        adjacent blocks («4 × 32K»), on a pill over them. A run too narrow
        for even «32K» is left to the tooltip.
        """
        rows: dict[int, list[tuple[QRectF, tuple]]] = {}
        for index, inner, instance in self.blocks():
            rows.setdefault(index, []).append((inner, instance))
        found = []
        for index, blocks in rows.items():
            each = [self._fitting(inner.width(), instance[1], instance[2])
                    for inner, instance in blocks]
            if all(each):
                found += [(index, inner, text, font, False)
                          for (inner, _instance), (text, font) in zip(blocks, each)]
                continue
            for run in self._runs(blocks):
                area = QRectF(run[0][0].left(), run[0][0].top(),
                              run[-1][0].right() - run[0][0].left(), run[0][0].height())
                short = run[0][1][2]
                if fitting := self._fitting(area.width() - 2 * self.PILL_PAD,
                                            render.cache_blocks_short(len(run), short), short):
                    found.append((index, area, fitting[0], fitting[1], True))
        return found

    @staticmethod
    def _runs(blocks: list[tuple[QRectF, tuple]]) -> list[list[tuple[QRectF, tuple]]]:
        """Blocks side by side, as runs. A row is one size of one level, so
        its blocks are all alike."""
        runs: list[list[tuple[QRectF, tuple]]] = []
        for block in sorted(blocks, key=lambda b: b[0].left()):
            last = runs[-1][-1] if runs else None
            if last and block[0].left() - last[0].right() < 3:
                runs[-1].append(block)
            else:
                runs.append([block])
        return runs

    def event(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ToolTip:
            point = QPointF(event.pos())
            for _row, inner, instance in self.blocks():
                if inner.contains(point):
                    QToolTip.showText(event.globalPos(), instance[3], self)
                    return True
            QToolTip.hideText()
            event.ignore()
            return True
        return super().event(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._axis or not self._rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gutter, plot_left, column = self._geometry()
        plot_width = column * len(self._axis)

        label_font = ui_font(max(7, theme.METRICS.small_pt - 1))
        letra_de_cifras = value_font(max(7, theme.METRICS.mono_pt - 1))
        max_level = max((row.get("level", 1) for row in self._rows), default=1)

        painter.setFont(label_font)
        painter.setPen(self._p.q("muted"))
        for index, row in enumerate(self._rows):
            top = index * (self.ROW_H + self.ROW_GAP)
            painter.drawText(
                QRectF(0, top, gutter, self.ROW_H),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                row["label"],
            )

        for index, inner, instance in self.blocks():
            # Cuanto más alto el nivel, más presencia: la L3 es la que manda.
            weight = 0.10 + 0.16 * (self._rows[index].get("level", 1) / max_level)
            painter.setPen(QPen(self._p.q("accent", 0.55), 1))
            painter.setBrush(QBrush(self._p.q("accent", weight)))
            painter.drawRoundedRect(inner, 4, 4)

        for _index, area, text, font, pill in self.plan():
            painter.setFont(font)
            if pill:
                width = QFontMetricsF(font).horizontalAdvance(text) + 2 * (self.TEXT_PAD + self.PILL_PAD)
                box = QRectF(area.center().x() - width / 2, area.top() + 4,
                             width, area.height() - 8)
                painter.setPen(QPen(self._p.q("accent", 0.55), 1))
                painter.setBrush(QBrush(self._p.q("surface")))
                painter.drawRoundedRect(box, 4, 4)
            painter.setPen(self._p.q("ink"))
            painter.drawText(area, int(Qt.AlignmentFlag.AlignCenter), text)

        axis_top = len(self._rows) * (self.ROW_H + self.ROW_GAP)
        painter.setFont(letra_de_cifras)
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
