"""Página de memoria.

Sin permisos solo se sabe el total, así que la página no finge: enseña lo que
puede y explica exactamente qué falta, cuánto se ganaría y con un botón para
pedirlo. Nada de diálogos de contraseña al arrancar.

Los zócalos vacíos se enseñan igual que los ocupados. Saber que quedan dos
libres es la mitad de la razón por la que alguien abre esta pestaña.
"""

from __future__ import annotations

import threading
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

from ... import membench, render
from ...i18n import _
from ...model import MemoryModule, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card, ChipRow, InfoGrid, Notice, ResponsiveRow, StackedBar, Table,
    boton_de_permiso_permanente, clear_layout, tone_for,
)

from ...model import Need

# A partir de esta fracción del techo de la herramienta, la cifra deja de
# hablar solo de la memoria y hay que decirlo.
CERCA_DEL_TECHO = 0.85

NEED_TITLES = {
    Need.ROOT: "note.needsroot",
    Need.DATABASE: "note.database",
    Need.HARDWARE: "note.hardware",
    Need.DRIVER: "note.needsmodule",
    Need.PLATFORM: "note.platform",
    Need.ERROR: "note.failed",
}

MODULE_FIELDS = ("memory.field.vendor", "memory.field.chips", "memory.field.part", "memory.field.type", "memory.field.size",
                 "memory.field.rated", "memory.field.running", "memory.field.ranks", "memory.field.voltage",
                 "memory.field.form", "memory.field.profiles", "memory.field.made", "memory.field.bank")

TIMING_HEADERS = ("memory.timing.profile", "memory.timing.speed", "memory.timing.cl", "memory.timing.trcd", "memory.timing.trp", "memory.timing.tras", "memory.timing.trc", "memory.field.voltage")


class MemoryPage(QScrollArea):
    elevation_requested = Signal()
    permanent_requested = Signal()
    # La medida corre en otro hilo y en otro proceso; vuelve por aquí, que es
    # la forma de tocar widgets desde fuera del hilo de la interfaz.
    _bw_listo = Signal(object)

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

        layout = QVBoxLayout(root)
        layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        layout.setSpacing(m.section_gap)

        layout.addWidget(self._build_header())
        self.elevation = self._build_elevation()
        layout.addWidget(self.elevation)

        self._slots_host = ResponsiveRow(min_item_width=290)
        layout.addWidget(self._slots_host)

        layout.addWidget(self._build_bandwidth())

        self.timings_card = Card(_("memory.card.timings"))
        self.timings = Table([_(h) for h in TIMING_HEADERS],
                             numeric=(False, True, True, True, True, True, True, True))
        explanation = QLabel(_("memory.spd.note"))
        explanation.setObjectName("Muted")
        explanation.setWordWrap(True)
        explanation.setFont(ui_font(theme.METRICS.small_pt))
        self.timings_card.body.addWidget(self.timings)
        self.timings_card.body.addWidget(explanation)
        layout.addWidget(self.timings_card)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        layout.addLayout(self._notices_host)

        layout.addStretch(1)

        self._module_signature: tuple = ()
        self._notice_signature: tuple = ()
        self._slot_grids: list[InfoGrid] = []
        self._cache_mas_grande: Optional[int] = None
        self._niveles: list = []
        self._bw_listo.connect(self._pintar_ancho_de_banda)

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("memory.loading"))
        self.title.setObjectName("Headline")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()
        self.bar = StackedBar(self._p)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        card.body.addWidget(self.bar)
        # Dos cosas que la gente no sabe que le pasan: la memoria en un solo
        # canal y el perfil rápido sin activar. Las dos se calculaban ya y
        # salían escondidas dentro de la ficha de un módulo, a dos clics.
        self.avisos = QLabel()
        self.avisos.setObjectName("NoticeHint")
        self.avisos.setWordWrap(True)
        self.avisos.hide()
        card.body.addWidget(self.avisos)
        return card

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

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.elevation_button)
        row.addWidget(self.permanent_button)
        row.addStretch(1)

        card.body.addWidget(self.elevation_text)
        card.body.addWidget(self.elevation_hint)
        card.body.addLayout(row)
        return card

    def _build_bandwidth(self) -> QWidget:
        """Lo que la memoria mueve de verdad, medido a petición.

        A petición y no al abrir la página: ocupa la máquina un instante y pide
        un bloque más grande que la caché, así que quien mira la cifra tiene
        que saber cuándo se tomó. Una medida que corre sola mientras el equipo
        hace otra cosa sale peor y nadie sabe por qué.
        """
        card = Card(_("memory.card.bandwidth"))

        # Solo la RAM. El bloque que cabe en la caché se sigue midiendo, pero
        # no como dato: ahí lo que limita no es la memoria sino esta forma de
        # medir, y las tres cachés de este equipo daban la misma cifra.
        self.bw_grid = InfoGrid()
        self.bw_grid.add(_("memory.bw.ram"))
        self.bw_grid.setVisible(False)

        self.bw_intro = QLabel(_("memory.bw.intro"))
        self.bw_intro.setObjectName("Muted")
        self.bw_intro.setWordWrap(True)
        self.bw_intro.setFont(ui_font(theme.METRICS.small_pt))

        # Debajo del ancho de banda y en su propia rejilla: son dos preguntas
        # distintas —cuánto cabe por el tubo y cuánto tarda en llegar lo
        # primero— y juntas en una lista se leen como si fueran lo mismo.
        self.lat_title = QLabel(_("memory.lat.title"))
        self.lat_title.setObjectName("FieldName")
        self.lat_title.setFont(ui_font(theme.METRICS.small_pt))
        self.lat_title.setVisible(False)
        self.lat_grid = InfoGrid()
        for nivel in ("L1", "L2", "L3", "RAM"):
            self.lat_grid.add(nivel)
        self.lat_grid.setVisible(False)
        self.lat_note = QLabel("")
        self.lat_note.setObjectName("Muted")
        self.lat_note.setWordWrap(True)
        self.lat_note.setFont(ui_font(theme.METRICS.small_pt))
        self.lat_note.setVisible(False)

        self.bw_note = QLabel(_("memory.bw.note"))
        self.bw_note.setObjectName("Muted")
        self.bw_note.setWordWrap(True)
        self.bw_note.setFont(ui_font(theme.METRICS.small_pt))
        self.bw_note.setVisible(False)

        self.bw_button = QPushButton(_("memory.bw.measure"))
        self.bw_button.clicked.connect(self._medir_ancho_de_banda)

        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(self.bw_button)
        fila.addStretch(1)

        card.body.addWidget(self.bw_intro)
        card.body.addWidget(self.bw_grid)
        card.body.addWidget(self.bw_note)
        card.body.addSpacing(theme.METRICS.card_gap)
        card.body.addWidget(self.lat_title)
        card.body.addWidget(self.lat_grid)
        card.body.addWidget(self.lat_note)
        card.body.addLayout(fila)

        self._bw_hilo = None
        self._bw_modulos: tuple = ()
        return card

    # -- ancho de banda -----------------------------------------------------

    def _medir_ancho_de_banda(self) -> None:
        if self._bw_hilo is not None and self._bw_hilo.is_alive():
            return
        self.bw_button.setEnabled(False)
        self.bw_button.setText(_("memory.bw.measuring"))
        cache = self._cache_mas_grande
        niveles = self._niveles

        def trabajo() -> None:
            # Fuera del hilo de la interfaz: son cien milisegundos, pero el
            # hijo tiene un minuto de plazo y si algo va mal se comería la
            # ventana entera.
            self._bw_listo.emit(membench.consultar(cache, niveles))

        self._bw_hilo = threading.Thread(target=trabajo, daemon=True)
        self._bw_hilo.start()

    def _pintar_ancho_de_banda(self, resultado) -> None:
        self.bw_button.setEnabled(True)
        self.bw_button.setText(_("memory.bw.again"))
        self.bw_intro.setVisible(False)
        self.bw_grid.setVisible(True)
        self.bw_note.setVisible(True)

        self._pintar_latencias(resultado)
        por_donde = {m.donde: m for m in resultado.medidas}
        teorico = render.memory_theoretical_bandwidth(self._bw_modulos)
        techo = por_donde.get("techo")

        ram = por_donde.get("ram")
        if ram is None:
            motivos = {"sin_memoria": "memory.bw.nomem",
                       "cache_enorme": "memory.bw.hugecache"}
            self.bw_grid.set(_("memory.bw.ram"), render.DASH)
            self.bw_note.setText(_(motivos.get(resultado.motivo,
                                               "memory.bw.failed")))
        else:
            parte = render.memory_bandwidth_share(ram.bandwidth_bytes, teorico)
            texto = render.bandwidth(ram.bandwidth_bytes)
            if parte is not None:
                texto += "   " + _("memory.bw.share").format(
                    pct=f"{parte:.0f}", total=render.bandwidth(teorico))
            self.bw_grid.set(_("memory.bw.ram"), texto)
            # Una memoria muy rápida puede chocar con el techo de esta forma de
            # medir, y entonces la cifra habla de la herramienta. Decirlo es la
            # diferencia entre una medida y un número bajo con cara de medida.
            if (techo and ram.bandwidth_bytes
                    > techo.bandwidth_bytes * CERCA_DEL_TECHO):
                self.bw_note.setText(_("memory.bw.capped").format(
                    techo=render.bandwidth(techo.bandwidth_bytes)))
            else:
                self.bw_note.setText(_("memory.bw.note"))

    # -- actualización ------------------------------------------------------

    def _pintar_latencias(self, resultado) -> None:
        """Cada nivel con lo que tarda un acceso suyo.

        Los que no se hayan podido medir se esconden en vez de salir con un
        guion: en un procesador sin L3 no falta el dato, es que no hay nivel.
        """
        por_nivel = {l.nivel: l for l in resultado.latencias}
        hay = bool(por_nivel)
        self.lat_title.setVisible(hay)
        self.lat_grid.setVisible(hay)
        for nivel in ("L1", "L2", "L3", "RAM"):
            medida = por_nivel.get(nivel)
            self.lat_grid.set_visible(nivel, medida is not None)
            if medida is not None:
                self.lat_grid.set(nivel, render.nanoseconds(medida.nanoseconds))

        motivos = {"cadena_enorme": "memory.lat.partial",
                   "no_x86": "memory.lat.nox86",
                   "sin_ejecutable": "memory.lat.noexec"}
        clave = motivos.get(resultado.motivo_latencias)
        texto = _(clave) if clave else (_("memory.lat.note") if hay else "")
        self.lat_note.setText(texto)
        self.lat_note.setVisible(bool(texto))

    def apply(self, snapshot: Snapshot) -> None:
        memory = snapshot.system.memory
        array = snapshot.memory_array
        modules = snapshot.modules

        self.title.setText(_("mem.title").format(
            tam=render.size(memory.total_bytes)))
        self.subtitle.setText(self._subtitle(snapshot))
        self._apply_avisos(snapshot)
        self._apply_badges(snapshot)

        # Para la medida: el tamaño de la caché más grande decide los bloques,
        # y los módulos, el teórico con el que compararla. Se guardan en cada
        # muestreo porque la medida la lanza el usuario cuando quiere.
        self._cache_mas_grande = max(
            (c.size_bytes for t in snapshot.cpu.types for c in t.caches
             if c.size_bytes), default=None)
        self._bw_modulos = modules
        # Un nivel por cada caché de datos o unificada, del más pequeño al
        # mayor. Las de instrucciones no entran: por ellas no pasan los datos
        # que persigue la medida.
        self._niveles = [list(n) for n in sorted(
            {(f"L{c.level}", c.size_bytes) for t in snapshot.cpu.types
             for c in t.caches
             if c.kind in ("data", "unified") and c.size_bytes},
            key=lambda par: par[1])]

        self.bar.set_segments(
            [
                (_("sys.mem.apps"), memory.apps_bytes, "accent"),
                (_("sys.mem.cache"), memory.cache_bytes, "info"),
                (_("sys.mem.buffers"), memory.buffers_bytes, "warn"),
                (_("sys.mem.free"), memory.free_bytes, "line"),
            ],
            total=memory.total_bytes,
            formatter=render.size,
        )

        display = self._display_modules(snapshot)
        self._apply_elevation(snapshot)
        self._apply_modules(tuple(display), array)
        self._apply_timings(display)
        self._apply_notices(snapshot)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        # La tarjeta de elevación ya explica lo de los permisos, así que aquí
        # solo van las notas que no cubre: por ejemplo, un SPD que no se sabe
        # interpretar todavía.
        notes = [n for n in snapshot.notes
                 if n.path.startswith("spd")
                 or (n.path.startswith("modules") and snapshot.modules)]
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(_(NEED_TITLES.get(note.need, note.need.value)),
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
        if (velocidad := render.memory_speed_warning(modulos)):
            lineas.append(velocidad)
        self.avisos.setText("  ".join(lineas))
        self.avisos.setVisible(bool(lineas))

    def _subtitle(self, snapshot: Snapshot) -> str:
        array = snapshot.memory_array
        modules = snapshot.modules
        if not modules:
            if snapshot.spd:
                catalogados = {i.rated_mts for i in snapshot.spd if i.rated_mts}
                velocidad = (_("memory.spd.at").format(mts=max(catalogados))
                             if catalogados else "")
                cuantos = len(snapshot.spd)
                return (_("memory.spd.read.one" if cuantos == 1
                          else "memory.spd.read.many").format(n=cuantos)
                        + velocidad + _("memory.spd.needsroot"))
            return _("memory.detail.needsroot")
        ocupados = sum(1 for m in modules if m.populated)
        partes = [_("memory.slots.used").format(
            n=ocupados, total=len(modules))]
        # En canal único la memoria rinde la mitad, y no lo dice nada en todo
        # el sistema. Va en la primera línea, no en la ficha de un módulo.
        if (canal := render.memory_channel_label(modules)):
            partes.insert(0, canal)
        if array and array.max_capacity_bytes:
            partes.append(_("memory.array.upto").format(
                tam=render.size(array.max_capacity_bytes)))
        if array and array.error_correction:
            partes.append(f"ECC: {array.error_correction.lower()}")
        return " · ".join(partes)

    def _apply_badges(self, snapshot: Snapshot) -> None:
        modules = [m for m in self._display_modules(snapshot) if m.populated]
        wanted = []
        if modules:
            tipos = {m.type for m in modules if m.type}
            wanted.extend(sorted(tipos))
            catalogadas = {m.rated_mts for m in modules}
            catalogadas.discard(None)
            wanted.extend(f"{v} MT/s" for v in sorted(catalogadas))
            if any(m.underclocked for m in modules):
                wanted.append(_("memory.chip.underclocked"))
            if any(m.has_ecc for m in modules):
                wanted.append("ECC")
        self.badges.set_chips(wanted, highlight_first=True)

    def _apply_elevation(self, snapshot: Snapshot) -> None:
        state = snapshot.privileged
        if snapshot.modules:
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
        else:
            leidos = len(snapshot.spd)
            if leidos:
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
        return [
            MemoryModule(
                locator=_("memory.slot.n").format(n=info.slot),
                populated=True,
                type=info.dram_type,
                form_factor=info.module_type,
                manufacturer=info.manufacturer,
                part_number=info.part_number,
                rank=info.ranks,
                data_width=info.bus_width,
                total_width=(info.bus_width or 0) + info.ecc_bits or None,
                spd=info,
            )
            for info in snapshot.spd
        ]

    def _apply_modules(self, modules: tuple[MemoryModule, ...], array) -> None:
        signature = tuple((m.locator, m.part_number, m.size_bytes,
                           m.spd.address if m.spd else None) for m in modules)
        if signature == self._module_signature:
            return
        self._module_signature = signature

        clear_layout(self._slots_host.layout())
        self._slots_host._items.clear()
        self._slot_grids.clear()

        for module in modules:
            card = Card(module.locator or _("memory.slot"))
            if not module.populated:
                empty = QLabel(_("memory.slot.empty"))
                empty.setObjectName("Muted")
                empty.setFont(ui_font(theme.METRICS.small_pt))
                card.body.addWidget(empty)
                self._slots_host.add(card)
                continue

            grid = InfoGrid()
            for name in MODULE_FIELDS:
                grid.add(_(name))
            card.body.addWidget(grid)
            self._fill(grid, module)
            self._slot_grids.append(grid)
            self._slots_host.add(card)

    @staticmethod
    def _fill(grid: InfoGrid, module: MemoryModule) -> None:
        d = render.DASH
        spd = module.spd

        grid.set(_("memory.field.vendor"), module.manufacturer or (spd.manufacturer if spd else None) or d)
        grid.set(_("memory.field.chips"), (spd.dram_manufacturer if spd else None) or d,
                 tooltip=_("memory.tip.chips"))
        grid.set(_("memory.field.part"), module.part_number or (spd.part_number if spd else None) or d)
        grid.set(_("memory.field.type"), module.type or (spd.dram_type if spd else None) or d)
        # La capacidad sale de SMBIOS, que pide permisos, pero el SPD de DDR5
        # la trae en la densidad de sus chips y ese se lee sin pedir nada.
        capacidad = module.size_bytes or (spd.capacity_bytes if spd else None)
        grid.set(_("memory.field.size"), render.size(capacidad) if capacidad else d,
                 tooltip=_("memory.tip.size")
                 if not module.size_bytes and capacidad else "")

        rated = module.rated_mts
        grid.set(_("memory.field.rated"), f"{rated} MT/s" if rated else d,
                 tooltip=_("memory.tip.rated") if spd else "")

        actual = module.configured_mts or module.speed_mts
        funcionando = f"{actual} MT/s" if actual else d
        if module.underclocked:
            funcionando += "   ⚠"
        grid.set(_("memory.field.running"), funcionando,
                 tooltip=_("memory.tip.running").format(
                     actual=actual, rated=rated)
                 if module.underclocked else "")

        rangos = str(module.rank) if module.rank else d
        if module.has_ecc:
            rangos += _("memory.ranks.ecc")
        grid.set(_("memory.field.ranks"), rangos)

        voltaje = (f"{module.voltage_configured_mv / 1000:.2f} V"
                   if module.voltage_configured_mv
                   else (f"{spd.jedec.voltage_v:.2f} V" if spd and spd.jedec
                         and spd.jedec.voltage_v else d))
        grid.set(_("memory.field.voltage"), voltaje)
        grid.set(_("memory.field.form"), module.form_factor or (spd.module_type if spd else None) or d)

        perfiles = spd.overclock_profiles if spd else ()
        grid.set(_("memory.field.profiles"), ", ".join(perfiles) if perfiles else d,
                 tooltip=_("memory.tip.profiles") if perfiles else "")
        grid.set(_("memory.field.made"), (spd.manufactured if spd else None) or d)
        grid.set(_("memory.field.bank"), module.bank or d)

    def _apply_timings(self, modules: list[MemoryModule]) -> None:
        rows: list[list[str]] = []
        tooltips: list[str] = []
        # Los zócalos de una placa se llaman casi igual —«Controller0-ChannelA»
        # y «Controller0-ChannelB»— y lo que los distingue está al final, que
        # es justo lo que se recorta cuando no cabe: las dos filas salían como
        # «Controller0-C…» y no había forma de saber cuál era cuál.
        corto = _sin_el_prefijo_comun(
            [m.locator or (m.spd.address if m.spd else "") for m in modules])
        for module in modules:
            spd = module.spd
            if spd is None:
                continue
            etiqueta = corto.get(module.locator or spd.address) or \
                module.locator or spd.address
            for timing in (spd.jedec, *spd.profiles):
                if timing is None:
                    continue
                rows.append([
                    f"{etiqueta} · {timing.name}",
                    f"{timing.speed_mts} MT/s",
                    str(timing.cl or render.DASH),
                    str(timing.trcd or render.DASH),
                    str(timing.trp or render.DASH),
                    str(timing.tras or render.DASH),
                    str(timing.trc or render.DASH),
                    f"{timing.voltage_v:.2f} V" if timing.voltage_v else render.DASH,
                ])
                tooltips.append(f"{spd.part_number or ''} · {spd.address}".strip(" ·"))

        self.timings_card.setVisible(bool(rows))
        if rows:
            self.timings.set_rows(rows, tooltips=tooltips)


def _sin_el_prefijo_comun(nombres: list[str]) -> dict[str, str]:
    """Quita a todos el trozo de nombre que comparten, si queda algo detrás.

    Con un solo módulo no hay nada que comparar y se devuelve tal cual.
    """
    utiles = [n for n in nombres if n]
    if len(utiles) < 2:
        return {}
    # Solo se toca lo que de verdad no cabe. «Zócalo 0» y «Zócalo 2» entran
    # enteros, y dejarlos en «0» y «2» quitaría contexto en vez de darlo.
    if max(len(n) for n in utiles) <= 14:
        return {}
    comun = utiles[0]
    for nombre in utiles[1:]:
        while not nombre.startswith(comun):
            comun = comun[:-1]
            if not comun:
                return {}
    # Se corta por el último separador, para no partir una palabra por la mitad.
    corte = max(comun.rfind(c) for c in "-_ .") + 1
    if corte <= 0:
        return {}
    recortados = {n: n[corte:] for n in utiles}
    # Si alguno se queda sin nada, el prefijo era todo el nombre: mejor dejarlo.
    return recortados if all(recortados.values()) else {}
