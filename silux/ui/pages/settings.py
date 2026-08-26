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

from ... import EMOJI, db
from ...settings import Preferences, config_path
from .. import theme
from ..theme import ui_font
from ..widgets import Card, ResponsiveRow

VERSION = "0.1.0"

AUTORIA = (
    ("rcv11x", "autor: diseño, desarrollo, pruebas y documentación"),
    ("Claude", ""),
)

CONSTRUIDO_CON = (
    ("Python 3", "sin dependencias fuera de la biblioteca estándar"),
    ("PySide6 / Qt 6", "solo para la interfaz"),
    ("ctypes y mmap", "CPUID, ioctl de DRM y las bibliotecas gráficas"),
    ("polkit", "el ayudante que lee la tabla SMBIOS"),
)

DATOS_DE_TERCEROS = (
    ("libcpuid", "identificación de procesadores · BSD-2"),
    ("CPU-X", "tabla de encapsulados · GPL-3.0"),
    ("hwdata", "pci.ids y pnp.ids del sistema"),
)

THEMES = (("Seguir al sistema", "system"), ("Claro", "light"), ("Oscuro", "dark"))
UNITS = (("Celsius (°C)", "c"), ("Fahrenheit (°F)", "f"))
DENSITIES = (("Amplia", "spacious"), ("Normal", "normal"), ("Compacta", "compact"))
# El tamaño de la letra va aparte de la densidad a propósito: son dos cosas
# distintas. La densidad decide cuánto aire hay entre las filas; esto, cómo de
# grande se lee lo que hay dentro. Quien necesita letra grande no tiene por qué
# querer además que todo ocupe el doble.
FONT_SCALES = (("Normal", "normal"), ("Grande", "grande"),
               ("Mayor", "mayor"), ("Máximo", "máximo"))
ACCENTS = (("Naranja", "naranja"), ("Azul", "azul"), ("Verde", "verde"),
           ("Morado", "morado"), ("Rojo", "rojo"), ("Cian", "cian"))
NETWORK_UNITS = (("Bytes por segundo (MB/s)", "bytes"),
                 ("Bits por segundo (Mb/s)", "bits"))


class _Field(QWidget):
    """Una fila de ajuste: nombre, control y una línea de explicación."""

    def __init__(self, name: str, control: QWidget, explanation: str = "", parent=None):
        super().__init__(parent)
        m = theme.METRICS

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        label = QLabel(name)
        label.setObjectName("FieldValue")
        label.setFont(ui_font(m.base_pt))
        label.setMinimumWidth(150)

        row.addWidget(label, 1)
        row.addWidget(control, 0)
        column.addLayout(row)

        if explanation:
            note = QLabel(explanation)
            note.setObjectName("Muted")
            note.setWordWrap(True)
            note.setFont(ui_font(m.small_pt))
            column.addWidget(note)


class SettingsPage(QScrollArea):
    changed = Signal(object)          # Preferences
    # La página de ajustes no tiene la foto del hardware; la pide y ya la
    # guarda la ventana, que sí la tiene.
    report_requested = Signal()

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
        card = Card("Muestreo")

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.2, 10.0)
        self.interval.setSingleStep(0.1)
        self.interval.setDecimals(1)
        self.interval.setSuffix(" s")
        self.interval.setValue(self._prefs.interval_s)
        self.interval.setFixedWidth(96)
        self.interval.valueChanged.connect(self._emit)

        card.body.addWidget(_Field(
            "Refrescar cada", self.interval,
            "Cada lectura recorre sysfs y hwmon. Por debajo de medio segundo el "
            "coste empieza a notarse; por encima de dos, las gráficas pierden detalle.",
        ))

        self.all_features = QCheckBox()
        self.all_features.setChecked(self._prefs.show_all_features)
        self.all_features.stateChanged.connect(self._emit)
        card.body.addWidget(_Field(
            "Mostrar todas las instrucciones", self.all_features,
            "Por defecto solo se enseñan las banderas relevantes. Activado, "
            "aparecen las 53 que devuelve CPUID en este equipo.",
        ))
        return card

    def _build_appearance(self) -> Card:
        card = Card("Apariencia")

        self.theme_box = QComboBox()
        for label, value in THEMES:
            self.theme_box.addItem(label, value)
        self.theme_box.setCurrentIndex([v for _, v in THEMES].index(self._prefs.theme))
        self.theme_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field("Tema", self.theme_box))

        self.density_box = QComboBox()
        for label, value in DENSITIES:
            self.density_box.addItem(label, value)
        self.density_box.setCurrentIndex([v for _, v in DENSITIES].index(self._prefs.density))
        self.density_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            "Densidad", self.density_box,
            "Amplia deja más aire entre filas y columnas; compacta aprieta para "
            "que quepa más en la misma pantalla.",
        ))

        self.font_box = QComboBox()
        for label, value in FONT_SCALES:
            self.font_box.addItem(label, value)
        self.font_box.setCurrentIndex(
            [v for _, v in FONT_SCALES].index(self._prefs.font_scale))
        self.font_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            "Tamaño de la letra", self.font_box,
            "Agranda todo el texto de la interfaz. Las tarjetas y las columnas "
            "crecen con él para que nada se recorte.",
        ))

        self.accent_box = QComboBox()
        for label, value in ACCENTS:
            self.accent_box.addItem(label, value)
        self.accent_box.setCurrentIndex([v for _, v in ACCENTS].index(self._prefs.accent))
        self.accent_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            "Color de acento", self.accent_box,
            "El color con el que se resaltan los datos, las gráficas y la "
            "sección abierta.",
        ))

        self.network_box = QComboBox()
        for label, value in NETWORK_UNITS:
            self.network_box.addItem(label, value)
        self.network_box.setCurrentIndex(
            [v for _, v in NETWORK_UNITS].index(self._prefs.network_unit))
        self.network_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field(
            "Velocidad de red", self.network_box,
            "Los mismos datos son 116 MB/s o 931 Mb/s. Los tests de velocidad y "
            "los operadores usan bits; los gestores de descargas, bytes.",
        ))

        self.unit_box = QComboBox()
        for label, value in UNITS:
            self.unit_box.addItem(label, value)
        self.unit_box.setCurrentIndex([v for _, v in UNITS].index(self._prefs.temperature_unit))
        self.unit_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field("Unidad de temperatura", self.unit_box))

        informe = QPushButton("Guardar informe del equipo…")
        informe.setToolTip(
            "Genera un archivo de texto con todo el hardware detectado y, sobre "
            "todo, con lo que no se ha podido leer y por qué. Es lo que hay que "
            "adjuntar al reportar un fallo.\n\n"
            "No incluye el nombre del equipo, las direcciones IP y MAC ni los "
            "números de serie."
        )
        informe.clicked.connect(self.report_requested.emit)
        fila_informe = QHBoxLayout()
        fila_informe.addStretch(1)
        fila_informe.addWidget(informe)
        card.body.addLayout(fila_informe)

        reset = QPushButton("Restablecer valores por defecto")
        reset.clicked.connect(self._reset)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reset)
        card.body.addLayout(row)
        return card

    def _build_credits(self) -> Card:
        """Quién lo hace y sobre qué está construido."""
        card = Card("Acerca de silux")
        m = theme.METRICS

        titulo = QLabel(f"{EMOJI} Silux {VERSION}")
        titulo.setObjectName("Headline")
        card.body.addWidget(titulo)

        lema = QLabel(
            "Perfilador de hardware para Linux. Lo que en Windows hacen "
            "CPU-Z, GPU-Z y HWMonitor, en un solo programa nativo: qué equipo "
            "tienes y qué está haciendo ahora mismo."
        )
        lema.setObjectName("Subhead")
        lema.setWordWrap(True)
        card.body.addWidget(lema)

        fila = ResponsiveRow(min_item_width=250)
        fila.add(self._bloque("Autoría", AUTORIA))
        fila.add(self._bloque("Construido con", CONSTRUIDO_CON))
        fila.add(self._bloque("Datos de terceros", DATOS_DE_TERCEROS))
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
        encabezado.setObjectName("CardTitle")
        columna.addWidget(encabezado)

        for nombre, detalle in lineas:
            etiqueta = QLabel(f"<b>{nombre}</b><br>{detalle}" if detalle else f"<b>{nombre}</b>")
            etiqueta.setObjectName("Muted")
            etiqueta.setWordWrap(True)
            etiqueta.setFont(ui_font(m.small_pt))
            etiqueta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            columna.addWidget(etiqueta)
        columna.addStretch(1)
        return caja

    def _build_about(self) -> Card:
        card = Card("Base de datos y configuración")
        m = theme.METRICS

        if db.available():
            data = db.load()
            counts = data.get("counts", {})
            sources = data.get("sources", {})
            text = (
                f"{counts.get('x86_intel', 0)} procesadores Intel · "
                f"{counts.get('x86_amd', 0)} AMD · {counts.get('arm_parts', 0)} piezas ARM · "
                f"{counts.get('sockets', 0)} encapsulados.\n"
                f"Generada de libcpuid {sources.get('libcpuid', {}).get('commit', '?')} "
                f"({sources.get('libcpuid', {}).get('date', '?')}) y "
                f"CPU-X {sources.get('cpu-x', {}).get('commit', '?')}.\n"
                "Se actualiza con:  python3 tools/gen_cpu_db.py"
            )
        else:
            text = ("No hay base de datos generada, así que no se puede identificar el nombre "
                    "en clave ni el encapsulado.\nGenérala con:  python3 tools/gen_cpu_db.py")

        info = QLabel(text)
        info.setObjectName("Muted")
        info.setWordWrap(True)
        info.setFont(ui_font(m.small_pt))
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(info)

        path = QLabel(f"Los ajustes se guardan en {config_path()}")
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
            theme=self.theme_box.currentData(),
            temperature_unit=self.unit_box.currentData(),
            density=self.density_box.currentData(),
            font_scale=self.font_box.currentData(),
            accent=self.accent_box.currentData(),
            network_unit=self.network_box.currentData(),
            show_all_features=self.all_features.isChecked(),
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
