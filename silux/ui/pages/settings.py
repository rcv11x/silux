"""Página de ajustes.

No guarda nada por su cuenta: emite las preferencias nuevas y quien la usa
decide qué hacer con ellas. Así la página no sabe si el cambio se persiste,
se aplica en caliente o las dos cosas.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import EMOJI, __version__, db, i18n
from ...i18n import _
from ...settings import Preferences, config_path
from .. import theme
from ..theme import ui_font
from ..widgets import Card, ResponsiveRow

AUTORIA = (
    ("rcv11x", "about.author"),
    ("Claude", ""),
)

CONSTRUIDO_CON = (
    ("Python 3", "about.python"),
    ("PySide6 / Qt 6", "about.qt"),
    ("ctypes y mmap", "about.ctypes"),
    ("polkit", "about.polkit"),
)

DATOS_DE_TERCEROS = (
    ("libcpuid", "about.libcpuid"),
    ("CPU-X", "about.cpux"),
    ("hwdata", "about.hwdata"),
)

THEMES = (("opt.theme.system", "system"), ("opt.theme.light", "light"), ("opt.theme.dark", "dark"))
UNITS = (("opt.temp.celsius", "c"), ("opt.temp.fahrenheit", "f"))
DENSITIES = (("opt.density.spacious", "spacious"), ("opt.density.normal", "normal"), ("opt.density.compact", "compact"))
# El tamaño de la letra va aparte de la densidad a propósito: son dos cosas
# distintas. La densidad decide cuánto aire hay entre las filas; esto, cómo de
# grande se lee lo que hay dentro. Quien necesita letra grande no tiene por qué
# querer además que todo ocupe el doble.
FONT_SCALES = (("opt.density.normal", "normal"), ("opt.font.large", "grande"),
               ("opt.font.larger", "mayor"), ("opt.font.largest", "máximo"))
ACCENTS = (("opt.accent.orange", "naranja"), ("opt.accent.blue", "azul"), ("opt.accent.green", "verde"),
           ("opt.accent.purple", "morado"), ("opt.accent.red", "rojo"), ("opt.accent.cyan", "cian"))
NETWORK_UNITS = (("opt.net.bytes", "bytes"),
                 ("opt.net.bits", "bits"))


# Para que la columna de controles quede recta de arriba abajo.
ANCHO_DEL_CONTROL = 150


class _Field(QWidget):
    """Una fila de ajuste: nombre, control y una línea de explicación."""

    def __init__(self, name: str, control: QWidget, explanation: str = "", parent=None):
        super().__init__(parent)
        m = theme.METRICS

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, m.card_gap)
        column.setSpacing(3)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        label = QLabel(name)
        label.setObjectName("FieldValue")
        label.setFont(ui_font(m.base_pt))
        label.setMinimumWidth(150)

        # Los que llevan texto dentro, con el mismo ancho: sin esto cada
        # desplegable mide lo que mida su opción más larga y el borde derecho
        # queda en diente de sierra. Una casilla no: es un cuadradito, y
        # reservarle ese ancho le come el nombre al ajuste.
        if not isinstance(control, QCheckBox):
            control.setMinimumWidth(ANCHO_DEL_CONTROL)
        row.addWidget(label, 1)
        row.addWidget(control, 0, Qt.AlignmentFlag.AlignRight)
        column.addLayout(row)

        if explanation:
            note = QLabel(explanation)
            note.setObjectName("Muted")
            note.setWordWrap(True)
            # Más pequeña que la etiqueta a propósito: la explicación acompaña
            # al ajuste, no compite con él. Al mismo tamaño, un texto de cinco
            # líneas se lee antes que el nombre de la opción que explica.
            note.setFont(ui_font(max(7, m.small_pt - 1)))
            note.setContentsMargins(0, 0, ANCHO_DEL_CONTROL // 2, 0)
            column.addWidget(note)


class SettingsPage(QScrollArea):
    changed = Signal(object)          # Preferences
    # La página de ajustes no tiene la foto del hardware; la pide y ya la
    # guarda la ventana, que sí la tiene.
    report_requested = Signal()
    share_copy_requested = Signal()
    share_save_requested = Signal()

    def __init__(self, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._prefs = prefs
        self._loading = True
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        layout.setSpacing(m.section_gap)

        columns = ResponsiveRow(min_item_width=280)
        columns.add(self._build_sampling())
        columns.add(self._build_appearance())
        layout.addWidget(columns)

        layout.addWidget(self._build_credits())
        layout.addWidget(self._build_about())
        layout.addStretch(1)

        self._loading = False

    # -- construcción -------------------------------------------------------

    def _build_sampling(self) -> Card:
        card = Card(_("settings.card.sampling"))

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.2, 10.0)
        self.interval.setSingleStep(0.1)
        self.interval.setDecimals(1)
        self.interval.setSuffix(" s")
        self.interval.setValue(self._prefs.interval_s)
        self.interval.setFixedWidth(96)
        self.interval.valueChanged.connect(self._emit)

        card.body.addWidget(_Field(
            _("settings.interval.label"), self.interval,
            _("settings.interval.help")
            ,
        ))

        self.all_features = QCheckBox()
        self.all_features.setChecked(self._prefs.show_all_features)
        self.all_features.stateChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.allflags.label"), self.all_features,
            _("settings.allflags.help")
            ,
        ))

        self.fluid_charts = QCheckBox()
        self.fluid_charts.setChecked(self._prefs.fluid_charts)
        self.fluid_charts.stateChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.fluid.label"), self.fluid_charts,
            _("settings.fluid.help")
            ,
        ))
        return card

    def _build_appearance(self) -> Card:
        card = Card(_("settings.card.appearance"))

        # El idioma va el primero de la tarjeta: es lo que cambia todo lo
        # demás, y quien lo busca no viene a mirar el tema.
        self.language_box = QComboBox()
        idiomas = i18n.disponible()
        for codigo, nombre in idiomas.items():
            self.language_box.addItem(nombre, codigo)
        actual = self._prefs.language if self._prefs.language in idiomas else "es"
        self.language_box.setCurrentIndex(list(idiomas).index(actual))
        self.language_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.language.label"), self.language_box,
            _("settings.language.help")))

        self.theme_box = QComboBox()
        for label, value in THEMES:
            self.theme_box.addItem(_(label), value)
        self.theme_box.setCurrentIndex([v for _descarte, v in THEMES].index(self._prefs.theme))
        self.theme_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(_("settings.theme.label"), self.theme_box))

        self.density_box = QComboBox()
        for label, value in DENSITIES:
            self.density_box.addItem(_(label), value)
        self.density_box.setCurrentIndex([v for _descarte, v in DENSITIES].index(self._prefs.density))
        self.density_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.density.label"), self.density_box,
            _("settings.density.help")
            ,
        ))

        self.font_box = QComboBox()
        for label, value in FONT_SCALES:
            self.font_box.addItem(_(label), value)
        self.font_box.setCurrentIndex(
            [v for _descarte, v in FONT_SCALES].index(self._prefs.font_scale))
        self.font_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.fontsize.label"), self.font_box,
            _("settings.fontsize.help")
            ,
        ))

        self.accent_box = QComboBox()
        for label, value in ACCENTS:
            self.accent_box.addItem(_(label), value)
        self.accent_box.setCurrentIndex([v for _descarte, v in ACCENTS].index(self._prefs.accent))
        self.accent_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.accent.label"), self.accent_box,
            _("settings.accent.help")
            ,
        ))

        self.network_box = QComboBox()
        for label, value in NETWORK_UNITS:
            self.network_box.addItem(_(label), value)
        self.network_box.setCurrentIndex(
            [v for _descarte, v in NETWORK_UNITS].index(self._prefs.network_unit))
        self.network_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            _("settings.netunit.label"), self.network_box,
            _("settings.netunit.help")
            ,
        ))

        self.unit_box = QComboBox()
        for label, value in UNITS:
            self.unit_box.addItem(_(label), value)
        self.unit_box.setCurrentIndex([v for _descarte, v in UNITS].index(self._prefs.temperature_unit))
        self.unit_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(_("settings.tempunit.label"), self.unit_box))

        informe = QPushButton(_("settings.report.button"))
        informe.setToolTip(
            _("settings.tip.report")
        )
        informe.clicked.connect(self.report_requested.emit)

        # Al lado del informe porque responden a la misma intención: sacar algo
        # de aquí para enseñárselo a otro. El informe es para diagnosticar y
        # esto es para presumir, y las dos cosas acaban pegadas en un chat.
        copiar = QPushButton(_("share.button.copy"))
        copiar.setToolTip(_("share.tip"))
        copiar.clicked.connect(self.share_copy_requested.emit)
        guardar = QPushButton(_("share.button.save"))
        guardar.setToolTip(_("share.tip"))
        guardar.clicked.connect(self.share_save_requested.emit)

        fila_informe = QHBoxLayout()
        fila_informe.addStretch(1)
        fila_informe.addWidget(copiar)
        fila_informe.addWidget(guardar)
        fila_informe.addWidget(informe)
        card.body.addLayout(fila_informe)

        reset = QPushButton(_("settings.reset.button"))
        reset.clicked.connect(self._reset)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reset)
        card.body.addLayout(row)
        return card

    def _build_credits(self) -> Card:
        """Quién lo hace y sobre qué está construido."""
        card = Card(_("about.card"))
        m = theme.METRICS

        titulo = QLabel(f"{EMOJI} Silux {__version__}")
        titulo.setObjectName("Headline")
        card.body.addWidget(titulo)

        lema = QLabel(
            _("about.tagline")
        )
        lema.setObjectName("Subhead")
        lema.setWordWrap(True)
        card.body.addWidget(lema)

        fila = ResponsiveRow(min_item_width=250)
        fila.add(self._bloque(_("about.credits"), AUTORIA))
        fila.add(self._bloque(_("about.builtwith"), CONSTRUIDO_CON))
        fila.add(self._bloque(_("about.thirdparty"), DATOS_DE_TERCEROS))
        card.body.addWidget(fila)
        return card

    def _bloque(self, titulo: str, lineas: tuple[tuple[str, str], ...]) -> QWidget:
        """Una columna de «cosa, para qué», con su encabezado."""
        m = theme.METRICS
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(3)

        encabezado = QLabel(titulo.upper())
        # De columna, no de tarjeta: estos tres encabezados nombran una lista
        # dentro de una tarjeta que ya tiene su propio título.
        encabezado.setObjectName("ColumnTitle")
        columna.addWidget(encabezado)
        columna.addSpacing(2)

        for nombre, clave in lineas:
            detalle = _(clave) if clave else ""
            # El nombre y su para-qué en dos renglones alineados por la
            # izquierda, en vez de un párrafo con negritas dentro: así las tres
            # columnas se leen a la misma altura y se comparan de un vistazo.
            titulo_linea = QLabel(nombre)
            titulo_linea.setObjectName("FieldValue")
            titulo_linea.setFont(ui_font(m.small_pt))
            titulo_linea.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            columna.addWidget(titulo_linea)

            if detalle:
                pie = QLabel(detalle)
                pie.setObjectName("Muted")
                pie.setWordWrap(True)
                pie.setFont(ui_font(max(7, m.small_pt - 1)))
                pie.setContentsMargins(0, 0, 0, m.card_gap - 2)
                pie.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse)
                columna.addWidget(pie)
        columna.addStretch(1)
        return caja

    def _build_about(self) -> Card:
        card = Card(_("about.storage"))
        m = theme.METRICS

        if db.available():
            data = db.load()
            counts = data.get("counts", {})
            sources = data.get("sources", {})
            text = _("settings.db.counts").format(
                intel=counts.get("x86_intel", 0),
                amd=counts.get("x86_amd", 0),
                arm=counts.get("arm_parts", 0),
                sockets=counts.get("sockets", 0),
                commit=sources.get("libcpuid", {}).get("commit", "?"),
                fecha=sources.get("libcpuid", {}).get("date", "?"),
                cpux=sources.get("cpu-x", {}).get("commit", "?"))
        else:
            text = _("settings.db.none")

        info = QLabel(text)
        info.setObjectName("Muted")
        info.setWordWrap(True)
        info.setFont(ui_font(m.small_pt))
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(info)

        path = QLabel(_("settings.savedat").format(ruta=config_path()))
        path.setObjectName("Muted")
        path.setWordWrap(True)
        path.setFont(ui_font(m.small_pt))
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(path)
        return card

    # -- señales ------------------------------------------------------------

    def current(self) -> Preferences:
        from dataclasses import replace

        return replace(
            self._prefs,
            interval_s=self.interval.value(),
            language=self.language_box.currentData(),
            theme=self.theme_box.currentData(),
            temperature_unit=self.unit_box.currentData(),
            density=self.density_box.currentData(),
            font_scale=self.font_box.currentData(),
            accent=self.accent_box.currentData(),
            network_unit=self.network_box.currentData(),
            show_all_features=self.all_features.isChecked(),
            fluid_charts=self.fluid_charts.isChecked(),
        ).normalized()

    def _emit(self, *_args) -> None:
        if self._loading:
            return
        self._prefs = self.current()
        self.changed.emit(self._prefs)

    def _reset(self) -> None:
        from dataclasses import replace

        defaults = Preferences()
        # El tamaño de ventana no es un ajuste que el usuario toque aquí:
        # se recuerda solo, y restablecer no debería moverle la ventana.
        self._prefs = replace(defaults,
                              window_width=self._prefs.window_width,
                              window_height=self._prefs.window_height)
        self.changed.emit(self._prefs)
