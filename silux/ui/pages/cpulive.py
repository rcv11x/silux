"""Lo que el procesador está haciendo ahora mismo: cifras vivas y núcleos.

Vivía dentro de la página de sensores, y su sitio es la de CPU: quien mira la
ficha del procesador quiere ver a cuánto va, no solo qué modelo es. En
Sensores ocupaba la mitad de la pantalla y dejaba el árbol —que es lo que esa
página tiene de propio— reducido a una rendija.

Está aparte porque lo usan dos sitios y porque el estado que guarda (el
historial de cada núcleo) tiene que sobrevivir entre muestreos.
"""

from __future__ import annotations

from collections import defaultdict, deque

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import render
from ...model import Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import Card, CoreMatrix, ResponsiveRow, StatTile

# Cuántas muestras guarda la curva de cada núcleo. Cuarenta a un segundo son
# cuarenta segundos, que es lo que cabe en un cuadro de ese tamaño sin que la
# línea se convierta en un borrón.
HISTORIAL = 40


class CpuLiveSection(QWidget):
    """Las cuatro cifras del procesador y la rejilla de núcleos."""

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._core_history: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=HISTORIAL))

        m = theme.METRICS
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(m.section_gap)

        column.addWidget(self._build_tiles())

        cores_card = Card("Núcleos lógicos")
        self.cores = CoreMatrix(palette)
        cores_card.body.addWidget(self.cores)
        # El punto de acento de las celdas no significa nada por sí solo. Esta
        # línea es la que lo traduce, y por eso va debajo de la rejilla y no en
        # la ficha de arriba: separadas, el punto se queda sin explicar.
        self.calidad = QLabel()
        self.calidad.setObjectName("Muted")
        self.calidad.setFont(ui_font(max(7, m.small_pt - 1)))
        self.calidad.setWordWrap(True)
        self.calidad.hide()
        cores_card.body.addWidget(self.calidad)
        column.addWidget(cores_card)

    def _build_tiles(self) -> QWidget:
        row = ResponsiveRow(min_item_width=150)
        self.tile_freq = StatTile("Frecuencia", "GHz", self._p)
        self.tile_usage = StatTile("Uso", "%", self._p)
        self.tile_temp = StatTile("Temperatura", "°C", self._p)
        self.tile_power = StatTile("Consumo", "W", self._p)

        # Cada gráfica sabe escribir su propia cifra cuando se la señala.
        intervalo = self._prefs.interval_s
        self.tile_freq.chart.set_formatter(lambda v: render.hz(v * 1e9), intervalo)
        self.tile_usage.chart.set_formatter(render.percent, intervalo)
        self.tile_temp.chart.set_formatter(
            lambda v: f"{v:.1f} °F" if self._prefs.fahrenheit else f"{v:.1f} °C",
            intervalo)
        self.tile_power.chart.set_formatter(render.watts, intervalo)
        for tile in (self.tile_freq, self.tile_usage, self.tile_temp, self.tile_power):
            row.add(tile)
        return row

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self._apply_tiles(snapshot)
        self._apply_cores(snapshot)

    def _temp(self, celsius: float) -> float:
        return celsius * 9 / 5 + 32 if self._prefs.fahrenheit else celsius

    def _apply_tiles(self, snapshot: Snapshot) -> None:
        cpu = snapshot.cpu
        if not cpu.types:
            return
        primary = cpu.types[0]
        clocks = primary.clocks

        if clocks.current_hz:
            self.tile_freq.update_value(f"{clocks.current_hz / 1e9:.2f}",
                                        clocks.current_hz / 1e9)
            self.tile_freq.chart.set_range(
                (clocks.min_hz or 0) / 1e9,
                (clocks.max_hz or clocks.max_turbo_hz or 0) / 1e9 or None,
            )
            # El mismo rango que dibuja la gráfica de debajo, para que la cifra
            # y el trazo digan lo mismo. Con base y máximo se leía «2.60 – 2.60
            # GHz» en un Xeon con el turbo apagado: cierto y sin información.
            suelo = clocks.min_hz or clocks.base_hz
            techo = clocks.max_hz or clocks.max_turbo_hz
            if suelo and techo:
                if abs(techo - suelo) < 1e7:          # menos de 10 MHz: es fijo
                    self.tile_freq.set_detail(f"fija en {techo / 1e9:.2f} GHz")
                else:
                    self.tile_freq.set_detail(
                        f"{suelo / 1e9:.2f} – {techo / 1e9:.2f} GHz")

        if cpu.usage_percent is not None:
            self.tile_usage.update_value(f"{cpu.usage_percent:.0f}", cpu.usage_percent)
            self.tile_usage.chart.set_range(0.0, 100.0)
            if cpu.load_average:
                self.tile_usage.set_detail(f"carga {cpu.load_average[0]:.2f}")

        temperature = primary.temp_c if primary.temp_c is not None else cpu.package_temp_c
        unit = "°F" if self._prefs.fahrenheit else "°C"
        self.tile_temp.set_unit(unit)
        if temperature is not None:
            shown = self._temp(temperature)
            self.tile_temp.update_value(f"{shown:.0f}", shown)
            if cpu.package_temp_c is not None:
                self.tile_temp.set_detail(
                    f"paquete {self._temp(cpu.package_temp_c):.0f} {unit}")

        power = cpu.power
        if power.package_w is not None:
            self.tile_power.update_value(f"{power.package_w:.0f}", power.package_w)
            self.tile_power.chart.set_range(0.0, power.limit_long_w)
            self.tile_power.set_detail(
                render.power_headline(power) or render.power_breakdown(power),
                render.power_tooltip(power),
            )

    def _apply_cores(self, snapshot: Snapshot) -> None:
        # Los núcleos que el firmware marca como los mejores de la pieza. Se
        # marcan los dos hilos del mismo núcleo porque el silicio es el mismo.
        orden = render.core_quality(snapshot.cpu.logical)
        cabeza = {core for core, nota, _ in orden if orden and nota == orden[0][1]}

        cells = []
        for logical in snapshot.cpu.logical:
            if logical.usage_percent is not None:
                self._core_history[logical.index].append(logical.usage_percent)
            freq = render.hz(logical.freq_hz)
            detail = freq
            if logical.temp_c is not None:
                detail = f"{freq}  {self._temp(logical.temp_c):.0f}°"
            cells.append({
                "name": f"CPU {logical.index}",
                "detail": detail,
                "detail_short": freq,
                "usage": logical.usage_percent,
                "history": tuple(self._core_history[logical.index]),
                "starred": logical.core_id in cabeza,
            })
        self.cores.set_cores(cells)

        if orden:
            reparto = render.core_quality_spread(snapshot.cpu.logical)
            self.calidad.setText(
                f'<span style="color:{self._p.accent}">●</span> '
                f"{render.best_cores(snapshot.cpu.logical)}: los que mejor "
                f"salieron de la oblea según el firmware, y a los que el "
                f"planificador manda el trabajo de un hilo suelto. "
                f"{reparto[0].upper()}{reparto[1:]}."
            )
            self.calidad.show()
        else:
            self.calidad.hide()
