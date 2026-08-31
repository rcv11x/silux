"""El árbol de sensores: la tabla de la página de Sensores.

Vivía en `widgets.py` y ocupaba ahí ochocientas líneas de las dos mil
quinientas, con dos clases más —`ResizableHeader` y `SparklineDelegate`— que
no usa nadie más y que desde fuera parecían primitivas de uso general. Solo
lo monta `pages/monitor.py`.

`COLUMNS` está declarada en `tools/gen_lang.py`: sus claves se traducen con
`_(c)` sobre una variable, y el extractor no ve eso. Si esta clase se muda
otra vez, esa entrada se muda con ella o la siguiente poda se lleva las seis
cabeceras.
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QSizePolicy,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from ..i18n import _
from . import theme
from .theme import Palette, mono_font, ui_font


def _cifra(texto: str) -> float:
    """La cifra que lleva dentro una celda, para poder ordenar por ella.

    Las celdas traen su unidad pegada —«82.5 °C», «1470 RPM»— y algunas están
    vacías. Lo que no tiene número se va al final ordene como ordene: un
    sensor sin lectura no es ni el más alto ni el más bajo.
    """
    import math

    for trozo in texto.replace(",", ".").split():
        try:
            return float(trozo)
        except ValueError:
            continue
    return -math.inf


# Dónde guarda cada fila su serie reciente para que el delegate la pinte.
ROL_SERIE = int(Qt.ItemDataRole.UserRole) + 1


class SparklineDelegate(QStyledItemDelegate):
    """Pinta la serie reciente de un sensor dentro de su propia celda.

    Es un delegate y no un widget por fila: cien sensores serían cien widgets
    a repintar cada segundo, que es justo lo que la regla de reutilizar
    widgets existe para evitar. Un delegate no crea nada; Qt le pasa el
    pincel y el rectángulo de la celda que toca dibujar.

    La curva se escala contra su propio mínimo y máximo, no contra los del
    sensor desde que arrancó el programa: lo que interesa aquí es la forma
    del último minuto, y contra un máximo histórico lejano toda serie se
    aplasta en una raya.
    """

    ALTO = 0.62          # fracción de la celda que ocupa la curva
    MARGEN = 12          # aire entre la última cifra y el arranque de la curva
    PLANO = 1e-9

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette

    def paint(self, painter: QPainter, option, index) -> None:
        serie = index.data(ROL_SERIE)
        if not serie or len(serie) < 2:
            return

        # El hueco de la izquierda separa la curva de la cifra de la columna
        # anterior, que termina pegada a su borde derecho. Sin él la línea
        # arranca del último dígito y parece salir de él.
        rect = QRectF(option.rect)
        alto = rect.height() * self.ALTO
        caja = QRectF(rect.left() + self.MARGEN, rect.center().y() - alto / 2,
                      max(1.0, rect.width() - self.MARGEN - 6), alto)

        suelo, techo = min(serie), max(serie)
        span = techo - suelo
        paso = caja.width() / (len(serie) - 1)
        if span < self.PLANO:
            # Un sensor quieto es una recta por el medio, no una serie vacía:
            # «lleva un minuto sin moverse» también es información.
            puntos = [QPointF(caja.left() + i * paso, caja.center().y())
                      for i in range(len(serie))]
        else:
            puntos = [
                QPointF(caja.left() + i * paso,
                        caja.bottom() - (valor - suelo) / span * caja.height())
                for i, valor in enumerate(serie)
            ]

        camino = QPainterPath(puntos[0])
        for punto in puntos[1:]:
            camino.lineTo(punto)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._p.q("accent", 0.85), 1.4))
        painter.drawPath(camino)
        # El último punto marcado: con cien filas iguales, saber dónde termina
        # la línea es lo que deja leer la de al lado sin perderse de renglón.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._p.q("accent")))
        painter.drawEllipse(puntos[-1], 1.8, 1.8)
        painter.restore()


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
    # Claves, no texto: se traducen al montar la cabecera. Como constantes de
    # clase se evaluarían al importar, cuando todavía no se sabe el idioma.
    COLUMNS = ("sensors.col.name", "sensors.col.current", "sensors.col.min",
               "sensors.col.max", "sensors.col.avg", "sensors.col.trend", "")
    VALUE_COLUMNS = 4
    # Dónde va la curva. Las cuatro de cifras son las que hay entre el nombre
    # y esta.
    TREND_COLUMN = 5

    columnsResized = Signal(tuple)

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._p = palette
        self._rows: dict[str, QTreeWidgetItem] = {}
        self._structure: tuple = ()

        self.setColumnCount(len(self.COLUMNS))
        self.setHeaderLabels([_(c) if c else "" for c in self.COLUMNS])
        # La cabecera se alinea como los datos que hay debajo: el nombre a la
        # izquierda y las cifras a la derecha. Centrada (que es lo que hace Qt
        # por omisión) no cuadra con ninguna de las dos columnas.
        header_item = self.headerItem()
        header_item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in range(1, len(self.COLUMNS)):
            # La de la curva se alinea con la curva, que arranca por la
            # izquierda; las de cifras con sus cifras, que terminan a la derecha.
            lado = (Qt.AlignmentFlag.AlignLeft if column == self.TREND_COLUMN
                    else Qt.AlignmentFlag.AlignRight)
            header_item.setTextAlignment(column, lado | Qt.AlignmentFlag.AlignVCenter)
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

        self._sparkline = SparklineDelegate(palette, self)
        self.setItemDelegateForColumn(self.TREND_COLUMN, self._sparkline)

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
            _("sensors.header.tip")
        )
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._ordenar_por)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        header.sectionResized.connect(self._on_section_resized)
        self._preferred_widths: tuple[int, ...] = ()
        self._applying_widths = False
        self._filtro = ""
        # `None` = no hay nada guardado todavía, que no es lo mismo que «no
        # había ninguna plegada»: en el primer caso se abren todas.
        self._plegadas_guardadas: Optional[set] = None
        # (columna, ascendente) o None mientras se respete el orden natural.
        self._orden: Optional[tuple[int, bool]] = None
        # Cómo estaba cada categoría al montarse, para poder volver.
        self._orden_natural: dict[int, tuple[str, ...]] = {}

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

    # Lo que se le da a la curva. Es ancho fijo y no medido porque no hay
    # texto que medir: es el tramo de tiempo que se quiere ver de un vistazo.
    TREND_WIDTH = 120
    # Hasta dónde puede crecer cuando sobra sitio. En una pantalla de 2560 el
    # hueco de la derecha era de más de mil píxeles vacíos mientras la curva
    # se apretaba en ciento veinte, y una curva más ancha son más muestras
    # distinguibles. El tope está para que no se estire hasta lo absurdo en
    # una ultrapanorámica, y solo se reparte lo que sobra: las columnas de
    # cifras no se tocan, que es lo que las mantiene pegadas al nombre.
    TREND_MAX = 460

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
        # Unos anchos guardados antes de que existiera una columna vienen
        # cortos. Las que falten se calculan en vez de quedarse con lo que Qt
        # tuviera puesto, que es cero hasta que alguien mide.
        anchos = list(widths)
        while len(anchos) < len(self.COLUMNS) - 1:
            columna = len(anchos)
            anchos.append(self.TREND_WIDTH if columna == self.TREND_COLUMN
                          else self.header().minimumSectionSize())

        self._applying_widths = True
        try:
            for column, width in enumerate(anchos):
                if column >= len(self.COLUMNS) - 1:
                    break
                if column == 0:
                    natural = medidos[0] + 46 if medidos else 0
                    floor = min(max(self.NAME_FLOOR, natural), 460)
                elif column == self.TREND_COLUMN:
                    floor = 60
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
            for column in range(1, 1 + self.VALUE_COLUMNS):
                self.setColumnWidth(
                    column,
                    max(52, min(widest[column] + self.RESPIRO_CIFRAS, 220)),
                )
            self.setColumnWidth(self.TREND_COLUMN, self.TREND_WIDTH)
        finally:
            self._applying_widths = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._repartir_sobrante()

    def _repartir_sobrante(self) -> None:
        """Le da a la curva el hueco que iba a quedarse la columna vacía.

        Solo mientras el usuario no haya tocado los anchos. Al arrastrar la
        columna para estrecharla volvía a estirarse sola en el muestreo
        siguiente: cambiar los valores recalcula la altura del árbol, eso es
        un `resizeEvent`, y aquí se repartía otra vez el sobrante como si
        nadie hubiera dicho nada. Lo que se arrastra manda.
        """
        if self._applying_widths or self._preferred_widths or not self.isVisible():
            return
        ocupado = sum(self.columnWidth(c) for c in range(len(self.COLUMNS) - 1))
        sobra = self.viewport().width() - ocupado
        actual = self.columnWidth(self.TREND_COLUMN)
        objetivo = max(self.TREND_WIDTH, min(actual + sobra, self.TREND_MAX))
        if objetivo == actual:
            return
        self._applying_widths = True
        try:
            self.setColumnWidth(self.TREND_COLUMN, objetivo)
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

        widest = [header_metrics.horizontalAdvance(_(name) if name else "") + 18
                  for name in self.COLUMNS]

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
        """Se apunta el ancho solo cuando lo ha movido una persona.

        La última columna es la que absorbe el sobrante, así que Qt la estira
        sola cada vez que cambia el tamaño de la ventana. Eso llegaba aquí
        igual que un arrastre y dejaba los anchos guardados como si alguien
        los hubiera puesto a mano: bastaba con maximizar la ventana una vez
        para que el árbol dejara de ajustarse solo nunca más.
        """
        if (self._applying_widths or not self.isVisible()
                or index >= len(self.COLUMNS) - 1):
            return
        self._preferred_widths = self.column_widths()
        self.columnsResized.emit(self._preferred_widths)

    # -- ordenar ------------------------------------------------------------

    def _ordenar_por(self, columna: int) -> None:
        """Ordena las hojas de cada rama por una columna, o vuelve al orden
        natural si ya estaba ordenado por ella.

        Se ordena **dentro de cada aparato** y no la lista entera: sacar la
        temperatura de un disco de debajo de su disco para ponerla entre las
        de la placa deja de decir de quién es cada cosa, que es justo lo que
        hace legible un árbol de noventa y nueve sensores.

        La columna del nombre vuelve al orden de siempre, que ya es el suyo.
        """
        if columna >= 1 + self.VALUE_COLUMNS:
            return
        # Tres estados y no dos: de mayor a menor es lo que se quiere casi
        # siempre («cuál está más caliente»), pero hay que poder volver al
        # orden por aparato, que es el que dice de quién es cada sensor.
        if columna == 0:
            self._orden = None
        elif self._orden is None or self._orden[0] != columna:
            self._orden = (columna, False)          # de mayor a menor
        elif self._orden[1] is False:
            self._orden = (columna, True)           # de menor a mayor
        else:
            self._orden = None                      # como estaba
        self._aplicar_orden()

    def _aplicar_orden(self) -> None:
        from PySide6.QtCore import Qt as _Qt

        cabecera = self.header()
        if self._orden is None:
            cabecera.setSortIndicatorShown(False)
            for _descarte, categoria, hojas in self._recorrer():
                # El orden natural es el que tenía al montarse, no el que
                # tenga ahora: reinsertar lo que ya está ordenado lo deja
                # exactamente igual.
                natural = self._orden_natural.get(id(categoria))
                if not natural:
                    continue
                for hoja in hojas:
                    categoria.removeChild(hoja)
                for clave in natural:
                    if (hoja := self._rows.get(clave)) is not None:
                        categoria.addChild(hoja)
            return

        columna, ascendente = self._orden
        cabecera.setSortIndicatorShown(True)
        cabecera.setSortIndicator(
            columna, _Qt.SortOrder.AscendingOrder if ascendente
            else _Qt.SortOrder.DescendingOrder)

        for aparato, categoria, hojas in self._recorrer():
            ordenadas = sorted(hojas, key=lambda h: _cifra(h.text(columna)),
                               reverse=not ascendente)
            for hoja in hojas:
                categoria.removeChild(hoja)
            for hoja in ordenadas:
                categoria.addChild(hoja)

    def _recorrer(self):
        """Cada categoría con sus hojas, tal y como están montadas ahora."""
        for i in range(self.topLevelItemCount()):
            aparato = self.topLevelItem(i)
            for j in range(aparato.childCount()):
                categoria = aparato.child(j)
                hojas = [categoria.child(k) for k in range(categoria.childCount())]
                yield aparato, categoria, hojas

    def _header_menu(self, position) -> None:
        menu = QMenu(self)
        action = menu.addAction(_("sensors.header.reset"))
        action.triggered.connect(self.reset_column_widths)
        menu.exec(self.header().mapToGlobal(position))

    def rebuild(self, tree: dict) -> None:
        """Rehace la estructura. Solo se llama cuando cambia qué hay, no
        cuánto vale."""
        expanded = {key for key, item in self._rows.items() if item.isExpanded()}
        self.clear()
        self._rows.clear()
        self._orden_natural.clear()

        for device, categories in tree.items():
            device_item = QTreeWidgetItem([device])
            device_item.setFont(0, self._branch_font)
            device_item.setForeground(0, self._p.q("ink"))
            device_item.setFirstColumnSpanned(True)
            self.addTopLevelItem(device_item)
            self._rows[f"::{device}"] = device_item

            for category, sensors in categories.items():
                category_item = QTreeWidgetItem([_(category)])
                category_item.setFont(0, self._label_font)
                for column in range(len(self.COLUMNS)):
                    category_item.setForeground(column, self._p.q("muted"))
                device_item.addChild(category_item)
                self._rows[f"::{device}/{category}"] = category_item

                if sensors:
                    category_item.setIcon(0, self._icon(sensors[0].kind.value))

                # Un aparato puede traer sus temperaturas por dos vías: una
                # placa Gigabyte las publica por su Super I/O y otra vez por
                # su interfaz WMI, y las dos se llaman «Temperatura 1». Sin
                # decir de cuál es cada una, la lista tiene seis renglones
                # repetidos y ninguna forma de saber cuál mirar.
                repetidas = {etiqueta for etiqueta in
                             (x.label for x in sensors)
                             if sum(1 for y in sensors if y.label == etiqueta) > 1}

                for sensor in sensors:
                    nombre = (f"{sensor.label} ({sensor.chip})"
                              if sensor.label in repetidas else sensor.label)
                    row = QTreeWidgetItem(
                        [nombre] + ["—"] * self.VALUE_COLUMNS)
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
                    # El color base de la fila lo pone el árbol y no la hoja
                    # de estilos: declararlo allí pisaría el de las celdas que
                    # piden otro, que es justo lo que tiene que poder pasar.
                    for column in range(len(self.COLUMNS)):
                        row.setForeground(column, self._p.q("ink_dim"))
                    # La columna del valor actual va sobre una banda tenue: es
                    # la que se mira, y anclarla evita recorrer con el dedo.
                    row.setBackground(1, QBrush(self._p.q("accent", 0.09)))
                    category_item.addChild(row)
                    self._rows[sensor.key] = row

                self._orden_natural[id(category_item)] = tuple(
                    s.key for s in sensors)
                category_item.setExpanded(
                    self._nace_abierta(f"::{device}/{category}", expanded))
            device_item.setExpanded(self._nace_abierta(f"::{device}", expanded))

        self._autosize_columns()
        self._fit_height()
        if self._filtro:
            self._aplicar_filtro()

    # -- ramas plegadas -----------------------------------------------------

    def _nace_abierta(self, clave: str, expandidas: set) -> bool:
        """Si una rama arranca desplegada.

        Manda lo que el usuario dejó en la sesión anterior. Solo cuando no hay
        nada guardado —el primer arranque— se abren todas, que es lo que deja
        ver de qué va la página sin tener que tocarla.
        """
        if self._plegadas_guardadas is not None:
            return clave not in self._plegadas_guardadas
        return clave in expandidas or not expandidas

    def set_collapsed(self, claves) -> None:
        """Las ramas que estaban plegadas al cerrar. Vacío = todas abiertas."""
        self._plegadas_guardadas = set(claves) if claves is not None else None

    def collapsed(self) -> tuple[str, ...]:
        """Las que están plegadas ahora, para guardarlas."""
        return tuple(sorted(clave for clave, item in self._rows.items()
                            if clave.startswith("::") and not item.isExpanded()))

    # -- filtro -------------------------------------------------------------

    def set_filter(self, texto: str) -> None:
        """Deja a la vista solo lo que casa. Vacío = todo.

        Con noventa y nueve sensores en ocho aparatos, encontrar «el de la
        VRAM» es plegar y desplegar ramas hasta dar con él. Se busca en el
        nombre del sensor y también en el del aparato, que es como la gente lo
        pide: «los del 9070» tanto como «temperatura».
        """
        nuevo = texto.strip().lower()
        if nuevo == self._filtro:
            return
        self._filtro = nuevo
        self._aplicar_filtro()

    def _aplicar_filtro(self) -> None:
        for indice in range(self.topLevelItemCount()):
            aparato = self.topLevelItem(indice)
            self._filtrar_rama(aparato, aparato.text(0).lower())
        self._fit_height()

    def _filtrar_rama(self, aparato, texto_aparato: str) -> None:
        """Un aparato entero casa si su nombre casa; si no, decide cada hijo."""
        aparato_casa = not self._filtro or self._filtro in texto_aparato
        visibles_aparato = 0

        for i in range(aparato.childCount()):
            categoria = aparato.child(i)
            casa_categoria = aparato_casa or self._filtro in categoria.text(0).lower()
            visibles = 0
            for j in range(categoria.childCount()):
                fila = categoria.child(j)
                visible = casa_categoria or self._filtro in fila.text(0).lower()
                fila.setHidden(not visible)
                visibles += visible
            categoria.setHidden(visibles == 0)
            # Buscando, las ramas se abren solas: filtrar y dejar el resultado
            # escondido dentro de una rama plegada no encuentra nada.
            if self._filtro and visibles:
                categoria.setExpanded(True)
            visibles_aparato += visibles

        aparato.setHidden(visibles_aparato == 0)
        if self._filtro and visibles_aparato:
            aparato.setExpanded(True)

    def coincidencias(self) -> int:
        """Cuántos sensores quedan a la vista. Cero es un resultado, no un
        fallo: hay que poder decirlo."""
        return sum(1 for clave, item in self._rows.items()
                   if not clave.startswith("::") and not item.isHidden())

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

    def _mezcla_calor(self, heat: float):
        """Del color normal al de aviso, según lo cerca que esté del umbral.

        La mezcla no es lineal. El ojo no ve el color así: entre el blanco de
        las cifras y el ámbar, el primer tercio del recorrido no se distingue
        de nada, y una CPU a 78 grados de 95 salía exactamente igual que una a
        50. Con la raíz, ese primer tercio ya se ve.
        """
        avance = heat ** 0.5
        normal = self._p.q("ink")
        aviso = self._p.q("warn")
        return QColor(
            round(normal.red() + (aviso.red() - normal.red()) * avance),
            round(normal.green() + (aviso.green() - normal.green()) * avance),
            round(normal.blue() + (aviso.blue() - normal.blue()) * avance),
        )

    def update_row(self, key: str, values: list[str], tooltip: str = "",
                   alarm: str = "ok", history=None, heat: float = 0.0,
                   heat_max: float = 0.0) -> None:
        item = self._rows.get(key)
        if item is None:
            return
        for column, text in enumerate(values, start=1):
            if item.text(column) != text:
                item.setText(column, text)
                self._ensanchar_para(column, text)
        # La serie va como dato de la fila, no como texto: la pinta el
        # delegate de esa columna. Se guarda una tupla y no el deque del
        # seguidor para que la vista no dependa de algo que muta bajo sus pies.
        if history is not None:
            item.setData(self.TREND_COLUMN, ROL_SERIE, tuple(history))
        # Tres estados y no dos: «alto» es donde el fabricante empieza a
        # incomodarse y «crítico» donde el equipo se protege solo. Pintarlos
        # igual deja sin saber si hay que hacer algo ahora o solo mirarlo.
        #
        # Y por debajo del umbral, el color va subiendo con `heat`: en una
        # lista de noventa y nueve renglones iguales, el que se está acercando
        # se encuentra mirando, no leyendo uno a uno.
        colour = {"crítico": self._p.q("crit"),
                  "alto": self._p.q("warn")}.get(alarm)
        if colour is None:
            colour = (self._p.q("ink") if not heat
                      else self._mezcla_calor(heat))
        item.setForeground(1, colour)

        # El máximo se tiñe con su propio calor y no con el de ahora. Es el
        # dato que sobrevive al pico: quien lanza una prueba de dos minutos y
        # va a mirar después encuentra la columna «Actual» ya fría, y lo que
        # quiere ver es hasta dónde llegó.
        item.setForeground(3, self._p.q("ink") if not heat_max
                           else self._mezcla_calor(heat_max))
        if tooltip:
            for column in range(len(self.COLUMNS)):
                item.setToolTip(column, tooltip)

    def _ensanchar_para(self, column: int, text: str) -> None:
        """Da sitio a un valor que ha crecido después de medir las columnas.

        Los anchos se calculan al montar el árbol, cuando muchas celdas están
        todavía vacías o traen un guion. Luego llegan los valores de verdad y
        alguno ya no cabe: la columna del reloj enseñaba «800.0 M…» porque se
        midió antes de que hubiera ningún reloj que medir.

        Solo ensancha, nunca encoge, o la tabla bailaría a cada muestreo.

        Ensancha también cuando el usuario ha puesto los anchos a mano, por el
        mismo motivo que el suelo de la columna de nombres: se respeta lo que
        arrastre, pero no hasta el punto de recortar una cifra. Con los anchos
        guardados de una sesión anterior, los relojes de núcleo salían como
        «3738.5 M…», y un ancho a medida no es una orden de esconder datos.
        """
        if not text:
            return
        # El relleno de la celda va a los dos lados y no se contaba: la cifra
        # cabía en la cuenta y no en la columna.
        necesario = (QFontMetrics(self._value_font).horizontalAdvance(text)
                     + theme.RELLENO_DE_CELDA * 2 + theme.METRICS.grid_hspace)
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
