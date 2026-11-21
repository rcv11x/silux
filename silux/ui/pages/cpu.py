"""Página de CPU: qué procesador es este.

Responde a una sola pregunta, y por eso todo lo que cambia con el tiempo se
mudó a la página de Monitor. Lo único vivo que queda es una tira compacta
arriba con cuatro cifras: ver el reloj actual de reojo forma parte de lo que
se espera de una herramienta de identificación, pero una gráfica de un minuto
no pinta nada entre la familia y el stepping.

El árbol de widgets se construye una vez y después solo se actualizan textos:
repintar es barato, recrear widgets cada segundo hace parpadear la ventana y
pierde la selección del usuario. Las filas de tarjetas son `ResponsiveRow`,
así que al encoger la ventana pasan a menos columnas en vez de recortarse.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import render
from ...features import para_arquitectura
from ...i18n import _
from ...model import CpuType, Need, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    ChipRow,
    InfoGrid,
    Notice,
    Plegable,
    ResponsiveRow,
    ScrollPage,
    StackedBar,
    clear_layout,
    tone_for,
)
from .cpulive import CpuLiveSection

NEED_TITLES = {
    Need.ROOT: "note.needsroot",
    Need.DATABASE: "note.database",
    Need.HARDWARE: "note.hardware",
    Need.PACKAGE: "note.package",
    Need.DRIVER: "note.needsmodule",
    Need.PLATFORM: "note.platform",
    Need.ERROR: "note.failed",
    Need.KERNEL: "note.kernel",
}

# El orden va de lo que identifica al procesador a lo que solo interesa
# para depurar. Antes había cuatro filas de familia y modelo (dos de ellas
# con los bits en crudo, que por sí solos no significan nada) y ahora se
# enseñan los valores compuestos, con el desglose en el tooltip de la firma.
LIMIT_FIELDS = ("cpu.limit.pl1", "cpu.limit.pl2", "cpu.throttle")
PROCESSOR_FIELDS = (
    "cpu.field.vendor", "cpu.field.spec", "cpu.field.codename", "cpu.field.process",
    "cpu.field.package", "cpu.field.arch", "cpu.field.cores", "cpu.field.threads", "cpu.field.virt",
    "cpu.field.voltage",
)
# Con qué números se identifica el silicio. Hacen falta para un informe o
# para buscar una errata, y casi nunca para otra cosa: van plegados.
IDENTITY_FIELDS = (
    "cpu.field.family", "cpu.field.model", "cpu.field.stepping", "cpu.field.signature",
    "cpu.field.microcode",
)

CLOCK_FIELDS = (
    "cpu.clock.current", "cpu.clock.multiplier", "cpu.clock.base", "cpu.clock.min",
    "cpu.clock.maxk", "cpu.clock.maxs", "cpu.clock.bus", "cpu.clock.turbo",
    "cpu.clock.driver", "bench.cond.governor", "bench.cond.epp",
)


def table_fields(cpu_type: CpuType) -> tuple:
    """The three fields that come from the CPU table and not from the chip:
    (row, value, notes that explain it missing). An unknown chip has one
    note for the three."""
    return (("cpu.field.codename", cpu_type.codename, ("cpu.codename",)),
            ("cpu.field.process", cpu_type.technology, ("cpu.codename", "cpu.technology")),
            ("cpu.field.package", cpu_type.socket, ("cpu.codename", "cpu.socket")))


class TypeSection(QWidget):
    """Las tarjetas de un tipo de núcleo. En una CPU híbrida hay dos."""

    def __init__(self, palette: Palette, prefs: Preferences, title: Optional[str], parent=None):
        super().__init__(parent)
        self._prefs = prefs
        m = theme.METRICS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.section_gap)

        if title:
            heading = QLabel(title)
            heading.setObjectName("Subhead")
            layout.addWidget(heading)

        processor_card = Card(_("cpu.card.processor"))
        self.processor = InfoGrid()
        for name in PROCESSOR_FIELDS:
            self.processor.add(_(name))
        # La cadena del procesador es larga y es una frase: dos líneas antes
        # que puntos suspensivos.
        self.processor._values[_("cpu.field.spec")].permitir_lineas(2)
        processor_card.body.addWidget(self.processor)
        self.virtual_foot = QLabel(_("cpu.virtual.foot"))
        self.virtual_foot.setObjectName("Muted")
        self.virtual_foot.setWordWrap(True)
        self.virtual_foot.setFont(ui_font(m.small_pt))
        self.virtual_foot.hide()
        processor_card.body.addWidget(self.virtual_foot)
        self.identity_fold = Plegable(_("cpu.card.identity"))
        self.identity = InfoGrid()
        for name in IDENTITY_FIELDS:
            self.identity.add(_(name))
        self.identity_fold.body.addWidget(self.identity)
        processor_card.body.addWidget(self.identity_fold)

        clocks_card = self.clocks_card = Card(_("cpu.card.clocks"))
        self.clocks = InfoGrid()
        for name in CLOCK_FIELDS:
            self.clocks.add(_(name))
        clocks_card.body.addWidget(self.clocks)
        self.turbo_hint = QLabel("")
        self.turbo_hint.setObjectName("Accent")
        self.turbo_hint.setWordWrap(True)
        self.turbo_hint.setFont(ui_font(m.small_pt))
        self.turbo_hint.hide()
        clocks_card.body.addWidget(self.turbo_hint)
        # What a machine without a frequency driver has not (rule 5).
        self.clocks_foot = QLabel("")
        self.clocks_foot.setObjectName("Muted")
        self.clocks_foot.setWordWrap(True)
        self.clocks_foot.setFont(ui_font(m.small_pt))
        self.clocks_foot.hide()
        clocks_card.body.addWidget(self.clocks_foot)

        columns = ResponsiveRow(min_item_width=270)
        columns.add(processor_card)
        columns.add(clocks_card)
        layout.addWidget(columns)

        cache_card = Card(_("cpu.card.cache"))
        self.caches = InfoGrid()
        cache_card.body.addWidget(self.caches)
        layout.addWidget(cache_card)

        features_card = Card(_("cpu.card.features"))
        self.chips = ChipRow()
        features_card.body.addWidget(self.chips)
        self.feature_count = QLabel("")
        self.feature_count.setObjectName("Muted")
        self.feature_count.setWordWrap(True)
        self.feature_count.setFont(ui_font(m.small_pt))
        layout.addWidget(features_card)
        features_card.body.addWidget(self.feature_count)

        self._cache_rows: list[str] = []
        self._voltaje = None
        self._base_hz = None
        self._base_texto = render.DASH
        self._chip_signature: tuple = ()

    def lock_voltage(self, nota, color: str) -> None:
        """El voltaje falta por permisos (`nota`) o por otra cosa (None)."""
        nombre = _("cpu.field.voltage")
        if nota is not None and self._voltaje is None:
            self.processor.set_locked(nombre, color, render.lock_tooltip(nota))
        elif self.processor.is_locked(nombre):
            self.processor.set(nombre, render.volts(self._voltaje),
                               tooltip=_("cpu.tip.voltage"))

    def lock_base(self, nota, color: str) -> None:
        """The base clock missing for permissions (`nota`): a Zen states it in
        its P0, which only the administrator reads."""
        nombre = _("cpu.clock.base")
        if nota is not None and self._base_hz is None:
            self.clocks.set_locked(nombre, color, render.lock_tooltip(nota))
        elif self.clocks.is_locked(nombre):
            self.clocks.set(nombre, self._base_texto)

    def apply(self, cpu_type: CpuType, explained: frozenset = frozenset()) -> None:
        """`explained`: the paths of the notes on the page about the CPU table."""
        p = self.processor.set  # noqa: E741
        p(_("cpu.field.vendor"), cpu_type.vendor or render.DASH)
        p(_("cpu.field.spec"), cpu_type.brand or render.DASH)
        virtual = cpu_type.in_virtual_machine
        self.virtual_foot.setVisible(virtual)
        for key, value, notes in table_fields(cpu_type):
            # Not in the CPU table: the row hides and the notice below the
            # cards says so (rule 5). Without a notice to say it, it stays.
            # A virtual CPU is not looked up: its foot says so.
            hidden = virtual or (not value and not explained.isdisjoint(notes))
            self.processor.set_visible(_(key), not hidden)
            if not hidden:
                p(_(key), render.from_cpu_table(value))
        p(_("cpu.field.arch"), cpu_type.architecture or render.DASH)
        p(_("cpu.field.cores"), str(cpu_type.cores))
        p(_("cpu.field.threads"), f"{cpu_type.threads}" + (_("cpu.smt.on") if cpu_type.smt else ""))
        p(_("cpu.field.virt"), self._virtualization(cpu_type))
        i = self.identity.set
        i(_("cpu.field.family"), render.hex_id(cpu_type.disp_family))
        i(_("cpu.field.model"), render.hex_id(cpu_type.disp_model))
        i(_("cpu.field.stepping"), render.dec(cpu_type.stepping))
        i(_("cpu.field.signature"), render.signature(cpu_type.signature),
          tooltip=render.signature_tooltip(cpu_type))
        i(_("cpu.field.microcode"), cpu_type.microcode or render.DASH)
        # A virtual CPU has no microcode or voltage of its own, and when the
        # hypervisor gives no clock at all the card would be all dashes: the
        # notice below the cards says why.
        self.identity.set_visible(_("cpu.field.microcode"),
                                  not (virtual and cpu_type.microcode is None))
        self.processor.set_visible(_("cpu.field.voltage"),
                                   not (virtual and cpu_type.voltage_v is None))
        self.clocks_card.setVisible(not (virtual and cpu_type.clocks.current_hz is None))
        # El voltaje va con los demás datos del silicio y no con los relojes:
        # es lo que la pieza pide para sostener la frecuencia que tiene puesta.
        # Si falta por permisos lleva candado, que lo pone la página después:
        # aquí solo se sabe del procesador, no de por qué falta algo.
        self._voltaje = cpu_type.voltage_v
        if self._voltaje is not None or not self.processor.is_locked(_("cpu.field.voltage")):
            p(_("cpu.field.voltage"), render.volts(cpu_type.voltage_v),
              tooltip=_("cpu.tip.voltage"))

        c = self.clocks.set
        clocks = cpu_type.clocks
        c(_("cpu.clock.current"), render.hz(clocks.current_hz))
        c(_("cpu.clock.multiplier"), render.multiplier(clocks.multiplier))
        self._base_hz = clocks.base_hz
        self._base_texto = render.clock_and_multiplier(clocks.base_hz, clocks.base_multiplier)
        if self._base_hz is not None or not self.clocks.is_locked(_("cpu.clock.base")):
            c(_("cpu.clock.base"), self._base_texto)
        c(_("cpu.clock.min"), render.clock_and_multiplier(
            clocks.min_hz, clocks.min_multiplier))
        c(_("cpu.clock.maxkernel"), render.clock_and_multiplier(
            clocks.max_hz, clocks.max_multiplier))
        c(_("cpu.clock.maxsilicon"), render.clock_and_multiplier(
            clocks.max_turbo_hz, clocks.max_turbo_multiplier))
        c(_("cpu.clock.bus"), render.hz(clocks.bus_hz, 0))
        c(_("cpu.clock.turbo"), render.turbo(clocks))
        c(_("cpu.clock.driver"), clocks.driver or render.DASH)
        c(_("cpu.clock.governor"), clocks.governor or render.DASH)
        c(_("cpu.clock.epp"), clocks.energy_preference or render.DASH)
        # Without cpufreq these do not exist: the foot says why, and where
        # the frequency above comes from.
        foot = render.without_frequency_driver(clocks)
        for clave in ("cpu.clock.min", "cpu.clock.maxkernel", "cpu.clock.driver",
                      "cpu.clock.governor", "cpu.clock.epp"):
            self.clocks.set_visible(_(clave), foot is None)
        self.clocks_foot.setText(foot or "")
        self.clocks_foot.setVisible(foot is not None)

        if hint := render.turbo_note(clocks):
            self.turbo_hint.setText(hint)
            self.turbo_hint.show()
        else:
            self.turbo_hint.hide()

        self._apply_caches(cpu_type)
        self._apply_features(cpu_type)

    @staticmethod
    def _virtualization(cpu_type: CpuType) -> str:
        if cpu_type.in_virtual_machine:
            base = _("cpu.virt.inside")
            return f"{cpu_type.virtualization} · {base}" if cpu_type.virtualization else base
        if cpu_type.virtualization:
            return f"{cpu_type.virtualization} {_('cpu.virt.supported')}"
        return _("cpu.virt.none")

    def _apply_caches(self, cpu_type: CpuType) -> None:
        # One row per level and kind. A 7950X3D has two L3 of different sizes,
        # and two rows with the same name made the second one replace the first.
        grupos: dict[str, list] = {}
        for cache in cpu_type.caches:
            grupos.setdefault(render.cache_label(cache), []).append(cache)
        labels = list(grupos)
        if labels != self._cache_rows:
            self.caches.reset()
            for label in labels:
                self.caches.add(label)
            self._cache_rows = labels

        for label, caches in grupos.items():
            cache = caches[0]
            tooltip = _("cpu.cache.tip").format(
                total=render.size(sum(c.total_bytes for c in caches)), sets=cache.sets)
            if len(caches) > 1 and cache.level == 3 and (reparto := render.l3_asimetrica(cpu_type)):
                tooltip = f"{reparto}\n\n{tooltip}"
            self.caches.set(
                label,
                render.caches_summary(caches) + "    "
                + _("cpu.cache.line.one" if cache.shared_by == 1 else "cpu.cache.line").format(
                    b=cache.line_bytes, hilos=cache.shared_by),
                tooltip=tooltip,
            )

    def _apply_features(self, cpu_type: CpuType) -> None:
        destacadas, bonitos = para_arquitectura(cpu_type.architecture)
        present = set(cpu_type.features)
        if self._prefs.show_all_features:
            shown = [bonitos.get(f, f.upper()) for f in cpu_type.features]
        else:
            shown = [bonitos.get(f, f.upper()) for f in destacadas if f in present]
        if cpu_type.smt:
            shown.insert(0, "HT" if cpu_type.vendor == "Intel" else "SMT")

        signature = tuple(shown)
        if signature != self._chip_signature:
            self.chips.set_chips(shown)
            self._chip_signature = signature

        rest = len(cpu_type.features) - len(shown)
        self.feature_count.setText(
            _("cpu.flags.count").format(n=len(cpu_type.features))
            + (_("cpu.flags.rest").format(n=rest) if rest > 0 else "")
        )


class CpuPage(ScrollPage):
    # La pide la ventana para lanzar el ayudante, igual que Memoria, Gráficos
    # y Almacenamiento. Todos los botones piden lo mismo y se lanza un solo
    # ayudante, así que pulsar cualquiera desbloquea todo.
    elevation_requested = Signal()
    # Los dos botones de apartar el aviso de permisos, que valen para todos.
    permission_snoozed = Signal()
    permission_dismissed = Signal()

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._sin_avisos_de_permisos = False
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        self._layout.addWidget(self._build_header())

        # Lo que el procesador está haciendo ahora, antes que sus fichas: aquí
        # es donde se busca a cuánto va, y en Sensores dejaba el árbol —que es
        # lo propio de esa página— reducido a una rendija.
        self.live = CpuLiveSection(palette, prefs)
        self.live.locked_clicked.connect(self.elevation_requested)
        self._layout.addWidget(self.live)

        # Cuánto puede gastar y cuánto descansa: lo que explica un consumo en
        # reposo alto o un procesador que no llega a su frecuencia.
        self.energy_card = Card(_("cpu.card.energy"))
        self.limits = InfoGrid()
        for name in LIMIT_FIELDS:
            self.limits.add(_(name))
        self.energy_card.body.addWidget(self.limits)
        self.idle_title = QLabel(_("cpu.idle.title"))
        self.idle_title.setObjectName("FieldName")
        self.idle_title.setFont(ui_font(theme.METRICS.small_pt))
        self.energy_card.body.addWidget(self.idle_title)
        self.idle_bar = StackedBar(palette)
        self.energy_card.body.addWidget(self.idle_bar)
        self.idle_note = QLabel("")
        self.idle_note.setObjectName("Muted")
        self.idle_note.setWordWrap(True)
        self.idle_note.setFont(ui_font(theme.METRICS.small_pt))
        self.energy_card.body.addWidget(self.idle_note)
        self.energy_pie = QLabel("")
        self.energy_pie.setObjectName("Muted")
        self.energy_pie.setWordWrap(True)
        self.energy_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.energy_card.body.addWidget(self.energy_pie)
        self.energy_card.hide()
        self._layout.addWidget(self.energy_card)

        self._sections_host = QVBoxLayout()
        self._sections_host.setSpacing(m.section_gap)
        self._layout.addLayout(self._sections_host)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        self._layout.addLayout(self._notices_host)

        self._layout.addStretch(1)

        self._sections: dict[str, TypeSection] = {}
        self._signature: tuple = ()
        self._notice_signature: tuple = ()
        self._badge_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("cpu.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")

        # Una fila fija de insignias impedía encoger la ventana: entre las
        # cuatro sumaban más de 300 px y el contenido se recortaba en silencio.
        self.badges = ChipRow()

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self.live.apply(snapshot)
        cpu = snapshot.cpu
        # Los avisos van antes de rendirse: si no se reconoce el procesador,
        # que es cuando más falta hace decir por qué, la página se plantaba y
        # no pintaba ninguno. Justo el caso de un equipo raro o de un ARM sin
        # entrada en la base de datos, donde el usuario se queda mirando una
        # pantalla vacía sin nada que le explique qué ha pasado.
        self._apply_notices(snapshot)
        self._apply_energy(snapshot)
        if not cpu.types:
            return

        primary = cpu.types[0]
        # El titular va sin la coletilla, como en Inicio: «AMD Ryzen 7 7445HS»
        # y no «AMD Ryzen 7 7445HS w/ Radeon 740M Graphics», que ocupa dos
        # líneas para hablar de la gráfica en la página del procesador. La
        # cadena entera sigue estando en «Especificación», que es el dato tal
        # y como lo dice el silicio.
        self.title.setText(render.cpu_short_name(primary.brand)
                           if primary.brand else _("cpu.unknown"))
        self.subtitle.setText(
            _("cpu.subtitle").format(
                nucleos=cpu.total_cores, hilos=cpu.total_threads,
                sockets=cpu.sockets,
                s="s" if cpu.sockets > 1 else "")
            + (_("cpu.subtitle.hybrid") if cpu.hybrid else "")
        )
        self._apply_badges(primary)
        self._apply_sections(snapshot)

    def _apply_badges(self, cpu_type: CpuType) -> None:
        # La de máquina virtual va primera y se lleva el resaltado: sin ella,
        # «2 núcleos · 2 hilos · 2 sockets» de un i5-10500T (que trae 6 y 12,
        # y un solo socket) se lee como que el programa cuenta mal, cuando es
        # la topología que le dio el hipervisor.
        wanted = tuple(x for x in (render.virtual_machine(cpu_type),
                                   cpu_type.codename, cpu_type.socket,
                                   cpu_type.technology, cpu_type.architecture) if x)
        if wanted == self._badge_signature:
            return
        self._badge_signature = wanted
        self.badges.set_chips(wanted, highlight_first=True)

    def _temp(self, celsius: float) -> float:
        return celsius * 9 / 5 + 32 if self._prefs.fahrenheit else celsius

    def _apply_sections(self, snapshot: Snapshot) -> None:
        cpu = snapshot.cpu
        signature = tuple(t.key for t in cpu.types)
        if signature != self._signature:
            clear_layout(self._sections_host)
            self._sections.clear()
            for cpu_type in cpu.types:
                title = render.core_type_label(cpu_type, cpu.hybrid) if cpu.hybrid else None
                section = TypeSection(self._p, self._prefs, title)
                # El candado del voltaje pide lo mismo que el botón del aviso.
                section.processor.locked_clicked.connect(self.elevation_requested)
                section.clocks.locked_clicked.connect(self.elevation_requested)
                self._sections[cpu_type.key] = section
                self._sections_host.addWidget(section)
            self._signature = signature

        explained = frozenset(n.path for n in snapshot.notes if n.need == Need.DATABASE)
        for cpu_type in cpu.types:
            if section := self._sections.get(cpu_type.key):
                section.apply(cpu_type, explained)
                section.lock_voltage(snapshot.permission_note("cpu.voltage_v"), self._p.info)
                section.lock_base(snapshot.permission_note("cpu.clocks.base_hz"), self._p.info)

    def hide_permission_notices(self, ocultos: bool) -> None:
        """Deja de enseñar los avisos de permisos, o los vuelve a enseñar."""
        self._sin_avisos_de_permisos = ocultos

    def _apply_energy(self, snapshot: Snapshot) -> None:
        """Los límites de potencia y el reposo. Lo que no hay no sale."""
        cpu = snapshot.cpu
        potencia, estados = cpu.power, cpu.idle_states
        limites = (("cpu.limit.pl1", potencia.limit_long_w, potencia.window_long_s),
                   ("cpu.limit.pl2", potencia.limit_short_w, potencia.window_short_s))
        for clave, valor, ventana in limites:
            self.limits.set(_(clave), render.power_limit(valor, ventana) if valor else render.DASH,
                            tooltip=_("cpu.limit.window.tip") if ventana else None)
            self.limits.set_visible(_(clave), bool(valor))
        hay_limites = any(valor for _clave, valor, _ventana in limites)
        frenos = cpu.thermal_throttle
        self.limits.set(_("cpu.throttle"), render.thermal_throttle(frenos),
                        tooltip=_("cpu.throttle.tip"))
        self.limits.set_visible(_("cpu.throttle"), frenos is not None)
        self.limits.setVisible(hay_limites or frenos is not None)
        # En AMD no faltan por leer: el kernel no los publica.
        es_amd = bool(cpu.types) and cpu.types[0].vendor == "AMD"
        self.energy_pie.setText(_("cpu.limit.amd") if es_amd and not hay_limites else "")
        self.energy_pie.setVisible(bool(self.energy_pie.text()))

        for widget in (self.idle_title, self.idle_bar, self.idle_note):
            widget.setVisible(bool(estados))
        if estados:
            self.idle_bar.set_segments(render.idle_segments(estados), 100.0,
                                       formatter=lambda v: f"{v:.0f} %")
            self.idle_note.setText(render.idle_deepest(estados) or "")
        self.energy_card.setVisible(hay_limites or bool(estados) or frenos is not None)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        # Solo las de esta pestaña: la de los módulos de memoria salía aquí
        # porque se enseñaban todas, y no pinta nada junto al procesador.
        notes = snapshot.notes_for("cpu")
        if self._sin_avisos_de_permisos:
            # Apartados desde aquí o desde Inicio. Lo que falta sigue dicho en
            # su sitio, con el candado, y en el enlace de la barra de estado.
            notes = tuple(n for n in notes if n.need is not Need.ROOT)
        signature = tuple((n.path, n.need, n.helper_outdated) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            # Con el botón dentro, como en Gráficos. Quien lee por qué falta el
            # consumo del procesador es quien quiere arreglarlo, y hasta ahora
            # el aviso salía aquí y el botón estaba en Memoria, en Gráficos y
            # en Almacenamiento. Lo trajo la captura de un usuario con los
            # vatios en blanco: el aviso lo tenía delante y la salida en otra
            # sección.
            aviso = Notice(
                render.permission_title(note, _(NEED_TITLES.get(note.need, note.need.value))),
                note.message, note.hint,
                action=(render.permission_action(note)
                        if note.need is Need.ROOT else None),
                tone=tone_for(note.need),
                dismissible=note.need is Need.ROOT,
            )
            if aviso.action_button is not None:
                aviso.action_clicked.connect(self.elevation_requested)
                aviso.snoozed.connect(self.permission_snoozed)
                aviso.dismissed.connect(self.permission_dismissed)
            self._notices_host.addWidget(aviso)
