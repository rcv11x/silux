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

from ... import db
from ...settings import Preferences, config_path
from .. import theme
from ..theme import ui_font
from ..widgets import Card, ResponsiveRow

THEMES = (("Seguir al sistema", "system"), ("Claro", "light"), ("Oscuro", "dark"))
UNITS = (("Celsius (°C)", "c"), ("Fahrenheit (°F)", "f"))
DENSITIES = (("Amplia", "spacious"), ("Normal", "normal"), ("Compacta", "compact"))


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

        self.unit_box = QComboBox()
        for label, value in UNITS:
            self.unit_box.addItem(label, value)
        self.unit_box.setCurrentIndex([v for _, v in UNITS].index(self._prefs.temperature_unit))
        self.unit_box.currentIndexChanged.connect(self._emit)
        card.body.addWidget(_Field("Unidad de temperatura", self.unit_box))

        reset = QPushButton("Restablecer valores por defecto")
        reset.clicked.connect(self._reset)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reset)
        card.body.addLayout(row)
        return card

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
