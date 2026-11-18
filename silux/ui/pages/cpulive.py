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
from ...i18n import _
from ...model import Snapshot, thread_name
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..corematrix import CoreMatrix
from ..widgets import Card, ResponsiveRow, StatTile

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

        cores_card = Card(_("cpu.card.cores"))
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
        self.tile_freq = StatTile(_("gpu.tile.clock"), "GHz", self._p)
        self.tile_usage = StatTile(_("gpu.tile.usage"), "%", self._p)
        self.tile_temp = StatTile(_("gpu.tile.temp"), "°C", self._p)
        self.tile_power = StatTile(_("gpu.tile.power"), "W", self._p)
        # Lo más ancho que puede escribir cada una: «0.00» gigahercios y tres
        # cifras para el uso, los grados (también en Fahrenheit) y los vatios.
        self.tile_freq.reserve([render.figure(9.99, 2)])
        for tile in (self.tile_usage, self.tile_temp, self.tile_power):
            tile.reserve([render.figure(999)])

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
            self.tile_freq.update_value(render.figure(clocks.current_hz / 1e9, 2),
                                        clocks.current_hz / 1e9)
            # Hasta el techo del silicio, no hasta el que aplica el kernel: con
            # el gobernador `performance` la frecuencia vive en ese techo, y la
            # curva pegada arriba rellenaba todo el alto —una barra vertical
            # mientras la gráfica se llenaba—. Y como el kernel lo mueve cuando
            # se apaga y se enciende el turbo, las muestras de 4,0 GHz quedaban
            # dibujadas a la altura de las de 2,9.
            suelo = clocks.min_hz or clocks.base_hz
            techo = clocks.highest_hz
            self.tile_freq.chart.set_range((suelo or 0) / 1e9,
                                           techo / 1e9 if techo else None)
            # El mismo rango que dibuja la gráfica de debajo, para que la cifra
            # y el trazo digan lo mismo. Con base y máximo se leía «2.60 – 2.60
            # GHz» en un Xeon con el turbo apagado: cierto y sin información.
            if suelo and techo:
                if abs(techo - suelo) < 1e7:          # menos de 10 MHz: es fijo
                    self.tile_freq.set_detail(f"fija en {render.hz(techo)}")
                else:
                    self.tile_freq.set_detail(f"{render.hz(suelo)} – {render.hz(techo)}")

        if cpu.usage_percent is not None:
            self.tile_usage.update_value(render.figure(cpu.usage_percent), cpu.usage_percent)
            self.tile_usage.chart.set_range(0.0, 100.0)
            if cpu.load_average:
                self.tile_usage.set_detail(_("cpu.tile.load").format(v=f"{cpu.load_average[0]:.2f}"))

        # La misma que Inicio: la decide el modelo. Debajo, la media de los
        # núcleos cuando la cifra grande es la del encapsulado.
        temperature = cpu.temperature_c
        unit = "°F" if self._prefs.fahrenheit else "°C"
        self.tile_temp.set_unit(unit)
        if temperature is not None:
            shown = self._temp(temperature)
            self.tile_temp.update_value(render.figure(shown), shown)
            # La media de los núcleos, debajo de la del encapsulado, solo si
            # hay sensores por núcleo. En AMD no los hay: `temp_c` del tipo es
            # entonces la misma Tctl de arriba, y «núcleos 59 °C» la repetía
            # con un nombre que no era el suyo.
            por_nucleo = any(l.temp_c is not None for l in cpu.logical)
            self.tile_temp.set_detail(
                _("cpu.tile.cores").format(
                    v=f"{self._temp(primary.temp_c):.0f} {unit}")
                if por_nucleo and cpu.package_temp_c is not None
                and primary.temp_c is not None else "")

        power = cpu.power
        if power.package_w is not None:
            self.tile_power.update_value(render.figure(power.package_w), power.package_w)
            self.tile_power.chart.set_range(0.0, power.limit_long_w)
            self.tile_power.set_detail(
                render.power_headline(power) or render.power_breakdown(power),
                render.power_tooltip(power),
            )
        else:
            # El contador de energía existe en casi todos los procesadores,
            # pero muchas distribuciones lo reservan a root desde CVE-2020-8694.
            # Sin esto la ficha se quedaba con «— W» y ni una palabra, que se
            # lee como que el programa no sabe leerlo. El motivo ya está abajo,
            # en su aviso; aquí va la mitad que se ve sin bajar.
            # Un dato, un motivo: el candado solo si lo que falta es un
            # permiso. Si el motivo es otro, ya lo dice su aviso, y aquí no
            # se da uno distinto.
            nota = snapshot.permission_note("cpu.power")
            if nota is not None:
                self.tile_power.set_locked(_("lock.detail"), render.lock_tooltip(nota))
            else:
                # Sin nota no hay motivo que dar: es la primera vuelta (el
                # consumo sale de restar dos lecturas) o un equipo volcado.
                self.tile_power.update_value(render.DASH, None)
                self.tile_power.set_detail("")

    def _apply_cores(self, snapshot: Snapshot) -> None:
        # Los núcleos que el firmware marca como los mejores de la pieza. Se
        # marcan los dos hilos del mismo núcleo porque el silicio es el mismo.
        cabeza = render.best_core_ids(snapshot.cpu.logical)

        cells = []
        for logical in snapshot.cpu.logical:
            if logical.usage_percent is not None:
                self._core_history[logical.index].append(logical.usage_percent)
            freq = render.hz(logical.freq_hz)
            detail = freq
            if logical.temp_c is not None:
                detail = f"{freq}  {self._temp(logical.temp_c):.0f}°"
            cells.append({
                "name": thread_name(logical.index),
                "detail": detail,
                "detail_short": freq,
                "usage": logical.usage_percent,
                "history": tuple(self._core_history[logical.index]),
                "starred": logical.core_id in cabeza,
            })
        self.cores.set_cores(cells)

        if cabeza:
            reparto = render.core_quality_spread(snapshot.cpu.logical)
            hilos = render.starred_cpus(snapshot.cpu.logical)
            # Con SMT las estrellas son el doble que los núcleos, y sin decirlo
            # quien mira cuenta cuatro y lee dos.
            aclaracion = (_("cpu.best.threads").format(hilos=hilos)
                          if hilos else "")
            # Una frase que diga qué es la estrella, y el porqué al pasar el
            # ratón: entero eran dos renglones de letra pequeña a todo el ancho
            # debajo de la rejilla.
            self.calidad.setText(
                f'<span style="color:{self._p.accent}">&#9733;</span> '
                + _("cpu.best.short").format(
                    nucleos=render.best_cores(snapshot.cpu.logical),
                    hilos=aclaracion)
            )
            self.calidad.setToolTip(_("cpu.best.tip").format(
                reparto=f"{reparto[0].upper()}{reparto[1:]}"))
            self.calidad.show()
        else:
            self.calidad.hide()
