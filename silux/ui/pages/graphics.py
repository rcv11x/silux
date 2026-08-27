"""Página de gráficos: qué tarjeta hay y qué está haciendo.

Es la sección que más fuentes junta de todo el programa, y por eso las tarjetas
están separadas por procedencia y no por tema: lo que dice el nodo PCI, lo que
dice el driver, lo que dicen las APIs. Cuando algo falta se ve dónde falta.

Con dos gráficas (una integrada y una dedicada, lo normal en un portátil) se
repite el bloque entero, igual que la pestaña de CPU repite el suyo para los
núcleos P y los E.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...model import Gpu, Need, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import (Card, ChipRow, InfoGrid, Notice, ResponsiveRow, StackedBar,
                       StatTile, Table, clear_layout)

NEED_TITLES = {
    Need.ROOT: "Requiere permisos",
    Need.DRIVER: "Falta un driver",
    Need.HARDWARE: "Este equipo no lo expone",
    Need.DATABASE: "Falta en la base de datos",
    Need.PLATFORM: "No aplica a esta plataforma",
    Need.ERROR: "Falló al leerse",
}

CARD_FIELDS = (
    "Fabricante", "Ensamblada por", "Nombre en clave", "Driver", "Versión del driver",
    "Identificador", "Subsistema", "Ranura PCI", "Nodo DRM", "BIOS de video",
    "Unidades de proceso", "Unidades de rasterizado", "Motores de sombreado",
    "Identificador único",
)

MEMORY_FIELDS = ("Total", "En uso", "Tipo", "Bus", "Ancho de banda", "Tasa de datos",
                 "Visible por la CPU", "Resizable BAR", "Chips",
                 "Prestada al sistema")

CLOCK_FIELDS = ("Núcleo", "Núcleo (máximo)", "Memoria", "Memoria (efectiva)",
                "Memoria (máximo)", "SoC", "Perfil de rendimiento",
                "Enlace", "Enlace (máximo)")

SENSOR_FIELDS = ("Estado", "Temperatura", "Punto caliente", "Chips de memoria",
                 "Regulador gráfico", "Regulador del SoC", "Regulador de memoria",
                 "Consumo", "Límite de consumo", "Ventilador",
                 "Voltaje", "Voltaje del SoC", "Voltaje de memoria", "Uso de video")

API_HEADERS = ("API", "Versión", "Driver", "Detalle")
DISPLAY_HEADERS = ("Salida", "Monitor", "Resolución", "Refresco", "Tamaño",
                   "Color y HDR", "Fabricado")


class GpuSection(QWidget):
    """El bloque completo de una tarjeta."""

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        m = theme.METRICS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.section_gap)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_tiles())

        fila = ResponsiveRow(min_item_width=280)
        self.card = self._grid_card(fila, "Tarjeta", CARD_FIELDS)
        fila.add(self._build_memory_card())
        layout.addWidget(fila)

        fila = ResponsiveRow(min_item_width=280)
        self.clocks = self._grid_card(fila, "Relojes y enlace", CLOCK_FIELDS)
        fila.add(self._build_sensor_card())
        layout.addWidget(fila)

        api_card = Card("Bibliotecas gráficas")
        self.apis = Table(API_HEADERS, numeric=(False, True, False, False))
        api_card.body.addWidget(self.apis)
        layout.addWidget(api_card)

        display_card = Card("Monitores y salidas de video")
        self.displays = Table(DISPLAY_HEADERS,
                              numeric=(False, False, True, True, True, False))
        display_card.body.addWidget(self.displays)
        layout.addWidget(display_card)

        self._chip_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    @staticmethod
    def _grid_card(host: ResponsiveRow, title: str, fields: tuple[str, ...]) -> InfoGrid:
        card = Card(title)
        grid = InfoGrid()
        for name in fields:
            grid.add(name)
        card.body.addWidget(grid)
        host.add(card)
        return grid

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel("Leyendo la gráfica…")
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        return card

    def _build_tiles(self) -> QWidget:
        fila = ResponsiveRow(min_item_width=150)
        self.tile_usage = StatTile("Uso", "%", self._p)
        self.tile_temp = StatTile("Temperatura", "°C", self._p)
        self.tile_power = StatTile("Consumo", "W", self._p)
        self.tile_vram = StatTile("VRAM ocupada", "%", self._p)
        for tile in (self.tile_usage, self.tile_temp, self.tile_power, self.tile_vram):
            fila.add(tile)
        self.tile_usage.chart.set_range(0, 100)
        self.tile_vram.chart.set_range(0, 100)

        intervalo = self._prefs.interval_s
        self.tile_usage.chart.set_formatter(render.percent, intervalo)
        self.tile_vram.chart.set_formatter(render.percent, intervalo)
        self.tile_power.chart.set_formatter(render.watts, intervalo)
        self.tile_temp.chart.set_formatter(
            lambda v: render.temperature(v, False), intervalo)
        return fila

    def _build_sensor_card(self) -> Card:
        card = Card("Sensores")
        self.power_bar = StackedBar(self._p)
        self.sensors = InfoGrid()
        for name in SENSOR_FIELDS:
            self.sensors.add(name)
        card.body.addWidget(self.power_bar)
        card.body.addWidget(self.sensors)
        return card

    def _build_memory_card(self) -> Card:
        card = Card("Memoria de video")
        self.memory_bar = StackedBar(self._p)
        self.memory = InfoGrid()
        for name in MEMORY_FIELDS:
            self.memory.add(name)
        card.body.addWidget(self.memory_bar)
        card.body.addWidget(self.memory)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, gpu: Gpu) -> None:
        d = render.DASH
        self.title.setText(gpu.display_name)
        self.subtitle.setText(" · ".join(p for p in (
            gpu.subsystem_name, gpu.codename, render.pcie_link(gpu.link)) if p))
        self._apply_badges(gpu)
        self._apply_tiles(gpu)

        c = self.card.set
        c("Fabricante", gpu.vendor or d)
        c("Ensamblada por", gpu.subsystem_name or d)
        c("Nombre en clave", gpu.codename or d)
        c("Driver", gpu.driver or d)
        c("Versión del driver", gpu.driver_version or d)
        c("Identificador", gpu.pci_id or d)
        c("Subsistema", gpu.subsystem_id or d)
        c("Ranura PCI", gpu.pci_slot or d)
        c("Nodo DRM", gpu.drm_node or d)
        c("BIOS de video", gpu.vbios or d)
        c("Unidades de proceso", render.compute_units(gpu),
          tooltip="Cada fabricante las cuenta a su manera y no son equivalentes: "
                  "una unidad de cómputo de AMD agrupa decenas de núcleos como "
                  "los que NVIDIA cuenta de uno en uno.")
        c("Unidades de rasterizado", str(gpu.rops) if gpu.rops else d,
          tooltip="Los ROP, que son los que escriben los píxeles ya calculados "
                  "en la imagen final.")
        c("Motores de sombreado", str(gpu.shader_engines) if gpu.shader_engines else d)
        c("Identificador único", gpu.unique_id or d)

        self._apply_memory(gpu)

        k = self.clocks.set
        k("Núcleo", render.hz(gpu.clocks.core_hz))
        k("Núcleo (máximo)", render.hz(gpu.clocks.core_max_hz))
        k("Memoria", render.hz(gpu.clocks.memory_hz))
        k("Memoria (efectiva)", render.hz(gpu.clocks.memory_effective_hz),
          tooltip="El reloj al que viajan los datos, que es el que anuncian las "
                  "fichas técnicas. La memoria mueve varias transferencias por "
                  "cada ciclo de su reloj de comando.")
        k("Memoria (máximo)", render.hz(gpu.clocks.memory_max_hz))
        k("SoC", render.hz(gpu.clocks.soc_hz))
        k("Perfil de rendimiento", gpu.clocks.performance_level or d)
        k("Enlace", render.pcie_link(gpu.link),
          tooltip=render.pcie_note(gpu.link) or "")
        k("Enlace (máximo)", render.pcie_link(gpu.link, maximum=True))

        if gpu.power_w is not None and gpu.power_cap_w:
            self.power_bar.set_segments(
                [("En uso", gpu.power_w, "accent"),
                 ("Sin usar", max(0.0, gpu.power_cap_w - gpu.power_w), "line")],
                total=gpu.power_cap_w,
                formatter=render.watts,
            )
            self.power_bar.show()
        else:
            self.power_bar.hide()

        s = self.sensors.set
        fahrenheit = self._prefs.fahrenheit
        s("Estado", render.throttle_state(gpu),
          tooltip="Si el firmware está recortando el rendimiento y por qué. Es "
                  "lo que explica que un juego rinda menos de lo que debería "
                  "sin que la tarjeta parezca estar al límite.")
        s("Temperatura", render.temperature(gpu.temp_c, fahrenheit))
        s("Punto caliente", render.temperature(gpu.hotspot_c, fahrenheit),
          tooltip="El punto más caliente del chip, siempre por encima de la "
                  "temperatura de borde. Es el que gobierna el ventilador.")
        s("Chips de memoria", render.temperature(gpu.memory_temp_c, fahrenheit))
        s("Consumo", render.watts(gpu.power_w))
        s("Límite de consumo", render.watts(gpu.power_cap_w))
        s("Ventilador", render.fan(gpu.fan_rpm, gpu.fan_percent))
        s("Regulador gráfico", render.temperature(gpu.vr_gfx_c, fahrenheit),
          tooltip="Los reguladores que alimentan al chip. No están en hwmon: "
                  "los cuenta el microcontrolador de la propia tarjeta.")
        s("Regulador del SoC", render.temperature(gpu.vr_soc_c, fahrenheit))
        s("Regulador de memoria", render.temperature(gpu.vr_memory_c, fahrenheit))
        s("Voltaje", render.volts(gpu.voltage_v))
        s("Voltaje del SoC", render.volts(gpu.voltage_soc_v))
        s("Voltaje de memoria", render.volts(gpu.voltage_memory_v))
        s("Uso de video", render.percent(gpu.video_busy_percent),
          tooltip="Los motores de codificación y decodificación de video, que "
                  "trabajan aparte del resto de la GPU.")

        self.apis.set_rows([
            (api.name, api.version or d, api.driver or d, api.extra or d)
            for api in gpu.apis
        ] or [("Sin bibliotecas gráficas", d, d, d)])

        self.displays.set_rows([_fila_de_salida(salida) for salida in gpu.displays]
                               or [("Sin salidas de video", d, d, d, d, d)])

    def _apply_badges(self, gpu: Gpu) -> None:
        chips = [c for c in (
            gpu.codename,
            f"{gpu.driver} {gpu.driver_version}".strip() if gpu.driver else None,
            render.size(gpu.memory.total_bytes) if gpu.memory.total_bytes else None,
            render.compute_units_short(gpu),
            "integrada" if gpu.integrated else None,
            "principal" if gpu.primary else None,
        ) if c]
        firma = tuple(chips)
        if firma != self._chip_signature:
            self._chip_signature = firma
            self.badges.set_chips(chips, highlight_first=True)

    def _apply_tiles(self, gpu: Gpu) -> None:
        self.tile_usage.update_value(
            f"{gpu.busy_percent:.0f}" if gpu.busy_percent is not None else render.DASH,
            gpu.busy_percent)
        self.tile_usage.set_detail(
            f"memoria {render.percent(gpu.memory_busy_percent)}"
            if gpu.memory_busy_percent is not None else "")

        temperatura = gpu.temp_c
        if self._prefs.fahrenheit and temperatura is not None:
            temperatura = temperatura * 9 / 5 + 32
        self.tile_temp.set_unit("°F" if self._prefs.fahrenheit else "°C")
        self.tile_temp.update_value(
            f"{temperatura:.0f}" if temperatura is not None else render.DASH, temperatura)
        self.tile_temp.set_detail(
            f"punto caliente {render.temperature(gpu.hotspot_c, self._prefs.fahrenheit)}"
            if gpu.hotspot_c is not None else "")

        self.tile_power.update_value(
            f"{gpu.power_w:.0f}" if gpu.power_w is not None else render.DASH, gpu.power_w)
        self.tile_power.set_detail(
            f"de {render.watts(gpu.power_cap_w)}" if gpu.power_cap_w else "")

        porcentaje = gpu.memory.used_percent
        self.tile_vram.update_value(
            f"{porcentaje:.0f}" if porcentaje is not None else render.DASH, porcentaje)
        self.tile_vram.set_detail(render.gpu_memory_summary(gpu.memory)
                                  if gpu.memory.total_bytes else "")

    def _apply_memory(self, gpu: Gpu) -> None:
        d = render.DASH
        memoria = gpu.memory
        if memoria.total_bytes and memoria.used_bytes is not None:
            self.memory_bar.set_segments(
                [("En uso", memoria.used_bytes, "accent"),
                 ("Libre", memoria.total_bytes - memoria.used_bytes, "line")],
                total=memoria.total_bytes,
                formatter=render.size,
            )
            self.memory_bar.show()
        else:
            self.memory_bar.hide()

        m = self.memory.set
        m("Total", render.size(memoria.total_bytes))
        m("En uso", render.gpu_memory_summary(memoria) if memoria.total_bytes else d)
        m("Tipo", render.vram_kind(memoria))
        m("Bus", render.vram_bus(memoria))
        m("Ancho de banda", render.bandwidth(memoria.bandwidth_bytes),
          tooltip="Cuántos datos caben por el bus en un segundo: la tasa de la "
                  "memoria por la anchura del bus. Es lo que limita a una "
                  "gráfica antes que la propia potencia de cálculo.")
        m("Tasa de datos", f"{memoria.data_rate_hz / 1e9:.1f} Gbps"
          if memoria.data_rate_hz else d,
          tooltip="La velocidad real a la que viajan los datos. No es el reloj: "
                  "una GDDR6 a 1258 MHz mueve dieciséis transferencias por "
                  "ciclo, o sea 20 Gbps.")
        m("Visible por la CPU", render.size(memoria.visible_bytes)
          if memoria.visible_bytes else d,
          tooltip="Cuánta VRAM puede direccionar la CPU de una vez.")
        m("Resizable BAR", render.resizable_bar(memoria),
          tooltip="Con Resizable BAR la CPU ve toda la memoria de la tarjeta de "
                  "una vez. Sin él solo alcanza una ventana de 256 MB y el "
                  "driver tiene que ir moviéndola, que cuesta rendimiento. Se "
                  "activa en la BIOS, y hace falta que la placa y la tarjeta lo "
                  "admitan las dos.")
        m("Chips", memoria.vendor or d)
        prestada = d
        if memoria.gtt_total_bytes:
            prestada = render.size(memoria.gtt_total_bytes)
            if memoria.gtt_used_bytes is not None:
                prestada = f"{render.size(memoria.gtt_used_bytes)} de {prestada}"
        m("Prestada al sistema", prestada,
          tooltip="GTT: memoria RAM del equipo que el driver le presta a la "
                  "tarjeta cuando la VRAM se queda corta. No es memoria de la "
                  "gráfica, por eso va aparte.")


def _fila_de_salida(salida) -> tuple[str, ...]:
    """Una línea de la tabla de monitores; la mitad se queda vacía si no hay."""
    d = render.DASH
    if not salida.connected:
        return (salida.connector, "libre", d, d, d, d, d)
    monitor = salida.monitor
    if monitor is None:
        # Conectada pero sin EDID legible: pasa con algunos adaptadores y KVM.
        return (salida.connector, "sin identificar", salida.resolution or d,
                d, d, d, d)
    return (
        salida.connector,
        render.monitor_name(monitor),
        salida.resolution or d,
        monitor.refresh_range or d,
        f'{monitor.diagonal_inches}"' if monitor.diagonal_inches else d,
        render.monitor_color(monitor),
        monitor.made or d,
    )


class GraphicsPage(QScrollArea):
    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(m.page_margin, m.page_margin,
                                        m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        self._empty = QLabel("No se ha encontrado ninguna tarjeta gráfica.")
        self._empty.setObjectName("Subhead")
        self._empty.setWordWrap(True)
        self._empty.hide()
        self._layout.addWidget(self._empty)

        self._sections_host = QVBoxLayout()
        self._sections_host.setSpacing(m.section_gap)
        self._layout.addLayout(self._sections_host)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        self._layout.addLayout(self._notices_host)

        self._layout.addStretch(1)

        self._sections: list[GpuSection] = []
        self._notice_signature: tuple = ()

    def apply(self, snapshot: Snapshot) -> None:
        self._empty.setVisible(not snapshot.gpus)

        # Las secciones se crean una vez y luego se reescriben: en una página
        # que se repinta cada segundo, rehacerlas dejaría widgets vivos a miles.
        while len(self._sections) < len(snapshot.gpus):
            seccion = GpuSection(self._p, self._prefs)
            self._sections.append(seccion)
            self._sections_host.addWidget(seccion)
        for sobrante in self._sections[len(snapshot.gpus):]:
            sobrante.hide()

        for seccion, gpu in zip(self._sections, snapshot.gpus):
            seccion.show()
            seccion.apply(gpu)

        self._apply_notices(snapshot)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        notes = snapshot.notes_for("gpus")
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(NEED_TITLES.get(note.need, note.need.value), note.message, note.hint)
            )
