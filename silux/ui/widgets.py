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

import math
import time
from collections import deque
from typing import Iterable, NamedTuple, Optional, Sequence

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import render
from ..i18n import _
from ..model import Need, plausible
from . import theme
from .theme import Palette, ui_font, value_font

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
        # El tooltip que puso quien usa la etiqueta: de dónde sale el dato,
        # por qué falta. Manda sobre el del recorte.
        self._explicacion = ""
        self._copiable = False
        self._lineas = 1
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_full_text(text)

    def permitir_lineas(self, cuantas: int) -> None:
        """Deja que el texto ocupe varias líneas antes de recortarlo.

        Para lo que es una frase y no una cifra: la especificación de un
        procesador («AMD Ryzen 7 5800X3D 8-Core Processor») salía cortada en
        compacto con un renglón entero libre debajo.
        """
        if max(1, cuantas) == self._lineas:
            return
        self._lineas = max(1, cuantas)
        self.setWordWrap(self._lineas > 1)
        self._refresh()
        self.updateGeometry()

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
        # La explicación era del valor anterior: quien cambia el valor pone
        # después la suya, si la tiene.
        self._explicacion = ""
        self._refresh()

    def setToolTip(self, texto: str) -> None:  # noqa: N802
        self._explicacion = texto or ""
        self._poner_tooltip()

    def _poner_tooltip(self) -> None:
        """La explicación de fuera, o el texto entero si sale recortado.

        `_refresh` corre en cada redimensionado: si pusiera aquí solo lo del
        recorte, borraría la explicación en cuanto la ventana cambia de tamaño.
        """
        recortado = self.text() != self._full
        super().setToolTip(self._explicacion or (self._full if recortado else ""))

    def full_text(self) -> str:
        return self._full

    def _needs_elide(self) -> bool:
        return self.fontMetrics().horizontalAdvance(self._full) > max(self.width(), 1)

    def _refresh(self) -> None:
        available = max(self.width(), 1)
        metricas = self.fontMetrics()
        if self._lineas > 1:
            # Entero si cabe en sus líneas partiendo por palabras; si no, se
            # recorta lo que cabría en ellas, con algo de margen porque las
            # líneas no se llenan hasta el borde.
            alto = metricas.boundingRect(0, 0, available, 100000,
                                         int(Qt.TextFlag.TextWordWrap), self._full).height()
            if alto <= metricas.lineSpacing() * self._lineas + 1:
                elided = self._full
            else:
                elided = metricas.elidedText(self._full, Qt.TextElideMode.ElideRight,
                                             int(available * (self._lineas - 0.25)))
        else:
            elided = metricas.elidedText(self._full, Qt.TextElideMode.ElideRight, available)
        super().setText(elided)
        self._poner_tooltip()

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

    Un hijo escondido no ocupa celda. En la gráfica integrada de Intel la
    ficha de la temperatura se esconde porque esa tarjeta no la publica, y
    con su celda reservada quedaba un hueco del ancho de una ficha entre
    Frecuencia y Consumo: las que hay se reparten el ancho entero.
    """

    def __init__(self, min_item_width: int = 200, parent: Optional[QWidget] = None,
                 span_last: bool = False):
        """`span_last`: si la última fila queda a medias, su último hijo se
        estira hasta el borde en vez de dejar un hueco a su derecha."""
        super().__init__(parent)
        self._span_last = span_last
        # El ancho mínimo se da en unidades de densidad normal y se escala con
        # la densidad activa, o en modo compacto sobrarían columnas vacías.
        scale = theme.METRICS.cell_w / theme.NORMAL.cell_w
        self._min_item_width = max(110, int(min_item_width * scale))
        self._items: list[QWidget] = []
        self._columns = 0
        self._colocados: list[QWidget] = []

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(theme.METRICS.section_gap)
        # El mínimo lo decide `minimumSizeHint`, no la rejilla montada.
        self._grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def _anchos_minimos(self) -> list[int]:
        return [self._min_item_width if self._escondido(w)
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

    @staticmethod
    def _escondido(widget: QWidget) -> bool:
        """Si alguien lo escondió a propósito.

        `isHidden` a secas no vale: un widget recién creado también lo está
        hasta que se enseña por primera vez. Con la página ya abierta, las
        tarjetas que nacían después (los módulos de memoria al dar permisos)
        contaban como escondidas, no entraban en la rejilla y nadie las
        enseñaba: no salían hasta cambiar de página y volver.
        """
        return widget.isHidden() and widget.testAttribute(
            Qt.WidgetAttribute.WA_WState_ExplicitShowHide)

    def _a_la_vista(self) -> list[QWidget]:
        return [w for w in self._items if not self._escondido(w)]

    def _wanted_columns(self) -> int:
        visibles = self._a_la_vista()
        count = len(visibles)
        if not count:
            return 1
        gap = self._grid.spacing()
        anchos = [max(self._min_item_width, w.minimumSizeHint().width())
                  for w in visibles]
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
        visibles = self._a_la_vista()
        if columns == self._columns and visibles == self._colocados and not force:
            return
        self._columns = columns
        self._colocados = visibles

        # `removeWidget` y no `takeAt`: desde Python el segundo no destruye
        # la celda, y un widget avisa de que cambió de tamaño a la primera
        # celda que tuvo. La nueva se quedaba con la altura de la primera
        # medida, y un texto que después pasaba a dos líneas salía cortado.
        while self._grid.count():
            self._grid.removeWidget(self._grid.itemAt(0).widget())
        for index in range(self._grid.columnCount()):
            self._grid.setColumnStretch(index, 0)

        for index, widget in enumerate(visibles):
            ultimo = index == len(visibles) - 1
            ancho = (columns - index % columns) if (self._span_last and ultimo) else 1
            self._grid.addWidget(widget, index // columns, index % columns, 1, ancho)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event) -> None:  # noqa: N802
        # Lo que se escondió con la página cerrada no avisa a nadie.
        super().showEvent(event)
        self._relayout()

    def event(self, event) -> bool:  # noqa: N802
        # Un hijo que crece con el dato nuevo —un nombre más largo— no cambia
        # el ancho de la fila, así que no llega ningún `resizeEvent`; lo que
        # llega es la petición de recolocar. Ahí se vuelve a mirar si caben.
        # Es también lo que llega cuando uno de ellos se esconde o vuelve.
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
            # Como viene escrito, sin pasarlo a mayúsculas: «nvme0n1» y
            # «enp6s0» son nombres, y «NVME0N1» no lo es de nada.
            self._title_label = QLabel(title)
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
            self._title_label.setText(title)


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


class Plegable(QWidget):
    """Un bloque que nace cerrado: un renglón que lo nombra y lo abre.

    Para lo que hay que tener y casi nadie mira —los identificadores PCI de
    una gráfica, la firma CPUID—. Sigue estando a un clic, pero no se lleva
    media tarjeta por delante de lo que sí se mira.
    """

    def __init__(self, titulo: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._titulo = titulo
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(theme.METRICS.grid_vspace)

        self.boton = QPushButton("")
        self.boton.setObjectName("TextButton")
        self.boton.setFlat(True)
        self.boton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton.clicked.connect(lambda: self.set_abierto(not self.abierto()))
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(self.boton)
        fila.addStretch(1)
        columna.addLayout(fila)

        self._caja = QWidget()
        self.body = QVBoxLayout(self._caja)
        self.body.setContentsMargins(0, 0, 0, 0)
        columna.addWidget(self._caja)
        self.set_abierto(False)

    def abierto(self) -> bool:
        return not self._caja.isHidden()

    def set_abierto(self, abierto: bool) -> None:
        self._caja.setVisible(abierto)
        self.boton.setText(f"{'▾' if abierto else '▸'} {self._titulo}")
        self.updateGeometry()


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
        # Dos estados de cada fila, y de los dos sale qué se ve (`_mostrar`):
        # si está escondida entera y si su valor lo guarda un permiso.
        self._ocultas: set[str] = set()
        self._bloqueadas: set[str] = set()
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
        value_label.setFont(value_font())
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
            candado.hide()
            self._grid.addWidget(candado, self._filas[name], 1,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._candados[name] = candado
        candado.setToolTip(tooltip)
        self._bloqueadas.add(name)
        label.set_full_text("")
        self._mostrar(name)

    def is_locked(self, name: str) -> bool:
        return name in self._bloqueadas

    def value_label(self, name: str) -> ElidingLabel:
        return self._values[name]

    def is_blank(self, name: str) -> bool:
        """The row holds a dash, not a value nor a padlock."""
        label = self._values.get(name)
        return (label is not None and name not in self._bloqueadas
                and label.full_text() == "—")

    def set(self, name: str, value: str, tooltip: Optional[str] = None) -> None:
        label = self._values.get(name)
        if label is None:
            return
        if name in self._bloqueadas:
            self._bloqueadas.discard(name)
            self._mostrar(name)
        label.set_full_text(value)
        if tooltip:
            label.setToolTip(f"{value}\n\n{tooltip}" if value else tooltip)

    def set_visible(self, name: str, visible: bool) -> None:
        """Esconde o enseña una fila entera, nombre incluido.

        Se ocultan, no se destruyen: crear widgets en cada muestreo es lo que
        hacía crecer la memoria medio megabyte por minuto. Y el candado se
        va con la fila: escondida, no queda suelto en la tarjeta.
        """
        if name not in self._names:
            return
        if visible:
            self._ocultas.discard(name)
        else:
            self._ocultas.add(name)
        self._mostrar(name)

    def _mostrar(self, name: str) -> None:
        """Lo que se ve de la fila, sacado de sus dos estados.

        Cada widget se toca solo si cambia (`setVisible` no hace nada si ya
        está así): quien rellena la tarjeta en cada muestreo no la recoloca
        si nada ha cambiado.
        """
        fila = name not in self._ocultas
        bloqueada = name in self._bloqueadas
        self._names[name].setVisible(fila)
        self._values[name].setVisible(fila and not bloqueada)
        if (candado := self._candados.get(name)) is not None:
            candado.setVisible(fila and bloqueada)

    def reset(self) -> None:
        clear_layout(self._grid)
        self._values.clear()
        self._names.clear()
        self._filas.clear()
        self._candados.clear()
        self._ocultas.clear()
        self._bloqueadas.clear()
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


class Series(NamedTuple):
    """What a chart draws: one quantity, of one thing, in one unit.

    `key` says what and of what, raw ("gpu:0000:00:02.0/power"); `unit` is
    one of `model.PLAUSIBLE`, and `ceiling` lowers its top where the thing
    itself says it (a link's speed). Inicio's GPU chart drew megahertz over
    percentages when a sample came without usage: a chart never draws one
    series over another.
    """

    key: str
    unit: str
    ceiling: Optional[float] = None


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
        self._series: Optional[Series] = None
        # Cuánto se ha avanzado hacia la muestra siguiente, de 0 a 1. Sirve
        # para que la línea se deslice en vez de dar un salto por segundo:
        # con el movimiento fluido apagado se queda en 1 y no se nota.
        self._phase = 1.0
        # La escala vertical que se está usando ahora mismo, que no siempre es
        # la que piden los datos: ver _escala_visible.
        self._escala: Optional[tuple[float, float]] = None
        # Lo que se dibuja, calculado una vez por muestra y por tamaño
        # (`_base`): con «Movimiento fluido», rehacer la curva en cada
        # fotograma para moverla una décima de píxel era la mitad de lo que
        # gastaba la ventana. `_version` cambia con cada dato.
        self._version = 0
        self._cache: Optional[tuple] = None
        self.setMinimumHeight(theme.METRICS.chart_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_range(self, floor: Optional[float], ceiling: Optional[float]) -> None:
        self._floor, self._ceiling = floor, ceiling
        self._version += 1

    def set_formatter(self, formatter, interval_s: float = 1.0) -> None:
        """Cómo escribir el valor que se lee bajo el cursor, y cada cuánto se
        toma una muestra, para poder decir hace cuánto ocurrió."""
        self._formatter = formatter
        self._interval_s = max(0.05, interval_s)
        self._version += 1

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
        # El paso lo marca la capacidad, no cuántas muestras hay todavía. Si
        # se reparte el ancho entre las que hay, cada muestra nueva estrecha
        # el paso y toda la curva se recoloca, a saltos, hasta que se llena.
        # Así se llena desde la derecha con el paso definitivo desde la
        # primera, sobre un eje que sí va de lado a lado (`_dibujar_eje`).
        capacidad = self._values.maxlen or max(1, len(self._values))
        paso = ancho / max(1, capacidad - 1)
        origen = (0.5 + ancho) - (len(self._values) - 1) * paso
        return origen, paso

    def _index_at(self, x: float) -> Optional[int]:
        if len(self._values) < 2 or self.width() <= 1:
            return None
        origen, paso = self._geometria()
        indice = round((x - origen) / paso)
        # Mientras la gráfica se llena, a la izquierda solo está el eje: ahí
        # no hay ninguna muestra que leer.
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

    def set_series(self, series: Series) -> None:
        """What it draws from now on. Another series starts it over."""
        if series != self._series:
            if self._series is not None:
                self.clear()
            self._series = series

    @property
    def series(self) -> Optional[Series]:
        return self._series

    def push(self, value: Optional[float]) -> None:
        """A point of its series. None (no datum) adds nothing, and a value
        that cannot be in its unit is not of it: it does not get in."""
        if value is None:
            return
        if self._series is None:
            raise TypeError("a chart takes the points of a declared series (set_series)")
        if not plausible(value, self._series.unit, self._series.ceiling):
            return
        if value is not None:
            self._values.append(float(value))
            self._version += 1
            self._phase = 0.0
            self.update()

    # Lo que tiene que moverse la curva para que valga la pena repintarla.
    # Un cuarto de píxel no se ve; repintar por él, en una gráfica estrecha
    # que avanza tres píxeles por segundo, eran treinta fotogramas para nada.
    PASO_VISIBLE_PX = 0.25

    def advance(self, phase: float) -> None:
        """Coloca la gráfica entre la muestra anterior y la siguiente.

        La llama un temporizador único de la ventana, no uno por gráfica: con
        cuarenta y tantas en pantalla, cuarenta temporizadores despertando por
        su cuenta cuestan más que lo que se dibuja.
        """
        nueva = max(0.0, min(1.0, phase))
        _origen, paso = self._geometria()
        if abs(nueva - self._phase) * paso < self.PASO_VISIBLE_PX and nueva < 1.0:
            return
        if nueva == self._phase:
            return
        self._phase = nueva
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self._escala = None
        self._version += 1
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

    def _base(self) -> Optional[dict]:
        """Lo que se dibuja, en su sitio de cuando llega la muestra.

        Se calcula una vez por muestra y por tamaño, no en cada fotograma: la
        curva, el área, el pico y dónde va su cifra. Mientras se desliza hacia
        la siguiente muestra, todo eso se dibuja corrido a la izquierda
        (`_desplazamiento`), que es moverlo, no rehacerlo. La escala también se
        decide aquí, una vez por muestra: así se estrecha al mismo ritmo con
        el movimiento fluido que sin él.
        """
        if len(self._values) < 2:
            return None
        clave = (self._version, self.width(), self.height())
        if self._cache is not None and self._cache[0] == clave:
            return self._cache[1]
        rect = self._recuadro()
        values = list(self._values)
        if self._cache is not None and self._cache[0][0] == self._version:
            low, high = self._cache[1]["escala"]       # el mismo dato, otro tamaño
        else:
            low, high = self._escala_visible(values)
        origen, step = self._geometria()

        def point(i: int, v: float) -> QPointF:
            y = rect.bottom() - (v - low) / (high - low) * rect.height()
            return QPointF(origen + i * step, max(rect.top(), min(rect.bottom(), y)))

        points = [point(i, v) for i, v in enumerate(values)]
        base = {"rect": rect, "points": points, "values": values, "escala": (low, high),
                "area": curva_suave(points, cerrar_en=rect.bottom()),
                "linea": curva_suave(points), "pico": self._pico(rect, points, values)}
        self._cache = (clave, base)
        return base

    def _desplazamiento(self) -> float:
        """Cuánto se ha corrido la curva hacia la muestra siguiente.

        Las muestras viejas se van hacia la izquierda y salen por ahí; la
        nueva ya está dibujada en el borde derecho. Al revés —empujando todo
        a la derecha— el relleno dejaba un hueco parpadeante en el borde
        izquierdo, que es el rebote que se veía.
        """
        return -self._phase * self._geometria()[1]

    def _trazado(self) -> Optional[tuple[QRectF, list, list]]:
        """El recuadro, los puntos de la curva tal como se ven y sus valores,
        o nada si no hay curva. Los mismos que se pintan, para quien coloca la
        cifra del pico y quien lo comprueba."""
        base = self._base()
        if base is None:
            return None
        dx = self._desplazamiento()
        return (base["rect"], [QPointF(p.x() + dx, p.y()) for p in base["points"]],
                base["values"])

    def _recuadro(self) -> QRectF:
        return QRectF(self.rect()).adjusted(0.5, 3.5, -0.5, -0.5)

    def _dibujar_eje(self, painter: QPainter, rect: QRectF) -> None:
        """La línea de base, de lado a lado, haya las muestras que haya.

        Recién abierta, una ficha tiene la curva en su esquina derecha y el
        resto en blanco: con el eje entero se ve que eso es una gráfica que se
        está llenando y no un hueco.
        """
        painter.setPen(QPen(self._p.q("muted", 0.35), 1.0))
        y = rect.bottom() - 0.5
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._dibujar_eje(painter, self._recuadro())

        base = self._base()
        if base is None:
            painter.end()
            return
        rect, points, values = base["rect"], base["points"], base["values"]
        if self._phase < 1.0:
            painter.setClipRect(self.rect())
        dx = self._desplazamiento()
        painter.translate(dx, 0)

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, self._p.q("accent", 0.28))
        gradient.setColorAt(1.0, self._p.q("accent", 0.02))
        painter.fillPath(base["area"], QBrush(gradient))

        painter.setPen(QPen(self._p.q("accent"), 1.6))
        painter.drawPath(base["linea"])

        painter.setBrush(QBrush(self._p.q("accent")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(points[-1], 2.6, 2.6)

        self._dibujar_pico(painter, points, base["pico"])

        if self._hover is not None and 0 <= self._hover < len(points):
            self._draw_hover(painter, rect, points[self._hover], values[self._hover])
        painter.end()

    # Cuánto tiene que despegarse el máximo de la media para que marcarlo
    # signifique algo. Sin este margen, una línea plana con una arruga de
    # medio grado sale con su punto y su cifra como si hubiera pasado algo.
    RELIEVE_MINIMO = 0.06

    def _pico(self, rect: QRectF, points: list, values: list) -> Optional[dict]:
        """El punto más alto del tramo que se está viendo, y dónde va su cifra.

        Se ve que la temperatura subió, pero no a cuánto llegó ni cuándo: para
        eso había que estar mirando en ese momento o pasar el ratón buscando a
        ciegas. Es el mismo dato que la columna «Máx» del árbol de sensores,
        puesto donde ocurrió.

        No se marca si el máximo es el último punto —ese ya lleva el suyo, y
        dos círculos juntos se leen como un error—, ni si la curva es
        prácticamente plana. Se decide con cada muestra (`_base`), no en cada
        fotograma: buscar sitio a la cifra recorre la curva entera.
        """
        indice = self._indice_del_pico()
        if indice is None:
            return None
        pico = {"indice": indice, "texto": None, "caja": None}
        if self._formatter is None:
            return pico
        texto = self._formatter(values[indice])
        letra = ui_font(max(7, theme.METRICS.small_pt - 2))
        # Enteras, como las del pintor: con las de coma flotante la caja
        # quedaba medio píxel corrida.
        metrica = QFontMetrics(letra)
        caja = self._sitio_de_la_cifra(rect, points, indice,
                                       metrica.horizontalAdvance(texto) + 6, metrica.height())
        # Sin sitio donde no tape la curva, no se pone: el punto hueco sigue
        # marcando dónde fue, y la cifra sale al pasar el ratón.
        if caja is not None:
            pico.update(texto=texto, caja=caja, letra=letra)
        return pico

    def _dibujar_pico(self, painter: QPainter, points: list, pico: Optional[dict]) -> None:
        if pico is None:
            return
        punto = points[pico["indice"]]
        painter.setPen(Qt.PenStyle.NoPen)
        # Hueco y no relleno: el punto lleno es «aquí estás ahora», y el pico
        # es otra cosa. Con los dos iguales habría que adivinar cuál es cuál.
        painter.setBrush(QBrush(self._p.q("surface")))
        painter.drawEllipse(punto, 3.0, 3.0)
        painter.setPen(QPen(self._p.q("accent", 0.75), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(punto, 3.0, 3.0)

        caja = pico["caja"]
        if caja is None:
            return
        # La cifra cae a veces sobre el relleno del área, y ahí un texto
        # suelto se pierde: en tema claro el gris sobre el azul aguado no se
        # lee. Lleva detrás el color del panel, igual que la etiqueta del
        # cursor.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._p.q("surface", 0.82)))
        painter.drawRoundedRect(caja, 3, 3)

        painter.setFont(pico["letra"])
        painter.setPen(self._p.q("ink_dim"))
        painter.drawText(caja, int(Qt.AlignmentFlag.AlignCenter), pico["texto"])

    # Lo que la cifra del pico se aparta de la línea, en píxeles.
    AIRE_DEL_PICO = 3.0
    # Y lo más lejos del punto que puede acabar: más allá ya no se lee como suya.
    ALCANCE_DEL_PICO = 48

    @staticmethod
    def _curva_entre(points: list, izquierda: float, derecha: float) -> tuple[float, float]:
        """Entre qué alturas pasa la curva en ese tramo horizontal.

        Por tramos rectos entre muestra y muestra: la curva suavizada se
        separa de ellos menos que el aire que se le deja a la cifra.
        """
        alturas = []
        for a, b in zip(points, points[1:]):
            if b.x() < izquierda or a.x() > derecha:
                continue
            for x in (max(a.x(), izquierda), min(b.x(), derecha)):
                t = (x - a.x()) / (b.x() - a.x()) if b.x() != a.x() else 0.0
                alturas.append(a.y() + (b.y() - a.y()) * t)
        if not alturas:
            return float("inf"), float("-inf")
        return min(alturas), max(alturas)

    def _sitio_de_la_cifra(self, rect: QRectF, points: list, indice: int,
                           ancho: float, alto: float) -> Optional[QRectF]:
        """Dónde cabe la cifra del pico sin montarse en la curva, o nada.

        Encima del punto es donde se lee mejor, pero un pico está por
        definición cerca del techo y ahí casi nunca cabe. Al lado, a su
        altura, solo vale si el pico es una aguja: en una meseta la línea
        sigue ahí y la cifra la tapaba. Así que se prueba cada sitio contra
        la curva de verdad, por este orden: encima, arriba a un lado, al lado,
        y debajo del pico, dentro del área. Si ninguno queda libre, no se pone.
        `dentro` no deja que se salga del cuadro: lo que hace es arrimarla.
        """
        punto = points[indice]
        aire = self.AIRE_DEL_PICO

        def dentro(x: float, y: float) -> Optional[QRectF]:
            x = min(max(x, rect.left()), rect.right() - ancho)
            if y < rect.top() or y + alto > rect.bottom():
                return None
            return QRectF(x, y, ancho, alto)

        def libre(caja: Optional[QRectF]) -> bool:
            if caja is None:
                return False
            arriba, abajo = self._curva_entre(points, caja.left() - aire, caja.right() + aire)
            # Toda por encima de la línea, o toda por debajo (sobre el área).
            return caja.bottom() + aire <= arriba or caja.top() - aire >= abajo

        candidatos = [dentro(punto.x() - ancho / 2, punto.y() - 5 - alto)]
        # Arriba y a un lado, cada vez un poco más lejos: junto a una aguja
        # la línea todavía está bajando.
        for lejos in range(6, self.ALCANCE_DEL_PICO, 4):
            candidatos += [dentro(punto.x() + lejos, rect.top()),
                           dentro(punto.x() - lejos - ancho, rect.top())]
        candidatos += [dentro(punto.x() + 6, punto.y() - alto / 2),
                       dentro(punto.x() - 6 - ancho, punto.y() - alto / 2),
                       dentro(punto.x() - ancho / 2, punto.y() + 6)]
        return next((caja for caja in candidatos if libre(caja)), None)

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


class _Cifra(QLabel):
    """La cifra de una ficha grande, con su unidad pintada detrás.

    La cifra va a la izquierda, como la etiqueta de debajo, y la unidad
    pegada a ella, en pequeño y en gris. Va pintada y no en otra etiqueta
    para que nada cambie de sitio cuando cambia la cifra: con dos etiquetas,
    o la unidad se movía a cada decena o se quedaba lejos, al otro lado del
    hueco reservado. `text()` es solo la cifra.
    """

    HUECO = 4

    def __init__(self) -> None:
        super().__init__("—")
        self._unidad = ""
        self._fuente_unidad = QFont()
        self._color_unidad = QColor()

    def set_unidad(self, unidad: str, fuente: QFont, color: QColor) -> None:
        self._unidad = unidad
        self._fuente_unidad = fuente
        self._color_unidad = color
        self.updateGeometry()
        self.update()

    # A word in place of the figure («en reposo»): it has no unit.
    palabra = False

    def _con_unidad(self) -> bool:
        return bool(self._unidad) and self.text() != render.DASH and not self.palabra

    def ancho_de_la_unidad(self) -> int:
        if not self._unidad:
            return 0
        return self.HUECO + QFontMetrics(self._fuente_unidad).horizontalAdvance(self._unidad)

    def sizeHint(self) -> QSize:  # noqa: N802
        base = super().sizeHint()
        if self._con_unidad():
            base.setWidth(base.width() + self.ancho_de_la_unidad())
        return base

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        base = super().minimumSizeHint()
        if self._con_unidad():
            base.setWidth(base.width() + self.ancho_de_la_unidad())
        return base

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._con_unidad():
            super().paintEvent(event)
            return
        pintor = QPainter(self)
        try:
            medida = QFontMetrics(self.font())
            caja = self.contentsRect()
            linea = caja.top() + (caja.height() - medida.height()) // 2 + medida.ascent()
            pintor.setFont(self.font())
            pintor.setPen(self.palette().color(self.foregroundRole()))
            pintor.drawText(caja.left(), linea, self.text())
            x = caja.left() + medida.horizontalAdvance(self.text()) + self.HUECO
            pintor.setFont(self._fuente_unidad)
            pintor.setPen(self._color_unidad)
            pintor.drawText(x, linea, self._unidad)
        finally:
            pintor.end()


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

        self.value = _Cifra()
        self.value.setObjectName("TileValue")
        self.value.setFont(value_font(theme.METRICS.tile_value_pt, bold=True))
        self.value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # La unidad la pinta la cifra (`_Cifra`). Esta etiqueta no se enseña:
        # guarda el texto, y su letra y su color salen de la hoja de estilo.
        self.unit = QLabel(unit, self)
        self.unit.setObjectName("TileUnit")
        self.unit.hide()
        self._paleta = palette
        self._reservados: tuple[str, ...] = ()

        # El candado de cuando la cifra falta por permisos: a tamaño de
        # cifra, en el sitio de la cifra.
        self.lock = LockMark(palette.info, theme.METRICS.tile_value_pt)
        self.lock.hacer_pulsable()
        self.lock.clicked.connect(self.locked_clicked)
        self.lock.hide()

        row.addWidget(self.lock)
        row.addWidget(self.value)
        row.addStretch(1)
        self._pasar_unidad()

        self.caption = QLabel(label)
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
            self._pasar_unidad()
            if self._reservados:
                self.reserve(self._reservados)

    def _pasar_unidad(self) -> None:
        """La unidad, con la letra y el color que le da la hoja de estilo
        (`QLabel#TileUnit`), a la cifra que la pinta."""
        self.unit.ensurePolished()
        # Con el peso de la letra normal a mano: la cifra va en negrita y el
        # pintor se lo pasaba a la unidad.
        fuente = QFont(self.unit.font())
        fuente.setWeight(QFont.Weight.Normal)
        self.value.set_unidad(self.unit.text(), fuente,
                              self.unit.palette().color(self.unit.foregroundRole()))

    def reserve(self, texts: Iterable[str]) -> None:
        """Reserva para la cifra el ancho de la más larga de `texts`, lo más
        largo que puede llegar a decir, y el de su unidad.

        Sin reserva, la cifra medía lo que su texto: de «9» a «10» se
        ensanchaba y lo de al lado saltaba diecisiete píxeles cada vez que el
        uso cruzaba una decena. Se mide con la letra de la cifra y no con la
        de la etiqueta, que con un guion es la pequeña.
        """
        self._reservados = tuple(texts)
        metricas = QFontMetrics(value_font(theme.METRICS.tile_value_pt, bold=True))
        ancho = max((metricas.size(0, t).width() for t in self._reservados), default=0)
        ancho += self.value.ancho_de_la_unidad()
        if self.value.minimumWidth() != ancho:
            self.value.setMinimumWidth(ancho)

    def set_label(self, label: str) -> None:
        """Cambia el nombre del recuadro.

        Casi ninguno lo necesita, pero hay uno que mide dos cosas distintas
        según el estado: en una batería, lo que queda de autonomía y lo que
        falta para llenarse no son la misma cifra ni se llaman igual.
        """
        texto = label
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
        self.lock.setToolTip(tooltip)
        self.lock.show()
        self.set_detail(detalle)

    def is_locked(self) -> bool:
        return not self.lock.isHidden()

    def figure_text(self) -> str:
        """The figure as it reads: with its unit only where it is painted."""
        cifra = self.value.text()
        return f"{cifra} {self.unit.text()}" if cifra and self.value._con_unidad() else cifra

    def update_value(self, text: str, series_value: Optional[float] = None,
                     word: bool = False, series: Optional[Series] = None) -> None:
        """`word` is a state instead of a figure («en reposo»): grey and
        without its unit. `series` is what `series_value` is a point of: a
        chart takes no point without it."""
        if series is not None:
            self.chart.set_series(series)
        if not self.lock.isHidden():
            self.lock.hide()
            self.value.show()
        if self.value.text() != text or self.value.palabra != word:
            self.value.palabra = word
            self.value.setText(text)
            # El guion de «sin dato» a treinta y seis píxeles es una raya
            # gruesa que no se lee como un guion: en una Intel, con cuatro de
            # los seis cuadros vacíos, la fila parecía tachada. Se pinta al
            # cuerpo del texto pequeño y en el gris de lo apagado, que es lo
            # que ya dice «aquí no hay nada» en el resto del programa.
            vacio = text == render.DASH
            self.value.setFont(
                ui_font(theme.METRICS.small_pt) if vacio
                else value_font(theme.METRICS.tile_value_pt, bold=True))
            # A state keeps the figure's size, in the grey of what is off.
            self.value.setObjectName("Muted" if vacio or word else "TileValue")
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
        self._tooltips: list[str] = []
        self._widgets: list[Badge] = []
        self._laid_width = 0
        # El ancho mínimo lo marca la insignia más ancha, no la fila entera:
        # si no, una lista larga impide encoger la ventana.
        self.setMinimumWidth(64)

    def set_chips(self, labels: Iterable[str], highlight_first: bool = False,
                  swatches: Optional[Sequence] = None,
                  tooltips: Optional[Sequence[str]] = None) -> None:
        """Pone las insignias. `swatches`: un (color, borde) por insignia, o
        nada; es lo que convierte la fila en la leyenda de una barra.
        `tooltips`: what each one is, on hover ("" for none)."""
        chips = [(str(text), highlight_first and i == 0)
                 for i, text in enumerate(labels)]
        self._swatches = list(swatches) if swatches is not None else []
        self._tooltips = list(tooltips) if tooltips is not None else []

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
            ayuda = self._tooltips[indice] if indice < len(self._tooltips) else ""
            if widget.toolTip() != ayuda:
                widget.setToolTip(ayuda)

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
    Need.ROOT: "action",
    Need.DRIVER: "action",
    Need.DATABASE: "action",
    Need.HARDWARE: "idle",
    # Fixable: installing a package.
    Need.PACKAGE: "action",
    Need.PLATFORM: "idle",
    Need.ERROR: "bad",
    # Tiene arreglo, pero no desde aquí: actualizar el kernel.
    Need.KERNEL: "idle",
}


def tone_for(need) -> str:
    """El color de la banda de un aviso, según se pueda hacer algo o no."""
    return NEED_TONES.get(need, "action")


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
        self.setProperty("tone", "action")
        self._p = palette
        self._compact = compact
        self._nombres: tuple[str, ...] = ()
        self._recaida = False
        self._outdated = False
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

    def set_missing(self, nombres: Sequence[str], recaida: bool = False,
                    outdated: bool = False) -> None:
        """Pone lo que falta. `recaida`: se tenía y ha dejado de leerse.
        `outdated`: the installed helper is from another version, and what
        brings it back is updating it, not giving permissions."""
        nombres = tuple(nombres)
        if (nombres, recaida, outdated) == (self._nombres, self._recaida, self._outdated):
            return
        self._nombres, self._recaida, self._outdated = nombres, recaida, outdated
        self.grant_button.setText(_("perm.replace.button") if outdated else _("perm.notice.grant"))
        self.explain_button.setVisible(not outdated)
        self.dismiss_button.setVisible(not outdated)
        n = len(nombres)
        if outdated:
            clave = "perm.outdated.home"
        elif recaida:
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
            fila.addWidget(LockMark(self._p.info, theme.METRICS.small_pt + 2))
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
                                  else _("perm.replace.button") if self._outdated
                                  else _("perm.notice.grant"))


def boton_de_permiso_permanente() -> QPushButton:
    """El botón que sustituye un ayudante instalado que se quedó atrás.

    Sale al lado del de elevar y solo cuando hace falta: la ventana lo
    esconde si no hay nada que actualizar. Instalarlo por primera vez se
    ofrece en «Qué hace esto».
    """
    boton = QPushButton(_("perm.replace.button"))
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


class _CuerpoDeTabla(QWidget):
    """El interior de una `Table`, con la raya que separa la cabecera.

    La raya es una sola, de lado a lado, y va en mitad del hueco entre los
    títulos y la primera fila. No es un borde de cada título: la rejilla deja
    aire entre columnas y saldría a trozos. Tampoco ocupa una fila de la
    rejilla, que alejaría la cabecera de sus datos; se coloca encima, cada vez
    que la rejilla se recoloca.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TableBody")
        self.raya = QFrame(self)
        self.raya.setObjectName("TableRule")
        self.raya.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._cabecera: Optional[QLabel] = None

    def set_cabecera(self, etiqueta: QLabel) -> None:
        self._cabecera = etiqueta
        self._colocar()

    def _colocar(self) -> None:
        if self._cabecera is None or self.layout() is None:
            return
        hueco = self.layout().verticalSpacing()
        y = self._cabecera.geometry().bottom() + 1 + max(0, (hueco - 1) // 2)
        self.raya.setGeometry(0, y, self.width(), 1)
        self.raya.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._colocar()

    def event(self, event) -> bool:  # noqa: N802
        resultado = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest:
            self._colocar()
        return resultado


class ScrollPage(QScrollArea):
    """A page of the window: a scroll area that stays where the user left it."""

    def focusNextPrevChild(self, next_: bool) -> bool:  # noqa: N802
        from PySide6.QtWidgets import QApplication

        focused = QApplication.focusWidget()
        if focused is not None and not focused.isEnabled():
            # A button that disables itself while it has the focus («Buscar
            # ahora», «Dar permisos»): Qt would hand the focus on, and the
            # scroll area would scroll to wherever it landed. Nobody gets it.
            return False
        return super().focusNextPrevChild(next_)


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

    # Alguien ha pulsado el candado de una celda: quiere los permisos.
    locked_clicked = Signal()

    def __init__(self, headers: Sequence[str], numeric: Sequence[bool] = (),
                 parent: Optional[QWidget] = None, cede: Sequence[int] = ()):
        """`cede`: las columnas de texto que pueden salir recortadas, con
        puntos suspensivos, cuando la tabla no cabe (`_encajar`)."""
        super().__init__(parent)
        self._headers = list(headers)
        # (fila, columna) → su candado, para las celdas que lo han tenido.
        self._candados: dict[tuple[int, int], "LockMark"] = {}
        self._cede = tuple(cede)
        self._numeric = list(numeric) + [False] * (len(headers) - len(numeric))

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Con nombre propio y sin fondo: con el de la página («Root»), que es
        # más oscuro que la tarjeta, cada tabla era un bloque negro dentro de
        # la suya.
        inner = _CuerpoDeTabla()
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
            if column == 0:
                inner.set_cabecera(label)

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

    def set_cell_tone(self, fila: int, columna: int, tono: str) -> None:
        """El tono de una celda: «yes», «no» o ninguno.

        Para un sí o un no que se lee de un vistazo. El color lo pone la hoja
        de estilos; el símbolo lo pone quien llama, porque el color solo no
        puede ser lo único que distinga una cosa de la otra.
        """
        if fila < len(self._cells) and columna < len(self._cells[fila]):
            celda = self._cells[fila][columna]
            if (celda.property("tone") or "") != tono:
                celda.setProperty("tone", tono)
                # Un símbolo suelto en la letra de las cifras es un trazo fino
                # que se pierde: va en la de la interfaz, más grande y gruesa.
                celda.setFont(ui_font(theme.METRICS.base_pt + 2, QFont.Weight.Bold)
                              if tono else value_font())
                celda.setMinimumHeight(celda.fontMetrics().height())
                celda.style().unpolish(celda)
                celda.style().polish(celda)
                # Con otra letra la fila mide otra cosa.
                self._fit_height()

    def set_cell_locked(self, fila: int, columna: int, color: str, tooltip: str = "") -> None:
        """La celda falta por permisos: candado en su sitio, como en
        `InfoGrid.set_locked`. Dura hasta el siguiente `set_rows`, que es
        cuando quien la monta vuelve a decidir con la foto nueva."""
        if not (fila < len(self._cells) and columna < len(self._cells[fila])):
            return
        celda = self._cells[fila][columna]
        candado = self._candados.get((fila, columna))
        if candado is None:
            candado = LockMark(color, max(10, celda.fontMetrics().ascent()))
            candado.hacer_pulsable()
            candado.clicked.connect(self.locked_clicked)
            lado = (Qt.AlignmentFlag.AlignRight if self._numeric[columna]
                    else Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(candado, fila + 1, columna, lado | Qt.AlignmentFlag.AlignVCenter)
            self._candados[(fila, columna)] = candado
        candado.setToolTip(tooltip)
        candado.show()
        celda.set_full_text("")
        celda.hide()

    def is_cell_locked(self, fila: int, columna: int) -> bool:
        candado = self._candados.get((fila, columna))
        return candado is not None and not candado.isHidden()

    def _quitar_candados(self, salvo=()) -> None:
        """Quita los candados de las celdas que ya no lo llevan.

        Los que siguen (`salvo`) no se tocan: quitarlo y volverlo a poner en
        la misma muestra recolocaba la tabla entera cada segundo.
        """
        for (fila, columna), candado in self._candados.items():
            if (fila, columna) in salvo or candado.isHidden():
                continue
            candado.hide()
            if fila < len(self._cells) and columna < len(self._cells[fila]):
                self._cells[fila][columna].show()

    def set_cell_tooltip(self, fila: int, columna: int, texto: str) -> None:
        """La explicación de una celda concreta: por qué lleva un guion."""
        if fila < len(self._cells) and columna < len(self._cells[fila]):
            celda = self._cells[fila][columna]
            if celda.toolTip() != texto and (texto or celda.toolTip() != celda.full_text()):
                celda.setToolTip(texto)

    def set_rows(self, rows: Sequence[Sequence[str]], tooltips: Sequence[str] = (),
                 locked: Optional[dict[tuple[int, int], tuple[str, str]]] = None) -> None:
        """`locked`: las celdas que faltan por permisos, (fila, columna) →
        (color, globo). Llevan candado en vez de su texto, y las que lo
        llevaban y ya no están ahí lo pierden."""
        locked = locked or {}
        # Todas las filas, con tantas celdas como columnas. Una fila corta
        # («ningún monitor conectado» traía seis valores para siete columnas)
        # dejaba en la última celda el dato de la fila anterior, y al volver
        # la fila entera se salía de las celdas que había.
        columnas = len(self._headers)
        rows = [(list(fila) + [""] * columnas)[:columnas] for fila in rows]
        # Mientras la tabla tenga la misma forma se reescriben las celdas que
        # ya están. Rehacerlas en cada muestreo dejaba miles de etiquetas vivas.
        if len(rows) == self._rows and self._cells:
            self._quitar_candados(salvo=locked)
            for index, values in enumerate(rows):
                tip = tooltips[index] if index < len(tooltips) else ""
                for column, value in enumerate(values):
                    if (index, column) in locked:
                        continue
                    cell = self._cells[index][column]
                    cell.set_full_text(str(value))
                    if tip:
                        cell.setToolTip(tip)
            self._poner_candados(locked)
            self._ajustar_anchos(rows)
            return

        while self._grid.count() > len(self._headers):
            item = self._grid.takeAt(self._grid.count() - 1)
            if (widget := item.widget()) is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cells.clear()
        # Los candados iban en la rejilla y se han ido con ella.
        self._candados.clear()

        for index, values in enumerate(rows):
            fila: list[ElidingLabel] = []
            tip = tooltips[index] if index < len(tooltips) else ""
            for column, value in enumerate(values):
                label = ElidingLabel(str(value))
                label.setObjectName("FieldValue" if column == 0 else "FieldName")
                label.setFont(value_font() if column else ui_font(theme.METRICS.small_pt))
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
        self._poner_candados(locked)
        self._ajustar_anchos(rows)
        self._fit_height()

    def _poner_candados(self, locked: dict[tuple[int, int], tuple[str, str]]) -> None:
        for (fila, columna), (color, globo) in locked.items():
            self.set_cell_locked(fila, columna, color, globo)

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
            # Con decimales y redondeando hacia arriba. `QFontMetrics` da el
            # avance en píxeles enteros, hacia abajo, y quien decide si el
            # texto cabe trabaja con el de verdad: «2560 × 1440» medía 79 y
            # ocupaba 79 y pico, la columna salía a 79 y la celda lo cortaba,
            # «2560 × 14…», con sitio de sobra en la tabla.
            metricas = QFontMetricsF(celda.font())
            ancho = max(
                (math.ceil(metricas.horizontalAdvance(str(fila[columna]))) + 1
                 for fila in rows if columna < len(fila)),
                default=0,
            )
            ancho = min(ancho, tope)
            if ancho > self._anchos[columna]:
                self._anchos[columna] = ancho
        self._encajar()

    def _encajar(self) -> None:
        """Reparte los anchos; si la tabla no cabe, cede el texto más largo.

        En compacto a 900 px la tabla de unidades pedía más de lo que hay y
        su última columna, «Escribiendo», quedaba cortada contra el borde, a
        un desplazamiento que nadie hace. Lo que sobra se le quita a las
        columnas que quien monta la tabla dijo que pueden ceder (un modelo de
        disco, un nombre de monitor), de la más ancha a la menos: salen con
        puntos suspensivos y enteras al pasar el ratón. Las demás no se
        tocan. Si ni así cabe, o ninguna cede, queda la barra de
        desplazamiento.
        """
        if not self._cells:
            return
        columnas = len(self._headers)
        anchos = list(self._anchos)
        hueco = self._grid.horizontalSpacing() * (columnas - 1)
        # Lo que ocupa cada columna es su dato o su título, lo que más pida.
        ocupa = sum(max(ancho, self._ancho_de_cabecera(c)) for c, ancho in enumerate(anchos))
        sobra = ocupa + hueco - self.viewport().width()
        if sobra < 0 and self.viewport().width() > 0:
            # Con sitio de sobra, las columnas se separan: en una ventana
            # grande la tabla se quedaba en el tercio izquierdo de su tarjeta.
            # Con tope, porque separadas sin límite la cifra acaba a un palmo
            # del nombre con el que hay que compararla; lo que aún sobre
            # sigue yendo detrás de la última.
            tope = QFontMetrics(value_font()).averageCharWidth() * self.HOLGURA_MAXIMA
            holgura = min(-sobra // columnas, tope)
            anchos = [max(ancho, self._ancho_de_cabecera(c)) + holgura
                      for c, ancho in enumerate(anchos)]
        if sobra > 0 and self.viewport().width() > 0:
            suelo = QFontMetrics(value_font()).averageCharWidth() * 10
            suelos = {c: max(suelo, self._ancho_de_cabecera(c))
                      for c in self._cede if c < columnas}
            while sobra > 0:
                cedibles = [c for c, minimo in suelos.items() if anchos[c] > minimo]
                if not cedibles:
                    break
                ancha = max(cedibles, key=lambda c: anchos[c])
                quita = min(sobra, anchos[ancha] - suelos[ancha], 8)
                anchos[ancha] -= quita
                sobra -= quita
        for columna, ancho in enumerate(anchos):
            if self._grid.columnMinimumWidth(columna) != ancho:
                self._grid.setColumnMinimumWidth(columna, ancho)
            recortada = ancho < max(self._anchos[columna], 1) and columna in self._cede
            for fila in self._cells:
                if columna < len(fila):
                    # Cedida, la celda no puede pedir más que su columna.
                    fila[columna].setMaximumWidth(ancho if recortada else 16777215)

    # Cuánto puede separarse como mucho cada columna, en anchos de letra.
    HOLGURA_MAXIMA = 14

    def _ancho_de_cabecera(self, columna: int) -> int:
        item = self._grid.itemAtPosition(0, columna)
        return item.widget().sizeHint().width() if item and item.widget() else 0

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._encajar()

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
            QFontMetrics(value_font()).height(),
            QFontMetrics(ui_font(theme.METRICS.small_pt)).height(),
        ) + 2
        # Cada fila, con la letra que llevan de verdad sus celdas: un «✓» o un
        # «✗» (`set_cell_tone`) va en una mayor que las cifras, y medida con
        # la de las cifras la tabla de códecs se quedaba corta y lo que
        # sobraba se desplazaba dentro, con la cabecera fuera de la vista.
        filas = sum(max([line] + [max(c.minimumHeight(), c.fontMetrics().height()) + 2
                                  for c in fila])
                    for fila in self._cells[:self._rows])
        filas += line * max(0, self._rows - len(self._cells))
        rows = self._rows + 1                       # las filas más la cabecera
        spacing = self._grid.verticalSpacing()
        extra = self.horizontalScrollBar().sizeHint().height() + 4
        alto = line + filas + max(0, rows - 1) * spacing + extra
        if self.height() != alto or self.minimumHeight() != alto:
            self.setFixedHeight(alto)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_height()














class Deslizador:
    """El largo que se ve de una barra, que llega al dato nuevo en un momento.

    Con «Movimiento fluido» encendido (`Deslizador.fluido`, lo pone la
    ventana), una barra no salta al dato nuevo: sale del largo que se ve en
    ese instante y llega en `DURACION` segundos, frenando al final. Un dato
    que llega a media animación sale de donde esté la barra entonces. Apagado,
    el dato nuevo se pinta en el acto. Solo el largo: la cifra de al lado
    salta al dato real, que es lo que se lee.

    Va por el reloj y no por la fase del muestreo, que es lo que mueve las
    gráficas: con la fase tardaría el intervalo entero en llegar e iría
    siempre por detrás de su cifra. Y con el reloj, lo que se ve en cada
    momento no depende de que alguien la haya ido avanzando: una barra de
    una página cerrada, que nadie avanza, está en su sitio al abrirla.

    El primer dato y el que llega a una barra que no está a la vista se
    ponen en su sitio sin animar: no hay de dónde venir que se haya visto.
    """

    fluido = False
    # Lo justo para que el ojo siga el cambio sin quedarse esperándolo.
    DURACION = 0.18
    reloj = staticmethod(time.monotonic)

    def __init__(self, valor: Optional[float] = None) -> None:
        self._desde = self._hasta = 0.0 if valor is None else float(valor)
        self._puesto = valor is not None
        # Cuándo empezó la animación en curso; None si está quieta.
        self._inicio: Optional[float] = None

    def fijar(self, nuevo: float, animar: bool = True) -> bool:
        """Pone el dato nuevo; dice si cambió algo que haya que repintar.

        `animar` lo decide la barra: falso si no está a la vista."""
        nuevo = float(nuevo)
        if self._puesto and abs(nuevo - self._hasta) < 1e-6:
            return False
        if Deslizador.fluido and animar and self._puesto:
            ahora = self.reloj()
            self._desde = self.valor(ahora)
            self._inicio = ahora
        else:
            self._desde = nuevo
            self._inicio = None
        self._hasta = nuevo
        self._puesto = True
        return True

    def valor(self, ahora: Optional[float] = None) -> float:
        if self._inicio is None:
            return self._hasta
        ahora = self.reloj() if ahora is None else ahora
        recorrido = (ahora - self._inicio) / self.DURACION
        if recorrido >= 1.0:
            return self._hasta
        # Frenando al final (cúbica): casi todo el camino se hace en el
        # primer tercio, que es lo que lo hace parecer inmediato.
        hecho = 1.0 - (1.0 - max(0.0, recorrido)) ** 3
        return self._desde + (self._hasta - self._desde) * hecho

    def avanzar(self) -> bool:
        """Dice si la barra tiene que repintarse en este fotograma: mientras
        se mueve, y una vez más al llegar, para pintarla en su sitio."""
        if self._inicio is None:
            return False
        # Con su margen: una resta de segundos en coma flotante se queda a
        # una millonésima de la duración y la barra pediría un fotograma más.
        if self.reloj() - self._inicio >= self.DURACION - 1e-6:
            self.terminar()
        return True

    def terminar(self) -> None:
        """La lleva a su sitio sin esperar a que acabe la animación."""
        self._desde, self._inicio = self._hasta, None

    def moviendose(self) -> bool:
        return self._inicio is not None

    def destino(self) -> float:
        return self._hasta


class LevelBar(QWidget):
    """Una barra de un solo tramo: cuánto de un total, sin leyenda."""

    HEIGHT = 8

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._fraccion = Deslizador()
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def fraction(self) -> float:
        """El dato, no lo que se ve a media animación."""
        return self._fraccion.destino()

    def shown_fraction(self) -> float:
        return self._fraccion.valor()

    def set_fraction(self, fraccion: float) -> None:
        fraccion = max(0.0, min(1.0, fraccion))
        if self._fraccion.fijar(fraccion, animar=self.isVisible()):
            self.update()

    def advance(self, phase: float) -> bool:
        """Un fotograma; dice si sigue moviéndose.

        La barra va por el reloj (`Deslizador`), no por la fase. La fase a 1
        es lo que pide la ventana al parar el movimiento: entonces se pone en
        su sitio, sin quedarse a medio camino hasta la muestra siguiente.
        """
        if phase >= 1.0 and self._fraccion.moviendose():
            self._fraccion.terminar()
            self.update()
        elif self._fraccion.avanzar():
            self.update()
        return self._fraccion.moviendose()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        camino = QPainterPath()
        camino.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setClipPath(camino)
        painter.setBrush(QBrush(self._p.q("line")))
        painter.drawRect(rect)
        painter.setBrush(QBrush(self._p.q("accent")))
        painter.drawRect(QRectF(0, 0, rect.width() * self._fraccion.valor(), rect.height()))
        painter.end()


class LevelList(QWidget):
    """Varias medidas de «tanto de tanto», una por renglón.

    Cada una con su nombre a la izquierda, su barra, y a la derecha la cifra
    y el porcentaje: se sabe qué es cada barra sin buscar una leyenda. Los
    renglones se crean una vez y se reescriben, como en `InfoGrid`; el que no
    tiene dato se esconde entero, y el que lo tiene guardado por un permiso
    lleva un candado en el sitio de la cifra (`set_locked`).
    """

    locked_clicked = Signal()

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._candados: dict[str, "LockMark"] = {}
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(theme.METRICS.grid_hspace)
        self._grid.setVerticalSpacing(theme.METRICS.grid_vspace + 1)
        self._grid.setColumnStretch(1, 1)
        self._rows: dict[str, tuple] = {}

    def add(self, name: str) -> None:
        fila = len(self._rows)
        nombre = QLabel(name)
        nombre.setObjectName("FieldName")
        barra = LevelBar(self._p)
        cifra = QLabel("")
        cifra.setObjectName("FieldValue")
        cifra.setFont(value_font())
        porcentaje = QLabel("")
        porcentaje.setObjectName("FieldValue")
        porcentaje.setFont(value_font(bold=True))
        for etiqueta in (cifra, porcentaje):
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # El hueco del «100 %» reservado: sin él la columna bailaba al pasar
        # de una cifra a dos.
        porcentaje.setMinimumWidth(self._ancho_de(porcentaje, "100 %"))
        for columna, widget in enumerate((nombre, barra, cifra, porcentaje)):
            self._grid.addWidget(widget, fila, columna)
        self._rows[name] = (nombre, barra, cifra, porcentaje)

    def set(self, name: str, fraction: Optional[float], text: str = "",
            tooltip: str = "") -> None:
        """Pone un renglón, o lo esconde si `fraction` es None."""
        fila = self._rows.get(name)
        if fila is None:
            return
        if (candado := self._candados.get(name)) is not None:
            candado.hide()
        nombre, barra, cifra, porcentaje = fila
        if fraction is None:
            for widget in fila:
                widget.hide()
            return
        # Antes de enseñar el renglón: si estaba escondido, la barra se pone
        # en su sitio en vez de deslizarse desde un dato que ya no se veía.
        barra.set_fraction(fraction)
        for widget in fila:
            widget.show()
        if cifra.text() != text:
            cifra.setText(text)
        pct = f"{fraction * 100:.0f} %"
        if porcentaje.text() != pct:
            porcentaje.setText(pct)
        if nombre.toolTip() != tooltip:
            nombre.setToolTip(tooltip)

    def reserve(self, name: str, texts: Iterable[str]) -> None:
        """Reserva para la cifra de ese renglón el ancho del más largo de
        `texts`, lo más largo que puede llegar a decir.

        La columna de las cifras es una para todos los renglones y mide lo
        que mida su texto más ancho: sin reserva, «97 GB/s de 644 GB/s»
        frente a «116 GB/s de 644 GB/s» cambiaba su ancho, y con él el largo
        del fondo de todas las barras. Las cifras son tabulares
        (`value_font`), así que el texto más largo es el más ancho.
        """
        fila = self._rows.get(name)
        if fila is None:
            return
        cifra = fila[2]
        ancho = max((self._ancho_de(cifra, t) for t in texts), default=0)
        if cifra.minimumWidth() != ancho:
            cifra.setMinimumWidth(ancho)

    @staticmethod
    def _ancho_de(etiqueta: QLabel, texto: str) -> int:
        """Lo que pide la etiqueta para ese texto, medido como lo mide ella:
        `horizontalAdvance` se queda a veces un píxel corto, y ese píxel
        movía la columna."""
        return etiqueta.fontMetrics().size(0, texto).width()

    def has(self, name: str) -> bool:
        return name in self._rows

    def set_locked(self, name: str, color: str, tooltip: str = "") -> None:
        """El renglón está, y su cifra la guarda un permiso: el nombre, la
        barra vacía y un candado donde iría el porcentaje. Pulsarlo los pide.
        Dura hasta el siguiente `set` de ese renglón."""
        fila = self._rows.get(name)
        if fila is None:
            return
        nombre, barra, cifra, porcentaje = fila
        candado = self._candados.get(name)
        if candado is None:
            candado = LockMark(color, max(10, porcentaje.fontMetrics().ascent()))
            candado.hacer_pulsable()
            candado.clicked.connect(self.locked_clicked)
            indice = self._grid.indexOf(porcentaje)
            fila_grid = self._grid.getItemPosition(indice)[0]
            self._grid.addWidget(candado, fila_grid, 3,
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._candados[name] = candado
        nombre.show()
        barra.set_fraction(0.0)
        barra.show()
        cifra.hide()
        porcentaje.hide()
        candado.setToolTip(tooltip)
        candado.show()

    def is_locked(self, name: str) -> bool:
        candado = self._candados.get(name)
        return candado is not None and not candado.isHidden()

    def visible_rows(self) -> list[str]:
        return [name for name, fila in self._rows.items() if not fila[0].isHidden()]

    def text_of(self, name: str) -> str:
        """Lo que se lee en un renglón: «2.6 GB de 15.9 GB · 16 %»."""
        _nombre, _barra, cifra, porcentaje = self._rows[name]
        return " · ".join(t for t in (cifra.text(), porcentaje.text()) if t)


def memory_segments(memory) -> list[render.Segment]:
    """Los tramos de la barra de memoria: lo mismo en Inicio, Memoria y Sistema.

    Los tres más el hueco del fondo suman el total, por eso van las
    aplicaciones y no «en uso»: lo segundo incluye caché que no se devuelve y
    haría que la barra se pasara. La caché va con su color y no con el del
    fondo: en Inicio iba con el de la línea, que es el de la barra vacía, y no
    se distinguía de lo libre.

    Los tres son tonos del acento, de más a menos lleno: lo que ocupan los
    programas, lo que se devuelve si hace falta y lo que casi no cuenta. Con
    el azul y el amarillo de los estados, una barra de memoria parecía llevar
    un aviso dentro.
    """
    return [
        render.Segment("apps", _("sys.mem.apps"), memory.apps_bytes, "accent"),
        render.Segment("cache", _("sys.mem.cache"), memory.cache_bytes, "accent/0.5"),
        render.Segment("buffers", _("sys.mem.buffers"), memory.buffers_bytes, "accent/0.25"),
        render.Segment("free", _("sys.mem.free"), memory.free_bytes, "line"),
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
        self._segments: list[render.Segment] = []
        self._total = 0.0
        # El largo que se ve de cada tramo, por su clave: se desliza
        # (`Deslizador`); la leyenda dice siempre el dato. Se crean una vez
        # por tramo y se reutilizan en cada muestra.
        self._largos: dict[str, Deslizador] = {}
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

    def set_segments(self, segments: list[render.Segment], total: float,
                     formatter=None, hover=None) -> None:
        """`hover`: the same value in other units, on each chip's tooltip
        (a disk's GiB under its GB)."""
        self._segments = list(segments)
        self._total = total or 1.0
        a_la_vista = self.isVisible()
        for tramo in self._segments:
            fraccion = max(0.0, tramo.value) / self._total
            if tramo.key not in self._largos:
                self._largos[tramo.key] = Deslizador(fraccion)
            else:
                self._largos[tramo.key].fijar(fraccion, animar=a_la_vista)
        if formatter is not None:
            self._formatter = formatter
        visibles = [s for s in self._segments if s.value > 0]
        borde = self._p.q("muted", 0.6)
        self._legend.set_chips(
            (f"{s.label}  {self._formatter(s.value)}" for s in visibles),
            swatches=[(self._color(s.token), borde) for s in visibles],
            tooltips=["\n\n".join(t for t in (hover(s.value) if hover else "", s.tooltip) if t)
                      for s in visibles],
        )
        self._reservar_alto()
        self._repintar_la_barra()

    def _repintar_la_barra(self) -> None:
        """Solo la franja de la barra. La leyenda va debajo, dentro de este
        mismo widget, y repintarlo entero repintaba también sus insignias en
        cada fotograma de la animación: casi cien por segundo en Inicio. Sus
        textos ya se repintan solos cuando cambian."""
        self.update(0, 0, self.width(), self.BAR_HEIGHT)

    def advance(self, phase: float) -> bool:
        """Un fotograma; dice si algún tramo sigue moviéndose (`LevelBar.advance`)."""
        if phase >= 1.0 and any(d.moviendose() for d in self._largos.values()):
            for largo in self._largos.values():
                largo.terminar()
            self._repintar_la_barra()
        elif any([d.avanzar() for d in self._largos.values()]):
            self._repintar_la_barra()
        return any(d.moviendose() for d in self._largos.values())

    def _color(self, token: str) -> QColor:
        """El color de un tramo: uno de la paleta, o un tono suyo.

        «accent/0.5» es el acento a medias con el fondo de la tarjeta. Mezclado
        y no translúcido, para que el cuadradito de la leyenda —que va sobre
        otro fondo— sea exactamente el de la barra.
        """
        nombre, _barra, cuanto = token.partition("/")
        color = self._p.q(nombre)
        if not cuanto:
            return color
        fondo, peso = self._p.q("surface"), float(cuanto)
        return QColor(*(round(f + (c - f) * peso) for c, f in (
            (color.red(), fondo.red()), (color.green(), fondo.green()),
            (color.blue(), fondo.blue()))))

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

    def _tramo_en(self, x: float) -> Optional[render.Segment]:
        """The segment drawn at that x, as paintEvent lays them."""
        offset = 0.0
        for tramo in self._segments:
            largo = self._largos.get(tramo.key)
            fraccion = largo.valor() if largo is not None else tramo.value / self._total
            if fraccion <= 0:
                continue
            offset += self.width() * fraccion
            if x < offset:
                return tramo
        return None

    def event(self, evento) -> bool:  # noqa: N802
        if evento.type() == QEvent.Type.ToolTip and evento.pos().y() <= self.BAR_HEIGHT:
            tramo = self._tramo_en(evento.pos().x())
            ayuda = tramo.tooltip if tramo else ""
            if ayuda:
                QToolTip.showText(evento.globalPos(), ayuda, self)
            else:
                QToolTip.hideText()
                evento.ignore()
            return True
        return super().event(evento)

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
        for tramo in self._segments:
            largo = self._largos.get(tramo.key)
            fraccion = largo.valor() if largo is not None else tramo.value / self._total
            if fraccion <= 0:
                continue
            width = rect.width() * fraccion
            painter.setBrush(QBrush(self._color(tramo.token)))
            painter.drawRect(QRectF(offset, 0, width, self.BAR_HEIGHT))
            offset += width
        painter.end()


