"""Página de sistema: sobre qué software corre esto.

Es la única sección que no habla de hardware, y está aquí porque las preguntas
que responde (qué kernel, cuánta memoria queda, desde cuándo está encendido)
son las que uno se hace justo después de mirar los sensores.

El reparto de memoria se enseña como barra además de como cifras: que el
espacio «libre» de Linux sea pequeño no es un problema, es el diseño, y una
barra donde la caché ocupa su parte lo explica sin párrafos.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...model import Snapshot, System
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, ChipRow, InfoGrid, ResponsiveRow, StackedBar

OS_FIELDS = ("Distribución", "Versión", "Variante", "Identificador", "Nombre del equipo")
KERNEL_FIELDS = ("Kernel", "Arquitectura", "Compilación", "Init", "Escritorio", "Sesión", "Shell")
MEMORY_FIELDS = ("Total", "Usada", "Disponible", "Aplicaciones", "Caché",
                 "Buffers", "Compartida", "Libre", "Intercambio", "Intercambio usado")
ACTIVITY_FIELDS = ("Encendido desde", "Tiempo encendido", "Procesos", "Hilos", "Archivos abiertos")


def format_uptime(seconds: float) -> str:
    """«2 d 14 h 07 min», que se lee mejor que un número de segundos."""
    total = int(seconds)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} d {hours} h {minutes:02d} min"
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"


class SystemPage(QScrollArea):
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

        memory_card = Card("Memoria")
        self.bar = StackedBar(palette)
        self.memory = InfoGrid()
        for name in MEMORY_FIELDS:
            self.memory.add(name)
        memory_card.body.addWidget(self.bar)
        memory_card.body.addWidget(self.memory)
        layout.addWidget(memory_card)

        row = ResponsiveRow(min_item_width=270)
        self.os = self._grid_card(row, "Sistema operativo", OS_FIELDS)
        self.kernel = self._grid_card(row, "Kernel y entorno", KERNEL_FIELDS)
        layout.addWidget(row)

        activity_card = Card("Actividad")
        self.activity = InfoGrid()
        for name in ACTIVITY_FIELDS:
            self.activity.add(name)
        activity_card.body.addWidget(self.activity)
        layout.addWidget(activity_card)

        layout.addStretch(1)
        self._badge_signature: tuple = ()

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
        self.title = QLabel("Leyendo el sistema…")
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        system = snapshot.system
        memory = system.memory
        d = render.DASH

        self.title.setText(system.distribution or "Sistema desconocido")
        self.subtitle.setText(
            f"{system.hostname or d} · encendido {format_uptime(system.uptime_seconds)}"
        )
        self._apply_badges(system)

        # Los tres segmentos más el hueco del fondo suman exactamente el
        # total, por eso se usa `apps_bytes` y no `used_bytes`: la segunda
        # incluye caché no recuperable y haría que la barra se pasara.
        self.bar.set_segments(
            [
                ("Aplicaciones", memory.apps_bytes, "accent"),
                ("Caché", memory.cache_bytes, "info"),
                ("Buffers", memory.buffers_bytes, "warn"),
                ("Libre", memory.free_bytes, "line"),
            ],
            total=memory.total_bytes,
            formatter=render.size,
        )

        m = self.memory.set
        m("Total", render.size(memory.total_bytes))
        m("Usada", f"{render.size(memory.used_bytes)}   ({memory.used_percent:.0f} %)",
          tooltip="Total menos disponible. No se resta solo la libre porque en "
                  "Linux el kernel usa como caché toda la que sobra y la "
                  "devuelve en cuanto un programa la pide.")
        m("Disponible", render.size(memory.available_bytes))
        m("Aplicaciones", render.size(memory.apps_bytes),
          tooltip="Total menos libre, buffers y caché recuperable. Sale algo "
                  "menor que «Usada» porque esa incluye la caché que el kernel "
                  "no puede devolver, como tmpfs y la memoria compartida.")
        m("Caché", render.size(memory.cache_bytes),
          tooltip="Caché de disco recuperable: Cached + SReclaimable − Shmem.")
        m("Buffers", render.size(memory.buffers_bytes))
        m("Compartida", render.size(memory.shared_bytes))
        m("Libre", render.size(memory.free_bytes))
        hay_swap = bool(memory.swap_total_bytes)
        m("Intercambio", render.size(memory.swap_total_bytes) if hay_swap else "sin swap")
        # Sin swap, «Intercambio usado: —» se lee como si faltara un dato. No
        # falta: es que no hay nada de lo que decir cuánto se usa.
        self.memory.set_visible("Intercambio usado", hay_swap)
        if hay_swap:
            m("Intercambio usado",
              f"{render.size(memory.swap_used_bytes)}   "
              f"({memory.swap_used_percent:.0f} %)")

        o = self.os.set
        o("Distribución", system.distribution or d)
        o("Versión", system.version_id or d)
        o("Variante", system.variant or d)
        o("Identificador", system.distribution_id or d)
        o("Nombre del equipo", system.hostname or d)

        k = self.kernel.set
        k("Kernel", system.kernel or d)
        k("Arquitectura", system.architecture or d)
        k("Compilación", system.kernel_build or d)
        k("Init", system.init or d)
        k("Escritorio", system.desktop or d)
        k("Sesión", system.session_type or d)
        k("Shell", system.shell or d)

        a = self.activity.set
        a("Encendido desde", system.boot_time or d)
        a("Tiempo encendido", format_uptime(system.uptime_seconds))
        a("Procesos", f"{system.processes:,}".replace(",", " "))
        a("Hilos", f"{system.threads:,}".replace(",", " "))
        a("Archivos abiertos", f"{system.open_files:,}".replace(",", " "))

    def _apply_badges(self, system: System) -> None:
        session = None
        if system.desktop:
            session = f"{system.desktop} · {system.session_type}" if system.session_type else system.desktop
        wanted = tuple(x for x in (
            system.kernel, session, system.architecture, system.init,
        ) if x)
        if wanted == self._badge_signature:
            return
        self._badge_signature = wanted
        self.badges.set_chips(wanted, highlight_first=True)
