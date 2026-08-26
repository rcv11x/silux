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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...features import HIGHLIGHTS, pretty as pretty_feature
from ...model import CpuType, Need, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card,
    ChipRow,
    InfoGrid,
    Notice,
    ResponsiveRow,
    clear_layout,
)

NEED_TITLES = {
    Need.ROOT: "Hace falta elevar permisos",
    Need.DATABASE: "Falta en la base de datos",
    Need.HARDWARE: "Este equipo no lo expone",
    Need.DRIVER: "Falta un módulo del kernel",
    Need.PLATFORM: "No aplica a esta plataforma",
}

# El orden va de lo que identifica al procesador a lo que solo interesa
# para depurar. Antes había cuatro filas de familia y modelo —dos de ellas
# con los bits en crudo, que por sí solos no significan nada— y ahora se
# enseñan los valores compuestos, con el desglose en el tooltip de la firma.
PROCESSOR_FIELDS = (
    "Fabricante", "Especificación", "Nombre en clave", "Tecnología",
    "Encapsulado", "Arquitectura", "Núcleos", "Hilos", "Virtualización",
    "Familia", "Modelo", "Stepping", "Firma CPUID", "Microcódigo",
)

CLOCK_FIELDS = (
    "Frecuencia", "Multiplicador", "Base", "Mínima",
    "Máxima (kernel)", "Máxima (silicio)", "Bus (BCLK)", "Turbo",
    "Driver", "Gobernador", "Preferencia de energía",
)


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

        processor_card = Card("Procesador")
        self.processor = InfoGrid()
        for name in PROCESSOR_FIELDS:
            self.processor.add(name)
        processor_card.body.addWidget(self.processor)

        clocks_card = Card("Relojes")
        self.clocks = InfoGrid()
        for name in CLOCK_FIELDS:
            self.clocks.add(name)
        clocks_card.body.addWidget(self.clocks)
        self.turbo_hint = QLabel("")
        self.turbo_hint.setObjectName("Accent")
        self.turbo_hint.setWordWrap(True)
        self.turbo_hint.setFont(ui_font(m.small_pt))
        self.turbo_hint.hide()
        clocks_card.body.addWidget(self.turbo_hint)

        columns = ResponsiveRow(min_item_width=270)
        columns.add(processor_card)
        columns.add(clocks_card)
        layout.addWidget(columns)

        cache_card = Card("Jerarquía de caché")
        self.caches = InfoGrid()
        cache_card.body.addWidget(self.caches)
        layout.addWidget(cache_card)

        features_card = Card("Juego de instrucciones")
        self.chips = ChipRow()
        features_card.body.addWidget(self.chips)
        self.feature_count = QLabel("")
        self.feature_count.setObjectName("Muted")
        self.feature_count.setWordWrap(True)
        self.feature_count.setFont(ui_font(m.small_pt))
        layout.addWidget(features_card)
        features_card.body.addWidget(self.feature_count)

        self._cache_rows: list[str] = []
        self._chip_signature: tuple = ()

    def apply(self, cpu_type: CpuType) -> None:
        p = self.processor.set  # noqa: E741
        p("Fabricante", cpu_type.vendor or render.DASH)
        p("Especificación", cpu_type.brand or render.DASH)
        p("Nombre en clave", cpu_type.codename or render.DASH)
        p("Tecnología", cpu_type.technology or render.DASH)
        p("Encapsulado", cpu_type.socket or render.DASH)
        p("Arquitectura", cpu_type.architecture or render.DASH)
        p("Núcleos", str(cpu_type.cores))
        p("Hilos", f"{cpu_type.threads}" + ("  (SMT activo)" if cpu_type.smt else ""))
        p("Virtualización", self._virtualization(cpu_type))
        p("Familia", render.hex_id(cpu_type.disp_family))
        p("Modelo", render.hex_id(cpu_type.disp_model))
        p("Stepping", str(cpu_type.stepping) if cpu_type.stepping is not None else render.DASH)
        p("Firma CPUID", render.signature(cpu_type.signature),
          tooltip=render.signature_tooltip(cpu_type))
        p("Microcódigo", cpu_type.microcode or render.DASH)

        c = self.clocks.set
        clocks = cpu_type.clocks
        c("Frecuencia", render.hz(clocks.current_hz))
        c("Multiplicador", render.multiplier(clocks.multiplier))
        c("Base", f"{render.hz(clocks.base_hz)}  {render.multiplier(clocks.base_multiplier)}")
        c("Mínima", f"{render.hz(clocks.min_hz)}  {render.multiplier(clocks.min_multiplier)}")
        c("Máxima (kernel)", f"{render.hz(clocks.max_hz)}  {render.multiplier(clocks.max_multiplier)}")
        c("Máxima (silicio)", f"{render.hz(clocks.max_turbo_hz)}  {render.multiplier(clocks.max_turbo_multiplier)}")
        c("Bus (BCLK)", render.hz(clocks.bus_hz, 0))
        c("Turbo", {True: "activado", False: "desactivado", None: render.DASH}[clocks.turbo_enabled])
        c("Driver", clocks.driver or render.DASH)
        c("Gobernador", clocks.governor or render.DASH)
        c("Preferencia de energía", clocks.energy_preference or render.DASH)

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
            base = "dentro de una máquina virtual"
            return f"{cpu_type.virtualization} · {base}" if cpu_type.virtualization else base
        return f"{cpu_type.virtualization} (soportada)" if cpu_type.virtualization else "no soportada"

    def _apply_caches(self, cpu_type: CpuType) -> None:
        labels = [render.cache_label(cache) for cache in cpu_type.caches]
        if labels != self._cache_rows:
            self.caches.reset()
            for label in labels:
                self.caches.add(label)
            self._cache_rows = labels

        for cache, label in zip(cpu_type.caches, labels):
            self.caches.set(
                label,
                f"{render.cache_summary(cache)}    línea {cache.line_bytes} B · {cache.shared_by} hilos",
                tooltip=f"Total del paquete: {render.size(cache.total_bytes)}\nConjuntos: {cache.sets}",
            )

    def _apply_features(self, cpu_type: CpuType) -> None:
        present = set(cpu_type.features)
        if self._prefs.show_all_features:
            shown = [pretty_feature(f) for f in cpu_type.features]
        else:
            shown = [pretty_feature(f) for f in HIGHLIGHTS if f in present]
        if cpu_type.smt:
            shown.insert(0, "HT" if cpu_type.vendor == "Intel" else "SMT")

        signature = tuple(shown)
        if signature != self._chip_signature:
            self.chips.set_chips(shown)
            self._chip_signature = signature

        rest = len(cpu_type.features) - len(shown)
        self.feature_count.setText(
            f"{len(cpu_type.features)} banderas detectadas por CPUID"
            + (f" · {rest} no destacadas" if rest > 0 else "")
        )


class CpuPage(QScrollArea):
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
        self._layout.setContentsMargins(m.page_margin, m.page_margin, m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        self._layout.addWidget(self._build_header())

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
        self.title = QLabel("Leyendo el procesador…")
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
        cpu = snapshot.cpu
        if not cpu.types:
            return

        primary = cpu.types[0]
        self.title.setText(primary.brand or "Procesador desconocido")
        self.subtitle.setText(
            f"{cpu.total_cores} núcleos · {cpu.total_threads} hilos · "
            f"{cpu.sockets} socket{'s' if cpu.sockets > 1 else ''}"
            + (" · híbrida" if cpu.hybrid else "")
        )
        self._apply_badges(primary)
        self._apply_sections(snapshot)
        self._apply_notices(snapshot)

    def _apply_badges(self, cpu_type: CpuType) -> None:
        wanted = tuple(x for x in (cpu_type.codename, cpu_type.socket,
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
                self._sections[cpu_type.key] = section
                self._sections_host.addWidget(section)
            self._signature = signature

        for cpu_type in cpu.types:
            if section := self._sections.get(cpu_type.key):
                section.apply(cpu_type)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        # Solo las de esta pestaña: la de los módulos de memoria salía aquí
        # porque se enseñaban todas, y no pinta nada junto al procesador.
        notes = snapshot.notes_for("cpu")
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(NEED_TITLES.get(note.need, note.need.value), note.message, note.hint)
            )
