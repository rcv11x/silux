"""Página de Monitor: todo lo que cambia con el tiempo.

Separar esto de la pestaña de CPU no es cosmética. Antes una sola página
respondía a dos preguntas («qué procesador es este» y «qué está haciendo
ahora») y no servía bien a ninguna: para mirar el socket había que pasar por
encima de gráficas, y para vigilar temperaturas había que pasar por encima de
la familia y el stepping. Aquí vive la segunda pregunta, con sitio para
hacerlo bien.

La columna de mínimos y máximos es lo que distingue a un monitor de hardware
de un visor de valores actuales: saber a cuánto llegó la temperatura mientras
jugabas importa más que saber a cuánto está ahora.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import render
from ...model import Sensor, SensorKind, Snapshot
from ...settings import Preferences
from ...tracking import Tracker
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    CoreMatrix,
    Notice,
    ResponsiveRow,
    SensorTree,
    StatTile,
    clear_layout,
)

# Cuántos decimales tiene sentido enseñar en cada magnitud.
DECIMALS = {
    SensorKind.TEMPERATURE: 1,
    SensorKind.VOLTAGE: 3,
    SensorKind.FAN: 0,
    SensorKind.POWER: 1,
    SensorKind.CURRENT: 2,
    SensorKind.ENERGY: 0,
}


class MonitorPage(QScrollArea):
    # Lo emite el árbol cuando el usuario arrastra una columna; la ventana lo
    # guarda para que el ajuste sobreviva al cierre.
    columns_resized = Signal(tuple)

    def __init__(self, palette: Palette, prefs: Preferences, tracker: Tracker, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._tracker = tracker
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        # Las cifras del procesador y la rejilla de núcleos se fueron a la
        # página de CPU, que es donde se buscan. Aquí ocupaban media pantalla
        # y dejaban el árbol —lo propio de esta página— en una rendija.
        sensors_card = Card()
        sensors_card.body.addWidget(self._build_sensor_header())
        self.tree = SensorTree(palette)
        self.tree.set_column_widths(prefs.sensor_columns)
        self.tree.itemExpanded.connect(lambda _: self.tree.refresh_height())
        self.tree.itemCollapsed.connect(lambda _: self.tree.refresh_height())
        self.tree.columnsResized.connect(self.columns_resized)
        sensors_card.body.addWidget(self.tree)
        self._layout.addWidget(sensors_card)

        self._hint_host = QVBoxLayout()
        self._hint_host.setSpacing(6)
        self._layout.addLayout(self._hint_host)

        self._layout.addStretch(1)

        self._core_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=40))
        self._structure: tuple = ()
        self._hint_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    def _build_sensor_header(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(2, 4, 2, 0)
        row.setSpacing(10)

        title = QLabel("SENSORES")
        title.setObjectName("CardTitle")

        self.count = QLabel("")
        self.count.setObjectName("Muted")
        self.count.setFont(ui_font(theme.METRICS.small_pt))

        self.reset_button = QPushButton("Reiniciar mín/máx")
        self.reset_button.setToolTip(
            "Vuelve a empezar a contar los extremos desde este momento.\n"
            "Útil justo antes de lanzar una prueba de carga."
        )
        self.reset_button.clicked.connect(self._reset_extremes)

        row.addWidget(title)
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(self.reset_button)
        return holder

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self._apply_sensors(snapshot)
        self._apply_hints(snapshot)

    def _temp(self, celsius: float) -> float:
        return celsius * 9 / 5 + 32 if self._prefs.fahrenheit else celsius

    def _apply_sensors(self, snapshot: Snapshot) -> None:
        tree = snapshot.sensor_tree()
        self._tracker.update_many((s.key, s.value) for s in snapshot.sensors)

        # La estructura solo cambia cuando aparece o desaparece hardware (al
        # cargar un módulo de sensores, por ejemplo), así que reconstruir es
        # excepcional y actualizar textos es lo normal.
        structure = tuple(
            (device, category, tuple(s.key for s in sensors))
            for device, categories in tree.items()
            for category, sensors in categories.items()
        )
        if structure != self._structure:
            self.tree.rebuild(tree)
            self._structure = structure
            self.count.setText(
                f"· {len(snapshot.sensors)} en {len(tree)} "
                + ("dispositivo" if len(tree) == 1 else "dispositivos")
            )

        avisos: dict[str, list[str]] = {}
        for sensor in snapshot.sensors:
            seguimiento = self._tracker.get(sensor.key)
            self.tree.update_row(
                sensor.key, self._values(sensor), self._tooltip(sensor),
                sensor.alarm_level,
                seguimiento.history if seguimiento else None,
            )
            if sensor.alarm_level != "ok":
                avisos.setdefault(sensor.device, []).append(sensor.alarm_level)

        # El aviso tiene que llegar a la rama cerrada: con ocho aparatos y cien
        # sensores, uno en rojo dentro de una rama plegada no lo ve nadie.
        for device in tree:
            niveles = avisos.get(device, [])
            self.tree.marcar_aviso(device, len(niveles), "crítico" in niveles)

    def _values(self, sensor: Sensor) -> list[str]:
        digits = DECIMALS.get(sensor.kind, 1)
        value, unit = self._converted(sensor)
        current = f"{value:.{digits}f} {unit}".strip()

        extremes = self._tracker.get(sensor.key)
        if extremes is None:
            return [current, "—", "—", "—"]

        low, high, average = (self._convert(sensor, v) for v in
                              (extremes.minimum, extremes.maximum, extremes.average))
        return [current, f"{low:.{digits}f}", f"{high:.{digits}f}", f"{average:.{digits}f}"]

    def _convert(self, sensor: Sensor, value: float) -> float:
        if sensor.kind is SensorKind.TEMPERATURE and self._prefs.fahrenheit:
            return value * 9 / 5 + 32
        return value

    def _converted(self, sensor: Sensor) -> tuple[float, str]:
        if sensor.kind is SensorKind.TEMPERATURE and self._prefs.fahrenheit:
            return sensor.value * 9 / 5 + 32, "°F"
        return sensor.value, sensor.unit

    def _tooltip(self, sensor: Sensor) -> str:
        lines = [f"{sensor.chip} · {sensor.key}"]
        limits = []
        if sensor.low is not None:
            limits.append(f"mínimo declarado {sensor.low:g} {sensor.unit}")
        if sensor.high is not None:
            limits.append(f"máximo declarado {sensor.high:g} {sensor.unit}")
        if sensor.critical is not None:
            limits.append(f"crítico {sensor.critical:g} {sensor.unit}")
        if limits:
            lines.append("\n".join(limits))
        if sensor.estimated_limits:
            lines.append("Este sensor no publica sus límites: los de arriba los "
                         "estima silux por el chip que es, y van del lado "
                         "prudente.")
        if sensor.alarm_level == "crítico":
            lines.append("⚠  Ha llegado al umbral crítico. Es donde el equipo "
                         "empieza a protegerse solo.")
        elif sensor.alarm_level == "alto":
            lines.append("⚠  Por encima del umbral alto. No es una avería, pero "
                         "conviene saberlo.")
        return "\n\n".join(lines)

    def _apply_hints(self, snapshot: Snapshot) -> None:
        signature = tuple(hint.module for hint in snapshot.driver_hints)
        if signature == self._hint_signature:
            return
        self._hint_signature = signature

        clear_layout(self._hint_host)
        for hint in snapshot.driver_hints:
            body = f"Cargando {hint.module} tendrías {hint.provides}."
            detail = hint.command + (f"\n{hint.caution}" if hint.caution else "")
            self._hint_host.addWidget(Notice("Falta un driver de sensores", body, detail))

    def _reset_extremes(self) -> None:
        self._tracker.reset()
