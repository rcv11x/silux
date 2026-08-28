"""Piezas visuales reutilizables.

Todas son widgets de Qt normales; las que dibujan datos (la gráfica y la
matriz de núcleos) usan QPainter directamente, que para esto es más rápido y
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
    QPushButton,
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

        self._title_label: Optional[QLabel] = None
        if title:
            self._title_label = QLabel(title.upper())
            self._title_label.setObjectName("CardTitle")
            outer.addWidget(self._title_label)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(max(4, m.card_gap - 2))
        outer.addLayout(self.body)
        # Sin este muelle, el espacio sobrante se reparte entre el título y el
        # contenido, y el título acaba flotando a media altura.
        outer.addStretch(0)

    def set_title(self, title: str) -> None:
        """Cambia el título de la tarjeta si la tenía."""
        if self._title_label is not None:
            self._title_label.setText(title.upper())


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
        self._names: dict[str, ElidingLabel] = {}
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
        self._names[name] = name_label
        self._rows += 1
        return value_label

    def set(self, name: str, value: str, tooltip: Optional[str] = None) -> None:
        label = self._values.get(name)
        if label is None:
            return
        label.set_full_text(value)
        if tooltip:
            label.setToolTip(f"{value}\n\n{tooltip}" if value else tooltip)

    def set_visible(self, name: str, visible: bool) -> None:
        """Esconde o enseña una fila entera, nombre incluido.

        Se ocultan, no se destruyen: crear widgets en cada muestreo es lo que
        hacía crecer la memoria medio megabyte por minuto.
        """
        for mapa in (self._values, self._names):
            if (label := mapa.get(name)) is not None:
                label.setVisible(visible)

    def reset(self) -> None:
        clear_layout(self._grid)
        self._values.clear()
        self._names.clear()
        self._rows = 0


# --------------------------------------------------------------------------
# gráfica
# --------------------------------------------------------------------------


def _rango_redondo(low: float, high: float) -> tuple[float, float]:
    """Redondea los extremos del eje a cifras que no bailen.

    Es lo que de verdad quita el tirón. Ajustar el eje al milímetro de lo
    medido significa moverlo en cuanto una muestra sube medio grado, y cada
    movimiento reescala la curva entera. Redondeando a pasos legibles, una
    temperatura que va de 45 a 52 se dibuja con el mismo eje todo el rato y
    la gráfica solo se reajusta cuando de verdad cambia el orden de magnitud.

    No se recorta nada: el redondeo siempre va hacia fuera.
    """
    span = high - low
    if span <= 0:
        return low, high
    # Un paso de la familia 1-2-5 por década, que es la que se lee sin pensar.
    import math
    decada = 10 ** math.floor(math.log10(span))
    for multiplo in (1, 2, 5, 10):
        paso = decada * multiplo
        if span / paso <= 4:
            break
    return math.floor(low / paso) * paso, math.ceil(high / paso) * paso


def curva_suave(points, cerrar_en=None) -> QPainterPath:
    """Una polilínea convertida en curva, sin inventarse lo que no midió.

    Unir las muestras con rectas deja una línea de sierra que cansa de mirar,
    sobre todo con el muestreo a un segundo. La curva se traza con el método
    de Catmull-Rom, que pasa por todos los puntos —eso no es negociable: son
    lecturas, no una tendencia—, y con los tiradores recortados para que no
    se salga por arriba ni por abajo de lo que hay medido.

    Sin ese recorte, una curva entre dos valores iguales y un tercero más alto
    se abomba por encima del máximo, y quien lo mira ve un pico de temperatura
    que nunca ocurrió.

    `cerrar_en` es la y donde bajar al terminar, para el relleno bajo la línea.
    """
    if len(points) < 2:
        camino = QPainterPath(points[0]) if points else QPainterPath()
        return camino

    inicio = QPointF(points[0].x(), cerrar_en) if cerrar_en is not None else points[0]
    camino = QPainterPath(inicio)
    if cerrar_en is not None:
        camino.lineTo(points[0])

    for i in range(len(points) - 1):
        p0 = points[i - 1] if i else points[0]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2

        c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0,
                     p1.y() + (p2.y() - p0.y()) / 6.0)
        c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0,
                     p2.y() - (p3.y() - p1.y()) / 6.0)
        # Los tiradores no pueden salirse del tramo: es lo que evita el pico
        # inventado entre dos muestras iguales.
        techo, suelo = min(p1.y(), p2.y()), max(p1.y(), p2.y())
        c1.setY(max(techo, min(suelo, c1.y())))
        c2.setY(max(techo, min(suelo, c2.y())))
        camino.cubicTo(c1, c2, p2)

    if cerrar_en is not None:
        camino.lineTo(points[-1].x(), cerrar_en)
        camino.closeSubpath()
    return camino


class Sparkline(QWidget):
    """Serie temporal compacta: relleno de área, línea y punto en el extremo.

    Con el ratón encima se puede leer cualquier punto de la curva, no solo el
    último. Una gráfica de este tamaño enseña la forma (si hubo un pico, si se
    mantiene plana) pero el pico sin su cifra deja a medias: se ve que pasó
    algo y no cuánto. Con el cursor aparece la guía, el valor y hace cuánto fue.
    """

    def __init__(self, palette: Palette, capacity: int = 90, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._values: deque[float] = deque(maxlen=capacity)
        self._floor: Optional[float] = None
        self._ceiling: Optional[float] = None
        self._hover: Optional[int] = None
        self._formatter = None
        self._interval_s = 1.0
        # Cuánto se ha avanzado hacia la muestra siguiente, de 0 a 1. Sirve
        # para que la línea se deslice en vez de dar un salto por segundo:
        # con el movimiento fluido apagado se queda en 1 y no se nota.
        self._phase = 1.0
        # La escala vertical que se está usando ahora mismo, que no siempre es
        # la que piden los datos: ver _escala_visible.
        self._escala: Optional[tuple[float, float]] = None
        self.setMinimumHeight(theme.METRICS.chart_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_range(self, floor: Optional[float], ceiling: Optional[float]) -> None:
        self._floor, self._ceiling = floor, ceiling

    def set_formatter(self, formatter, interval_s: float = 1.0) -> None:
        """Cómo escribir el valor que se lee bajo el cursor, y cada cuánto se
        toma una muestra, para poder decir hace cuánto ocurrió."""
        self._formatter = formatter
        self._interval_s = max(0.05, interval_s)

    # -- lectura con el ratón ----------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        indice = self._index_at(event.position().x())
        if indice != self._hover:
            self._hover = indice
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.update()

    def _geometria(self) -> tuple[float, float]:
        """Dónde empieza la serie y cuánto ocupa cada muestra.

        En un solo sitio a propósito: al pintar y al leer con el cursor hay
        que hacer la misma cuenta, y cuando cada uno la hacía por su lado, el
        cursor señalaba una muestra y la guía se dibujaba sobre otra.
        """
        ancho = max(1.0, self.width() - 1.0)
        capacidad = self._values.maxlen or max(1, len(self._values))
        paso = ancho / max(1, capacidad - 1)
        origen = (0.5 + ancho) - (len(self._values) - 1) * paso
        return origen, paso

    def _index_at(self, x: float) -> Optional[int]:
        if len(self._values) < 2 or self.width() <= 1:
            return None
        origen, paso = self._geometria()
        indice = round((x - origen) / paso)
        # Mientras la gráfica se está llenando, la mitad izquierda está vacía
        # y ahí no hay ninguna muestra que leer.
        if not 0 <= indice < len(self._values):
            return None
        return indice

    def _hover_text(self, valor: float, indice: int) -> str:
        cifra = self._formatter(valor) if self._formatter else f"{valor:g}"
        atras = (len(self._values) - 1 - indice) * self._interval_s
        if atras < 1:
            return f"{cifra} · ahora"
        if atras < 60:
            return f"{cifra} · hace {atras:.0f} s"
        return f"{cifra} · hace {atras / 60:.0f} min"

    def push(self, value: Optional[float]) -> None:
        if value is not None:
            self._values.append(float(value))
            self._phase = 0.0
            self.update()

    def advance(self, phase: float) -> None:
        """Coloca la gráfica entre la muestra anterior y la siguiente.

        La llama un temporizador único de la ventana, no uno por gráfica: con
        cuarenta y tantas en pantalla, cuarenta temporizadores despertando por
        su cuenta cuestan más que lo que se dibuja.
        """
        nueva = max(0.0, min(1.0, phase))
        if abs(nueva - self._phase) < 0.01:
            return
        self._phase = nueva
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self._escala = None
        self.update()

    def stats(self) -> Optional[tuple[float, float, float]]:
        """Mínimo, máximo y media de lo que se está viendo."""
        if not self._values:
            return None
        values = list(self._values)
        return min(values), max(values), sum(values) / len(values)

    def _escala_visible(self, values: list[float]) -> tuple[float, float]:
        """Hasta dónde llega el eje vertical, sin que baile.

        De aquí salía el tirón, y no del deslizamiento: con 90 muestras en 300
        píxeles la línea avanza 3,4 px por segundo, que no se ve. Lo que se
        veía era el eje reajustándose. Ajustarlo al milímetro de lo medido
        significa moverlo en cuanto una muestra sube medio grado, y cada
        movimiento reescala la curva entera de golpe.

        La regla es: si lo que hay que dibujar cabe en el eje que ya está
        puesto, no se toca. Solo se cambia cuando algo se sale —y entonces
        de inmediato, porque encoger un dato para que quepa sería dibujarlo
        donde no está— o cuando sobra tanto hueco que la curva se ha quedado
        aplastada abajo, y eso se corrige poco a poco.
        """
        suelo = self._floor if self._floor is not None else min(values)
        techo = self._ceiling if self._ceiling is not None else max(values)
        if self._floor is not None and self._ceiling is not None:
            return (suelo, techo) if techo > suelo else (suelo, suelo + 1.0)

        if techo - suelo < 1e-9:
            techo = suelo + 1.0
        margen = (techo - suelo) * 0.12
        suelo, techo = suelo - margen, techo + margen

        previa = self._escala
        if previa is None:
            self._escala = _rango_redondo(suelo, techo)
            return self._escala

        antes_suelo, antes_techo = previa
        if suelo >= antes_suelo and techo <= antes_techo:
            # Cabe. Solo se estrecha si ha quedado ridículamente holgado, y
            # despacio: ahí no hay ninguna lectura en juego, solo el hueco que
            # dejó un pico que ya pasó.
            if (antes_techo - antes_suelo) > (techo - suelo) * 2.5:
                paso = 1 / 12
                self._escala = (antes_suelo + (suelo - antes_suelo) * paso,
                                antes_techo + (techo - antes_techo) * paso)
            return self._escala

        # Algo se sale: el eje crece ya, y redondeado para que aguante.
        self._escala = _rango_redondo(min(suelo, antes_suelo),
                                      max(techo, antes_techo))
        return self._escala

    def paintEvent(self, event) -> None:  # noqa: N802
        if len(self._values) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 3.5, -0.5, -0.5)
        values = list(self._values)

        low, high = self._escala_visible(values)

        # El paso lo marca la capacidad, no cuántas muestras hay todavía. Si
        # se reparte el ancho entre las que hay, cada muestra nueva estrecha
        # el paso y toda la curva se recoloca: un salto de seis píxeles hasta
        # que la cola se llena. Así la gráfica se llena desde la derecha con
        # el paso definitivo desde el primer momento.
        origen, step = self._geometria()
        # Las muestras viejas se van hacia la izquierda y salen por ahí; la
        # nueva ya está dibujada en el borde derecho. Al revés —empujando
        # todo a la derecha— el relleno dejaba un hueco parpadeante en el
        # borde izquierdo, que es el rebote que se veía.
        deslizamiento = -self._phase * step
        if self._phase < 1.0:
            painter.setClipRect(self.rect())

        def point(i: int, v: float) -> QPointF:
            y = rect.bottom() - (v - low) / (high - low) * rect.height()
            return QPointF(origen + i * step + deslizamiento,
                           max(rect.top(), min(rect.bottom(), y)))

        points = [point(i, v) for i, v in enumerate(values)]

        area = curva_suave(points, cerrar_en=rect.bottom())

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, self._p.q("accent", 0.28))
        gradient.setColorAt(1.0, self._p.q("accent", 0.02))
        painter.fillPath(area, QBrush(gradient))

        line = curva_suave(points)
        painter.setPen(QPen(self._p.q("accent"), 1.6))
        painter.drawPath(line)

        painter.setBrush(QBrush(self._p.q("accent")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(points[-1], 2.6, 2.6)

        if self._hover is not None and 0 <= self._hover < len(points):
            self._draw_hover(painter, rect, points[self._hover], values[self._hover])
        painter.end()

    def _draw_hover(self, painter: QPainter, rect: QRectF,
                    punto: QPointF, valor: float) -> None:
        """La guía vertical, el punto marcado y la cifra que hay debajo."""
        painter.setPen(QPen(self._p.q("muted", 0.55), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(punto.x(), rect.top()), QPointF(punto.x(), rect.bottom()))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._p.q("surface")))
        painter.drawEllipse(punto, 3.6, 3.6)
        painter.setBrush(QBrush(self._p.q("accent")))
        painter.drawEllipse(punto, 2.4, 2.4)

        texto = self._hover_text(valor, self._hover or 0)
        painter.setFont(ui_font(max(7, theme.METRICS.small_pt - 1)))
        metrica = painter.fontMetrics()
        ancho = metrica.horizontalAdvance(texto) + 8
        alto = metrica.height() + 2

        # La etiqueta se pega al lado que tenga sitio, para no salirse.
        izquierda = punto.x() + 6
        if izquierda + ancho > rect.right():
            izquierda = punto.x() - 6 - ancho
        izquierda = max(rect.left(), izquierda)
        caja = QRectF(izquierda, rect.top(), ancho, alto)

        painter.setBrush(QBrush(self._p.q("surface", 0.92)))
        painter.setPen(QPen(self._p.q("line"), 1.0))
        painter.drawRoundedRect(caja, 3, 3)
        painter.setPen(QPen(self._p.q("ink")))
        painter.drawText(caja, Qt.AlignmentFlag.AlignCenter, texto)


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

            # Un punto en la esquina para los núcleos que el firmware marca
            # como los mejores de la pieza. Va aquí y no en una columna aparte
            # porque el dato no cambia nunca: ocupar una fila entera con algo
            # que se lee una vez en la vida sería caro para lo que dice.
            if destacado:
                radio = max(2.0, linea * 0.16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self._p.q("accent")))
                painter.drawEllipse(
                    QPointF(cell.right() - radio * 3.0, cell.top() + radio * 3.0),
                    radio, radio,
                )

            inner = cell.adjusted(pad_h, pad_v, -pad_h, -pad_v)
            # La caja del texto la marca la fuente. Estaba fija en 12 px, y
            # con la letra al máximo la línea seguía ocupando doce mientras
            # las letras medían dieciocho: el nombre del núcleo se comía la
            # gráfica por arriba y quedaba un hueco por abajo.
            text_height = min(float(metrics.height()), inner.height() - pad_v * 2)

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


# --------------------------------------------------------------------------
# chips y avisos
# --------------------------------------------------------------------------


class ChipRow(QWidget):
    """Lista de etiquetas que salta de línea sola. Qt no trae una disposición
    así, y para el juego de instrucciones (que cambia de largo según la CPU)
    es justo lo que hace falta."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(max(4, theme.METRICS.card_gap - 2))
        self._chips: list[tuple[str, bool]] = []
        self._widgets: list[Badge] = []
        self._laid_width = 0
        # El ancho mínimo lo marca la insignia más ancha, no la fila entera:
        # si no, una lista larga impide encoger la ventana.
        self.setMinimumWidth(64)

    def set_chips(self, labels: Iterable[str], highlight_first: bool = False) -> None:
        chips = [(str(text), highlight_first and i == 0)
                 for i, text in enumerate(labels)]

        # Si solo ha cambiado el texto (el caso normal: una leyenda que sigue a
        # unos valores vivos) se reescriben las insignias que ya existen. Crear
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
            # El hueco entre insignias sigue a la densidad: pegadas unas a
            # otras, una leyenda de tres se lee como una sola etiqueta larga.
            hueco = max(6, theme.METRICS.card_gap)
            needed = chip.sizeHint().width() + hueco
            if row is None or (used and used + needed > width):
                row = QHBoxLayout()
                row.setSpacing(hueco)
                row.setContentsMargins(0, 0, 0, 0)
                self._column.addLayout(row)
                used = 0
            row.addWidget(chip)
            used += needed
        if row is not None:
            row.addStretch(1)

        # Avisar al layout de arriba: al pasar de una fila a dos, esto mide
        # el doble, y si nadie se lo dice sigue repartiendo el sitio de antes.
        # Era lo que dejaba las insignias pintadas encima de la barra hasta
        # que se volvía a mover la ventana.
        self.updateGeometry()

    def filas(self) -> int:
        """Cuántas líneas de insignias hay montadas ahora mismo."""
        return max(1, self._column.count())

    def alto_de_fila(self) -> int:
        """Lo que mide una fila de insignias, haya o no alguna todavía.

        No vale preguntarle al `sizeHint`: en el primer trazado aún no se han
        creado, devuelve cero y quien reserve sitio a partir de ahí se queda
        corto. La altura sale de la fuente y del relleno, que se saben antes.
        """
        if self._widgets:
            return max(w.sizeHint().height() for w in self._widgets)
        muestra = Badge("Ag", quiet=True)
        alto = muestra.sizeHint().height()
        muestra.deleteLater()
        return alto

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if abs(self.width() - self._laid_width) > 16:
            self._rebuild()
            # Quien nos contenga puede tener que reservar más alto: al pasar
            # de una fila a dos, esto mide el doble.
            if (padre := self.parentWidget()) is not None:
                reservar = getattr(padre, "_reservar_alto", None)
                if reservar is not None:
                    reservar()


class Notice(QFrame):
    """Explica un dato que falta. Sustituye a esconder la pestaña entera.

    `tone` decide el color de la banda: no es lo mismo algo que el usuario
    puede arreglar —dar permisos, cargar un módulo— que un hecho del hardware
    que no va a cambiar nunca. Pintar los dos del mismo ámbar convierte «esta
    gráfica no trae sensor de temperatura» en una alarma permanente.

    `action` añade un botón dentro del propio aviso, que es donde hace falta:
    quien lee por qué falta un dato es quien quiere arreglarlo.
    """

    action_clicked = Signal()

    def __init__(self, title: str, body: str, hint: str = "",
                 parent: Optional[QWidget] = None, tone: str = "warn",
                 action: Optional[str] = None):
        super().__init__(parent)
        self.setObjectName("Notice")
        # Antes de que Qt aplique la hoja de estilos, para no tener que
        # repintar a mano.
        self.setProperty("tone", tone)
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

        self.action_button: Optional[QPushButton] = None
        if action:
            self.action_button = QPushButton(action)
            self.action_button.clicked.connect(self.action_clicked)
            fila = QHBoxLayout()
            fila.setContentsMargins(0, 6, 0, 0)
            fila.addWidget(self.action_button)
            fila.addStretch(1)
            layout.addLayout(fila)


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
        # Más aire entre filas del que pide la rejilla general: aquí cada
        # renglón es un registro entero, no un campo suelto, y pegados unos a
        # otros la tabla se lee como un bloque de texto.
        self._grid.setVerticalSpacing(theme.METRICS.grid_vspace + 3)

        for column, title in enumerate(self._headers):
            label = QLabel(title.upper())
            label.setObjectName("ColumnTitle")
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
        # Los anchos se calculan al montar la tabla, con las celdas vacías, y
        # los valores llegan después: la columna «Uso» se quedaba con el ancho
        # de su cabecera y enseñaba «12…» en vez de «12.4 %». Al llegar un
        # valor la columna se ensancha si hace falta; nunca se encoge, o la
        # tabla bailaría a cada muestreo.
        self._anchos = [0] * len(self._headers)

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
            self._ajustar_anchos(rows)
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
        self._ajustar_anchos(rows)
        self._fit_height()

    def _ajustar_anchos(self, rows: Sequence[Sequence[str]]) -> None:
        """Que cada columna quepa, midiendo el texto que de verdad lleva.

        Se mide contra la fuente de cada columna, que no es la misma: la
        primera va en la tipografía de la interfaz y las demás en
        monoespaciada, y la cabecera en versalitas.
        """
        if not self._cells:
            return
        tope = theme.METRICS.small_pt * 26      # freno para un valor absurdo
        for columna in range(len(self._headers)):
            celda = self._cells[0][columna] if columna < len(self._cells[0]) else None
            if celda is None:
                continue
            metricas = celda.fontMetrics()
            ancho = max(
                (metricas.horizontalAdvance(str(fila[columna]))
                 for fila in rows if columna < len(fila)),
                default=0,
            )
            ancho = min(ancho, tope)
            if ancho > self._anchos[columna]:
                self._anchos[columna] = ancho
                self._grid.setColumnMinimumWidth(columna, ancho)

    def _fit_height(self) -> None:
        """La tabla ocupa justo lo que necesita de alto; el ancho lo negocia
        su propia barra de desplazamiento.

        Se mide el layout y no el widget: el `sizeHint` del widget se calcula
        en la siguiente pasada de Qt, así que justo después de añadir filas
        aún devuelve el alto anterior y la tabla se quedaba recortada.
        """
        if self.widget() is None:
            return

        # Se calcula, no se pregunta. `sizeHint` (tanto del layout como del
        # widget) se refresca en la siguiente pasada de Qt, así que justo
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
    descubre por accidente. Una marca en cada división dice «esto se mueve»
    antes de que nadie pase el ratón, que es la diferencia entre una función
    que existe y una que se usa.

    La marca tiene dos formas. En reposo es una raya corta y tenue: ahí solo
    tiene que separar dos columnas sin llamar la atención. Con el cursor
    cerca se abre en dos rayitas del color de acento, que es cuando de verdad
    dice «agárrame». Antes eran las dos siempre, y a la altura de las cifras
    quedaban tan pegadas al texto que se leían como parte de él: «Actual |».
    """

    GRIP_HEIGHT = 9
    GRIP_REPOSO = 5
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
        painter.save()
        if active:
            painter.setPen(QPen(self._p.q("accent", 1.0), 1))
            alto, equis = self.GRIP_HEIGHT, (rect.right() - 3, rect.right())
        else:
            painter.setPen(QPen(self._p.q("muted", 0.28), 1))
            alto, equis = self.GRIP_REPOSO, (rect.right() - 1,)
        middle = rect.center().y()
        top = middle - alto // 2
        for x in equis:
            painter.drawLine(x, top, x, top + alto)
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
        # izquierda y las cifras a la derecha. Centrada (que es lo que hace Qt
        # por omisión) no cuadra con ninguna de las dos columnas.
        header_item = self.headerItem()
        header_item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in range(1, len(self.COLUMNS)):
            header_item.setTextAlignment(
                column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        # Sin selección: esto es una tabla de lectura, no una lista de la que
        # se elige algo. Un clic dejaba la fila marcada en azul hasta que se
        # pulsaba otra, y esa marca no significa nada. El resaltado al pasar
        # el cursor sí se queda, que ese ayuda a seguir el renglón.
        self.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # En una ventana estrecha (o en densidad amplia) las columnas suman
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

    # Lo que se deja entre una columna de cifras y la siguiente. Va aparte del
    # respiro general porque estas columnas no tienen nada que las separe: el
    # texto de todas termina en el mismo sitio, pegado al borde derecho, y sin
    # este hueco la marca de arrastre de la cabecera cae encima del número.
    # Se suma al de la densidad elegida en vez de sustituirlo, que quien pide
    # compacta lo pide también aquí.
    RESPIRO_EXTRA = 18

    @property
    def RESPIRO_CIFRAS(self) -> int:  # noqa: N802
        return theme.METRICS.grid_hspace + self.RESPIRO_EXTRA

    def _apply_widths(self, widths) -> None:
        """Aplica anchos con un suelo en la columna de nombres.

        Sin él, unos anchos guardados con otra densidad (o un arrastre
        demasiado entusiasta) dejan la columna tan estrecha que el sangrado y
        el icono se la comen entera y las etiquetas desaparecen.

        El suelo de la primera cuenta además lo que de verdad hay escrito: unos
        anchos guardados cuando la tabla vivía en media pantalla dejaban
        «Intercam…» y «Temperat…» al mudarla a una pantalla entera. Se respeta
        lo que el usuario haya arrastrado, pero nunca por debajo de lo legible.

        Las de cifras tienen el mismo suelo por el mismo motivo, con el
        respiro incluido: cuatro columnas de números alineados a la derecha y
        en monoespaciada, sin hueco entre ellas, se leen como un número largo.
        """
        medidos = self._measure_columns() if self.topLevelItemCount() else []
        self._applying_widths = True
        try:
            for column, width in enumerate(widths):
                if column >= len(self.COLUMNS) - 1:
                    break
                if column == 0:
                    natural = medidos[0] + 46 if medidos else 0
                    floor = min(max(self.NAME_FLOOR, natural), 460)
                elif medidos:
                    floor = min(medidos[column] + self.RESPIRO_CIFRAS, 220)
                else:
                    floor = self.header().minimumSectionSize()
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
                self.setColumnWidth(
                    column,
                    max(52, min(widest[column] + self.RESPIRO_CIFRAS, 220)),
                )
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

    def marcar_aviso(self, device: str, cuantos: int, critico: bool) -> None:
        """Pone en la rama del aparato cuántos de sus sensores están fuera.

        Sin esto, un aviso solo se ve desplegando la rama que lo tiene, y con
        ocho aparatos y noventa y nueve sensores eso es no verlo. La rama va
        cerrada casi siempre; el aviso tiene que llegar hasta arriba.
        """
        item = self._rows.get(f"::{device}")
        if item is None:
            return
        texto = device if not cuantos else f"{device}   ⚠ {cuantos}"
        if item.text(0) != texto:
            item.setText(0, texto)
        item.setForeground(0, self._p.q("crit") if critico
                           else self._p.q("warn") if cuantos
                           else self._p.q("ink"))

    def update_row(self, key: str, values: list[str], tooltip: str = "",
                   alarm: str = "ok") -> None:
        item = self._rows.get(key)
        if item is None:
            return
        for column, text in enumerate(values, start=1):
            if item.text(column) != text:
                item.setText(column, text)
                self._ensanchar_para(column, text)
        # Tres estados y no dos: «alto» es donde el fabricante empieza a
        # incomodarse y «crítico» donde el equipo se protege solo. Pintarlos
        # igual deja sin saber si hay que hacer algo ahora o solo mirarlo.
        colour = {"crítico": self._p.q("crit"),
                  "alto": self._p.q("warn")}.get(alarm, self._p.q("ink"))
        item.setForeground(1, colour)
        if tooltip:
            for column in range(len(self.COLUMNS)):
                item.setToolTip(column, tooltip)

    def _ensanchar_para(self, column: int, text: str) -> None:
        """Da sitio a un valor que ha crecido después de medir las columnas.

        Los anchos se calculan al montar el árbol, cuando muchas celdas están
        todavía vacías o traen un guion. Luego llegan los valores de verdad y
        alguno ya no cabe: la columna del reloj enseñaba «800.0 M…» porque se
        midió antes de que hubiera ningún reloj que medir.

        Solo ensancha, nunca encoge, o la tabla bailaría a cada muestreo. Y no
        toca nada si el usuario ha puesto los anchos a mano.
        """
        if self._preferred_widths or not text:
            return
        necesario = (QFontMetrics(self._value_font).horizontalAdvance(text)
                     + theme.METRICS.grid_hspace)
        if necesario <= self.columnWidth(column):
            return
        self._applying_widths = True
        try:
            self.setColumnWidth(column, min(necesario, 220))
        finally:
            self._applying_widths = False

    def has(self, key: str) -> bool:
        return key in self._rows

    # -- geometría ----------------------------------------------------------

    def _fit_height(self) -> None:
        """El árbol crece con su contenido en vez de tener su propio scroll.

        Dos zonas de desplazamiento anidadas (la página y el árbol) hacen que
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
        # Un hueco de verdad y no un `addSpacing`: ese es comprimible, y
        # cuando la ventana se estrecha y la leyenda pasa a dos filas, Qt lo
        # aplastaba y las insignias acababan pintadas encima de la barra.
        self._hueco_de_la_barra = QWidget()
        self._hueco_de_la_barra.setFixedHeight(self.BAR_HEIGHT)
        self._hueco_de_la_barra.setSizePolicy(QSizePolicy.Policy.Expanding,
                                              QSizePolicy.Policy.Fixed)
        layout.addWidget(self._hueco_de_la_barra)
        layout.addWidget(self._legend)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_segments(self, segments: list[tuple[str, float, str]], total: float,
                     formatter=None) -> None:
        self._segments = segments
        self._total = total or 1.0
        if formatter is not None:
            self._formatter = formatter
        self._legend.set_chips(
            f"{label}  {self._formatter(value)}" for label, value, _ in segments if value > 0
        )
        self._reservar_alto()
        self.update()

    def _reservar_alto(self) -> None:
        """Exige el alto de la barra más el de su leyenda, sin negociar.

        Un layout apretado reparte a base de encoger a quien se deja, y aquí
        lo que se encogía era el hueco de la barra: la leyenda subía encima de
        ella y las insignias salían cortadas por la mitad. Con un mínimo de
        verdad, el que cede es el espacio de alrededor.
        """
        filas = max(1, self._legend.filas())
        alto = (self.BAR_HEIGHT + self.layout().spacing()
                + filas * self._legend.alto_de_fila()
                + max(0, filas - 1) * self._legend.layout().spacing())
        if self.minimumHeight() != alto:
            self.setMinimumHeight(alto)
            self.updateGeometry()

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
