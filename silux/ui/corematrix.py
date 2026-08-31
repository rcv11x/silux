"""La rejilla de núcleos: un cuadro por CPU lógica, con su curva y su reloj.

Solo la monta `pages/cpulive.py`. `pages/monitor.py` la importaba también,
pero no la usaba: era un import muerto de antes, y al repartir el archivo se
notó porque obligaba a esa página a cargar este módulo para nada.

`estrella` se viene con ella porque marca los núcleos que el firmware señala
como los mejores de la pieza y no la dibuja nadie más.

`curva_suave` se queda en `widgets.py`, que es de donde la usa también
`Sparkline`.
"""

from __future__ import annotations

from typing import Optional, Sequence
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget
from . import theme
from .theme import Palette, mono_font
from .widgets import curva_suave


def estrella(centro: QPointF, radio: float) -> QPainterPath:
    """Una estrella de cinco puntas, apuntando hacia arriba.

    Dentro de la celda se dibuja en vez de escribir «★»: ahí hace falta un
    tamaño exacto —que crece con la letra— y un color que case con el fondo
    pintado a mano, y el carácter sale del tamaño que la fuente quiera. En un
    texto corrido el carácter vale y se usa.
    """
    import math

    camino = QPainterPath()
    for vertice in range(10):
        # -90° para que la punta mire arriba; el radio interior de una
        # estrella de cinco puntas es el exterior partido por phi².
        angulo = math.radians(-90 + vertice * 36)
        alcance = radio if vertice % 2 == 0 else radio * 0.382
        punto = QPointF(centro.x() + alcance * math.cos(angulo),
                        centro.y() + alcance * math.sin(angulo))
        camino.lineTo(punto) if vertice else camino.moveTo(punto)
    camino.closeSubpath()
    return camino


class CoreMatrix(QWidget):
    """Una celda por CPU lógica: barra de uso, frecuencia y temperatura.

    Se pinta entero en un solo widget en vez de crear uno por núcleo: un
    servidor de 128 hilos convertiría eso en 128 widgets a repintar cada
    segundo. Cuando la celda se queda estrecha, la temperatura se cae antes
    que dejar que el texto se recorte.
    """

    GAP = 6

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._cores: list[dict] = []
        self._cell_w = theme.METRICS.cell_w
        # La celda crece para dejar sitio al historial: una barra dice cómo
        # está el núcleo ahora, la curva dice si viene de estar cargado. Ese
        # hueco se mide en letra, no en píxeles sueltos, o con el texto grande
        # la gráfica se queda con lo que sobre.
        self._cell_h = theme.METRICS.cell_h + max(10, theme.METRICS.mono_pt)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(120)

    def set_cores(self, cores: Sequence[dict]) -> None:
        changed = len(cores) != len(self._cores)
        self._cores = list(cores)
        if changed:
            self.setFixedHeight(self.sizeHint().height())
        self.update()

    def _columns(self) -> int:
        """Cuántas celdas por fila, repartidas para no dejar un renglón cojo.

        Con lo que cabe a secas, dieciséis hilos salían doce arriba y cuatro
        abajo, y ocho salían seis y dos. Se prueba a quitar columnas —nunca a
        añadir, que no caben— buscando primero un reparto exacto: dieciséis en
        dos filas de ocho se lee de un vistazo como los dos chiplets o los dos
        hilos por núcleo que casi siempre son.

        Se elige el reparto que deje menos huecos en la última fila, y a
        igualdad de huecos el que use más columnas, que es el que aprovecha el
        ancho. Quitar columnas ensancha las celdas, así que hay suelo: no se
        baja del 60 % de lo que cabía.
        """
        import math

        usable = max(self.width(), self._cell_w)
        caben = max(1, int((usable + self.GAP) // (self._cell_w + self.GAP)))
        total = len(self._cores)
        if total <= caben or caben < 3:
            return caben

        suelo = max(2, math.ceil(caben * 0.6))
        return min(
            range(suelo, caben + 1),
            key=lambda c: ((c - total % c) % c, -c),
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        if not self._cores:
            return QSize(self._cell_w, self._cell_h)
        columns = self._columns()
        rows = (len(self._cores) + columns - 1) // columns
        return QSize(self._cell_w, rows * self._cell_h + (rows - 1) * self.GAP)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.setFixedHeight(self.sizeHint().height())
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._cores:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        columns = self._columns()
        cell_width = (self.width() - (columns - 1) * self.GAP) / columns
        font = mono_font(max(7, theme.METRICS.mono_pt - 1))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        # Todo lo de dentro se mide contra la altura de línea, que es lo único
        # que crece cuando el usuario pide letra grande.
        linea = metrics.height()
        pad_h = max(5.0, linea * 0.45)
        pad_v = max(4.0, linea * 0.35)
        grosor = max(3.0, round(linea * 0.28))

        for i, core in enumerate(self._cores):
            col, row = i % columns, i // columns
            cell = QRectF(col * (cell_width + self.GAP), row * (self._cell_h + self.GAP),
                          cell_width, self._cell_h)

            destacado = core.get("starred")
            painter.setPen(QPen(self._p.q("accent", 0.55) if destacado
                                else self._p.q("line_soft"), 1))
            painter.setBrush(QBrush(self._p.q("surface_alt")))
            painter.drawRoundedRect(cell.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)


            inner = cell.adjusted(pad_h, pad_v, -pad_h, -pad_v)
            # La caja del texto la marca la fuente. Estaba fija en 12 px, y
            # con la letra al máximo la línea seguía ocupando doce mientras
            # las letras medían dieciocho: el nombre del núcleo se comía la
            # gráfica por arriba y quedaba un hueco por abajo.
            text_height = min(float(metrics.height()), inner.height() - pad_v * 2)

            # La estrella de los núcleos que el firmware marca como los
            # mejores de la pieza, delante del nombre. En la esquina de la
            # celda no cabe: ahí termina la frecuencia, que está alineada a la
            # derecha, y se pisaban.
            sangria = 0.0
            if destacado:
                radio = max(3.0, text_height * 0.26)
                sangria = radio * 2 + 4
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self._p.q("accent")))
                painter.drawPath(estrella(
                    QPointF(inner.left() + radio, inner.top() + text_height / 2),
                    radio,
                ))

            name = core["name"]
            detail = core["detail"]
            # Si no cabe todo, se sacrifica primero la temperatura y luego el
            # detalle entero, pero nunca se recorta a mitad de una cifra.
            name_width = metrics.horizontalAdvance(name) + 6 + sangria
            if name_width + metrics.horizontalAdvance(detail) > inner.width():
                detail = core.get("detail_short", detail)
            if name_width + metrics.horizontalAdvance(detail) > inner.width():
                detail = ""

            painter.setPen(self._p.q("muted"))
            painter.drawText(
                QRectF(inner.left() + sangria, inner.top(),
                       name_width - sangria, text_height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name,
            )
            if detail:
                painter.setPen(self._p.q("ink_dim"))
                painter.drawText(
                    QRectF(inner.left() + name_width, inner.top(),
                           inner.width() - name_width, text_height),
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), detail,
                )

            history = core.get("history") or ()
            if len(history) >= 2:
                self._draw_history(painter, QRectF(
                    inner.left(), inner.top() + text_height + 1,
                    inner.width(),
                    max(8.0, inner.height() - text_height - grosor - 3),
                ), history)

            track = QRectF(inner.left(), inner.bottom() - grosor,
                           inner.width(), grosor)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._p.q("line")))
            painter.drawRoundedRect(track, 2, 2)

            usage = core.get("usage")
            if usage is not None:
                filled = QRectF(track)
                filled.setWidth(max(3.0, track.width() * min(100.0, max(0.0, usage)) / 100.0))
                painter.setBrush(QBrush(self._colour_for(usage)))
                painter.drawRoundedRect(filled, 2, 2)

        painter.end()

    def _draw_history(self, painter: QPainter, rect: QRectF, values) -> None:
        """Curva de uso reciente, siempre en escala 0-100 para que las celdas
        se puedan comparar entre sí de un vistazo."""
        points = []
        step = rect.width() / (len(values) - 1)
        for i, value in enumerate(values):
            ratio = min(100.0, max(0.0, float(value))) / 100.0
            points.append(QPointF(rect.left() + i * step, rect.bottom() - ratio * rect.height()))

        area = curva_suave(points, cerrar_en=rect.bottom())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(area, QBrush(self._p.q("accent", 0.16)))

        line = curva_suave(points)
        painter.setPen(QPen(self._p.q("accent", 0.75), 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line)

    def _colour_for(self, usage: float) -> QColor:
        if usage >= 85:
            return self._p.q("crit")
        if usage >= 55:
            return self._p.q("warn")
        return self._p.q("accent")
