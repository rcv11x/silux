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
from ...i18n import _
from ...model import Gpu, Need, Snapshot
from ...settings import Preferences
from ...throttling import SeguidorDeRecortes
from .. import theme
from ..theme import Palette, ui_font
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
    Need.ROOT: "note.needsperm",
    Need.DRIVER: "note.needsdriver",
    Need.HARDWARE: "note.hardware",
    Need.DATABASE: "note.database",
    Need.PLATFORM: "note.platform",
    Need.ERROR: "note.failed",
}

CARD_FIELDS = (
    "gpu.field.vendor", "gpu.field.subsystem", "gpu.field.codename", "gpu.field.driver", "gpu.field.driverver",
    "gpu.field.id", "gpu.field.subid", "gpu.field.slot", "gpu.field.drm", "gpu.field.vbios",
    "gpu.field.compute", "gpu.field.rops", "gpu.field.shaders",
    "gpu.field.uuid",
)

MEMORY_FIELDS = ("gpu.vram.total", "gpu.vram.used", "gpu.vram.type", "gpu.vram.bus", "gpu.vram.bandwidth", "gpu.vram.datarate",
                 "gpu.vram.visible", "gpu.vram.rebar", "gpu.vram.chips",
                 "gpu.vram.shared")

CLOCK_FIELDS = ("gpu.clock.core", "gpu.clock.coremax", "gpu.clock.memory", "gpu.clock.memeff",
                "gpu.clock.memmax", "SoC", "gpu.clock.profile",
                "gpu.clock.link", "gpu.clock.linkmax")

SENSOR_FIELDS = ("gpu.sensor.state", "gpu.sensor.temp", "gpu.sensor.hotspot", "gpu.sensor.memtemp",
                 "gpu.sensor.vrgfx", "gpu.sensor.vrsoc", "gpu.sensor.vrmem",
                 "gpu.sensor.power", "gpu.sensor.powercap", "gpu.sensor.fan",
                 "gpu.sensor.voltage", "gpu.sensor.vsoc", "gpu.sensor.vmem", "gpu.sensor.videouse")

ENGINE_HEADERS = ("gpu.engine.name", "gpu.engine.role", "gpu.tile.usage", "gpu.engine.can")
CODEC_HEADERS = ("gpu.codec.name", "gpu.codec.decode", "gpu.codec.encode", "gpu.codec.depth", "gpu.codec.profiles")

API_HEADERS = ("API", "gpu.api.version", "gpu.field.driver", "gpu.api.detail")
DISPLAY_HEADERS = ("gpu.display.output", "gpu.display.monitor", "gpu.display.res", "gpu.display.refresh", "gpu.display.size",
                   "gpu.display.color", "gpu.display.made")


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
        self.card = self._grid_card(fila, _("gpu.card.card"), CARD_FIELDS)
        fila.add(self._build_memory_card())
        layout.addWidget(fila)

        fila = ResponsiveRow(min_item_width=280)
        self.clocks = self._grid_card(fila, _("gpu.card.clocks"), CLOCK_FIELDS)
        fila.add(self._build_sensor_card())
        layout.addWidget(fila)

        # Una tarjeta moderna no es un bloque «al 40 %»: son varias unidades
        # independientes, y saber cuál va cargada distingue «no da más» de
        # «solo está saturado el decodificador de video».
        self.engine_card = Card(_("gpu.card.engines"))
        self.engine_summary = InfoGrid()
        self.engine_summary.add(_("gpu.engines.idle"))
        self.engines = Table([_(h) for h in ENGINE_HEADERS], numeric=(False, False, True, False))
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
        self.codec_card = Card(_("gpu.card.codecs"))
        self.codecs = Table([_(h) for h in CODEC_HEADERS],
                            numeric=(False, False, False, True, False))
        self.codec_card.body.addWidget(self.codecs)
        layout.addWidget(self.codec_card)

        api_card = Card(_("gpu.card.apis"))
        self.apis = Table([_(h) for h in API_HEADERS], numeric=(False, True, False, False))
        api_card.body.addWidget(self.apis)
        layout.addWidget(api_card)

        display_card = Card(_("gpu.card.displays"))
        self.displays = Table([_(h) for h in DISPLAY_HEADERS],
                              numeric=(False, False, True, True, True, False))
        display_card.body.addWidget(self.displays)
        # Las salidas sin nada enchufado, en una línea. Un MacBook Air de 11"
        # enseñaba cuatro filas seguidas —DP-1, DP-2, HDMI-A-1, HDMI-A-2— con
        # los seis campos a guiones y solo la quinta con datos: cuatro quintas
        # partes de la tabla eran conectores que esa carcasa ni siquiera trae.
        self.displays_free = QLabel("")
        self.displays_free.setObjectName("Muted")
        self.displays_free.setWordWrap(True)
        self.displays_free.setFont(ui_font(theme.METRICS.small_pt))
        display_card.body.addWidget(self.displays_free)
        layout.addWidget(display_card)

        self._chip_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    @staticmethod
    def _grid_card(host: ResponsiveRow, title: str, fields: tuple[str, ...]) -> InfoGrid:
        card = Card(title)
        grid = InfoGrid()
        for name in fields:
            grid.add(_(name))
        card.body.addWidget(grid)
        host.add(card)
        return grid

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("gpu.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        self.recorte = QLabel()
        self.recorte.setObjectName("NoticeHint")
        self.recorte.setWordWrap(True)
        self.recorte.hide()
        card.body.addWidget(self.recorte)
        return card

    def _build_tiles(self) -> QWidget:
        fila = ResponsiveRow(min_item_width=150)
        self.tile_usage = StatTile(_("gpu.tile.usage"), "%", self._p)
        self.tile_temp = StatTile(_("gpu.tile.temp"), "°C", self._p)
        self.tile_power = StatTile(_("gpu.tile.power"), "W", self._p)
        self.tile_vram = StatTile(_("gpu.tile.vram"), "%", self._p)
        # La frecuencia del núcleo es la primera cifra que se mira de una
        # gráfica y estaba solo en la ficha de relojes, sin curva. Sin ella no
        # se distingue una tarjeta que va al máximo de una que se está
        # frenando, que es lo que las otras cuatro dejan a medio explicar.
        self.tile_clock = StatTile(_("gpu.tile.clock"), "MHz", self._p)
        # Y el bus de memoria, que no es lo mismo que la VRAM ocupada: una dice
        # cuánta cabe y esta cuánta se está moviendo. Una tarjeta con la VRAM
        # llena y el bus parado tiene datos cargados y no los está tocando.
        self.tile_membus = StatTile(_("gpu.tile.membus"), "%", self._p)

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
        card = Card(_("gpu.card.sensors"))
        self.power_bar = StackedBar(self._p)
        self.sensors = InfoGrid()
        for name in SENSOR_FIELDS:
            self.sensors.add(_(name))
        card.body.addWidget(self.power_bar)
        card.body.addWidget(self.sensors)
        return card

    def _build_memory_card(self) -> Card:
        card = Card(_("gpu.card.vram"))
        self.memory_bar = StackedBar(self._p)
        self.memory = InfoGrid()
        for name in MEMORY_FIELDS:
            self.memory.add(_(name))
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
                _(NEED_TITLES.get(note.need, note.need.value)), note.message, note.hint,
                tone=NEED_TONES.get(note.need, "warn"),
                action=(_("perm.button.read")
                        if note.need is Need.ROOT else None),
            )
            if aviso.action_button is not None:
                aviso.action_clicked.connect(self.elevation_requested)
                self.elevation_buttons.append(aviso.action_button)
            self._notices_host.addWidget(aviso)

    def apply(self, gpu: Gpu, recorte: str = "") -> None:
        d = render.DASH
        self.title.setText(gpu.display_name)
        # Va arriba, debajo del nombre: es lo que explica por qué las cifras de
        # al lado no llegan a donde deberían, y escondido en una fila de la
        # ficha de sensores no lo lee quien no sabía que existía.
        self.recorte.setText(recorte)
        self.recorte.setVisible(bool(recorte))
        # `pcie_link` devuelve un guion cuando no hay enlace que contar, y una
        # integrada no lo tiene: el subtítulo salía «Apple Inc. · —». Un guion
        # entre dos datos se lee como si faltara algo en medio.
        self.subtitle.setText(" · ".join(
            p for p in (gpu.subsystem_name, gpu.codename,
                        render.pcie_link(gpu.link))
            if p and p != render.DASH))
        self._apply_badges(gpu)
        self._apply_tiles(gpu)

        c = self.card.set
        c(_("gpu.field.vendor"), gpu.vendor or d)
        c(_("gpu.field.subsystem"), gpu.subsystem_name or d)
        c(_("gpu.field.codename"), gpu.codename or d)
        c(_("gpu.field.driver"), gpu.driver or d)
        c(_("gpu.field.driverver"), gpu.driver_version or d)
        c(_("gpu.field.id"), gpu.pci_id or d)
        c(_("gpu.field.subid"), gpu.subsystem_id or d)
        c(_("gpu.field.slot"), gpu.pci_slot or d)
        c(_("gpu.field.drm"), gpu.drm_node or d)
        c(_("gpu.field.vbios"), gpu.vbios or d)
        c(_("gpu.field.compute"), render.compute_units(gpu),
          tooltip=_("gpu.tip.compute"))
        c(_("gpu.field.rops"), str(gpu.rops) if gpu.rops else d,
          tooltip=_("gpu.tip.rops"))
        c(_("gpu.field.shaders"), str(gpu.shader_engines) if gpu.shader_engines else d)
        c(_("gpu.field.uuid"), gpu.unique_id or d)

        self._apply_memory(gpu)

        k = self.clocks.set
        k(_("gpu.clock.core"), render.hz(gpu.clocks.core_hz))
        k(_("gpu.clock.coremax"), render.hz(gpu.clocks.core_max_hz))
        k(_("gpu.clock.memory"), render.hz(gpu.clocks.memory_hz))
        k(_("gpu.clock.memeff"), render.hz(gpu.clocks.memory_effective_hz),
          tooltip=_("gpu.tip.memeff"))
        k(_("gpu.clock.memmax"), render.hz(gpu.clocks.memory_max_hz))
        k("SoC", render.hz(gpu.clocks.soc_hz))
        k(_("gpu.clock.profile"), gpu.clocks.performance_level or d)
        k(_("gpu.clock.link"), render.pcie_link(gpu.link),
          tooltip=render.pcie_note(gpu.link) or "")
        k(_("gpu.clock.linkmax"), render.pcie_link(gpu.link, maximum=True))

        if gpu.power_w is not None and gpu.power_cap_w:
            self.power_bar.set_segments(
                [(_("gpu.bar.inuse"), gpu.power_w, "accent"),
                 (_("gpu.bar.unused"),
                  max(0.0, gpu.power_cap_w - gpu.power_w), "line")],
                total=gpu.power_cap_w,
                formatter=render.watts,
            )
            self.power_bar.show()
        else:
            self.power_bar.hide()

        s = self.sensors.set
        fahrenheit = self._prefs.fahrenheit
        s(_("gpu.sensor.state"), render.throttle_state(gpu),
          tooltip=_("gpu.tip.state"))
        s(_("gpu.sensor.temp"), render.temperature(gpu.temp_c, fahrenheit))
        s(_("gpu.sensor.hotspot"), render.temperature(gpu.hotspot_c, fahrenheit),
          tooltip=_("gpu.tip.hotspot"))
        s(_("gpu.sensor.memtemp"), render.temperature(gpu.memory_temp_c, fahrenheit))
        s(_("gpu.sensor.power"), render.watts(gpu.power_w))
        s(_("gpu.sensor.powercap"), render.watts(gpu.power_cap_w))
        s(_("gpu.sensor.fan"), render.fan(gpu.fan_rpm, gpu.fan_percent))
        s(_("gpu.sensor.vrgfx"), render.temperature(gpu.vr_gfx_c, fahrenheit),
          tooltip=_("gpu.tip.vr"))
        s(_("gpu.sensor.vrsoc"), render.temperature(gpu.vr_soc_c, fahrenheit))
        s(_("gpu.sensor.vrmem"), render.temperature(gpu.vr_memory_c, fahrenheit))
        s(_("gpu.sensor.voltage"), render.volts(gpu.voltage_v))
        s(_("gpu.sensor.vsoc"), render.volts(gpu.voltage_soc_v))
        s(_("gpu.sensor.vmem"), render.volts(gpu.voltage_memory_v))
        s(_("gpu.sensor.videouse"), render.percent(gpu.video_busy_percent),
          tooltip=_("gpu.tip.videouse"))

        self._apply_engines(gpu)
        self._apply_codecs(gpu)
        self.apis.set_rows([
            (api.name, api.version or d, api.driver or d, api.extra or d)
            for api in gpu.apis
        ] or [(_("gpu.apis.none"), d, d, d)])

        conectadas = [s for s in gpu.displays if s.connected]
        libres = [s.connector for s in gpu.displays if not s.connected]
        self.displays.set_rows([_fila_de_salida(s) for s in conectadas]
                               or [(_("gpu.displays.none"), d, d, d, d, d)])
        self.displays_free.setText(
            _("gpu.displays.free.one" if len(libres) == 1
              else "gpu.displays.free").format(n=len(libres),
                                               salidas=", ".join(libres))
            if libres else "")
        self.displays_free.setVisible(bool(libres))

    def _apply_engines(self, gpu: Gpu) -> None:
        """Los motores de la tarjeta, si el driver los publica.

        La tarjeta se esconde entera cuando no hay ninguno: en AMD y NVIDIA el
        kernel no los enumera, y una tabla vacía no explica nada.
        """
        self.engine_card.setVisible(bool(gpu.engines))
        if not gpu.engines:
            return
        self.engine_summary.set(_("gpu.engines.idle"), render.percent(gpu.sleep_percent))
        self.engines.set_rows([
            (motor.name,
             _(motor.kind) if motor.kind else render.DASH,
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
            _("gpu.chip.integrated") if gpu.integrated else None,
            _("gpu.chip.primary") if gpu.primary else None,
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
            _("gpu.tile.video").format(
                pct=render.percent(gpu.video_busy_percent))
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
                _("gpu.tile.memclock").format(
                    valor=render.hz(relojes.memory_effective_hz)))
        elif relojes.memory_hz:
            self.tile_clock.set_detail(_("gpu.tile.memclock").format(
                valor=render.hz(relojes.memory_hz)))
        else:
            self.tile_clock.set_detail("")

        bus = gpu.memory_busy_percent
        self.tile_membus.update_value(
            f"{bus:.0f}" if bus is not None else render.DASH, bus)
        # Contra qué se compara ese porcentaje: sin el ancho de banda de la
        # tarjeta, un 21 % no dice si son megas o gigas por segundo.
        if bus is not None and gpu.memory.bandwidth_bytes:
            movido = gpu.memory.bandwidth_bytes * bus / 100
            self.tile_membus.set_detail(_("gpu.tile.bandwidth").format(
                actual=render.bandwidth(int(movido)),
                max=render.bandwidth(gpu.memory.bandwidth_bytes)))
        else:
            self.tile_membus.set_detail("")

        temperatura = gpu.temp_c
        if self._prefs.fahrenheit and temperatura is not None:
            temperatura = temperatura * 9 / 5 + 32
        self.tile_temp.set_unit("°F" if self._prefs.fahrenheit else "°C")
        self.tile_temp.update_value(
            f"{temperatura:.0f}" if temperatura is not None else render.DASH, temperatura)
        self.tile_temp.set_detail(
            _("gpu.tile.hotspot").format(valor=render.temperature(
                gpu.hotspot_c, self._prefs.fahrenheit))
            if gpu.hotspot_c is not None else "")

        self.tile_power.update_value(
            f"{gpu.power_w:.0f}" if gpu.power_w is not None else render.DASH, gpu.power_w)
        self.tile_power.set_detail(
            _("gpu.tile.of").format(valor=render.watts(gpu.power_cap_w))
            if gpu.power_cap_w else "")

        porcentaje = gpu.memory.used_percent
        self.tile_vram.update_value(
            f"{porcentaje:.0f}" if porcentaje is not None else render.DASH, porcentaje)
        # La ficha ya enseña el porcentaje; aquí solo hace falta contra qué.
        self.tile_vram.set_detail(
            _("gpu.tile.of").format(valor=render.size(gpu.memory.total_bytes))
            if gpu.memory.total_bytes else "")

    def _apply_memory(self, gpu: Gpu) -> None:
        d = render.DASH
        memoria = gpu.memory
        if memoria.total_bytes and memoria.used_bytes is not None:
            self.memory_bar.set_segments(
                [(_("gpu.bar.inuse"), memoria.used_bytes, "accent"),
                 (_("gpu.bar.free"),
                  memoria.total_bytes - memoria.used_bytes, "line")],
                total=memoria.total_bytes,
                formatter=render.size,
            )
            self.memory_bar.show()
        else:
            self.memory_bar.hide()

        m = self.memory.set
        m(_("gpu.vram.total"), render.size(memoria.total_bytes))
        m(_("gpu.vram.used"), render.gpu_memory_summary(memoria) if memoria.total_bytes else d)
        m(_("gpu.vram.type"), render.vram_kind(memoria))
        m(_("gpu.vram.bus"), render.vram_bus(memoria))
        m(_("gpu.vram.bandwidth"), render.bandwidth(memoria.bandwidth_bytes),
          tooltip=_("gpu.tip.bandwidth"))
        m(_("gpu.vram.datarate"), f"{memoria.data_rate_hz / 1e9:.1f} Gbps"
          if memoria.data_rate_hz else d,
          tooltip=_("gpu.tip.datarate"))
        m(_("gpu.vram.visible"), render.size(memoria.visible_bytes)
          if memoria.visible_bytes else d,
          tooltip=_("gpu.tip.visible"))
        m(_("gpu.vram.rebar"), render.resizable_bar(memoria),
          tooltip=_("gpu.tip.rebar"))
        m(_("gpu.vram.chips"), memoria.vendor or d)
        prestada = d
        if memoria.gtt_total_bytes:
            prestada = render.size(memoria.gtt_total_bytes)
            if memoria.gtt_used_bytes is not None:
                prestada = _("gpu.vram.of").format(
                    usado=render.size(memoria.gtt_used_bytes), total=prestada)
        m(_("gpu.vram.shared"), prestada,
          tooltip=_("gpu.tip.shared"))


def _fila_de_salida(salida) -> tuple[str, ...]:
    """Una línea de la tabla de monitores; la mitad se queda vacía si no hay."""
    d = render.DASH
    if not salida.connected:
        return (salida.connector, _("gpu.display.free"), d, d, d, d, d)
    monitor = salida.monitor
    if monitor is None:
        # Conectada pero sin EDID legible: pasa con algunos adaptadores y KVM.
        return (salida.connector, _("gpu.display.unknown"), salida.resolution or d,
                d, d, d, d)
    return (
        salida.connector,
        render.monitor_name(monitor),
        salida.resolution or d,
        monitor.refresh_summary or d,
        f'{monitor.diagonal_inches}"' if monitor.diagonal_inches else d,
        render.monitor_color(monitor),
        monitor.made or d,
    )


class GraphicsPage(QScrollArea):
    elevation_requested = Signal()

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        # Lleva la cuenta de cuánto tiempo lleva frenándose cada tarjeta. Es
        # estado entre muestreos, así que vive en la página y no en el modelo.
        self._recortes = SeguidorDeRecortes()
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

        self._empty = QLabel(_("gpu.none"))
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

        ahora = snapshot.monotonic_ns
        for seccion, gpu in zip(self._sections, snapshot.gpus):
            # La ranura PCI es lo único que no cambia entre muestreos: el
            # índice se mueve si aparece o desaparece una tarjeta.
            clave = gpu.pci_slot or f"gpu{gpu.index}"
            self._recortes.update(clave, gpu.throttled, gpu.throttle_reasons, ahora)
            seccion.show()
            seccion.apply(gpu, render.throttle_episode(
                self._recortes.relevante(clave, ahora), ahora) or "")

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
                Notice(_(NEED_TITLES.get(note.need, note.need.value)),
                       note.message, note.hint)
            )
