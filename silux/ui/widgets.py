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

from PySide6.QtCore import (QEvent, QPoint, QPointF, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (
    QBrush, QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import render
from ..i18n import _
from ..model import Need
from . import theme
from .theme import Palette, mono_font, ui_font


# --------------------------------------------------------------------------
# texto que se adapta
# --------------------------------------------------------------------------


def avisar_copiado(cerca_de: QLabel, texto: str = "") -> None:
    """Un «copiado» pequeño donde acaba de hacer clic el usuario.

    Va flotando sobre la ventana y no en la barra de estado: quien acaba de
    hacer clic está mirando el valor, no el borde inferior de la pantalla, y
    un aviso que aparece donde no se está mirando no confirma nada.

    Sale a la derecha del valor y a su misma altura, no bajo el cursor: así
    aparece en el mismo sitio se pinche donde se pinche dentro de la fila, en
    vez de bailar unos píxeles según dónde cayera el ratón. Y ahí no tapa lo
    que se acaba de copiar, que es lo que uno mira para comprobar que copió
    lo que quería.

    Se destruye solo. No se reutiliza uno guardado porque dos clics seguidos
    en dos filas distintas tienen que poder solaparse sin que el primero le
    robe el sitio al segundo.
    """
    ventana = cerca_de.window()
    if ventana is None:
        return
    globo = QLabel(texto or _("app.copied"), ventana)
    globo.setObjectName("Toast")
    globo.setFont(ui_font(theme.METRICS.small_pt))
    globo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    globo.adjustSize()

    # El final del texto, no el del widget: la etiqueta ocupa toda la columna
    # aunque el valor sea corto, y midiendo el widget el aviso aparecía a un
    # palmo de «AMD».
    esquina = cerca_de.mapTo(ventana, QPoint(0, 0))
    ancho_texto = cerca_de.fontMetrics().horizontalAdvance(cerca_de.text())
    x = esquina.x() + min(ancho_texto, cerca_de.width()) + 10
    y = esquina.y() + (cerca_de.height() - globo.height()) // 2

    # Siempre dentro de la ventana: en la columna de la derecha, o con la
    # ventana estrecha, se salía por el borde.
    x = min(max(0, x), max(0, ventana.width() - globo.width() - 4))
    y = min(max(0, y), max(0, ventana.height() - globo.height() - 4))
    globo.move(x, y)
    globo.show()
    globo.raise_()

    QTimer.singleShot(MILISEGUNDOS_DEL_AVISO, globo.deleteLater)


# Cuánto dura el «copiado». Lo justo para verlo sin que estorbe: por debajo de
# un segundo no da tiempo a leerlo si uno mueve la vista, y por encima de dos
# se queda ahí molestando cuando ya se ha entendido.
MILISEGUNDOS_DEL_AVISO = 1400


class ElidingLabel(QLabel):
    """Recorta con puntos suspensivos y deja el texto completo en el tooltip.

    QLabel no sabe hacer esto por sí solo: o desborda la tarjeta o fuerza a
    la ventana a ser más ancha. Aquí el texto se recorta al ancho disponible
    y sigue siendo accesible al pasar el ratón y al copiar.
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._full = ""
        self._copiable = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_full_text(text)

    def hacer_copiable(self) -> None:
        """Un clic deja el texto completo en el portapapeles.

        Se copia lo entero y no lo que se ve: la gracia de esto es justo la
        fila que no cabe y sale con puntos suspensivos, que es la que uno no
        puede transcribir a mano.
        """
        self._copiable = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        # Un guion no es un valor: es la marca de uno que falta, y copiarlo
        # deja en el portapapeles algo que no significa nada.
        if (self._copiable and event.button() == Qt.MouseButton.LeftButton
                and self._full and self._full != "—"):
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._full)
            avisar_copiado(self)
        super().mouseReleaseEvent(event)

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

    Una columna solo cabe si caben sus hijos. `min_item_width` es lo que quien
    la monta cree que necesita cada uno, y no siempre acierta: en Ajustes la
    tarjeta de Apariencia lleva una fila de tres botones que pide 529 px, y a
    900×680 en compacto se repartía en dos columnas de 360. La rejilla exigía
    entonces el doble de ese mínimo, la fila se ensanchaba para dárselo y el
    área de desplazamiento, que no tiene barra horizontal, cortaba lo que
    sobraba por la derecha sin avisar. Por eso un reparto solo vale si la suma
    de lo que pide cada columna —lo que pide su hijo más ancho, y nunca menos
    de `min_item_width`— cabe en el ancho de la fila. Y la fila no le pide a
    quien la contiene más que el ancho de su hijo más ancho: si pidiera el de
    la rejilla montada, su propia anchura le diría que caben dos columnas y
    nunca bajaría a una.
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
        # El mínimo lo decide `minimumSizeHint`, no la rejilla montada.
        self._grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def _anchos_minimos(self) -> list[int]:
        return [self._min_item_width if w.isHidden()
                else max(self._min_item_width, w.minimumSizeHint().width())
                for w in self._items]

    def _ancho_minimo_de_hijo(self) -> int:
        return max(self._anchos_minimos(), default=self._min_item_width)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        alto = super().minimumSizeHint().height()
        return QSize(self._ancho_minimo_de_hijo(), max(alto, 0))

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        widget.setParent(self)
        self._relayout(force=True)

    def _wanted_columns(self) -> int:
        count = len(self._items)
        if not count:
            return 1
        gap = self._grid.spacing()
        anchos = self._anchos_minimos()
        usable = max(self.width(), max(anchos))
        fits = int(max(1, (usable + gap) // (self._min_item_width + gap)))
        for tope in range(fits, 0, -1):
            columnas = balanced_columns(count, tope)
            pide = sum(max(anchos[i] for i in range(columna, count, columnas))
                       for columna in range(columnas))
            if columnas == 1 or pide + gap * (columnas - 1) <= usable:
                return columnas
        return 1

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

    def event(self, event) -> bool:  # noqa: N802
        # Un hijo que crece con el dato nuevo —un nombre más largo— no cambia
        # el ancho de la fila, así que no llega ningún `resizeEvent`; lo que
        # llega es la petición de recolocar. Ahí se vuelve a mirar si caben.
        resultado = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest:
            self._relayout()
        return resultado


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
        self._muestra: Optional[QColor] = None
        self._borde: Optional[QColor] = None

    def set_swatch(self, color: Optional[QColor], borde: Optional[QColor] = None) -> None:
        """Un cuadrado de color delante del texto: de qué tramo habla.

        En la leyenda de una barra, sin él hay que contar tramos para saber
        cuál es «Caché». Lleva borde porque el tramo libre es del color del
        fondo de la barra, y sin borde su cuadrado no se vería.
        """
        if color == self._muestra:
            return
        self._muestra, self._borde = color, borde
        self.setIndent(self._lado() + 6 if color is not None else -1)
        self.updateGeometry()
        self.update()

    def swatch(self) -> Optional[QColor]:
        return self._muestra

    def _lado(self) -> int:
        return max(7, int(self.fontMetrics().ascent() * 0.8))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._muestra is None:
            return
        lado = self._lado()
        zona = self.contentsRect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._borde, 1.0) if self._borde is not None
                       else Qt.PenStyle.NoPen)
        painter.setBrush(self._muestra)
        painter.drawRoundedRect(
            QRectF(zona.left() + 0.5, zona.center().y() - lado / 2 + 0.5, lado, lado), 2, 2)
        painter.end()


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

    # Alguien ha pulsado el candado de un campo que falta por permisos.
    locked_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._filas: dict[str, int] = {}
        self._candados: dict[str, "LockMark"] = {}
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
        value_label.hacer_copiable()

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
        self._filas[name] = self._rows
        self._rows += 1
        return value_label

    def set_locked(self, name: str, color: str, tooltip: str = "") -> None:
        """El cuarto estado de un campo: está, y lo guarda un permiso.

        Los otros tres ya existían: el dato, el guion de «no lo sé» y el campo
        escondido y nombrado al pie porque no existe. Un dato que falta por
        permisos salía con el mismo guion que uno que no se pudo leer, y no
        son lo mismo: este tiene arreglo, y el arreglo es pulsar aquí.
        """
        label = self._values.get(name)
        if label is None:
            return
        candado = self._candados.get(name)
        if candado is None:
            candado = LockMark(color, max(10, label.fontMetrics().ascent()))
            candado.hacer_pulsable()
            candado.clicked.connect(self.locked_clicked)
            self._grid.addWidget(candado, self._filas[name], 1,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._candados[name] = candado
        candado.setToolTip(tooltip)
        candado.show()
        label.set_full_text("")
        label.hide()

    def is_locked(self, name: str) -> bool:
        candado = self._candados.get(name)
        return candado is not None and not candado.isHidden()

    def set(self, name: str, value: str, tooltip: Optional[str] = None) -> None:
        label = self._values.get(name)
        if label is None:
            return
        if (candado := self._candados.get(name)) is not None and not candado.isHidden():
            candado.hide()
            label.show()
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
            return _("chart.now").format(cifra=cifra)
        if atras < 60:
            return _("chart.ago.s").format(cifra=cifra, n=f"{atras:.0f}")
        return _("chart.ago.min").format(cifra=cifra, n=f"{atras / 60:.0f}")

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

        self._dibujar_pico(painter, rect, points, values)

        if self._hover is not None and 0 <= self._hover < len(points):
            self._draw_hover(painter, rect, points[self._hover], values[self._hover])
        painter.end()

    # Cuánto tiene que despegarse el máximo de la media para que marcarlo
    # signifique algo. Sin este margen, una línea plana con una arruga de
    # medio grado sale con su punto y su cifra como si hubiera pasado algo.
    RELIEVE_MINIMO = 0.06

    def _dibujar_pico(self, painter: QPainter, rect: QRectF,
                      points: list, values: list) -> None:
        """Marca el punto más alto del tramo que se está viendo.

        Se ve que la temperatura subió, pero no a cuánto llegó ni cuándo: para
        eso había que estar mirando en ese momento o pasar el ratón buscando a
        ciegas. Es el mismo dato que la columna «Máx» del árbol de sensores,
        puesto donde ocurrió.

        No se marca si el máximo es el último punto —ese ya lleva el suyo, y
        dos círculos juntos se leen como un error—, ni si la curva es
        prácticamente plana.
        """
        indice = self._indice_del_pico()
        if indice is None:
            return

        alto = values[indice]
        punto = points[indice]
        painter.setPen(Qt.PenStyle.NoPen)
        # Hueco y no relleno: el punto lleno es «aquí estás ahora», y el pico
        # es otra cosa. Con los dos iguales habría que adivinar cuál es cuál.
        painter.setBrush(QBrush(self._p.q("surface")))
        painter.drawEllipse(punto, 3.0, 3.0)
        painter.setPen(QPen(self._p.q("accent", 0.75), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(punto, 3.0, 3.0)

        if self._formatter is None:
            return
        texto = self._formatter(alto)
        painter.setFont(ui_font(max(7, theme.METRICS.small_pt - 2)))
        metrica = painter.fontMetrics()
        ancho = metrica.horizontalAdvance(texto)
        alto_texto = metrica.height()

        # Encima del punto es donde se lee mejor, pero un pico está por
        # definición cerca del techo y ahí casi nunca cabe. Debajo tapaba la
        # curva justo en el tramo que se estaba mirando, así que el segundo
        # sitio es al lado, a la altura del punto: a los lados del máximo la
        # curva ya ha bajado y no hay nada que tapar.
        arriba = punto.y() - 5 - alto_texto
        if arriba >= rect.top():
            x = min(max(punto.x() - ancho / 2, rect.left()), rect.right() - ancho)
            y = arriba
        else:
            y = min(max(punto.y() - alto_texto / 2, rect.top()),
                    rect.bottom() - alto_texto)
            derecha = punto.x() + 6
            x = (derecha if derecha + ancho <= rect.right()
                 else punto.x() - 6 - ancho)

        # La cifra cae sobre el relleno del área, y ahí un texto suelto se
        # pierde: en tema claro el gris sobre el azul aguado no se lee. Lleva
        # detrás el color del panel, igual que la etiqueta del cursor.
        caja = QRectF(x - 3, y, ancho + 6, alto_texto)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._p.q("surface", 0.82)))
        painter.drawRoundedRect(caja, 3, 3)

        painter.setPen(self._p.q("ink_dim"))
        painter.drawText(caja, int(Qt.AlignmentFlag.AlignCenter), texto)

    def _indice_del_pico(self) -> Optional[int]:
        """Dónde está el máximo del tramo visible, o nada si no hay uno claro.

        Nada cuando aún hay pocas muestras —al arrancar, cualquier subida es
        «el máximo hasta ahora»—, cuando el máximo es el último punto, que ya
        lleva su propia marca, y cuando la curva es prácticamente plana.
        """
        valores = list(self._values)
        if len(valores) < 5:
            return None
        indice = max(range(len(valores)), key=valores.__getitem__)
        if indice >= len(valores) - 1:
            return None
        alto, bajo = valores[indice], min(valores)
        escala = abs(alto) or 1.0
        if (alto - bajo) / escala < self.RELIEVE_MINIMO:
            return None
        return indice

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

    # Alguien ha pulsado el candado de una cifra que falta por permisos.
    locked_clicked = Signal()

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

        # El candado de cuando la cifra falta por permisos: a tamaño de
        # cifra, en el sitio de la cifra.
        self.lock = LockMark(palette.warn, theme.METRICS.tile_value_pt)
        self.lock.hacer_pulsable()
        self.lock.clicked.connect(self.locked_clicked)
        self.lock.hide()

        row.addWidget(self.lock)
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

    def set_label(self, label: str) -> None:
        """Cambia el nombre del recuadro.

        Casi ninguno lo necesita, pero hay uno que mide dos cosas distintas
        según el estado: en una batería, lo que queda de autonomía y lo que
        falta para llenarse no son la misma cifra ni se llaman igual.
        """
        texto = label.upper()
        if self.caption.text() != texto:
            self.caption.setText(texto)

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

    def set_locked(self, detalle: str, tooltip: str = "") -> None:
        """La cifra falta por permisos: candado en su sitio, sin unidad.

        El detalle dice «con permisos» y no repite el porqué, que ya está en
        el aviso de la página y en el tooltip.
        """
        self.value.hide()
        self.unit.hide()
        self.lock.setToolTip(tooltip)
        self.lock.show()
        self.set_detail(detalle)

    def is_locked(self) -> bool:
        return not self.lock.isHidden()

    def update_value(self, text: str, series_value: Optional[float] = None) -> None:
        if not self.lock.isHidden():
            self.lock.hide()
            self.value.show()
            self.unit.show()
        if self.value.text() != text:
            self.value.setText(text)
            # El guion de «sin dato» a treinta y seis píxeles es una raya
            # gruesa que no se lee como un guion: en una Intel, con cuatro de
            # los seis cuadros vacíos, la fila parecía tachada. Se pinta al
            # cuerpo del texto pequeño y en el gris de lo apagado, que es lo
            # que ya dice «aquí no hay nada» en el resto del programa.
            vacio = text == render.DASH
            self.value.setFont(
                ui_font(theme.METRICS.small_pt) if vacio
                else mono_font(theme.METRICS.tile_value_pt, bold=True))
            self.value.setObjectName("Muted" if vacio else "TileValue")
            self.value.style().unpolish(self.value)
            self.value.style().polish(self.value)
        self.chart.push(series_value)


# --------------------------------------------------------------------------
# matriz de núcleos
# --------------------------------------------------------------------------








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
        self._swatches: list = []
        self._widgets: list[Badge] = []
        self._laid_width = 0
        # El ancho mínimo lo marca la insignia más ancha, no la fila entera:
        # si no, una lista larga impide encoger la ventana.
        self.setMinimumWidth(64)

    def set_chips(self, labels: Iterable[str], highlight_first: bool = False,
                  swatches: Optional[Sequence] = None) -> None:
        """Pone las insignias. `swatches`: un (color, borde) por insignia, o
        nada; es lo que convierte la fila en la leyenda de una barra."""
        chips = [(str(text), highlight_first and i == 0)
                 for i, text in enumerate(labels)]
        self._swatches = list(swatches) if swatches is not None else []

        # Si solo ha cambiado el texto (el caso normal: una leyenda que sigue a
        # unos valores vivos) se reescriben las insignias que ya existen. Crear
        # widgets nuevos en cada muestreo iba dejando miles vivos: era la fuga
        # que hacía crecer la memoria medio megabyte por minuto.
        if len(chips) == len(self._widgets) and \
                [loud for _descarte, loud in chips] == [loud for _descarte, loud in self._chips]:
            self._chips = chips
            for widget, (text, _tono) in zip(self._widgets, chips):
                if widget.text() != text:
                    widget.setText(text)
            self._poner_muestras()
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
        for indice, (text, loud) in enumerate(self._chips):
            chip = Badge(text, quiet=not loud)
            if indice < len(self._swatches):
                # Antes de medirla: la muestra ensancha la insignia.
                chip.set_swatch(*self._swatches[indice])
            self._widgets.append(chip)
            # El hueco entre insignias sigue a la densidad: pegadas unas a
            # otras, una leyenda de tres se lee como una sola etiqueta larga.
            hueco = max(6, theme.METRICS.card_gap)
            needed = chip.sizeHint().width() + hueco
            if row is None or (used and used + needed > width):
                if row is not None:
                    # Cada fila lleva su muelle, no solo la última: sin él,
                    # las insignias de las filas llenas se repartían por todo
                    # el ancho y solo la de abajo quedaba a la izquierda.
                    row.addStretch(1)
                row = QHBoxLayout()
                row.setSpacing(hueco)
                row.setContentsMargins(0, 0, 0, 0)
                self._column.addLayout(row)
                used = 0
            row.addWidget(chip)
            used += needed
        if row is not None:
            row.addStretch(1)
        self._poner_muestras()

        # Avisar al layout de arriba: al pasar de una fila a dos, esto mide
        # el doble, y si nadie se lo dice sigue repartiendo el sitio de antes.
        # Era lo que dejaba las insignias pintadas encima de la barra hasta
        # que se volvía a mover la ventana.
        self.updateGeometry()

    def _poner_muestras(self) -> None:
        for indice, widget in enumerate(self._widgets):
            color, borde = (self._swatches[indice] if indice < len(self._swatches)
                            else (None, None))
            widget.set_swatch(color, borde)

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


# Qué se puede arreglar y qué no. Lo primero va en ámbar y lleva botón cuando
# lo hay; lo segundo, en gris: un hecho del hardware no es una avería. Vive
# aquí, al lado de `Notice`, porque la tabla estaba escrita solo en Gráficos y
# las otras tres páginas que enseñan avisos pintaban de ámbar hasta lo que no
# se puede arreglar: «el hipervisor no expone la frecuencia» salía tan urgente
# como un permiso por dar.
NEED_TONES = {
    Need.ROOT: "warn",
    Need.DRIVER: "warn",
    Need.DATABASE: "warn",
    Need.HARDWARE: "idle",
    Need.PLATFORM: "idle",
    Need.ERROR: "bad",
}


def tone_for(need) -> str:
    """El color de la banda de un aviso, según se pueda hacer algo o no."""
    return NEED_TONES.get(need, "warn")


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
    snoozed = Signal()
    dismissed = Signal()

    def __init__(self, title: str, body: str, hint: str = "",
                 parent: Optional[QWidget] = None, tone: str = "warn",
                 action: Optional[str] = None, dismissible: bool = False):
        """`dismissible`: lleva además «Ahora no» y «No volver a mostrar».
        Para los avisos de permisos, que son los que se pueden apartar."""
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
            if dismissible:
                self.snooze_button, self.dismiss_button = dismiss_buttons()
                self.snooze_button.clicked.connect(self.snoozed)
                self.dismiss_button.clicked.connect(self.dismissed)
                fila.addWidget(self.snooze_button)
                fila.addWidget(self.dismiss_button)
            layout.addLayout(fila)


class LockMark(QWidget):
    """Un candado pequeño: «este dato está, y lo guarda un permiso».

    Dibujado y no un carácter: el emoji del candado sale en color, con otra
    altura y, según la tipografía instalada, no sale. Toma el color que se le
    diga, que es el ámbar de lo que tiene arreglo.
    """

    clicked = Signal()

    def __init__(self, color: str, lado: int = 12, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(lado, lado)

    def hacer_pulsable(self) -> None:
        """Donde el candado es el dato que falta: pulsarlo pide los permisos."""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pulsable = True

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if getattr(self, "_pulsable", False) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        lado = min(self.width(), self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # El arco, de trazo; el cuerpo, relleno.
        pluma = QPen(self._color, max(1.2, lado * 0.13))
        painter.setPen(pluma)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(lado * 0.27, lado * 0.06, lado * 0.46, lado * 0.62),
                        0, 180 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawRoundedRect(QRectF(lado * 0.14, lado * 0.42, lado * 0.72, lado * 0.52),
                                lado * 0.1, lado * 0.1)
        painter.end()


def dismiss_buttons() -> tuple[QPushButton, QPushButton]:
    """«Ahora no» y «No volver a mostrar», los mismos en Inicio y en las páginas.

    Dos botones de texto y no un aspa: un aspa no dice si es por ahora o para
    siempre, y son dos cosas distintas. Quien los usa conecta cada uno.
    """
    luego = QPushButton(_("perm.notice.later"))
    luego.setToolTip(_("perm.notice.later.tip"))
    nunca = QPushButton(_("perm.notice.never"))
    nunca.setToolTip(_("perm.notice.never.tip"))
    for boton in (luego, nunca):
        boton.setObjectName("TextButton")
        boton.setFlat(True)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
    return luego, nunca


class PermissionNotice(QFrame):
    """Lo que falta por permisos, junto, y el botón para darlos.

    Cada página explica sus huecos donde están. Esto los junta en un sitio:
    quien abre el programa por primera vez no ha entrado todavía en Memoria ni
    en Almacenamiento, y no sabe que ahí falta nada.

    La lista sale de las notas de la foto y no de un texto fijo: en un equipo
    sin SMART no promete la salud de los discos. Se reescribe solo cuando
    cambia lo que falta, que es casi nunca.
    """

    grant_requested = Signal()
    explain_requested = Signal()
    snoozed = Signal()
    dismissed = Signal()

    def __init__(self, palette: "Palette", compact: bool = False,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Notice")
        self.setProperty("tone", "warn")
        self._p = palette
        self._compact = compact
        self._nombres: tuple[str, ...] = ()
        self._recaida = False
        m = theme.METRICS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(m.card_pad_h - 2, m.card_pad_v - 3,
                                  m.card_pad_h - 2, m.card_pad_v - 3)
        layout.setSpacing(4)

        self.title = QLabel("")
        self.title.setObjectName("NoticeTitle")
        layout.addWidget(self.title)

        self._lista = QVBoxLayout()
        self._lista.setContentsMargins(0, 2, 0, 2)
        self._lista.setSpacing(2)
        layout.addLayout(self._lista)
        self.lines: list[QLabel] = []

        self.grant_button = QPushButton(_("perm.notice.grant"))
        self.grant_button.setObjectName("Primary")
        self.grant_button.clicked.connect(self.grant_requested)
        # Al lado del que pide la contraseña: quien duda si pulsarlo es quien
        # quiere saber antes qué va a pasar.
        self.explain_button = QPushButton(_("perm.notice.explain"))
        self.explain_button.setObjectName("GhostButton")
        self.explain_button.clicked.connect(self.explain_requested)
        self.snooze_button, self.dismiss_button = dismiss_buttons()
        self.snooze_button.clicked.connect(self.snoozed)
        self.dismiss_button.clicked.connect(self.dismissed)

        self.buttons = QHBoxLayout()
        self.buttons.setContentsMargins(0, 4, 0, 0)
        self.buttons.addWidget(self.grant_button)
        self.buttons.addWidget(self.explain_button)
        self.buttons.addStretch(1)
        self.buttons.addWidget(self.snooze_button)
        self.buttons.addWidget(self.dismiss_button)
        layout.addLayout(self.buttons)

    def set_missing(self, nombres: Sequence[str], recaida: bool = False) -> None:
        """Pone lo que falta. `recaida`: se tenía y ha dejado de leerse."""
        nombres = tuple(nombres)
        if nombres == self._nombres and recaida == self._recaida:
            return
        self._nombres, self._recaida = nombres, recaida
        n = len(nombres)
        if recaida:
            clave = "perm.notice.lost.one" if n == 1 else "perm.notice.lost.many"
        else:
            clave = "perm.notice.title.one" if n == 1 else "perm.notice.title.many"
        self.title.setText(_(clave).format(n=n))

        # En compacto, una sola línea: cinco renglones se comían media página.
        textos = [" · ".join(nombres)] if self._compact else list(nombres)
        while len(self.lines) > len(textos):
            fila = self._lista.takeAt(len(self.lines) - 1)
            self.lines.pop()
            clear_layout(fila.layout())
        for indice, texto in enumerate(textos):
            if indice < len(self.lines):
                if self.lines[indice].text() != texto:
                    self.lines[indice].setText(texto)
                continue
            fila = QHBoxLayout()
            fila.setSpacing(6)
            fila.addWidget(LockMark(self._p.warn, theme.METRICS.small_pt + 2))
            etiqueta = QLabel(texto)
            etiqueta.setObjectName("NoticeBody")
            etiqueta.setWordWrap(self._compact)
            fila.addWidget(etiqueta, 1)
            self._lista.addLayout(fila)
            self.lines.append(etiqueta)

    def set_waiting(self, esperando: bool) -> None:
        """Mientras polkit pregunta, el botón lo dice y no se puede repetir."""
        self.grant_button.setEnabled(not esperando)
        self.grant_button.setText(_("perm.waiting") if esperando
                                  else _("perm.notice.grant"))


def boton_de_permiso_permanente() -> QPushButton:
    """El botón que deja de pedir la contraseña en cada arranque.

    Sale al lado del de elevar, que es donde está mirando quien acaba de
    descubrir que le falta un permiso. Se esconde solo cuando ya está hecho:
    un botón que no hace nada es peor que ninguno.
    """
    boton = QPushButton(_("perm.permanent.button"))
    boton.setObjectName("GhostButton")
    boton.setToolTip(
        _("perm.permanent.tip")
    )
    return boton


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
            # Abajo de su celda, pegado a las filas que titula. La celda mide
            # lo que una fila y la letra es pequeña: con el texto arriba
            # quedaba un hueco de fila vacía entre los títulos y los datos.
            label.setAlignment(
                (Qt.AlignmentFlag.AlignRight if self._numeric[column]
                 else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignBottom
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
                # Aquí viven los modelos de disco, las direcciones y las
                # referencias de los módulos: lo que uno pega en un buscador.
                label.hacer_copiable()
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














def memory_segments(memory) -> list[tuple[str, float, str]]:
    """Los tramos de la barra de memoria: lo mismo en Inicio, Memoria y Sistema.

    Los tres más el hueco del fondo suman el total, por eso van las
    aplicaciones y no «en uso»: lo segundo incluye caché que no se devuelve y
    haría que la barra se pasara. La caché va con su color y no con el del
    fondo: en Inicio iba con el de la línea, que es el de la barra vacía, y no
    se distinguía de lo libre.
    """
    return [
        (_("sys.mem.apps"), memory.apps_bytes, "accent"),
        (_("sys.mem.cache"), memory.cache_bytes, "info"),
        (_("sys.mem.buffers"), memory.buffers_bytes, "warn"),
        (_("sys.mem.free"), memory.free_bytes, "line"),
    ]


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
        visibles = [s for s in segments if s[1] > 0]
        borde = self._p.q("muted", 0.6)
        self._legend.set_chips(
            (f"{label}  {self._formatter(value)}" for label, value, _token in visibles),
            swatches=[(self._p.q(token), borde) for _label, _value, token in visibles],
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
        for _descarte, value, token in self._segments:
            if value <= 0:
                continue
            width = rect.width() * value / self._total
            painter.setBrush(QBrush(self._p.q(token)))
            painter.drawRect(QRectF(offset, 0, width, self.BAR_HEIGHT))
            offset += width
        painter.end()


