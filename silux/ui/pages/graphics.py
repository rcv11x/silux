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
from ..widgets import (Plegable, Card, ChipRow, Divider, InfoGrid, LevelList, Notice, ResponsiveRow,
                       StatTile, Table, clear_layout, tone_for)

# Un símbolo se lee de un vistazo; un «No» hay que leerlo. Los dos son
# distintos por su forma, no solo por el color con que los pinta la tabla.
SI = "✓"
NO = "✗"

NEED_TITLES = {
    Need.ROOT: "note.needsperm",
    Need.DRIVER: "note.needsdriver",
    Need.HARDWARE: "note.hardware",
    Need.DATABASE: "note.database",
    Need.PLATFORM: "note.platform",
    Need.ERROR: "note.failed",
    Need.KERNEL: "note.kernel",
}

# Qué tarjeta es y con qué driver va: lo que se mira.
CARD_FIELDS = (
    "gpu.field.vendor", "gpu.field.subsystem", "gpu.field.codename", "gpu.field.driver", "gpu.field.driverver",
    "gpu.field.compute", "gpu.field.rops", "gpu.field.shaders",
)
# Y con qué números la identifica el sistema: lo que se busca una vez, para
# un informe o un foro. Va plegado debajo.
INVENTORY_FIELDS = (
    "gpu.field.id", "gpu.field.subid", "gpu.field.slot", "gpu.field.drm", "gpu.field.vbios",
    "gpu.field.uuid",
)

# Lo que está pasando ahora, en una barra por medida: cuánta memoria de video
# hay ocupada, cuánto consume de lo que puede y cuánto bus se mueve. Juntas
# debajo de las fichas: repartidas por las tarjetas de abajo, cada una con su
# leyenda, había que bajar a buscarlas.
NOW_FIELDS = ("gpu.now.vram", "gpu.now.power", "gpu.now.bus")

# El nombre de la barra de cada motor en «Ahora mismo» (render.engine_levels).
# Cada una dice qué cuenta: «Video» a secas no decía si era ver o grabar, y
# en AMD son las dos cosas en una sola cifra.
BARRAS_DE_MOTOR = {
    "engine.render": "gpu.now.engine.render",
    "engine.compute": "gpu.now.engine.compute",
    "engine.video": "gpu.now.engine.video",
    "engine.decode": "gpu.now.engine.decode",
    "engine.encode": "gpu.now.engine.encode",
    "engine.videoenhance": "gpu.now.engine.videoenhance",
    "engine.copy": "gpu.now.engine.copy",
}
# Y cómo se nombra al pie el que la gráfica no deja medir (render.engine_gaps).
MOTORES_AL_PIE = {
    "engine.render": "gpu.now.gap.render",
    "engine.video": "gpu.now.gap.video",
    "engine.decode": "gpu.now.gap.decode",
    "engine.encode": "gpu.now.gap.encode",
}

MEMORY_FIELDS = ("gpu.vram.total", "gpu.vram.type", "gpu.vram.bus", "gpu.vram.bandwidth", "gpu.vram.datarate",
                 "gpu.vram.visible", "gpu.vram.rebar", "gpu.vram.chips",
                 "gpu.vram.shared")

CLOCK_FIELDS = ("gpu.clock.core", "gpu.clock.coremax", "gpu.clock.silmax", "gpu.clock.efficient",
                "gpu.clock.silmin", "gpu.clock.limits", "gpu.clock.memory", "gpu.clock.memeff",
                "gpu.clock.memmax", "SoC", "gpu.clock.profile",
                "gpu.clock.link", "gpu.clock.linkmax")

# El estado y las temperaturas de dentro de la tarjeta. La del núcleo no
# está: es la de la ficha de arriba. Tampoco el consumo ni su límite, que
# van en «Ahora mismo» con su barra: repetidos aquí eran la misma cifra dos
# veces en la misma pantalla.
SENSOR_FIELDS = ("gpu.sensor.state",
                 "gpu.sensor.hotspot", "gpu.sensor.memtemp",
                 "gpu.sensor.vrgfx", "gpu.sensor.vrsoc", "gpu.sensor.vrmem",
                 "gpu.sensor.fan",
                 "gpu.sensor.voltage", "gpu.sensor.vsoc", "gpu.sensor.vmem", "gpu.sensor.videouse")

# Lo que en algunas tarjetas no está vacío: es que no existe.
#
# Un guion dice «no lo sé», y en una integrada eso era falso diez veces
# seguidas: no es que falte el tipo de memoria, es que no hay chip de memoria
# del que decirlo. La ficha de una Iris Xe salía con un dato de once en
# «Memoria de video» y dos de catorce en «Sensores», toda ella rayas.
#
# Aquí solo entra lo que se puede afirmar. Lo dudoso se queda en guion, que
# para eso está: el enlace PCIe no se esconde por ser integrada, porque la
# Radeon 740M lo es y publica su «PCIe 4.0 × 16». «Integrada» no implica «sin
# enlace»; «integrada de Intel» sí (`NA_INTEL_INTEGRADA`).
#
# Las claves van crudas y se traducen al usarlas: `_()` en una constante de
# módulo se resuelve al importar, cuando todavía no se sabe qué idioma quiere
# nadie.
# Cada tarjeta lleva su propia frase: en «Relojes» lo que se esconde es el
# reloj de memoria, no el bus, así que repetir ahí el texto de la memoria
# nombraba campos que en esa tarjeta no estaban.
NA_SIN_VRAM = {
    "memory": (("gpu.vram.total", "gpu.vram.type", "gpu.vram.bus",
                "gpu.vram.bandwidth", "gpu.vram.datarate", "gpu.vram.visible",
                "gpu.vram.rebar", "gpu.vram.chips"), "gpu.na.novram"),
    "clocks": (("gpu.clock.memory", "gpu.clock.memeff", "gpu.clock.memmax"),
               "gpu.na.novram.clocks"),
    "sensors": (("gpu.sensor.memtemp", "gpu.sensor.vmem"), "gpu.na.novram.sensors"),
}

# Los reguladores los cuenta el microcontrolador de una tarjeta, y el
# ventilador es suyo. Una integrada se alimenta y se refrigera con el resto del
# equipo, así que esos sensores no son que falten: no son de ella. En una
# NVIDIA dedicada sí existen y NVML no los publica, y eso sigue siendo un
# guion, que es lo que corresponde a «no lo sé».
NA_INTEGRADA = {
    "sensors": (("gpu.sensor.vrgfx", "gpu.sensor.vrsoc", "gpu.sensor.vrmem",
                 "gpu.sensor.fan"), "gpu.na.integrated"),
}

# Lo que una integrada de Intel no tiene o i915 no cuenta. Las unidades de
# rasterizado y los motores de sombreado salen de una consulta de `amdgpu`, y
# el recuento de Intel son las unidades de ejecución; no tiene reloj de SoC ni
# perfil de rendimiento; y el voltaje del núcleo, en Intel, solo lo publican
# las dedicadas (Arc). Las frases del pie no nombran a AMD: quien mira una
# Intel no tiene por qué saber qué cuenta otro driver. En una UHD no son
# datos que falten por leer: no hay de dónde. Tampoco el enlace: la integrada
# de Intel es un dispositivo del propio procesador (00:02.0) y no cuelga de
# ninguna ranura; la de AMD sí publica el suyo, y por eso esto no vale para
# cualquier integrada. El estado de limitación va aparte
# (`NA_INTEL_SIN_MOTIVOS`): `i915` lo publica en las generaciones recientes.
NA_INTEL_INTEGRADA = {
    "card": (("gpu.field.rops", "gpu.field.shaders"), "gpu.na.intel.card"),
    "clocks": (("SoC", "gpu.clock.profile", "gpu.clock.link", "gpu.clock.linkmax"),
               "gpu.na.intel.clocks"),
    "sensors": (("gpu.sensor.voltage", "gpu.sensor.vsoc"), "gpu.na.intel.sensors"),
}

# Una Intel de las que no publican `throttle_reason_*` (un Comet Lake): no
# dice si se frena ni por qué. Las recientes sí, y entonces se enseña.
NA_INTEL_SIN_MOTIVOS = {
    "sensors": (("gpu.sensor.state",), "gpu.na.intel.throttle"),
}

# Las frecuencias del silicio, que solo publica Intel. No pasan por
# `no_aplica`: en una AMD no es que falten, es que su driver cuenta la
# frecuencia por escalones, y eso ya lo dice «Núcleo (máximo)».
SILICIO = ("gpu.clock.silmax", "gpu.clock.efficient", "gpu.clock.silmin")

# Cuando «Consumo y temperaturas» se va entera, lo escondido se nombra al pie
# en una frase (regla 5) y el porqué de cada hueco va en el globo. Primero lo
# que una integrada no tiene; después lo que esta no publica.
SENSORES_AUSENTES = (
    (("gpu.sensor.vrgfx", "gpu.sensor.vrsoc", "gpu.sensor.vrmem"), "gpu.na.piece.vr"),
    (("gpu.sensor.fan",), "gpu.na.piece.fan"),
    (("gpu.sensor.vsoc",), "gpu.na.piece.soc"),
    (("gpu.sensor.memtemp", "gpu.sensor.vmem"), "gpu.na.piece.vram"),
)
SENSORES_CALLADOS = (
    (("gpu.sensor.hotspot",), "gpu.na.piece.temp"),
    (("gpu.sensor.voltage",), "gpu.na.piece.voltage"),
    (("gpu.sensor.state",), "gpu.na.piece.state"),
)

# Una APU de AMD: el consumo que publica su driver es el del encapsulado
# entero, con los núcleos del procesador, y la segunda temperatura de su
# telemetría es la del SoC. Ninguna de las dos es de la gráfica, así que no
# se enseñan como suyas, y el pie lo dice. «gpu.tile.power» no es un campo de
# la ficha: es la de arriba, la del consumo.
NA_APU_AMD = {
    "sensors": (("gpu.sensor.hotspot", "gpu.tile.power"), "gpu.na.apu"),
}

# Una Arc: su enlace no se lee con seguridad (`_arc_tras_su_conmutador` en
# el proveedor), así que no hay enlace que enseñar.
NA_ARC_ENLACE = {
    "clocks": (("gpu.clock.link", "gpu.clock.linkmax"), "gpu.na.arc.link"),
}

# Una Intel no publica su temperatura por ningún camino. Un guion ahí se lee
# como «no la he podido leer», y no va a poderse nunca.
NA_SIN_TEMPERATURA = {
    "sensors": (("gpu.sensor.hotspot",), "gpu.na.notemp"),
}

ENGINE_HEADERS = ("gpu.engine.name", "gpu.engine.role", "gpu.tile.usage", "gpu.engine.can")
CODEC_HEADERS = ("gpu.codec.name", "gpu.codec.decode", "gpu.codec.encode", "gpu.codec.depth", "gpu.codec.profiles")

API_HEADERS = ("API", "gpu.api.version", "gpu.field.driver", "gpu.api.detail")
DISPLAY_HEADERS = ("gpu.display.output", "gpu.display.monitor", "gpu.display.res", "gpu.display.refresh", "gpu.display.size",
                   "gpu.display.color", "gpu.display.made")


def no_aplica(gpu: Gpu) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Qué campos no existen en esta tarjeta y con qué frase se explica.

    Devuelve, por cada tarjeta de la ficha, las claves que hay que esconder y
    el texto del pie. Se esconden en vez de marcarse una a una porque la queja
    era que la ficha está vacía, y cambiar diez guiones por diez «no aplica» la
    deja igual de vacía y con más letra. El pie es lo que evita que algo
    desaparezca en silencio: si a alguien le falta un campo que su tarjeta sí
    tiene, lo lee ahí y se puede reportar.

    `integrated` es None cuando no se ha podido decidir —con nouveau no se lee
    la VRAM y por ahí una GTX 1050 acababa marcada como integrada—, y entonces
    no se esconde nada: quitarle la memoria a una dedicada sería peor que
    dejar un guion de más.
    """
    reglas = []
    if gpu.integrated and not gpu.memory.total_bytes:
        reglas.append(NA_SIN_VRAM)
    if gpu.integrated:
        reglas.append(NA_INTEGRADA)
    if gpu.no_temperature_sensor and gpu.temp_c is None:
        reglas.append(NA_SIN_TEMPERATURA)
    if gpu.integrated and gpu.vendor == "AMD":
        reglas.append(NA_APU_AMD)
    if (gpu.integrated is False and gpu.driver in ("i915", "xe")
            and render.pcie_link(gpu.link) == render.DASH):
        reglas.append(NA_ARC_ENLACE)
    if gpu.integrated and gpu.driver in ("i915", "xe"):
        regla = dict(NA_INTEL_INTEGRADA)
        if render.pcie_link(gpu.link) != render.DASH:
            # Si alguna publicase un enlace de verdad, se enseña.
            claves, frase = regla["clocks"]
            regla["clocks"] = (tuple(c for c in claves if not c.startswith("gpu.clock.link")),
                               "gpu.na.intel.clocks.link")
        reglas.append(regla)
        if gpu.throttled is None:
            reglas.append(NA_INTEL_SIN_MOTIVOS)

    tarjetas = ("card", "memory", "clocks", "sensors")
    ocultos: dict[str, set[str]] = {tarjeta: set() for tarjeta in tarjetas}
    frases: dict[str, list[str]] = {tarjeta: [] for tarjeta in tarjetas}
    for regla in reglas:
        for tarjeta, (claves, frase) in regla.items():
            ocultos[tarjeta].update(claves)
            frases[tarjeta].append(frase)
    return ocultos, {t: " ".join(_(f) for f in v) for t, v in frases.items()}


def pie_de_sensores(ocultos: set[str]) -> str:
    """Lo que falta de «Consumo y temperaturas», nombrado en una frase."""
    ausentes = [_(clave) for campos, clave in SENSORES_AUSENTES if ocultos & set(campos)]
    callados = [_(clave) for campos, clave in SENSORES_CALLADOS if ocultos & set(campos)]
    partes = []
    if ausentes:
        partes.append(_("gpu.na.sensors.absent").format(
            campos=render.enumeration(ausentes, "list.nor")))
    if callados:
        partes.append(_("gpu.na.sensors.silent").format(
            campos=render.enumeration(callados, "list.nor")))
    return " ".join(partes)


class GpuSection(QWidget):
    """El bloque completo de una tarjeta."""

    # El uso y el consumo de una Intel salen de contadores del kernel que
    # piden permisos. Sin botón aquí había que ir a Memoria o a
    # Almacenamiento a darlos y volver, que es pedirle al usuario que adivine.
    elevation_requested = Signal()
    permission_snoozed = Signal()
    permission_dismissed = Signal()

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

        self.now_card = Card(_("gpu.card.now"))
        self.now = LevelList(self._p)
        for name in NOW_FIELDS:
            self.now.add(_(name))
        self.now.locked_clicked.connect(self.elevation_requested)
        self.now_card.body.addWidget(self.now)
        self.now_pie = self._pie(self.now_card)
        layout.addWidget(self.now_card)
        self.elevation_buttons: list = []

        fila = ResponsiveRow(min_item_width=280)
        self.card, self.card_pie = self._grid_card(fila, _("gpu.card.card"), CARD_FIELDS)
        self.inventory_fold = Plegable(_("gpu.card.inventory"))
        self.inventory = InfoGrid()
        for name in INVENTORY_FIELDS:
            self.inventory.add(_(name))
        self.inventory_fold.body.addWidget(self.inventory)
        self.card.parentWidget().body.addWidget(self.inventory_fold)
        fila.add(self._build_memory_card())
        layout.addWidget(fila)

        fila = ResponsiveRow(min_item_width=280)
        self.clocks, self.clocks_pie = self._grid_card(
            fila, _("gpu.card.clocks"), CLOCK_FIELDS)
        fila.add(self._build_sensor_card())
        layout.addWidget(fila)
        # Lo que explicaría «Consumo y temperaturas» cuando esa tarjeta no
        # tiene nada propio que enseñar y se va (`_apply_no_aplica`).
        self.sensors_outside = QLabel("")
        self.sensors_outside.setObjectName("Muted")
        self.sensors_outside.setWordWrap(True)
        self.sensors_outside.setFont(ui_font(theme.METRICS.small_pt))
        self.sensors_outside.setVisible(False)
        layout.addWidget(self.sensors_outside)

        # Una tarjeta moderna no es un bloque «al 40 %»: son varias unidades
        # independientes, y saber cuál va cargada distingue «no da más» de
        # «solo está saturado el decodificador de video».
        self.engine_card = Card(_("gpu.card.engines"))
        self.engine_summary = InfoGrid()
        self.engine_summary.add(_("gpu.engines.idle"))
        self.engines = Table([_(h) for h in ENGINE_HEADERS], numeric=(False, False, True, False))
        self.engines.locked_clicked.connect(self.elevation_requested)
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
        # Si no cabe, cede el nombre del monitor y no sus cifras.
        self.displays = Table([_(h) for h in DISPLAY_HEADERS],
                              numeric=(False, False, True, True, True, False), cede=(1,))
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

    def _grid_card(self, host: ResponsiveRow, title: str,
                   fields: tuple[str, ...]) -> tuple[InfoGrid, QLabel]:
        card = Card(title)
        grid = InfoGrid()
        for name in fields:
            grid.add(_(name))
        card.body.addWidget(grid)
        pie = self._pie(card)
        host.add(card)
        return grid, pie

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
        # La frecuencia del núcleo es la primera cifra que se mira de una
        # gráfica y estaba solo en la ficha de relojes, sin curva. Sin ella no
        # se distingue una tarjeta que va al máximo de una que se está
        # frenando, que es lo que las otras cuatro dejan a medio explicar.
        self.tile_clock = StatTile(_("gpu.tile.clock"), "MHz", self._p)
        for tile in (self.tile_usage, self.tile_power):
            tile.locked_clicked.connect(self.elevation_requested)
        # Cuatro, las de la tarjeta entera. La memoria tenía aquí otras dos
        # —ocupada y bus— y justo debajo su tarjeta con lo mismo: ahora está
        # toda allí, con su barra.
        for tile in (self.tile_usage, self.tile_clock, self.tile_temp, self.tile_power):
            fila.add(tile)
        self.tile_usage.chart.set_range(0, 100)

        intervalo = self._prefs.interval_s
        self.tile_usage.chart.set_formatter(render.percent, intervalo)
        self.tile_power.chart.set_formatter(render.watts, intervalo)
        self.tile_clock.chart.set_formatter(
            lambda v: render.hz(v * 1e6), intervalo)
        self.tile_temp.chart.set_formatter(
            lambda v: render.temperature(v, False), intervalo)
        return fila

    @staticmethod
    def _pie(card: Card) -> QLabel:
        """La línea que dice qué campos no aplican y por qué.

        Misma forma que la de las salidas libres, que resuelve lo mismo un
        poco más abajo en esta página.
        """
        etiqueta = QLabel("")
        etiqueta.setObjectName("Muted")
        etiqueta.setWordWrap(True)
        etiqueta.setFont(ui_font(theme.METRICS.small_pt))
        etiqueta.setVisible(False)
        card.body.addWidget(etiqueta)
        return etiqueta

    def _build_sensor_card(self) -> Card:
        card = Card(_("gpu.card.sensors"))
        self.sensors = InfoGrid()
        for name in SENSOR_FIELDS:
            self.sensors.add(_(name))
        card.body.addWidget(self.sensors)
        self.sensors.locked_clicked.connect(self.elevation_requested)
        self.sensors_pie = self._pie(card)
        self.sensor_card = card
        return card

    def _build_memory_card(self) -> Card:
        card = Card(_("gpu.card.vram"))
        self.memory = InfoGrid()
        for name in MEMORY_FIELDS:
            self.memory.add(_(name))
        card.body.addWidget(self.memory)
        self.memory_pie = self._pie(card)
        return card

    # -- actualización ------------------------------------------------------

    def set_notes(self, notes, sin_permisos: bool = False) -> None:
        """`sin_permisos`: los avisos de permisos están apartados."""
        if sin_permisos:
            notes = [n for n in notes if n.need is not Need.ROOT]
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        self.elevation_buttons = []
        for note in notes:
            aviso = Notice(
                _(NEED_TITLES.get(note.need, note.need.value)), note.message, note.hint,
                tone=tone_for(note.need),
                action=(_("perm.button.read")
                        if note.need is Need.ROOT else None),
                dismissible=note.need is Need.ROOT,
            )
            if aviso.action_button is not None:
                aviso.action_clicked.connect(self.elevation_requested)
                aviso.snoozed.connect(self.permission_snoozed)
                aviso.dismissed.connect(self.permission_dismissed)
                self.elevation_buttons.append(aviso.action_button)
            self._notices_host.addWidget(aviso)

    def apply(self, gpu: Gpu, recorte: str = "") -> None:
        d = render.DASH
        self.title.setText(gpu.display_name)
        # Va arriba, debajo del nombre: es lo que explica por qué las cifras de
        # al lado no llegan a donde deberían, y escondido en una fila de la
        # ficha de sensores no lo lee quien no sabía que existía.
        # Una tarjeta suspendida no se frena: duerme, y es lo que se dice.
        recorte = render.gpu_asleep(gpu, self._prefs.fahrenheit) or recorte
        self.recorte.setText(recorte)
        self.recorte.setVisible(bool(recorte))
        # `pcie_link` devuelve un guion cuando no hay enlace que contar, y una
        # integrada no lo tiene: el subtítulo salía «Apple Inc. · —». Un guion
        # entre dos datos se lee como si faltara algo en medio.
        self.subtitle.setText(" · ".join(
            p for p in (render.maker(gpu.subsystem_name), gpu.codename,
                        render.pcie_link(gpu.link))
            if p and p != render.DASH))
        self._apply_badges(gpu)
        self._apply_tiles(gpu)

        c = self.card.set
        c(_("gpu.field.vendor"), gpu.vendor or d)
        c(_("gpu.field.subsystem"), render.maker(gpu.subsystem_name) or d)
        c(_("gpu.field.codename"), gpu.codename or d)
        c(_("gpu.field.driver"), gpu.driver or d)
        c(_("gpu.field.driverver"), gpu.driver_version or d)
        c(_("gpu.field.compute"), render.compute_units(gpu),
          tooltip=_("gpu.tip.compute"))
        c(_("gpu.field.rops"), str(gpu.rops) if gpu.rops else d,
          tooltip=_("gpu.tip.rops"))
        c(_("gpu.field.shaders"), str(gpu.shader_engines) if gpu.shader_engines else d)
        # Un identificador todo a ceros no identifica nada: es lo que da un
        # driver que no lo tiene, y lo que deja una captura anónima. La fila
        # se va entera; con un guion parecería un dato que falta.
        identificador = render.unique_id(gpu.unique_id)
        i = self.inventory.set
        i(_("gpu.field.id"), gpu.pci_id or d)
        i(_("gpu.field.subid"), gpu.subsystem_id or d)
        i(_("gpu.field.slot"), gpu.pci_slot or d)
        i(_("gpu.field.drm"), gpu.drm_node or d)
        i(_("gpu.field.vbios"), gpu.vbios or d)
        i(_("gpu.field.uuid"), identificador or d)
        self.inventory.set_visible(_("gpu.field.uuid"), identificador is not None)

        self._apply_memory(gpu)

        k = self.clocks.set
        # Parado no es una frecuencia: «0 MHz» se lee como un fallo de lectura.
        k(_("gpu.clock.core"), _("gpu.clock.idle") if gpu.clocks.core_hz == 0
          else render.hz(gpu.clocks.core_hz))
        k(_("gpu.clock.coremax"), render.hz(gpu.clocks.core_max_hz))
        k(_("gpu.clock.silmax"), render.hz(gpu.clocks.silicon_max_hz),
          tooltip=_("gpu.tip.silmax"))
        k(_("gpu.clock.efficient"), render.hz(gpu.clocks.efficient_hz),
          tooltip=_("gpu.tip.efficient"))
        k(_("gpu.clock.silmin"), render.hz(gpu.clocks.silicon_min_hz),
          tooltip=(_("gpu.tip.silmin.efficient").format(eficiente=_("gpu.tip.efficient"))
                   if gpu.clocks.efficient_hz == gpu.clocks.silicon_min_hz else None))
        k(_("gpu.clock.limits"), render.gpu_clock_limits(gpu.clocks) or d,
          tooltip=_("gpu.tip.limits"))
        k(_("gpu.clock.memory"), render.hz(gpu.clocks.memory_hz))
        k(_("gpu.clock.memeff"), render.hz(gpu.clocks.memory_effective_hz),
          tooltip=_("gpu.tip.memeff"))
        k(_("gpu.clock.memmax"), render.hz(gpu.clocks.memory_max_hz))
        k("SoC", render.hz(gpu.clocks.soc_hz))
        k(_("gpu.clock.profile"), gpu.clocks.performance_level or d)
        k(_("gpu.clock.link"), render.pcie_link(gpu.link),
          tooltip=render.pcie_note(gpu.link) or "")
        k(_("gpu.clock.linkmax"), render.pcie_link(gpu.link, maximum=True))

        self._apply_now(gpu)

        s = self.sensors.set
        fahrenheit = self._prefs.fahrenheit
        s(_("gpu.sensor.state"), render.throttle_state(gpu),
          tooltip=_("gpu.tip.state"))
        s(_("gpu.sensor.hotspot"), render.temperature(gpu.hotspot_c, fahrenheit),
          tooltip=_("gpu.tip.hotspot"))
        s(_("gpu.sensor.memtemp"), render.temperature(gpu.memory_temp_c, fahrenheit))
        s(_("gpu.sensor.fan"), render.fan(gpu.fan_rpm, gpu.fan_percent))
        s(_("gpu.sensor.vrgfx"), render.temperature(gpu.vr_gfx_c, fahrenheit),
          tooltip=_("gpu.tip.vr"))
        s(_("gpu.sensor.vrsoc"), render.temperature(gpu.vr_soc_c, fahrenheit))
        s(_("gpu.sensor.vrmem"), render.temperature(gpu.vr_memory_c, fahrenheit))
        s(_("gpu.sensor.voltage"), render.volts(gpu.voltage_v))
        s(_("gpu.sensor.vsoc"), render.volts(gpu.voltage_soc_v))
        s(_("gpu.sensor.vmem"), render.volts(gpu.voltage_memory_v))
        candado = getattr(self, "_candado", None)
        if gpu.video_busy_percent is None and candado is not None:
            # Sale del mismo contador que el uso: con candado, no con guion.
            self.sensors.set_locked(_("gpu.sensor.videouse"), self._p.info,
                                    render.lock_tooltip(candado))
        else:
            s(_("gpu.sensor.videouse"), render.percent(gpu.video_busy_percent),
              tooltip=_("gpu.tip.videouse"))

        self._apply_no_aplica(gpu)
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

    def _apply_no_aplica(self, gpu: Gpu) -> None:
        """Esconde lo que esta tarjeta no tiene y lo dice al pie.

        Se recorren siempre todos los campos, no solo los que se esconden: una
        sección se reutiliza entre muestreos y hay que volver a enseñar lo que
        se ocultó si la tarjeta que ocupa ese sitio cambia.
        """
        ocultos, pies = no_aplica(gpu)

        # La ficha de la temperatura, donde la tarjeta no la publica: una
        # ficha grande con un guion para siempre era el hueco más visible de
        # la página. Queda dicho al pie de «Consumo y temperaturas». Se deriva
        # de lo que ya decidió `no_aplica` en vez de repetir aquí la condición.
        self.tile_temp.setVisible(not (gpu.no_temperature_sensor and gpu.temp_c is None))
        self.tile_power.setVisible("gpu.tile.power" not in ocultos["sensors"])

        for nombre, grid, campos, pie in (
                ("card", self.card, CARD_FIELDS, self.card_pie),
                ("memory", self.memory, MEMORY_FIELDS, self.memory_pie),
                ("clocks", self.clocks, CLOCK_FIELDS, self.clocks_pie),
                ("sensors", self.sensors, SENSOR_FIELDS, self.sensors_pie)):
            for clave in campos:
                grid.set_visible(_(clave), clave not in ocultos[nombre])
            pie.setText(pies[nombre])
            pie.setVisible(bool(pies[nombre]))

        # En una integrada de Intel, de «Consumo y temperaturas» solo queda el
        # uso del motor de video, que ya es una fila de la tabla de motores:
        # una tarjeta para un dato repetido y un párrafo de lo que no hay. Se
        # va, y lo que no hay se nombra al pie de la fila, en una frase; por
        # qué falta cada cosa, en el globo. Vuelve en cuanto tenga algo suyo
        # (el estado de una Intel reciente, o cualquier AMD).
        # El uso del motor de video ya es una barra de «Ahora mismo» (o su
        # candado): repetido aquí, el mismo dato salía dos veces.
        if any(clave == "engine.video" for clave, _v in render.engine_levels(gpu)):
            self.sensors.set_visible(_("gpu.sensor.videouse"), False)
        propios = [c for c in SENSOR_FIELDS
                   if c not in ocultos["sensors"] and c != "gpu.sensor.videouse"]
        solo_el_video = bool(gpu.engines) and not propios
        self.sensor_card.setVisible(not solo_el_video)
        fuera = pie_de_sensores(ocultos["sensors"]) if solo_el_video else ""
        self.sensors_outside.setText(fuera)
        self.sensors_outside.setToolTip(pies["sensors"] if fuera else "")
        self.sensors_outside.setVisible(bool(fuera))

        # Con las del silicio, el máximo puesto no va solo: si es el de
        # fábrica ya lo dice «Máxima (silicio)», y si alguien lo cambió va en
        # «Límites puestos», con el mínimo.
        silicio = gpu.clocks.silicon_max_hz is not None
        for clave in SILICIO:
            self.clocks.set_visible(_(clave), silicio)
        if silicio:
            self.clocks.set_visible(_("gpu.clock.coremax"), False)
        # La UHD 630 tiene la eficiente y la mínima en 350 MHz: la misma cifra
        # dos veces. Queda la mínima, y lo de eficiente pasa a su globo.
        if silicio and gpu.clocks.efficient_hz == gpu.clocks.silicon_min_hz:
            self.clocks.set_visible(_("gpu.clock.efficient"), False)
        self.clocks.set_visible(_("gpu.clock.limits"),
                                render.gpu_clock_limits(gpu.clocks) is not None)

    def _apply_engines(self, gpu: Gpu) -> None:
        """Los motores de la tarjeta, si el driver los publica.

        La tarjeta se esconde entera cuando no hay ninguno: en AMD y NVIDIA el
        kernel no los enumera, y una tabla vacía no explica nada.
        """
        self.engine_card.setVisible(bool(gpu.engines))
        if not gpu.engines:
            return
        self.engine_summary.set(_("gpu.engines.idle"), render.gpu_sleep(gpu))
        self.engines.set_rows([
            (motor.name,
             _(motor.kind) if motor.kind else render.DASH,
             render.percent(motor.busy_percent),
             # Vacía si el motor no tiene nada especial: no es un dato que
             # falte, es que no hay nada que decir.
             ", ".join(motor.capabilities))
            for motor in gpu.engines
        ])
        # El uso de cada motor sale del contador que piden los permisos: con
        # candado, como en la ficha de arriba, y no con guion.
        candado = getattr(self, "_candado", None)
        if candado is not None:
            for fila, motor in enumerate(gpu.engines):
                if motor.busy_percent is None:
                    self.engines.set_cell_locked(fila, 2, self._p.info,
                                                 render.lock_tooltip(candado))

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
        for fila, codec in enumerate(gpu.codecs):
            for columna, puede in ((1, codec.decode), (2, codec.encode)):
                self.codecs.set_cell_tone(fila, columna, "yes" if puede else "no")
                self.codecs.set_cell_tooltip(
                    fila, columna, _("gpu.codec.yes" if puede else "gpu.codec.no"))

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

    def set_lock(self, nota) -> None:
        """La nota de permisos que guarda el uso y el consumo, o None.

        La pone la página antes de `apply`, que es quien tiene la foto.
        """
        self._candado = nota

    def _apply_tiles(self, gpu: Gpu) -> None:
        candado = getattr(self, "_candado", None)
        if gpu.busy_percent is None and candado is not None:
            # Con candado y no con guion: este dato está, y tiene arreglo.
            self.tile_usage.set_locked(_("lock.detail"), render.lock_tooltip(candado))
        else:
            self._apply_usage(gpu)
        self._apply_tiles_rest(gpu, candado)

    def _apply_usage(self, gpu: Gpu) -> None:
        self.tile_usage.update_value(
            f"{gpu.busy_percent:.0f}" if gpu.busy_percent is not None else render.DASH,
            gpu.busy_percent)
        # El detalle del uso deja de repetir la memoria: ahora tiene su cuadro.
        self.tile_usage.set_detail(
            _("gpu.tile.video").format(
                pct=render.percent(gpu.video_busy_percent))
            if gpu.video_busy_percent else "")

    def _apply_tiles_rest(self, gpu: Gpu, candado) -> None:
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
            self.tile_clock.set_detail(_("gpu.clock.idle") if relojes.core_hz == 0 else "")

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

        if gpu.power_w is None and candado is not None:
            self.tile_power.set_locked(_("lock.detail"), render.lock_tooltip(candado))
        else:
            self.tile_power.update_value(
                f"{gpu.power_w:.0f}" if gpu.power_w is not None else render.DASH,
                gpu.power_w)
            self.tile_power.set_detail(
                _("gpu.tile.of").format(valor=render.watts(gpu.power_cap_w))
                if gpu.power_cap_w else "")

    def _apply_now(self, gpu: Gpu) -> None:
        """Las tres barras de «Ahora mismo». La que no tiene dato no sale, y
        sin ninguna se va la tarjeta: una integrada sin VRAM propia, sin
        permisos, no tiene nada que poner aquí."""
        de = _("gpu.now.of")
        memoria = gpu.memory
        if memoria.total_bytes and memoria.used_bytes is not None:
            self.now.set(_("gpu.now.vram"), memoria.used_bytes / memoria.total_bytes,
                         de.format(actual=render.size(memoria.used_bytes),
                                   total=render.size(memoria.total_bytes)))
        else:
            self.now.set(_("gpu.now.vram"), None)
        if gpu.power_w is not None and gpu.power_cap_w:
            self.now.set(_("gpu.now.power"), gpu.power_w / gpu.power_cap_w,
                         de.format(actual=render.watts(gpu.power_w),
                                   total=render.watts(gpu.power_cap_w)))
        else:
            self.now.set(_("gpu.now.power"), None)
        # Cuánta memoria se está moviendo, que no es cuánta hay ocupada: una
        # tarjeta con la VRAM llena y el bus parado tiene datos cargados y no
        # los toca. Y con contra qué se compara: un 21 % a secas no dice si
        # son megas o gigas por segundo.
        bus = gpu.memory_busy_percent
        if bus is not None:
            ancho = memoria.bandwidth_bytes
            self.now.set(_("gpu.now.bus"), bus / 100,
                         de.format(actual=render.bandwidth(int(ancho * bus / 100)),
                                   total=render.bandwidth(ancho)) if ancho else "",
                         tooltip=_("gpu.tip.busy"))
        else:
            self.now.set(_("gpu.now.bus"), None)
        self._apply_engine_bars(gpu)
        huecos = [_(MOTORES_AL_PIE[clave]) for clave in render.engine_gaps(gpu)]
        pie = (_("gpu.now.gap").format(motores=render.enumeration(huecos, "list.nor"))
               if huecos else "")
        self.now_pie.setText(pie)
        self.now_pie.setVisible(bool(pie))
        # Sin barras pero con algo que decir de las que faltan, la tarjeta se
        # queda: es donde se busca el uso, y sin ella desaparecería en silencio.
        self.now_card.setVisible(bool(self.now.visible_rows()) or bool(pie))

    def _apply_engine_bars(self, gpu: Gpu) -> None:
        """Una barra por motor, debajo de las de memoria, consumo y bus.

        Solo los que esta gráfica deja medir (`render.engine_levels`); lo que
        tiene y guarda un permiso sale con candado, y con permisos se mueve
        con cada muestreo. Lo que su driver no publica se nombra al pie.
        """
        candado = getattr(self, "_candado", None)
        presentes = set()
        for clave, valor in render.engine_levels(gpu):
            nombre = _(BARRAS_DE_MOTOR[clave])
            presentes.add(nombre)
            if not self.now.has(nombre):
                self.now.add(nombre)
            if valor is not None:
                self.now.set(nombre, valor / 100)
            elif candado is not None:
                self.now.set_locked(nombre, self._p.info, render.lock_tooltip(candado))
            else:
                self.now.set(nombre, None)
        for nombre in getattr(self, "_barras_de_motor", set()) - presentes:
            self.now.set(nombre, None)
        self._barras_de_motor = presentes

    def _apply_memory(self, gpu: Gpu) -> None:
        d = render.DASH
        memoria = gpu.memory
        m = self.memory.set
        m(_("gpu.vram.total"), render.size(memoria.total_bytes))
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
        render.monitor_diagonal(monitor) or d,
        render.monitor_color(monitor),
        monitor.made or d,
    )


class GraphicsPage(QScrollArea):
    elevation_requested = Signal()
    permission_snoozed = Signal()
    permission_dismissed = Signal()

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        # Lleva la cuenta de cuánto tiempo lleva frenándose cada tarjeta. Es
        # estado entre muestreos, así que vive en la página y no en el modelo.
        self._recortes = SeguidorDeRecortes()
        self._prefs = prefs
        self._sin_avisos_de_permisos = False
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
            seccion.permission_snoozed.connect(self.permission_snoozed)
            seccion.permission_dismissed.connect(self.permission_dismissed)
            self._sections.append(seccion)
            self._sections_host.addWidget(seccion)
        for sobrante in self._sections[len(snapshot.gpus):]:
            sobrante.hide()

        ahora = snapshot.monotonic_ns
        for indice, (seccion, gpu) in enumerate(zip(self._sections, snapshot.gpus)):
            # Si el uso y el consumo de esta tarjeta faltan por permisos, sus
            # fichas llevan candado en vez de guion.
            seccion.set_lock(snapshot.permission_note(f"gpus.{indice}.usage"))
            # La ranura PCI es lo único que no cambia entre muestreos: el
            # índice se mueve si aparece o desaparece una tarjeta.
            clave = gpu.pci_slot or f"gpu{gpu.index}"
            self._recortes.update(clave, gpu.throttled, gpu.throttle_reasons, ahora)
            seccion.show()
            seccion.apply(gpu, render.throttle_episode(
                self._recortes.relevante(clave, ahora), ahora) or "")

        self._apply_notices(snapshot)

    def hide_permission_notices(self, ocultos: bool) -> None:
        """Deja de enseñar los avisos de permisos, o los vuelve a enseñar."""
        self._sin_avisos_de_permisos = ocultos

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
            seccion.set_notes(por_seccion.get(indice, []),
                              sin_permisos=self._sin_avisos_de_permisos)

        signature = tuple((n.path, n.need) for n in sueltos)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in sueltos:
            self._notices_host.addWidget(
                Notice(_(NEED_TITLES.get(note.need, note.need.value)),
                       note.message, note.hint, tone=tone_for(note.need))
            )
