"""Página de memoria.

Sin permisos solo se sabe el total, así que la página no finge: enseña lo que
puede y explica exactamente qué falta, cuánto se ganaría y con un botón para
pedirlo. Nada de diálogos de contraseña al arrancar.

Cada módulo tiene su tarjeta; los zócalos vacíos no se enseñan ni se
cuentan: la tabla del firmware declara ranuras que la placa no tiene, y no
hay forma segura de distinguir una vacía de verdad de una fantasma.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import db, kernel, render
from ...i18n import _
from ...model import (
    JEDEC_TOP_MTS,
    MemoryModule,
    Need,
    SensorKind,
    Snapshot,
    firmware_contradicted,
    module_numbers,
)
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    ChipRow,
    FoldingRow,
    InfoGrid,
    ModuleNotices,
    Notice,
    Plegable,
    ResponsiveRow,
    ScrollPage,
    StackedBar,
    Table,
    boton_de_permiso_permanente,
    clear_layout,
    dismiss_buttons,
    memory_segments,
    paint_level,
    tone_for,
)

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

MODULE_FIELDS = ("memory.field.slot", "memory.field.vendor", "memory.field.chips", "memory.field.part", "memory.field.type", "memory.field.size",
                 "memory.field.rated", "memory.field.running", "memory.field.ranks", "memory.field.voltage",
                 "memory.field.form", "memory.field.profiles", "memory.field.made", "memory.field.bank",
                 "memory.field.temp")

# Cómo se nombra, en la frase del pie, cada campo que solo trae el SPD.
SOLO_DEL_SPD = {
    "memory.field.vendor": "memory.na.vendor",
    "memory.field.part": "memory.na.part",
    "memory.field.size": "memory.na.size",
    "memory.field.ranks": "memory.na.ranks",
    "memory.field.chips": "memory.na.chips",
    "memory.field.profiles": "memory.na.profiles",
    "memory.field.made": "memory.na.made",
}

# What a module's SPD may leave blank, and how the foot names it.
SPD_DECLARES = {
    "memory.field.vendor": "memory.na.vendor",
    "memory.field.chips": "memory.na.chips",
    "memory.field.part": "memory.na.part",
    "memory.field.made": "memory.na.made",
}

TIMING_HEADERS = ("memory.timing.profile", "memory.timing.speed", "memory.timing.cl",
                  "memory.timing.taa", "memory.timing.trcd", "memory.timing.trp",
                  "memory.timing.tras", "memory.timing.trc", "memory.field.voltage")


# El desglose del uso, tal como lo cuenta el kernel. Va plegado en la
# cabecera: la barra ya dice lo principal.
USAGE_FIELDS = ("sys.mem.total", "sys.mem.used", "sys.mem.available",
                "sys.mem.apps", "sys.mem.cache", "sys.mem.buffers",
                "sys.mem.shared", "sys.mem.free", "sys.mem.swap",
                "sys.mem.swapused")


class MemoryPage(ScrollPage):
    elevation_requested = Signal()
    permanent_requested = Signal()
    explain_requested = Signal()
    permission_snoozed = Signal()
    permission_dismissed = Signal()
    # Someone wants the memory test: it lives in Performance.
    benchmark_requested = Signal()

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        # El máximo oficial de memoria del procesador, si la tabla lo sabe.
        self._limite = None
        # La versión del kernel de la foto, (6, 11).
        self._kernel = None
        self._nota_spd = None
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        layout.setSpacing(m.section_gap)

        # El orden de la página es el de lo que se viene a mirar: cuánta hay
        # y cómo está ocupada, los módulos, sus temporizaciones, lo que se
        # puede medir, y al final lo que falta y por qué. La tarjeta que pide
        # permisos iba la segunda, y sin ellos no había un dato hasta el
        # tercer bloque; lo que falta lo señala ya el candado de cada módulo.
        layout.addWidget(self._build_header())
        self.elevation = self._build_elevation()

        self._slots_host = ResponsiveRow(min_item_width=290)
        layout.addWidget(self._slots_host)

        self.spd_missing = QLabel("")
        self.spd_missing.setObjectName("Muted")
        self.spd_missing.setWordWrap(True)
        self.spd_missing.setFont(ui_font(theme.METRICS.small_pt))
        self.spd_missing.hide()
        layout.addWidget(self.spd_missing)

        self.timings_card = Card(_("memory.card.timings"))
        self.timings = Table([_(h) for h in TIMING_HEADERS],
                             numeric=(False, True, True, True, True, True, True, True, True))
        self.timings.set_header_tooltip(TIMING_HEADERS.index("memory.timing.taa"),
                                        _("memory.tip.taa"))
        self.spd_note = QLabel(_("memory.spd.note"))
        self.spd_note.setObjectName("Muted")
        self.spd_note.setWordWrap(True)
        self.spd_note.setFont(ui_font(theme.METRICS.small_pt))
        self.timings_card.body.addWidget(self.timings)
        self.timings_card.body.addWidget(self.spd_note)
        layout.addWidget(self.timings_card)

        layout.addWidget(self._build_bandwidth())
        layout.addWidget(self._build_traffic())
        layout.addWidget(self.elevation)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        layout.addLayout(self._notices_host)
        self.module_notices = ModuleNotices(frozenset({"spd5118", "ee1004", "at24"}))
        layout.addWidget(self.module_notices)

        layout.addStretch(1)

        self._module_signature: tuple = ()
        self._notice_signature: tuple = ()
        self._slot_grids: list[InfoGrid] = []
        self._sin_avisos_de_permisos = False

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("memory.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.subtitle.setWordWrap(True)
        self.badges = ChipRow()
        self.bar = StackedBar(self._p)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        card.body.addWidget(self.bar)
        # Lo que la barra no dice, en un renglón: cuánta queda de verdad
        # disponible y cómo va el intercambio. Y el desglose entero —que
        # vivía en Sistema, repetido con esta misma barra— plegado debajo.
        self.usage_line = QLabel("")
        self.usage_line.setObjectName("Muted")
        self.usage_line.setWordWrap(True)
        self.usage_line.setFont(ui_font(theme.METRICS.small_pt))
        card.body.addWidget(self.usage_line)
        self.usage_fold = Plegable(_("memory.usage.fold"))
        self.usage = InfoGrid()
        for name in USAGE_FIELDS:
            self.usage.add(_(name))
        self.usage_fold.body.addWidget(self.usage)
        card.body.addWidget(self.usage_fold)
        # Dos cosas que la gente no sabe que le pasan: la memoria en un solo
        # canal y el perfil rápido sin activar. Las dos se calculaban ya y
        # salían escondidas dentro de la ficha de un módulo, a dos clics.
        self.avisos = QLabel()
        self.avisos.setObjectName("NoticeHint")
        self.avisos.setWordWrap(True)
        self.avisos.hide()
        card.body.addWidget(self.avisos)
        return card

    def _apply_usage(self, memory) -> None:
        hay_swap = bool(memory.swap_total_bytes)
        self.usage_line.setText(
            _("memory.usage.line").format(
                disponible=render.size(memory.available_bytes),
                usado=render.size(memory.swap_used_bytes),
                total=render.size(memory.swap_total_bytes))
            if hay_swap else
            _("memory.usage.line.noswap").format(
                disponible=render.size(memory.available_bytes)))
        m = self.usage.set
        m(_("sys.mem.total"), render.size(memory.total_bytes))
        m(_("sys.mem.used"), _("sys.value.pct").format(
            valor=render.size(memory.used_bytes),
            pct=f"{memory.used_percent:.0f}"),
          tooltip=_("sys.tip.used"))
        m(_("sys.mem.available"), render.size(memory.available_bytes))
        m(_("sys.mem.apps"), render.size(memory.apps_bytes),
          tooltip=_("sys.tip.apps"))
        m(_("sys.mem.cache"), render.size(memory.cache_bytes),
          tooltip=_("sys.tip.cache"))
        m(_("sys.mem.buffers"), render.size(memory.buffers_bytes))
        m(_("sys.mem.shared"), render.size(memory.shared_bytes))
        m(_("sys.mem.free"), render.size(memory.free_bytes))
        m(_("sys.mem.swap"), render.size(memory.swap_total_bytes) if hay_swap else _("sys.noswap"))
        # Sin swap, «Intercambio usado: —» se lee como si faltara un dato. No
        # falta: es que no hay nada de lo que decir cuánto se usa.
        self.usage.set_visible(_("sys.mem.swapused"), hay_swap)
        if hay_swap:
            m(_("sys.mem.swapused"),
              _("sys.value.pct").format(
                  valor=render.size(memory.swap_used_bytes),
                  pct=f"{memory.swap_used_percent:.0f}"))

    def _build_elevation(self) -> QWidget:
        card = Card(_("memory.card.modules"))

        self.elevation_text = QLabel("")
        self.elevation_text.setObjectName("NoticeBody")
        self.elevation_text.setWordWrap(True)
        self.elevation_text.setFont(ui_font(theme.METRICS.small_pt))

        self.elevation_hint = QLabel("")
        self.elevation_hint.setObjectName("Muted")
        self.elevation_hint.setWordWrap(True)
        self.elevation_hint.setFont(ui_font(theme.METRICS.small_pt))

        self.elevation_button = QPushButton(_("perm.read.button"))
        self.elevation_button.setToolTip(
            _("memory.tip.elevate")
        )
        self.elevation_button.clicked.connect(self.elevation_requested)

        self.permanent_button = boton_de_permiso_permanente()
        self.permanent_button.clicked.connect(self.permanent_requested)
        # «Qué hace esto», como en el aviso de Inicio: lo que pasa al dar
        # permisos y cómo darlos para siempre se cuenta en un sitio solo.
        self.explain_button = QPushButton(_("perm.notice.explain"))
        self.explain_button.setObjectName("GhostButton")
        self.explain_button.clicked.connect(self.explain_requested)

        # Los mismos dos botones que el aviso de Inicio, y hacen lo mismo.
        self.snooze_button, self.dismiss_button = dismiss_buttons()
        self.snooze_button.clicked.connect(self.permission_snoozed)
        self.dismiss_button.clicked.connect(self.permission_dismissed)

        row = FoldingRow()
        # First, where the one that gives permissions goes: with the helper
        # out of date it's the only thing to do, as in Home's notice.
        row.add_widget(self.permanent_button)
        row.add_widget(self.elevation_button)
        row.add_widget(self.explain_button)
        row.add_stretch(1)
        row.add_widget(self.snooze_button)
        row.add_widget(self.dismiss_button)

        card.body.addWidget(self.elevation_text)
        card.body.addWidget(self.elevation_hint)
        card.body.addWidget(row)
        return card

    def _build_traffic(self) -> QWidget:
        """Lo que la memoria mueve sin que nadie se lo pida.

        Va pegada a la del ancho de banda y no dentro: son dos preguntas que
        se responden en la misma unidad y significan cosas contrarias —lo que
        la memoria está dando y lo que podría dar—, y en una sola lista se
        leen como la misma cifra medida dos veces.
        """
        card = Card(_("memory.card.traffic"))

        self.traffic_grid = InfoGrid()
        self.traffic_grid.add(_("memory.traffic.now"))
        self.traffic_grid.add(_("memory.traffic.read"))
        self.traffic_grid.add(_("memory.traffic.write"))
        # De dónde sale el resto va en la ayuda y no en una fila suya: son la
        # gráfica integrada y los dispositivos, y sus contadores marcan lo
        # mismo con la máquina parada que a plena carga, así que no se separan.
        self.traffic_grid.add(_("memory.traffic.cpu"),
                              tooltip=_("memory.traffic.cpu.tip"))

        self.traffic_note = QLabel(_("memory.traffic.note"))
        self.traffic_note.setObjectName("Muted")
        self.traffic_note.setWordWrap(True)
        self.traffic_note.setFont(ui_font(theme.METRICS.small_pt))

        card.body.addWidget(self.traffic_grid)
        card.body.addWidget(self.traffic_note)
        self.traffic_card = card
        return card

    def _build_bandwidth(self) -> QWidget:
        """The last memory test, in short, and the way to its tab.

        The test itself lives in Performance, with the others: here is only
        what it gave, next to the modules it was measured on.
        """
        card = Card(_("memory.card.lasttest"))
        self.test_when = QLabel("")
        self.test_when.setObjectName("Muted")
        self.test_when.setFont(ui_font(theme.METRICS.small_pt))
        self.test_summary = QLabel("")
        self.test_summary.setWordWrap(True)
        self.test_link = QPushButton("")
        self.test_link.setObjectName("TextButton")
        self.test_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_link.clicked.connect(self.benchmark_requested)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.test_link)
        row.addStretch(1)
        card.body.addWidget(self.test_when)
        card.body.addWidget(self.test_summary)
        card.body.addLayout(row)
        self.set_last_test(None)
        return card

    def set_last_test(self, result) -> None:
        """What the last memory test gave, or that there is none yet."""
        from ... import memtest

        if result is None or not result.measured:
            self.test_when.hide()
            self.test_summary.setText(_("memory.lasttest.none"))
            self.test_link.setText(_("memory.lasttest.measure"))
            return
        parts = []
        if (ram := result.level("RAM")) is not None:
            parts.append(_("memory.lasttest.ram").format(ns=render.nanoseconds(ram.nanoseconds)))
        if (read := result.rate("read")) is not None:
            text = _("memory.lasttest.read").format(
                rate=render.bandwidth(read.bytes_per_second, 1))
            if (share := memtest.share_of_theoretical(result)) is not None:
                text += " " + _("memory.lasttest.share").format(pct=f"{share:.0f}")
            parts.append(text)
        self.test_when.setText(time.strftime("%d/%m/%Y %H:%M", time.localtime(result.timestamp)))
        self.test_when.show()
        self.test_summary.setText(" · ".join(parts))
        self.test_link.setText(_("memory.lasttest.open"))


    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self.module_notices.apply(snapshot.driver_hints)
        memory = snapshot.system.memory
        array = snapshot.memory_array

        instalada = snapshot.installed_memory_bytes
        if instalada:
            self.title.setText(_("mem.title.installed").format(
                instalada=render.size(instalada), util=render.size(memory.total_bytes)))
        else:
            self.title.setText(_("mem.title").format(util=render.size(memory.total_bytes)))
        self.subtitle.setText(self._subtitle(snapshot))
        self._limite = self._limite_del_procesador(snapshot)
        self._kernel = kernel.version(snapshot.system.kernel)
        # Por qué no se lee el SPD, si no se lee: lo diagnostica el proveedor.
        self._nota_spd = next((n for n in snapshot.notes if n.path == "spd"), None)
        self._apply_avisos(snapshot)
        self._apply_badges(snapshot)

        self.bar.set_segments(
            memory_segments(memory),
            total=memory.total_bytes,
            formatter=render.size,
        )
        self._apply_usage(memory)

        display = self._display_modules(snapshot)
        self._apply_elevation(snapshot)
        # Sin SMBIOS las tarjetas se fabrican del SPD y su título es un
        # contador nuestro, no el zócalo: hace falta saberlo para la pista.
        self._apply_modules(tuple(display), array,
                            del_spd=not snapshot.modules,
                            candado=(snapshot.permission_note("modules")
                                     if not snapshot.modules else None))
        self._apply_module_temperatures(snapshot, display)
        self._apply_timings(display)
        self._apply_traffic(snapshot)
        self._apply_notices(snapshot)

    def _apply_traffic(self, snapshot: Snapshot) -> None:
        """El tráfico de ahora mismo, o la tarjeta escondida si no lo hay.

        Escondida y no a guiones: sin el contador no es que falte la cifra, es
        que este equipo no la publica, y una tarjeta con cuatro rayas se lee
        como un dato que se ha perdido. Lo que queda dicho es la nota, que
        explica cuál de las dos cosas pasa.
        """
        trafico = snapshot.memory_traffic
        self.traffic_card.setVisible(trafico is not None)
        if trafico is None:
            return

        teorico = render.memory_theoretical_bandwidth(snapshot.modules)
        parte = render.memory_bandwidth_share(trafico.total_bytes_s, teorico)
        texto = render.rate(trafico.total_bytes_s)
        if parte is not None:
            texto += "   " + _("memory.bw.share").format(
                pct=f"{parte:.0f}", total=render.bandwidth(teorico))
        self.traffic_grid.set(_("memory.traffic.now"), texto)
        self.traffic_grid.set(_("memory.traffic.read"), render.rate(trafico.read_bytes_s))
        self.traffic_grid.set(_("memory.traffic.write"), render.rate(trafico.write_bytes_s))

        hay_nucleos = trafico.cpu_bytes_s is not None
        self.traffic_grid.set_visible(_("memory.traffic.cpu"), hay_nucleos)
        if hay_nucleos:
            self.traffic_grid.set(_("memory.traffic.cpu"),
                                  render.rate(trafico.cpu_bytes_s))

    def _apply_notices(self, snapshot: Snapshot) -> None:
        # La tarjeta de elevación ya explica lo de los permisos, así que aquí
        # solo van las notas que no cubre: por ejemplo, un SPD que no se sabe
        # interpretar todavía.
        told = getattr(self, "_spd_reason_told", False)
        notes = [n for n in snapshot.notes
                 if (n.path.startswith("spd") and not (told and n.path == "spd"))
                 or (n.path.startswith("modules") and snapshot.modules)
                 or (n.path == "memory.traffic" and n.need is not Need.ROOT)]
        signature = tuple((n.path, n.need, n.title, n.message, n.hint) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(render.note_title(note, NEED_TITLES),
                       note.message, note.hint, tone=tone_for(note.need))
            )

    def _apply_avisos(self, snapshot: Snapshot) -> None:
        modulos = self._display_modules(snapshot)
        lineas = []
        if (canal := render.memory_channel_warning(snapshot.modules)):
            lineas.append(canal)
        # Decidirlo aquí era el fallo: se tomaba `lentos[0]` y se prometía su
        # velocidad catalogada, que con módulos desparejos es la del que no
        # manda. La regla vive en `render`, al lado de la del canal.
        chipset = bool(snapshot.cpu.types) and db.memory_controller_in_chipset(
            snapshot.cpu.types[0])
        if (velocidad := render.memory_speed_warning(modulos, self._limite, chipset)):
            lineas.append(velocidad)
        if chipset:
            # Antes de Nehalem: no hay «máximo del procesador» del que hablar.
            lineas.append(_("mem.chipset"))
        self.avisos.setText("  ".join(lineas))
        self.avisos.setVisible(bool(lineas))

    @staticmethod
    def _limite_del_procesador(snapshot: Snapshot):
        """El máximo oficial de memoria de este procesador con estos módulos.

        Con un solo tipo de memoria puesto: es el que decide la fila. Los
        rangos de cada módulo deciden la disposición en AMD; salen de la
        tabla del firmware o, sin permisos, del SPD.
        """
        if snapshot.cpu.types and db.memory_controller_in_chipset(snapshot.cpu.types[0]):
            return None
        tipos = {m.type for m in snapshot.modules if m.populated and m.type
                 and "type" not in firmware_contradicted(m, snapshot.modules)}
        tipos |= {s.dram_type for s in snapshot.spd if s.dram_type}
        marca = snapshot.cpu.types[0].brand if snapshot.cpu.types else ""
        puestos = [m for m in snapshot.modules if m.populated]
        if puestos:
            rangos = tuple(m.ranks for m in puestos)
        else:
            rangos = tuple(s.ranks for s in snapshot.spd)
        return db.memory_limit(marca, tipos.pop(), rangos) if len(tipos) == 1 else None

    def _subtitle(self, snapshot: Snapshot) -> str:
        array = snapshot.memory_array
        modules = snapshot.modules
        if not modules and snapshot.cpu.types and snapshot.cpu.types[0].in_virtual_machine:
            return _("memory.detail.virtual")
        if not modules:
            if snapshot.spd:
                catalogados = {i.rated_mts for i in snapshot.spd if i.rated_mts}
                cuantos = len(snapshot.spd)
                # «Catalogados a», no «a»: el SPD dice a cuánto pueden ir, y a
                # cuánto van lo decide la BIOS y solo se sabe con permisos.
                # «2 módulos… a 3200 MT/s» se leía como la velocidad real, y
                # sin XMP activado van a 2133.
                velocidad = (_("memory.spd.rated.one" if cuantos == 1
                               else "memory.spd.rated.many").format(
                                   mts=render.enumeration([str(v) for v in sorted(catalogados)]))
                             if catalogados else "")
                # What the chips read don't account for may be soldered (no
                # chip) or a chip the kernel didn't register: only that it
                # wasn't read is known.
                resto = (_("memory.spd.needsroot.one" if cuantos == 1 else "memory.spd.needsroot")
                         if snapshot.spd_accounts_for_all_memory else _("memory.spd.notall"))
                return (_("memory.spd.read.one" if cuantos == 1
                          else "memory.spd.read.many").format(n=cuantos)
                        + velocidad + resto)
            return _("memory.detail.needsroot")
        # Cuántos módulos, y no «2 de 4 zócalos»: la tabla del firmware
        # declara ranuras que la placa no tiene (la H510M PRO-E de la oficina
        # tiene dos y declara cuatro), y una vacía de verdad y una fantasma
        # son idénticas ahí. Sin permisos se dice lo mismo, del SPD.
        # En canal único la memoria rinde la mitad, y no lo dice nada en todo
        # el sistema. Va en la primera línea, no en la ficha de un módulo; y
        # ya lleva cuántos módulos lo forman.
        ocupados = sum(1 for m in modules if m.populated)
        canal = render.memory_channel_label(modules)
        partes = [canal or _("mem.modules.one" if ocupados == 1
                             else "mem.modules.many").format(n=ocupados)]
        if array and array.max_capacity_bytes:
            partes.append(_("memory.array.upto").format(
                tam=render.size(array.max_capacity_bytes)))
        if correccion := render.memory_error_correction(array.error_correction if array else None):
            partes.append(f"ECC: {correccion.lower()}")
        return " · ".join(partes)

    def _apply_badges(self, snapshot: Snapshot) -> None:
        modules = [m for m in self._display_modules(snapshot) if m.populated]
        wanted = []
        if modules:
            # What the firmware says against the others' SPD isn't counted.
            contradicted = {id(m): firmware_contradicted(m, modules) for m in modules}
            tipos = {render.module_type(m) for m in modules
                     if render.module_type(m) and "type" not in contradicted[id(m)]}
            wanted.extend(sorted(tipos))
            # The speed it runs at when the firmware says it, and else the one
            # it is rated at: «3200 MT/s · al máximo del procesador» was read
            # of memory running at 2933.
            velocidades = {render.memory_speed(m.configured_mts) or m.rated_mts
                           for m in modules if "running" not in contradicted[id(m)]}
            velocidades.discard(None)
            wanted.extend(f"{v} MT/s" for v in sorted(velocidades))
            veredictos = {render.memory_module_verdict(m, self._limite) for m in modules}
            if "slow" in veredictos:
                wanted.append(_("memory.chip.underclocked"))
            elif "cpu_max" in veredictos:
                wanted.append(_("memory.chip.cpumax"))
            if any(m.has_ecc for m in modules):
                wanted.append("ECC")
        self.badges.set_chips(wanted, highlight_first=True)

    def hide_permission_notices(self, ocultos: bool) -> None:
        """Deja de enseñar la tarjeta que pide permisos, o la vuelve a enseñar."""
        self._sin_avisos_de_permisos = ocultos

    def _apply_elevation(self, snapshot: Snapshot) -> None:
        state = snapshot.privileged
        # Apartada con sus dos botones, aquí o en Inicio, mientras lo que hay
        # que hacer sea dar permisos: si no hay ayudante o ya se es root, la
        # tarjeta explica otra cosa y se queda.
        apartada = (self._sin_avisos_de_permisos and state.supported
                    and not state.already_root)
        if snapshot.modules or apartada:
            self.elevation.hide()
            return

        self.elevation.show()
        if state.already_root:
            self.elevation_text.setText(
                _("memory.elev.alreadyroot")
            )
            self.elevation_button.hide()
        elif not state.supported:
            self.elevation_text.setText(
                _("memory.elev.nopkexec")
            )
            self.elevation_hint.setText(
                _("memory.elev.nopkexec.hint")
            )
            self.elevation_button.hide()
        elif state.outdated:
            # What brings it back is updating the helper: its button is the
            # one left, «Actualizar el ayudante».
            self.elevation_text.setText(_("perm.outdated.body"))
            self.elevation_hint.setText("")
            self.elevation_button.hide()
        else:
            leidos = len(snapshot.spd)
            sized = sum(m.capacity_bytes or 0 for m in snapshot.spd)
            if sized and not snapshot.spd_accounts_for_all_memory:
                # The chips read add up to less than the system sees: a
                # module the kernel did not register, or soldered memory.
                self.elevation_text.setText(
                    _("memory.elev.spd.notall.one" if leidos == 1
                      else "memory.elev.spd.notall.many").format(
                        n=leidos, read=render.size(sized),
                        total=render.size(snapshot.system.memory.total_bytes)))
            elif leidos:
                self.elevation_text.setText(
                    _("memory.elev.spd.one" if leidos == 1
                      else "memory.elev.spd.many").format(n=leidos))
            else:
                self.elevation_text.setText(
                    _("memory.elev.smbios")
                )
            self.elevation_hint.setText(
                state.message or
                _("memory.elev.helper")
            )
            self.elevation_button.show()
        # With the helper out of date, updating it is what is left, with
        # «Not now», as in Home's notice.
        self.explain_button.setVisible(not state.outdated)
        self.dismiss_button.setVisible(not state.outdated)

    @staticmethod
    def _display_modules(snapshot: Snapshot) -> list[MemoryModule]:
        """Los módulos a enseñar, vengan de donde vengan.

        Con permisos manda SMBIOS, que sabe el zócalo y la capacidad. Sin
        ellos se fabrican tarjetas a partir del SPD, que se lee sin pedir
        nada: menos campos, pero fabricante, referencia y velocidad
        catalogada ya están ahí.
        """
        if snapshot.modules:
            return list(snapshot.modules)
        # Numerados por orden de lectura y no por el zócalo, que aquí no se
        # sabe: el `slot` del SPD es la dirección del chip en el bus i2c —0x50
        # es 0 y 0x52 es 2—, no la posición en la placa. Titular «Zócalo 0» y
        # «Zócalo 2» afirmaba una numeración física que la propia pantalla
        # admite no tener dos líneas más arriba, en «el zócalo y la capacidad
        # necesitan permisos», y hacía pensar que el 1 estaba libre.
        return [
            MemoryModule(
                locator=_("memory.module.n").format(n=orden),
                populated=True,
                type=info.dram_type,
                manufacturer=info.manufacturer,
                part_number=info.part_number,
                rank=info.ranks,
                data_width=info.bus_width,
                total_width=(info.bus_width or 0) + info.ecc_bits or None,
                spd=info,
            )
            for orden, info in enumerate(snapshot.spd, start=1)
        ]

    def _apply_modules(self, modules: tuple[MemoryModule, ...], array,
                       del_spd: bool = False, candado=None) -> None:
        signature = tuple((m.locator, m.part_number, m.size_bytes,
                           m.spd.address if m.spd else None) for m in modules
                          ) + (candado is not None,)
        if signature == self._module_signature:
            return
        self._module_signature = signature

        clear_layout(self._slots_host.layout())
        self._slots_host._items.clear()
        self._slot_grids.clear()

        # El firmware pega el controlador, el canal y el número sin espacios y
        # cada fabricante a su manera, así que la misma pestaña se veía distinta
        # en cada equipo y con cuatro zócalos salían dos «DIMM 0».
        # Por posición y no por localizador, que se repite: una Gigabyte
        # llama «DIMM 1» a dos zócalos y pone el canal en el banco.
        nombres = render.slot_names([(m.locator, m.bank) for m in modules])

        sin_spd: list[str] = []
        # The numbers of the modules in a slot whose chip wasn't read.
        unread: list[int] = []
        sin_spd_soldada: list[str] = []
        undeclared: list[tuple[int, list[str]]] = []
        numero = 0
        for nombre, module in zip(nombres, modules):
            crudo = module.locator or ""
            if not module.populated:
                continue
            # El mismo título con permisos y sin ellos: «Módulo 1», en el
            # orden de la tabla del firmware o del SPD, que es el mismo (el
            # chip 0x50 va en el primer canal). Antes era «Canal A» con
            # permisos y «Módulo 1» sin ellos: la misma pieza con dos nombres.
            numero += 1
            card = Card(_("memory.module.n").format(n=numero))
            if del_spd and module.spd is not None:
                # La dirección del chip es el único dato de posición que hay.
                card.setToolTip(_("memory.tip.module").format(
                    address=module.spd.address or "0x50"))

            grid = InfoGrid()
            for name in MODULE_FIELDS:
                grid.add(_(name))
            card.body.addWidget(grid)
            self._fill(grid, module, self._limite,
                       otro_con_spd=any(o.spd is not None for o in modules if o is not module),
                       contradicted=firmware_contradicted(module, modules))
            # El zócalo: con permisos, el de la tabla del firmware (y lo que
            # puso tal cual, al pasar el ratón); sin ellos, candado.
            if del_spd:
                if candado is not None:
                    grid.set_locked(_("memory.field.slot"), self._p.info,
                                    render.lock_tooltip(candado))
                else:
                    grid.set_visible(_("memory.field.slot"), False)
            else:
                grid.set(_("memory.field.slot"), nombre,
                         tooltip=crudo if crudo and crudo != nombre else None)
            nota_spd = getattr(self, "_nota_spd", None)
            # Soldered on the board, while another module's SPD is read: it has
            # no chip, which is not «could not be read».
            soldada = (module.spd is None and not module.in_a_slot
                       and any(m.spd is not None for m in modules if m.populated))
            for clave in self._solo_del_spd(module):
                if soldada:
                    grid.set_visible(_(clave), False)
                    if clave not in sin_spd_soldada:
                        sin_spd_soldada.append(clave)
                    continue
                grid.set_visible(_(clave), False)
                if clave not in sin_spd:
                    sin_spd.append(clave)
                if module.spd is None and numero not in unread:
                    unread.append(numero)
            # Read and blank: the module doesn't declare it. Hidden, and the
            # foot says which.
            blank = self._undeclared(module)
            for key in blank:
                grid.set_visible(_(key), False)
            if blank:
                undeclared.append((numero, blank))
            if module.spd is not None and not module.spd.overclock_profiles:
                # El dato no falta: esos módulos solo tienen el perfil de JEDEC.
                grid.set_visible(_("memory.field.profiles"), False)
            if candado is not None:
                # Del SPD sale a cuánto puede ir el módulo, no a cuánto va ni
                # en qué banco está: eso lo guarda la tabla del firmware. Con
                # candado y no con guion, que es lo que lo distingue de lo que
                # el SPD no trae.
                for clave in ("memory.field.running", "memory.field.bank"):
                    grid.set_locked(_(clave), self._p.info, render.lock_tooltip(candado))
                grid.locked_clicked.connect(self.elevation_requested)
            self._slot_grids.append(grid)
            self._slots_host.add(card)

        # Los libres no se dicen: no hay forma segura de saber cuáles existen
        # (ver `_subtitle`).
        # Lo que no sale en las fichas y por qué, en el orden de la ficha.
        lista = render.enumeration(
            [_(SOLO_DEL_SPD[clave]) for clave in MODULE_FIELDS if clave in sin_spd])
        pies = []
        spd_reason_told = False
        # El SPD de la DDR5 lo lee el driver spd5118, de Linux 6.11: con un
        # kernel anterior no es la placa la que no deja, es que no hay driver.
        ddr5 = any(m.type == "DDR5" for m in modules if m.populated)
        viejo = kernel.too_old("spd5118", getattr(self, "_kernel", None)) if ddr5 else None
        if sin_spd and viejo:
            pies.append(_("memory.na.nospd.kernel").format(
                campos=lista[:1].upper() + lista[1:], kernel=viejo))
        elif sin_spd:
            # La causa, si el proveedor la sabe (sin bus, o bus reservado por
            # el firmware); si no, se dice que no se pudo leer, sin culpar a
            # la placa de lo que puede ser un permiso o un driver.
            nota_spd = getattr(self, "_nota_spd", None)
            campos = lista[:1].upper() + lista[1:]
            # With another module's chip read and shown beside it, «each
            # module's chip could not be read» is false: say whose.
            some_read = any(m.spd is not None for m in modules if m.populated)
            numbers = render.enumeration([str(n) for n in unread])
            if not (some_read and unread):
                not_read = _("memory.na.nospd").format(campos=campos)
            elif len(unread) == 1:
                not_read = _("memory.na.nospd.one").format(campos=campos, n=numbers)
            else:
                not_read = _("memory.na.nospd.many").format(campos=campos, n=numbers)
            if nota_spd is not None and nota_spd.key == "prov.spd.partial":
                pies.append(_("memory.na.spd.partial").format(campos=campos))
                spd_reason_told = True
            elif nota_spd is not None and nota_spd.key == "prov.spd.unregistered":
                # Its notice stays, with the order to copy.
                pies.append(not_read)
            elif nota_spd is not None:
                # The reason and what to do about it go here, once: the note's
                # own box is left out (`_apply_notices`).
                motivo = nota_spd.message[:1].lower() + nota_spd.message[1:]
                if not (some_read and unread):
                    why = _("memory.na.nospd.why").format(campos=campos, motivo=motivo)
                elif len(unread) == 1:
                    why = _("memory.na.nospd.why.one").format(
                        campos=campos, n=numbers, motivo=motivo)
                else:
                    why = _("memory.na.nospd.why.many").format(
                        campos=campos, n=numbers, motivo=motivo)
                pies.append(" ".join(p for p in (why, nota_spd.hint) if p))
                spd_reason_told = True
            else:
                pies.append(not_read)
        no_chips_field = False
        for number, keys in undeclared:
            # DDR2's SPD has no field for the chips' maker: not undeclared.
            if "memory.field.chips" in keys and any(
                    m.spd and m.spd.dram_type == "DDR2" for m in modules if m.populated):
                keys = [k for k in keys if k != "memory.field.chips"]
                no_chips_field = True
            if keys:
                pies.append(_("memory.na.undeclared").format(
                    n=number, fields=render.enumeration(
                        [_(SPD_DECLARES[key]) for key in keys], "list.nor")))
        if no_chips_field:
            pies.append(_("memory.na.ddr2.chips"))
        if sin_spd_soldada:
            lista = render.enumeration([_(SOLO_DEL_SPD[clave]) for clave in MODULE_FIELDS
                                        if clave in sin_spd_soldada])
            pies.append(_("memory.na.soldered").format(campos=lista[:1].upper() + lista[1:]))
        # Que no traen perfiles rápidos se dice una vez, en la nota de la tabla
        # de perfiles, que es donde se buscan (`_apply_timings`); la fila se
        # esconde sin repetirlo aquí.
        # Above every JEDEC speed of its type the module runs a maker's
        # profile, whose voltage the firmware's table often doesn't show.
        perfil = next((m for m in modules if m.populated and m.above_jedec
                       and m.voltage_from_firmware), None)
        if perfil is not None:
            pies.append(_("memory.na.voltage.profile").format(
                tipo=render.memory_type(perfil.type), jedec=JEDEC_TOP_MTS[perfil.type]))
        self._spd_reason_told = spd_reason_told
        # One paragraph per matter: why the SPD isn't read is not the profile.
        self.spd_missing.setText("\n\n".join(pies))
        self.spd_missing.setVisible(bool(pies))

    @staticmethod
    def _solo_del_spd(module: MemoryModule) -> tuple[str, ...]:
        """Los campos que este módulo no puede tener porque no se leyó su SPD.

        Quién fabricó los chips, qué perfiles rápidos trae y cuándo se hizo
        solo están en el chip de identificación del módulo; la tabla del
        firmware no los lleva. Sin SPD no son datos que falten por leer mejor:
        no hay de dónde, y cuatro guiones por módulo no dicen eso. Se esconden
        y se nombran al pie. El fabricante sí suele venir en la tabla; solo se
        esconde si tampoco está ahí.
        """
        # With only its first page read, what the rest holds is missing too:
        # the part, and the organization the capacity and the ranks come from,
        # unless the firmware's table gives them.
        if module.spd is not None and not module.spd.partial:
            return ()
        partial = module.spd is not None
        return tuple(key for key, missing in (
            ("memory.field.vendor", not module.manufacturer),
            ("memory.field.part", partial and not module.part_number),
            ("memory.field.size", partial and not module.size_bytes),
            ("memory.field.ranks", partial and not module.rank),
            ("memory.field.chips", True),
            ("memory.field.profiles", True),
            ("memory.field.made", True)) if missing)

    def _apply_module_temperatures(self, snapshot: Snapshot, modules) -> None:
        """Each module's temperature, from the sensor on its SPD chip, in its
        card. Every sample: the cards are built once."""
        sensors = {s.bus_address: s for s in snapshot.sensors
                   if s.bus_address and s.kind is SensorKind.TEMPERATURE}
        numbers = module_numbers(modules, set(sensors))
        by_number = {number: sensors[address] for address, number in numbers.items()}
        fahrenheit = self._prefs.fahrenheit
        for number, grid in enumerate(self._slot_grids, start=1):
            sensor = by_number.get(number)
            limits = (render.temperature_limits(sensor.high, sensor.critical, fahrenheit)
                      if sensor else None)
            grid.set(_("memory.field.temp"),
                     render.temperature(sensor.value, fahrenheit) if sensor else render.DASH,
                     tooltip=_("temp.limits.declared").format(limites=limits) if limits else "")
            paint_level(grid.value_label(_("memory.field.temp")),
                        sensor.alarm_level if sensor else "ok")
            grid.set_visible(_("memory.field.temp"), sensor is not None)

    @staticmethod
    def _undeclared(module: MemoryModule) -> list[str]:
        """The fields its SPD was read and left blank, and the firmware's
        table doesn't fill either."""
        spd = module.spd
        if spd is None or not spd.decoded or spd.partial:
            return []
        values = {
            "memory.field.vendor": spd.manufacturer or module.manufacturer,
            "memory.field.chips": spd.dram_manufacturer,
            "memory.field.part": spd.part_number or module.part_number,
            "memory.field.made": spd.manufactured_year,
        }
        return [key for key in SPD_DECLARES if not values[key]]

    @staticmethod
    def _fill(grid: InfoGrid, module: MemoryModule, limite=None,
              otro_con_spd: bool = False, contradicted: frozenset = frozenset()) -> None:
        d = render.DASH
        spd = module.spd
        mismatch = _("memory.tip.mismatch")

        grid.set(_("memory.field.vendor"), render.memory_module_maker(module) or d,
                 tooltip=_("memory.tip.source.bios") if module.maker_from_firmware else "")
        grid.set(_("memory.field.chips"), render.maker(spd.dram_manufacturer if spd else None) or d,
                 tooltip=_("memory.tip.chips"))
        grid.set(_("memory.field.part"), render.memory_module_part(module) or d,
                 tooltip=_("memory.tip.source.bios") if module.part_from_firmware else "")
        if "type" in contradicted:
            grid.set(_("memory.field.type"), render.firmware_mismatch(render.module_type(module)),
                     tooltip=mismatch)
        else:
            grid.set(_("memory.field.type"), render.module_type(module) or d,
                     tooltip=_("memory.tip.ddr3l")
                     if (render.module_type(module) or "").endswith("L") else "")
        # La capacidad sale de SMBIOS, que pide permisos, pero el SPD de DDR5
        # la trae en la densidad de sus chips y ese se lee sin pedir nada.
        capacidad = module.size_bytes or (spd.capacity_bytes if spd else None)
        grid.set(_("memory.field.size"), render.size(capacidad) if capacidad else d,
                 tooltip=_("memory.tip.size")
                 if not module.size_bytes and capacidad else "")

        rated = module.rated_mts
        grid.set(_("memory.field.rated"), render.memory_rated(module),
                 tooltip=_("memory.tip.rated.bios") if module.rated_from_firmware
                 else _("memory.tip.rated") if spd else "")

        crudo_mts = module.configured_mts or module.speed_mts
        actual = render.memory_speed(crudo_mts)
        funcionando = f"{actual} MT/s" if actual else d
        veredicto = render.memory_module_verdict(module, limite)
        if veredicto == "slow":
            funcionando += "   ⚠"
        # Si la BIOS escribió el otro redondeo del mismo grado, su número queda
        # aquí: es el que sale en `dmidecode` y hace falta para contrastar.
        if veredicto == "cpu_max":
            pista = _("memory.tip.cpumax").format(actual=actual, rated=rated,
                                                  modelo=render.memory_limit_label(limite))
        elif veredicto == "slow":
            pista = _("memory.tip.running").format(actual=actual, rated=rated)
        else:
            pista = ""
        if crudo_mts and crudo_mts != actual:
            firmware = _("memory.tip.firmware").format(mts=crudo_mts)
            pista = f"{pista}\n\n{firmware}" if pista else firmware
        if "running" in contradicted:
            funcionando, pista = render.firmware_mismatch(funcionando), mismatch
        grid.set(_("memory.field.running"), funcionando, tooltip=pista)

        rangos = str(module.ranks) if module.ranks else d
        if module.has_ecc:
            rangos += _("memory.ranks.ecc")
        grid.set(_("memory.field.ranks"), rangos)

        grid.set(_("memory.field.voltage"), render.memory_voltage(module),
                 tooltip=_("memory.tip.voltage.bios") if module.voltage_from_firmware
                 else "" if module.voltage_mv is not None
                 else _("memory.tip.voltage.either") if render.voltage_choice(module)
                 else _("memory.tip.voltage.spd") if module.nominal_voltage_mv is not None
                 else "")
        if module.soldered_by:
            # What the firmware calls it (a T14 says «SODIMM») isn't what it is.
            motivo = (_("memory.tip.soldered.form") if module.soldered_by == "form"
                      else _("memory.tip.soldered.place").format(
                          formato=render.memory_form_factor(module.form_factor) or d))
            if module.spd is None and otro_con_spd:
                motivo += " " + _("memory.tip.soldered.nospd")
            grid.set(_("memory.field.form"), _("memory.form.soldered"), tooltip=motivo)
        elif "form" in contradicted:
            grid.set(_("memory.field.form"), render.firmware_mismatch(render.module_form(module)),
                     tooltip=mismatch)
        else:
            grid.set(_("memory.field.form"), render.module_form(module) or d)

        perfiles = spd.overclock_profiles if spd else ()
        grid.set(_("memory.field.profiles"), ", ".join(perfiles) if perfiles else d,
                 tooltip=_("memory.tip.profiles") if perfiles else "")
        grid.set(_("memory.field.made"),
                 (render.made(spd.manufactured_year, spd.manufactured_week) if spd else None) or d)
        grid.set(_("memory.field.bank"), render.memory_bank(module.bank) or d)

    def _apply_timings(self, modules: list[MemoryModule]) -> None:
        rows: list[list[str]] = []
        tooltips: list[str] = []
        # Con el mismo nombre que la ficha del módulo, «Módulo 1», con
        # permisos y sin ellos.
        puestos = [m for m in modules if m.populated]
        nombres = [_("memory.module.n").format(n=n) for n in range(1, len(puestos) + 1)]
        modules = puestos
        for etiqueta, module in zip(nombres, modules):
            spd = module.spd
            if spd is None:
                continue
            for timing in (spd.jedec, *spd.profiles):
                if timing is None:
                    continue
                rows.append([
                    f"{etiqueta} · {timing.name}",
                    f"{timing.speed_mts} MT/s",
                    str(timing.cl or render.DASH),
                    render.spd_time(timing.taa_ps),
                    str(timing.trcd or render.DASH),
                    str(timing.trp or render.DASH),
                    str(timing.tras or render.DASH),
                    str(timing.trc or render.DASH),
                    render.timing_voltage(timing, spd),
                ])
                tooltips.append(f"{spd.part_number or ''} · {spd.address}".strip(" ·"))

        self.timings_card.setVisible(bool(rows))
        if rows:
            self.timings.set_rows(rows, tooltips=tooltips)
        # «Sin XMP activado se queda en JEDEC» solo vale si hay XMP que activar.
        # DDR4's decoded profiles are in `profiles`, DDR5's recognised ones in
        # `overclock_profiles`: a tester's DDR4 with XMP read «no traen
        # perfiles rápidos». With the XMP header and no profile that passes
        # the sanity check (F-A2), it has one this version cannot read.
        spds = [m.spd for m in modules if m.spd is not None]
        if any(s.profiles or s.overclock_profiles for s in spds):
            nota = "memory.spd.note"
        elif any(s.partial for s in spds):
            # The profiles would be on the pages that couldn't be read.
            nota = "memory.spd.note.partial"
        elif any(s.xmp_revision for s in spds):
            nota = "memory.spd.note.xmpunread"
        else:
            nota = "memory.spd.note.noxmp"
        self.spd_note.setText(_("memory.spd.note.short"))
        self.spd_note.setToolTip(_(nota))
