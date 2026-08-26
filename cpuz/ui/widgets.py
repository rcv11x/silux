"""Piezas visuales reutilizables.

Todas son widgets de Qt normales; las que dibujan datos —la gráfica y la
matriz de núcleos— usan QPainter directamente, que para esto es más rápido y
más controlable que componer decenas de widgets pequeños.

Dos piezas existen para que la ventana aguante tamaños pequeños:
`ResponsiveRow`, que reparte sus hijos en las columnas que quepan, y
`ElidingLabel`, que recorta el texto con puntos suspensivos en vez de dejar
que se salga de la tarjeta. Sin ellas, encoger la ventana cortaba datos.

Ninguna de estas clases sabe leer hardware.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QScrollArea,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .theme import Palette, mono_font, ui_font


# --------------------------------------------------------------------------
# texto que se adapta
# --------------------------------------------------------------------------


class ElidingLabel(QLabel):
    """Recorta con puntos suspensivos y deja el texto completo en el tooltip.

    QLabel no sabe hacer esto por sí solo: o desborda la tarjeta o fuerza a
    la ventana a ser más ancha. Aquí el texto se recorta al ancho disponible
    y sigue siendo accesible al pasar el ratón y al copiar.
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._full = ""
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        if text == self._full:
            return
        self._full = text
        self.setToolTip(text if self._needs_elide() else "")
        self._refresh()

    def full_text(self) -> str:
        return self._full

    def _needs_elide(self) -> bool:
        return self.fontMetrics().horizontalAdvance(self._full) > max(self.width(), 1)

    def _refresh(self) -> None:
        available = max(self.width(), 1)
        elided = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, available)
        super().setText(elided)
        self.setToolTip(self._full if elided != self._full else "")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # Un ancho mínimo pequeño es lo que permite que la ventana encoja.
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), 48), hint.height())


def balanced_columns(count: int, fits: int) -> int:
    """Cuántas columnas usar para `count` elementos si caben `fits`.

    Cuatro fichas en tres columnas dejan una sola en la segunda fila, que se
    ve desequilibrada. Si hay un divisor exacto que da el mismo número de
    filas, se prefiere ese; si no, se usan todas las que quepan.
    """
    if count <= 0:
        return 1
    fits = max(1, min(fits, count))
    if count % fits == 0:
        return fits

    rows_needed = -(-count // fits)              # división entera hacia arriba
    for candidate in range(fits - 1, 0, -1):
        if count % candidate == 0 and -(-count // candidate) == rows_needed:
            return candidate
    return fits


class ResponsiveRow(QWidget):
    """Coloca sus hijos en tantas columnas como quepan y reparte el resto.

    Con la ventana ancha, las cuatro fichas van en fila; al encogerla pasan a
    dos y luego a una, en vez de comprimirse hasta quedar ilegibles.
    """

    def __init__(self, min_item_width: int = 200, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # El ancho mínimo se da en unidades de densidad normal y se escala con
        # la densidad activa, o en modo compacto sobrarían columnas vacías.
        scale = theme.METRICS.cell_w / theme.NORMAL.cell_w
        self._min_item_width = max(110, int(min_item_width * scale))
        self._items: list[QWidget] = []
        self._columns = 0

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(theme.METRICS.section_gap)

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        widget.setParent(self)
        self._relayout(force=True)

    def _wanted_columns(self) -> int:
        count = len(self._items)
        if not count:
            return 1
        gap = self._grid.spacing()
        usable = max(self.width(), self._min_item_width)
        fits = int(max(1, (usable + gap) // (self._min_item_width + gap)))
        return balanced_columns(count, fits)

    def _relayout(self, force: bool = False) -> None:
        columns = self._wanted_columns()
        if columns == self._columns and not force:
            return
        self._columns = columns

        while self._grid.count():
            self._grid.takeAt(0)
        for index in range(self._grid.columnCount()):
            self._grid.setColumnStretch(index, 0)

        for index, widget in enumerate(self._items):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()


# --------------------------------------------------------------------------
# contenedores
# --------------------------------------------------------------------------


class Card(QFrame):
    """Panel con título opcional. El contenido va en `body`."""

    def __init__(self, title: str = "", parent: Optional[QWidget] = None, flat: bool = False):
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "Card")
        m = theme.METRICS

        outer = QVBoxLayout(self)
        outer.setContentsMargins(m.card_pad_h, m.card_pad_v, m.card_pad_h, m.card_pad_v)
        outer.setSpacing(m.card_gap)

        if title:
            label = QLabel(title.upper())
            label.setObjectName("CardTitle")
            outer.addWidget(label)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(max(4, m.card_gap - 2))
        outer.addLayout(self.body)
        # Sin este muelle, el espacio sobrante se reparte entre el título y el
        # contenido, y el título acaba flotando a media altura.
        outer.addStretch(0)


class Badge(QLabel):
    def __init__(self, text: str = "", quiet: bool = False, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setObjectName("BadgeQuiet" if quiet else "Badge")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)


class Divider(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


# --------------------------------------------------------------------------
# rejilla de campos
# --------------------------------------------------------------------------


class InfoGrid(QWidget):
    """Filas de nombre y valor, con los valores en tipografía monoespaciada
    para que las cifras queden alineadas al refrescar."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        m = theme.METRICS
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(m.grid_hspace)
        self._grid.setVerticalSpacing(m.grid_vspace)
        self._grid.setColumnStretch(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._values: dict[str, ElidingLabel] = {}
        self._rows = 0

    def add(self, name: str, value: str = "—", tooltip: str = "") -> ElidingLabel:
        name_label = ElidingLabel(name)
        name_label.setObjectName("FieldName")
        name_label.setFont(ui_font(theme.METRICS.small_pt))

        value_label = ElidingLabel(value)
        value_label.setObjectName("FieldValue")
        value_label.setFont(mono_font())

        # Sin altura mínima, el layout comprime la tarjeta con más filas para
        # igualar la de al lado y las filas acaban solapándose.
        line_height = max(name_label.fontMetrics().height(), value_label.fontMetrics().height())
        name_label.setMinimumHeight(line_height)
        value_label.setMinimumHeight(line_height)

        if tooltip:
            name_label.setToolTip(tooltip)

        self._grid.addWidget(name_label, self._rows, 0, Qt.AlignmentFlag.AlignTop)
        self._grid.addWidget(value_label, self._rows, 1)
        self._values[name] = value_label
        self._rows += 1
        return value_label

    def set(self, name: str, value: str, tooltip: Optional[str] = None) -> None:
        label = self._values.get(name)
        if label is None:
            return
        label.set_full_text(value)
        if tooltip:
            label.setToolTip(f"{value}\n\n{tooltip}" if value else tooltip)

    def reset(self) -> None:
        clear_layout(self._grid)
        self._values.clear()
        self._rows = 0


# --------------------------------------------------------------------------
# gráfica
# --------------------------------------------------------------------------


class Sparkline(QWidget):
    """Serie temporal compacta: relleno de área, línea y punto en el extremo."""

    def __init__(self, palette: Palette, capacity: int = 90, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._values: deque[float] = deque(maxlen=capacity)
        self._floor: Optional[float] = None
        self._ceiling: Optional[float] = None
        self.setMinimumHeight(theme.METRICS.chart_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_range(self, floor: Optional[float], ceiling: Optional[float]) -> None:
        self._floor, self._ceiling = floor, ceiling

    def push(self, value: Optional[float]) -> None:
        if value is not None:
            self._values.append(float(value))
            self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def stats(self) -> Optional[tuple[float, float, float]]:
        """Mínimo, máximo y media de lo que se está viendo."""
        if not self._values:
            return None
        values = list(self._values)
        return min(values), max(values), sum(values) / len(values)

    def paintEvent(self, event) -> None:  # noqa: N802
        if len(self._values) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 3.5, -0.5, -0.5)
        values = list(self._values)

        low = self._floor if self._floor is not None else min(values)
        high = self._ceiling if self._ceiling is not None else max(values)
        if high - low < 1e-9:
            high = low + 1.0
        margin = (high - low) * 0.12
        low, high = low - margin, high + margin

        step = rect.width() / (len(values) - 1)

        def point(i: int, v: float) -> QPointF:
            y = rect.bottom() - (v - low) / (high - low) * rect.height()
            return QPointF(rect.left() + i * step, max(rect.top(), min(rect.bottom(), y)))

        points = [point(i, v) for i, v in enumerate(values)]

        area = QPainterPath(QPointF(points[0].x(), rect.bottom()))
        for pt in points:
            area.lineTo(pt)
        area.lineTo(points[-1].x(), rect.bottom())
        area.closeSubpath()

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, self._p.q("accent", 0.28))
        gradient.setColorAt(1.0, self._p.q("accent", 0.02))
        painter.fillPath(area, QBrush(gradient))

        line = QPainterPath(points[0])
        for pt in points[1:]:
            line.lineTo(pt)
        painter.setPen(QPen(self._p.q("accent"), 1.6))
        painter.drawPath(line)

        painter.setBrush(QBrush(self._p.q("accent")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(points[-1], 2.6, 2.6)
        painter.end()


class StatTile(Card):
    """Cifra grande con su unidad, una etiqueta y la serie reciente debajo."""

    def __init__(self, label: str, unit: str, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.body.setSpacing(3)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        self.value = QLabel("—")
        self.value.setObjectName("TileValue")
        self.value.setFont(mono_font(theme.METRICS.tile_value_pt, bold=True))

        self.unit = QLabel(unit)
        self.unit.setObjectName("TileUnit")

        row.addWidget(self.value)
        row.addWidget(self.unit, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)

        self.caption = QLabel(label.upper())
        self.caption.setObjectName("TileLabel")

        # Línea opcional de contexto: sin ella, un "7 W" no dice si está bien.
        self.detail = ElidingLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setFont(ui_font(max(7, theme.METRICS.small_pt - 1)))
        self.detail.hide()

        self.chart = Sparkline(palette)

        self.body.addLayout(row)
        self.body.addWidget(self.caption)
        self.body.addWidget(self.detail)
        self.body.addWidget(self.chart)

    def set_unit(self, unit: str) -> None:
        if self.unit.text() != unit:
            self.unit.setText(unit)

    def set_detail(self, text: str, tooltip: str = "") -> None:
        self.detail.set_full_text(text)
        self.detail.setVisible(bool(text))
        if tooltip:
            self._extra_tooltip = tooltip
            self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        parts = [getattr(self, "_extra_tooltip", ""), getattr(self, "_series_tooltip", "")]
        self.setToolTip("\n\n".join(p for p in parts if p))

    def set_series_tooltip(self, text: str) -> None:
        self._series_tooltip = text
        self._refresh_tooltip()

    def update_value(self, text: str, series_value: Optional[float] = None) -> None:
        if self.value.text() != text:
            self.value.setText(text)
        self.chart.push(series_value)


# --------------------------------------------------------------------------
# matriz de núcleos
# --------------------------------------------------------------------------


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
        # está el núcleo ahora, la curva dice si viene de estar cargado.
        self._cell_h = theme.METRICS.cell_h + 10
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(120)

    def set_cores(self, cores: Sequence[dict]) -> None:
        changed = len(cores) != len(self._cores)
        self._cores = list(cores)
        if changed:
            self.setFixedHeight(self.sizeHint().height())
        self.update()

    def _columns(self) -> int:
        usable = max(self.width(), self._cell_w)
        return max(1, int((usable + self.GAP) // (self._cell_w + self.GAP)))

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

        for i, core in enumerate(self._cores):
            col, row = i % columns, i // columns
            cell = QRectF(col * (cell_width + self.GAP), row * (self._cell_h + self.GAP),
                          cell_width, self._cell_h)

            painter.setPen(QPen(self._p.q("line_soft"), 1))
            painter.setBrush(QBrush(self._p.q("surface_alt")))
            painter.drawRoundedRect(cell.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)

            inner = cell.adjusted(7, 5, -7, -5)
            text_height = min(12.0, inner.height() - 8)

            name = core["name"]
            detail = core["detail"]
            # Si no cabe todo, se sacrifica primero la temperatura y luego el
            # detalle entero, pero nunca se recorta a mitad de una cifra.
            name_width = metrics.horizontalAdvance(name) + 6
            if name_width + metrics.horizontalAdvance(detail) > inner.width():
                detail = core.get("detail_short", detail)
            if name_width + metrics.horizontalAdvance(detail) > inner.width():
                detail = ""

            painter.setPen(self._p.q("muted"))
            painter.drawText(
                QRectF(inner.left(), inner.top(), name_width, text_height),
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
                    inner.width(), max(8.0, inner.height() - text_height - 8),
                ), history)

            track = QRectF(inner.left(), inner.bottom() - 5, inner.width(), 4)
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

        area = QPainterPath(QPointF(points[0].x(), rect.bottom()))
        for point in points:
            area.lineTo(point)
        area.lineTo(points[-1].x(), rect.bottom())
        area.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(area, QBrush(self._p.q("accent", 0.16)))

        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)
        painter.setPen(QPen(self._p.q("accent", 0.75), 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line)

    def _colour_for(self, usage: float) -> QColor:
        if usage >= 85:
            return self._p.q("crit")
        if usage >= 55:
            return self._p.q("warn")
        return self._p.q("accent")


# --------------------------------------------------------------------------
# chips y avisos
# --------------------------------------------------------------------------


class ChipRow(QWidget):
    """Lista de etiquetas que salta de línea sola. Qt no trae una disposición
    así, y para el juego de instrucciones —que cambia de largo según la CPU—
    es justo lo que hace falta."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(4)
        self._chips: list[tuple[str, bool]] = []
        self._widgets: list[Badge] = []
        self._laid_width = 0
        # El ancho mínimo lo marca la insignia más ancha, no la fila entera:
        # si no, una lista larga impide encoger la ventana.
        self.setMinimumWidth(64)

    def set_chips(self, labels: Iterable[str], highlight_first: bool = False) -> None:
        chips = [(str(text), highlight_first and i == 0)
                 for i, text in enumerate(labels)]

        # Si solo ha cambiado el texto —el caso normal: una leyenda que sigue a
        # unos valores vivos— se reescriben las insignias que ya existen. Crear
        # widgets nuevos en cada muestreo iba dejando miles vivos: era la fuga
        # que hacía crecer la memoria medio megabyte por minuto.
        if len(chips) == len(self._widgets) and \
                [loud for _, loud in chips] == [loud for _, loud in self._chips]:
            self._chips = chips
            for widget, (text, _) in zip(self._widgets, chips):
                if widget.text() != text:
                    widget.setText(text)
            return

        self._chips = chips
        self._laid_width = 0
        self._rebuild()

    def _rebuild(self) -> None:
        clear_layout(self._column)
        self._widgets.clear()
        width = max(self.width(), 64)
        self._laid_width = self.width()

        row: Optional[QHBoxLayout] = None
        used = 0
        for text, loud in self._chips:
            chip = Badge(text, quiet=not loud)
            self._widgets.append(chip)
            needed = chip.sizeHint().width() + 4
            if row is None or (used and used + needed > width):
                row = QHBoxLayout()
                row.setSpacing(4)
                row.setContentsMargins(0, 0, 0, 0)
                self._column.addLayout(row)
                used = 0
            row.addWidget(chip)
            used += needed
        if row is not None:
            row.addStretch(1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if abs(self.width() - self._laid_width) > 16:
            self._rebuild()


class Notice(QFrame):
    """Explica un dato que falta. Sustituye a esconder la pestaña entera."""

    def __init__(self, title: str, body: str, hint: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Notice")
        m = theme.METRICS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.card_pad_h - 2, m.card_pad_v - 3, m.card_pad_h - 2, m.card_pad_v - 3)
        layout.setSpacing(2)

        header = QLabel(title)
        header.setObjectName("NoticeTitle")
        header.setFont(ui_font(m.small_pt))

        text = QLabel(body)
        text.setObjectName("NoticeBody")
        text.setWordWrap(True)
        text.setFont(ui_font(m.small_pt))

        layout.addWidget(header)
        layout.addWidget(text)

        if hint:
            note = QLabel(hint)
            note.setObjectName("NoticeHint")
            note.setWordWrap(True)
            note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(note)


def clear_layout(layout) -> None:
    """Vacía un layout, borrando también los sublayouts que contenga."""
    while layout.count():
        item = layout.takeAt(0)
        if (widget := item.widget()) is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif (child := item.layout()) is not None:
            clear_layout(child)
            child.deleteLater()


class Table(QScrollArea):
    """Tabla ligera de cabecera y filas, sin el peso de un QTableWidget.

    Aquí no hace falta selección, ordenación ni edición: solo alinear cifras.
    Un QGridLayout con etiquetas hace el trabajo, se estiliza con la misma
    hoja que el resto y no arrastra un modelo detrás.

    Va dentro de su propia zona de desplazamiento horizontal a propósito. Una
    tabla de ocho columnas no puede encogerse indefinidamente, y sin esto su
    ancho mínimo arrastraba a toda la página: las demás tarjetas se estiraban
    con ella y el contenido se recortaba por el lado derecho.
    """

    def __init__(self, headers: Sequence[str], numeric: Sequence[bool] = (),
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._headers = list(headers)
        self._numeric = list(numeric) + [False] * (len(headers) - len(numeric))

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        inner = QWidget()
        inner.setObjectName("Root")
        self.setWidget(inner)

        self._grid = QGridLayout(inner)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(theme.METRICS.grid_hspace)
        self._grid.setVerticalSpacing(theme.METRICS.grid_vspace)

        for column, title in enumerate(self._headers):
            label = QLabel(title.upper())
            label.setObjectName("CardTitle")
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight if self._numeric[column]
                else Qt.AlignmentFlag.AlignLeft
            )
            self._grid.addWidget(label, 0, column)

        # El hueco sobrante va detrás de la última columna, no dentro de la
        # primera. Estirando la primera, en pantalla completa las cifras
        # acababan a un palmo del nombre que hay que comparar con ellas.
        self._grid.setColumnStretch(len(self._headers), 1)
        self._rows = 0
        self._cells: list[list[ElidingLabel]] = []

    def set_rows(self, rows: Sequence[Sequence[str]], tooltips: Sequence[str] = ()) -> None:
        # Mientras la tabla tenga la misma forma se reescriben las celdas que
        # ya están. Rehacerlas en cada muestreo dejaba miles de etiquetas vivas.
        if len(rows) == self._rows and self._cells:
            for index, values in enumerate(rows):
                tip = tooltips[index] if index < len(tooltips) else ""
                for column, value in enumerate(values):
                    cell = self._cells[index][column]
                    cell.set_full_text(str(value))
                    if tip:
                        cell.setToolTip(tip)
            return

        while self._grid.count() > len(self._headers):
            item = self._grid.takeAt(self._grid.count() - 1)
            if (widget := item.widget()) is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cells.clear()

        for index, values in enumerate(rows):
            fila: list[ElidingLabel] = []
            tip = tooltips[index] if index < len(tooltips) else ""
            for column, value in enumerate(values):
                label = ElidingLabel(str(value))
                label.setObjectName("FieldValue" if column == 0 else "FieldName")
                label.setFont(mono_font() if column else ui_font(theme.METRICS.small_pt))
                label.setMinimumHeight(label.fontMetrics().height())
                if column < len(self._numeric) and self._numeric[column]:
                    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if tip:
                    label.setToolTip(tip)
                self._grid.addWidget(label, index + 1, column)
                fila.append(label)
            self._cells.append(fila)
        self._rows = len(rows)
        self._fit_height()

    def _fit_height(self) -> None:
        """La tabla ocupa justo lo que necesita de alto; el ancho lo negocia
        su propia barra de desplazamiento.

        Se mide el layout y no el widget: el `sizeHint` del widget se calcula
        en la siguiente pasada de Qt, así que justo después de añadir filas
        aún devuelve el alto anterior y la tabla se quedaba recortada.
        """
        if self.widget() is None:
            return

        # Se calcula, no se pregunta. `sizeHint` —tanto del layout como del
        # widget— se refresca en la siguiente pasada de Qt, así que justo
        # después de añadir filas devuelve el alto anterior y la tabla se
        # quedaba recortada a una sola línea.
        line = max(
            QFontMetrics(mono_font()).height(),
            QFontMetrics(ui_font(theme.METRICS.small_pt)).height(),
        ) + 2
        rows = self._rows + 1                       # las filas más la cabecera
        spacing = self._grid.verticalSpacing()
        extra = self.horizontalScrollBar().sizeHint().height() + 4
        self.setFixedHeight(rows * line + max(0, rows - 1) * spacing + extra)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_height()


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
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), "CPU",
        )
        painter.end()


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


class MiniStat(Card):
    """Etiqueta y valor en una línea, sin gráfica.

    Es la versión de `StatTile` para cuando el dato acompaña pero no es el
    protagonista: en la pestaña de identificación interesa ver el reloj actual
    de reojo, no una serie temporal.
    """

    def __init__(self, label: str, parent: Optional[QWidget] = None):
        super().__init__(parent=parent, flat=True)
        self.body.setSpacing(1)

        self.caption = QLabel(label.upper())
        self.caption.setObjectName("TileLabel")

        self.value = ElidingLabel("—")
        self.value.setObjectName("FieldValue")
        self.value.setFont(mono_font(theme.METRICS.mono_pt + 3, bold=True))

        self.body.addWidget(self.caption)
        self.body.addWidget(self.value)

    def set_value(self, text: str, tooltip: str = "") -> None:
        self.value.set_full_text(text)
        if tooltip:
            self.setToolTip(tooltip)


class ResizableHeader(QHeaderView):
    """Cabecera que enseña dónde se puede arrastrar.

    Qt cambia el cursor al pasar por encima de un separador, pero eso solo se
    descubre por accidente. Un par de rayitas en cada división dice «esto se
    mueve» antes de que nadie pase el ratón, que es la diferencia entre una
    función que existe y una que se usa.
    """

    GRIP_HEIGHT = 9
    GRAB_MARGIN = 4

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._p = palette
        self._hovered = -1
        self.setMouseTracking(True)

    def paintSection(self, painter: QPainter, rect, index: int) -> None:  # noqa: N802
        super().paintSection(painter, rect, index)

        # La última columna es el hueco que absorbe el sobrante: su borde
        # izquierdo ya lo dibuja la anterior, y por la derecha no hay nada.
        if index >= self.count() - 1:
            return
        if self.sectionResizeMode(index) != QHeaderView.ResizeMode.Interactive:
            return

        active = index == self._hovered
        colour = self._p.q("accent" if active else "muted", 1.0 if active else 0.55)
        painter.save()
        painter.setPen(QPen(colour, 1))
        middle = rect.center().y()
        top = middle - self.GRIP_HEIGHT // 2
        for offset in (-2, 1):
            x = rect.right() + offset
            painter.drawLine(x, top, x, top + self.GRIP_HEIGHT)
        painter.restore()

    def _divider_at(self, x: int) -> int:
        for index in range(self.count() - 1):
            edge = self.sectionViewportPosition(index) + self.sectionSize(index)
            if abs(x - edge) <= self.GRAB_MARGIN:
                return index
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hovered = self._divider_at(int(event.position().x()))
        if hovered != self._hovered:
            self._hovered = hovered
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hovered != -1:
            self._hovered = -1
            self.viewport().update()
        super().leaveEvent(event)


class SensorTree(QTreeWidget):
    """El árbol de sensores, al estilo de HWMonitor y HWiNFO.

    Aparato → categoría → sensor, con las columnas Actual, Mín, Máx y Media.
    Se usa un QTreeWidget de verdad y no un dibujo propio porque aquí sí
    compensa: plegar ramas, recorrer con el teclado, seleccionar y copiar
    vienen de serie, y son justo las cosas que la gente hace con una lista
    larga de sensores.

    El árbol se construye una vez y luego solo se cambian textos. Reconstruirlo
    en cada muestreo perdería el estado de las ramas plegadas y la selección,
    que es exactamente lo que uno acaba de ajustar antes de mirar.
    """

    # La última columna está vacía a propósito: absorbe el ancho sobrante.
    # Sin ella, la columna de nombres se estiraba hasta llenar la ventana y en
    # pantalla completa dejaba las cifras a un palmo de distancia del nombre,
    # que es justo lo que uno quiere comparar de un vistazo.
    COLUMNS = ("Sensor", "Actual", "Mín", "Máx", "Media", "")
    VALUE_COLUMNS = 4

    columnsResized = Signal(tuple)

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._rows: dict[str, QTreeWidgetItem] = {}
        self._structure: tuple = ()

        self.setColumnCount(len(self.COLUMNS))
        self.setHeaderLabels(list(self.COLUMNS))
        # La cabecera se alinea como los datos que hay debajo: el nombre a la
        # izquierda y las cifras a la derecha. Centrada —que es lo que hace Qt
        # por omisión— no cuadra con ninguna de las dos columnas.
        header_item = self.headerItem()
        header_item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in range(1, len(self.COLUMNS)):
            header_item.setTextAlignment(
                column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # En una ventana estrecha —o en densidad amplia— las columnas suman
        # más que el ancho disponible. Antes se recortaba la última en
        # silencio; ahora el árbol se desplaza dentro de su tarjeta, que es lo
        # que se espera de una tabla ancha.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)

        self.setHeader(ResizableHeader(palette, self))
        header = self.header()
        # Todas las columnas visibles se arrastran. Antes las de cifras se
        # ajustaban solas al contenido y no se dejaban tocar, que es justo lo
        # que uno quiere hacer cuando le parecen apretadas.
        for column in range(len(self.COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(40)
        header.setSectionsMovable(False)
        header.setToolTip(
            "Arrastra los separadores para ajustar el ancho.\n"
            "Botón derecho para volver a los anchos automáticos."
        )
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        header.sectionResized.connect(self._on_section_resized)
        self._preferred_widths: tuple[int, ...] = ()
        self._applying_widths = False

        self._label_font = ui_font(theme.METRICS.small_pt)
        self._value_font = mono_font()
        self._branch_font = ui_font(theme.METRICS.small_pt, QFont.Weight.DemiBold)
        self._icons: dict[str, QIcon] = {}
        self.setIconSize(QSize(13, 13))
        # El sangrado por omisión de Qt son 20 px por nivel: con tres niveles
        # se come cien píxeles de la columna que menos sobra.
        self.setIndentation(14)

    def _icon(self, kind: str) -> QIcon:
        if kind not in self._icons:
            self._icons[kind] = QIcon(theme.sensor_icon(kind, self._p))
        return self._icons[kind]

    # -- construcción -------------------------------------------------------

    def set_column_widths(self, widths) -> None:
        """Aplica anchos guardados. Una tupla vacía = calcularlos del contenido."""
        self._preferred_widths = tuple(widths or ())
        if self._preferred_widths:
            self._apply_widths(self._preferred_widths)

    def column_widths(self) -> tuple[int, ...]:
        return tuple(self.columnWidth(c) for c in range(len(self.COLUMNS) - 1))

    def reset_column_widths(self) -> None:
        self._preferred_widths = ()
        self._autosize_columns()
        self.columnsResized.emit(())

    NAME_FLOOR = 150

    def _apply_widths(self, widths) -> None:
        """Aplica anchos con un suelo en la columna de nombres.

        Sin él, unos anchos guardados con otra densidad —o un arrastre
        demasiado entusiasta— dejan la columna tan estrecha que el sangrado y
        el icono se la comen entera y las etiquetas desaparecen.
        """
        self._applying_widths = True
        try:
            for column, width in enumerate(widths):
                if column >= len(self.COLUMNS) - 1:
                    break
                floor = self.NAME_FLOOR if column == 0 else self.header().minimumSectionSize()
                self.setColumnWidth(column, max(floor, int(width)))
        finally:
            self._applying_widths = False

    def _autosize_columns(self) -> None:
        """Ancho natural de cada columna más un respiro que sigue a la densidad.

        El contenido a secas queda incómodo de leer: las cifras se pegan unas
        a otras. El margen sale de las métricas para que la densidad amplia
        respire de verdad y la compacta apriete.
        """
        if self._preferred_widths:
            self._apply_widths(self._preferred_widths)
            return

        breathing = theme.METRICS.grid_hspace
        widest = self._measure_columns()

        self._applying_widths = True
        try:
            # La primera lleva icono y sangrado, así que necesita más margen.
            self.setColumnWidth(
                0, max(self.NAME_FLOOR, min(widest[0] + breathing + 46, 460))
            )
            for column in range(1, len(self.COLUMNS) - 1):
                self.setColumnWidth(column, max(52, min(widest[column] + breathing, 220)))
        finally:
            self._applying_widths = False

    def _measure_columns(self) -> list[int]:
        """Mide el texto más ancho de cada columna, cabecera incluida.

        `sizeHintForColumn` no vale aquí: en un árbol solo tiene en cuenta los
        elementos de primer nivel, y los nuestros son los aparatos, que tienen
        vacías todas las columnas de cifras. Medir a mano da anchos reales.
        """
        label_metrics = QFontMetrics(self._label_font)
        value_metrics = QFontMetrics(self._value_font)
        header_metrics = QFontMetrics(self.header().font())

        widest = [header_metrics.horizontalAdvance(name) + 18 for name in self.COLUMNS]

        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            depth = 0
            walker = item
            while (walker := walker.parent()) is not None:
                depth += 1
            widest[0] = max(
                widest[0],
                label_metrics.horizontalAdvance(item.text(0)) + depth * self.indentation(),
            )
            for column in range(1, len(self.COLUMNS) - 1):
                text = item.text(column)
                if text:
                    widest[column] = max(widest[column],
                                         value_metrics.horizontalAdvance(text))
            stack.extend(item.child(i) for i in range(item.childCount()))
        return widest

    def _on_section_resized(self, index: int, _old: int, _new: int) -> None:
        if self._applying_widths or not self.isVisible():
            return
        self._preferred_widths = self.column_widths()
        self.columnsResized.emit(self._preferred_widths)

    def _header_menu(self, position) -> None:
        menu = QMenu(self)
        action = menu.addAction("Restablecer anchos automáticos")
        action.triggered.connect(self.reset_column_widths)
        menu.exec(self.header().mapToGlobal(position))

    def rebuild(self, tree: dict) -> None:
        """Rehace la estructura. Solo se llama cuando cambia qué hay, no
        cuánto vale."""
        expanded = {key for key, item in self._rows.items() if item.isExpanded()}
        self.clear()
        self._rows.clear()

        for device, categories in tree.items():
            device_item = QTreeWidgetItem([device])
            device_item.setFont(0, self._branch_font)
            device_item.setForeground(0, self._p.q("ink"))
            device_item.setFirstColumnSpanned(True)
            self.addTopLevelItem(device_item)
            self._rows[f"::{device}"] = device_item

            for category, sensors in categories.items():
                category_item = QTreeWidgetItem([category])
                category_item.setFont(0, self._label_font)
                category_item.setForeground(0, self._p.q("muted"))
                device_item.addChild(category_item)
                self._rows[f"::{device}/{category}"] = category_item

                if sensors:
                    category_item.setIcon(0, self._icon(sensors[0].kind.value))

                for sensor in sensors:
                    row = QTreeWidgetItem([sensor.label, "—", "—", "—", "—"])
                    row.setFont(0, self._label_font)
                    row.setIcon(0, self._icon(sensor.kind.value))
                    for column in range(1, len(self.COLUMNS)):
                        row.setFont(column, self._value_font)
                        # Sin int(): la sobrecarga con entero está obsoleta
                        # desde PySide6 6.11 y avisa por cada celda.
                        row.setTextAlignment(
                            column,
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        )
                    # La columna del valor actual va sobre una banda tenue: es
                    # la que se mira, y anclarla evita recorrer con el dedo.
                    row.setBackground(1, QBrush(self._p.q("accent", 0.09)))
                    category_item.addChild(row)
                    self._rows[sensor.key] = row

                category_item.setExpanded(f"::{device}/{category}" not in self._rows
                                          or f"::{device}/{category}" in expanded or not expanded)
            device_item.setExpanded(f"::{device}" in expanded or not expanded)

        self._autosize_columns()
        self._fit_height()

    def update_row(self, key: str, values: list[str], tooltip: str = "",
                   alarm: bool = False) -> None:
        item = self._rows.get(key)
        if item is None:
            return
        for column, text in enumerate(values, start=1):
            if item.text(column) != text:
                item.setText(column, text)
        colour = self._p.q("crit") if alarm else self._p.q("ink")
        item.setForeground(1, colour)
        if tooltip:
            for column in range(len(self.COLUMNS)):
                item.setToolTip(column, tooltip)

    def has(self, key: str) -> bool:
        return key in self._rows

    # -- geometría ----------------------------------------------------------

    def _fit_height(self) -> None:
        """El árbol crece con su contenido en vez de tener su propio scroll.

        Dos zonas de desplazamiento anidadas —la página y el árbol— hacen que
        la rueda del ratón haga cosas distintas según dónde esté el puntero,
        que es de las cosas que más molestan de una interfaz.
        """
        visible = self._count_visible()
        row_height = max(self.sizeHintForRow(0), 20) if visible else 20
        extra = self.header().height() + 6
        if self.horizontalScrollBar().isVisible():
            extra += self.horizontalScrollBar().height()
        self.setFixedHeight(visible * row_height + extra)

    def _count_visible(self) -> int:
        total = 0
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            total += 1
            if item.isExpanded():
                stack.extend(item.child(i) for i in range(item.childCount()))
        return total

    def refresh_height(self) -> None:
        self._fit_height()


class StackedBar(QWidget):
    """Barra de segmentos con leyenda: cuánto ocupa cada cosa de un total.

    Para la memoria dice de un vistazo algo que una lista de cifras no cuenta:
    que el hueco «libre» de Linux es pequeño a propósito, porque lo que sobra
    se usa como caché de disco y se devuelve en cuanto hace falta.
    """

    BAR_HEIGHT = 14

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._segments: list[tuple[str, float, str]] = []   # (etiqueta, valor, token)
        self._total = 0.0
        self._formatter = str

        self._legend = ChipRow()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addSpacing(self.BAR_HEIGHT)
        layout.addWidget(self._legend)

    def set_segments(self, segments: list[tuple[str, float, str]], total: float,
                     formatter=None) -> None:
        self._segments = segments
        self._total = total or 1.0
        if formatter is not None:
            self._formatter = formatter
        self._legend.set_chips(
            f"{label}  {self._formatter(value)}" for label, value, _ in segments if value > 0
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._segments:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = QRectF(0, 0, self.width(), self.BAR_HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        painter.setClipPath(path)

        painter.setBrush(QBrush(self._p.q("line")))
        painter.drawRect(rect)

        offset = 0.0
        for _, value, token in self._segments:
            if value <= 0:
                continue
            width = rect.width() * value / self._total
            painter.setBrush(QBrush(self._p.q(token)))
            painter.drawRect(QRectF(offset, 0, width, self.BAR_HEIGHT))
            offset += width
        painter.end()
