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

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...model import Gpu, Need, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import (Card, ChipRow, Divider, InfoGrid, Notice, ResponsiveRow, StackedBar,
                       StatTile, Table, clear_layout)

# Qué se puede arreglar y qué no. Lo primero va en ámbar y lleva botón cuando
# lo hay; lo segundo, en gris: un hecho del hardware no es una avería.
NEED_TONES = {
    Need.ROOT: "warn",
    Need.DRIVER: "warn",
    Need.DATABASE: "warn",
    Need.HARDWARE: "idle",
    Need.PLATFORM: "idle",
    Need.ERROR: "bad",
}

# Un aspa se lee de un vistazo; un «No» hay que leerlo.
SI = "✓"
NO = "·"

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

ENGINE_HEADERS = ("Motor", "Función", "Uso", "Sabe hacer")
CODEC_HEADERS = ("Códec", "Decodifica", "Codifica", "Profundidad", "Perfiles")

API_HEADERS = ("API", "Versión", "Driver", "Detalle")
DISPLAY_HEADERS = ("Salida", "Monitor", "Resolución", "Refresco", "Tamaño",
                   "Color y HDR", "Fabricado")


class GpuSection(QWidget):
    """El bloque completo de una tarjeta."""

    # El uso y el consumo de una Intel salen de contadores del kernel que
    # piden permisos. Sin botón aquí había que ir a Memoria o a
    # Almacenamiento a darlos y volver, que es pedirle al usuario que adivine.
    elevation_requested = Signal()

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

        # Justo debajo de las fichas, que es donde se ve el hueco. Antes esto
        # vivía al final de la página: para enterarse de por qué las cuatro
        # fichas están vacías había que pasar por delante de todas las
        # tarjetas vacías, así que en la práctica nadie lo leía.
        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        self._notices_host.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._notices_host)
        self._notice_signature: tuple = ()
        self.elevation_buttons: list = []

        fila = ResponsiveRow(min_item_width=280)
        self.card = self._grid_card(fila, "Tarjeta", CARD_FIELDS)
        fila.add(self._build_memory_card())
        layout.addWidget(fila)

        fila = ResponsiveRow(min_item_width=280)
        self.clocks = self._grid_card(fila, "Relojes y enlace", CLOCK_FIELDS)
        fila.add(self._build_sensor_card())
        layout.addWidget(fila)

        # Una tarjeta moderna no es un bloque «al 40 %»: son varias unidades
        # independientes, y saber cuál va cargada distingue «no da más» de
        # «solo está saturado el decodificador de video».
        self.engine_card = Card("Motores gráficos")
        self.engine_summary = InfoGrid()
        self.engine_summary.add("En reposo")
        self.engines = Table(ENGINE_HEADERS, numeric=(False, False, True, False))
        self.engine_card.body.addWidget(self.engine_summary)
        # El reposo habla de la tarjeta entera y la tabla de cada motor: son
        # dos cosas distintas. Pegadas, «En reposo» se leía como una fila más
        # de la tabla, justo encima de su cabecera.
        self.engine_card.body.addSpacing(theme.METRICS.card_gap)
        self.engine_card.body.addWidget(Divider())
        self.engine_card.body.addSpacing(theme.METRICS.card_gap)
        self.engine_card.body.addWidget(self.engines)
        layout.addWidget(self.engine_card)

        # Lo que decide si un vídeo se ve gastando dos vatios o quemando la
        # CPU. Y decodificar no es codificar: casi todas leen AV1 y muy pocas
        # lo escriben.
        self.codec_card = Card("Códecs de video por hardware")
        self.codecs = Table(CODEC_HEADERS,
                            numeric=(False, False, False, True, False))
        self.codec_card.body.addWidget(self.codecs)
        layout.addWidget(self.codec_card)

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
        # La frecuencia del núcleo es la primera cifra que se mira de una
        # gráfica y estaba solo en la ficha de relojes, sin curva. Sin ella no
        # se distingue una tarjeta que va al máximo de una que se está
        # frenando, que es lo que las otras cuatro dejan a medio explicar.
        self.tile_clock = StatTile("Frecuencia", "MHz", self._p)
        # Y el bus de memoria, que no es lo mismo que la VRAM ocupada: una dice
        # cuánta cabe y esta cuánta se está moviendo. Una tarjeta con la VRAM
        # llena y el bus parado tiene datos cargados y no los está tocando.
        self.tile_membus = StatTile("Bus de memoria", "%", self._p)

        for tile in (self.tile_usage, self.tile_clock, self.tile_temp,
                     self.tile_power, self.tile_vram, self.tile_membus):
            fila.add(tile)
        self.tile_usage.chart.set_range(0, 100)
        self.tile_vram.chart.set_range(0, 100)
        self.tile_membus.chart.set_range(0, 100)

        intervalo = self._prefs.interval_s
        self.tile_usage.chart.set_formatter(render.percent, intervalo)
        self.tile_vram.chart.set_formatter(render.percent, intervalo)
        self.tile_membus.chart.set_formatter(render.percent, intervalo)
        self.tile_power.chart.set_formatter(render.watts, intervalo)
        self.tile_clock.chart.set_formatter(
            lambda v: render.hz(v * 1e6), intervalo)
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

    def set_notes(self, notes) -> None:
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        self.elevation_buttons = []
        for note in notes:
            aviso = Notice(
                NEED_TITLES.get(note.need, note.need.value), note.message, note.hint,
                tone=NEED_TONES.get(note.need, "warn"),
                action=("Leer con permisos de administrador"
                        if note.need is Need.ROOT else None),
            )
            if aviso.action_button is not None:
                aviso.action_clicked.connect(self.elevation_requested)
                self.elevation_buttons.append(aviso.action_button)
            self._notices_host.addWidget(aviso)

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

        self._apply_engines(gpu)
        self._apply_codecs(gpu)
        self.apis.set_rows([
            (api.name, api.version or d, api.driver or d, api.extra or d)
            for api in gpu.apis
        ] or [("Sin bibliotecas gráficas", d, d, d)])

        self.displays.set_rows([_fila_de_salida(salida) for salida in gpu.displays]
                               or [("Sin salidas de video", d, d, d, d, d)])

    def _apply_engines(self, gpu: Gpu) -> None:
        """Los motores de la tarjeta, si el driver los publica.

        La tarjeta se esconde entera cuando no hay ninguno: en AMD y NVIDIA el
        kernel no los enumera, y una tabla vacía no explica nada.
        """
        self.engine_card.setVisible(bool(gpu.engines))
        if not gpu.engines:
            return
        self.engine_summary.set("En reposo", render.percent(gpu.sleep_percent))
        self.engines.set_rows([
            (motor.name,
             motor.kind or render.DASH,
             render.percent(motor.busy_percent),
             ", ".join(motor.capabilities) or render.DASH)
            for motor in gpu.engines
        ])

    def _apply_codecs(self, gpu: Gpu) -> None:
        """Qué códecs acelera la tarjeta, y en qué sentido.

        Se esconde entera si no hay VA-API que preguntar: una tabla vacía se
        lee como «esta tarjeta no acelera nada», que es justo lo contrario de
        lo que quiere decir.
        """
        self.codec_card.setVisible(bool(gpu.codecs))
        if not gpu.codecs:
            return
        self.codecs.set_rows([
            (codec.name,
             SI if codec.decode else NO,
             SI if codec.encode else NO,
             f"{codec.max_bit_depth} bits" if codec.max_bit_depth else render.DASH,
             ", ".join(codec.profiles) or render.DASH)
            for codec in gpu.codecs
        ])

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
        # El detalle del uso deja de repetir la memoria: ahora tiene su cuadro.
        self.tile_usage.set_detail(
            f"video {render.percent(gpu.video_busy_percent)}"
            if gpu.video_busy_percent else "")

        relojes = gpu.clocks
        nucleo_mhz = relojes.core_hz / 1e6 if relojes.core_hz is not None else None
        self.tile_clock.update_value(
            f"{nucleo_mhz:.0f}" if nucleo_mhz is not None else render.DASH,
            nucleo_mhz)
        # La escala llega hasta el techo de la tabla DPM, que es lo que hace
        # que la curva diga «va al máximo» en vez de solo «va subiendo».
        if relojes.core_max_hz:
            self.tile_clock.chart.set_range(0, relojes.core_max_hz / 1e6)
        # Las dos cifras de la memoria son ciertas y distintas: el reloj y la
        # tasa de datos, que en GDDR6 son dieciséis transferencias por ciclo.
        if relojes.memory_effective_hz:
            self.tile_clock.set_detail(
                f"memoria {render.hz(relojes.memory_effective_hz)}")
        elif relojes.memory_hz:
            self.tile_clock.set_detail(f"memoria {render.hz(relojes.memory_hz)}")
        else:
            self.tile_clock.set_detail("")

        bus = gpu.memory_busy_percent
        self.tile_membus.update_value(
            f"{bus:.0f}" if bus is not None else render.DASH, bus)
        # Contra qué se compara ese porcentaje: sin el ancho de banda de la
        # tarjeta, un 21 % no dice si son megas o gigas por segundo.
        if bus is not None and gpu.memory.bandwidth_bytes:
            movido = gpu.memory.bandwidth_bytes * bus / 100
            self.tile_membus.set_detail(f"{render.bandwidth(int(movido))} de "
                                        f"{render.bandwidth(gpu.memory.bandwidth_bytes)}")
        else:
            self.tile_membus.set_detail("")

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
        # La ficha ya enseña el porcentaje; aquí solo hace falta contra qué.
        self.tile_vram.set_detail(f"de {render.size(gpu.memory.total_bytes)}"
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
    elevation_requested = Signal()

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
            seccion.elevation_requested.connect(self.elevation_requested)
            self._sections.append(seccion)
            self._sections_host.addWidget(seccion)
        for sobrante in self._sections[len(snapshot.gpus):]:
            sobrante.hide()

        for seccion, gpu in zip(self._sections, snapshot.gpus):
            seccion.show()
            seccion.apply(gpu)

        self._apply_notices(snapshot)

    @property
    def elevation_buttons(self) -> list:
        """Los botones de permisos que haya vivos ahora mismo en la página.

        Se crean y se destruyen con los avisos, así que no vale guardarse uno:
        hay que preguntarlo cada vez.
        """
        return [boton for seccion in self._sections
                for boton in seccion.elevation_buttons]

    def _apply_notices(self, snapshot: Snapshot) -> None:
        """Cada aviso, junto a la tarjeta de la que habla.

        Los avisos vienen con la ruta «gpus.N», así que se pueden repartir. Los
        que no llevan número —los que hablan de todas o de ninguna— se quedan
        al pie de la página.
        """
        sueltos = []
        por_seccion: dict[int, list] = {}
        for note in snapshot.notes_for("gpus"):
            resto = note.path[len("gpus"):].lstrip(".")
            indice = int(resto.split(".")[0]) if resto.split(".")[0].isdigit() else None
            if indice is not None and indice < len(self._sections):
                por_seccion.setdefault(indice, []).append(note)
            else:
                sueltos.append(note)

        for indice, seccion in enumerate(self._sections):
            seccion.set_notes(por_seccion.get(indice, []))

        signature = tuple((n.path, n.need) for n in sueltos)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in sueltos:
            self._notices_host.addWidget(
                Notice(NEED_TITLES.get(note.need, note.need.value), note.message, note.hint)
            )
