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

from ...i18n import _
from ... import render
from ...model import Snapshot, System
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, ChipRow, InfoGrid, ResponsiveRow, StackedBar

# Claves, no texto ni `_()`: estas tuplas se evalúan al importar el módulo,
# cuando todavía no se sabe qué idioma quiere el usuario. La traducción ocurre
# al montar cada rejilla.
OS_FIELDS = ("sys.field.distro", "sys.field.version", "sys.os.variant",
             "sys.os.id", "sys.field.hostname")
KERNEL_FIELDS = ("sys.kernel.name", "sys.kernel.arch", "sys.field.build",
                 "sys.kernel.init", "sys.kernel.desktop", "sys.field.session",
                 "sys.kernel.shell")
MEMORY_FIELDS = ("sys.mem.total", "sys.mem.used", "sys.mem.available",
                 "sys.mem.apps", "sys.mem.cache", "sys.mem.buffers",
                 "sys.mem.shared", "sys.mem.free", "sys.mem.swap",
                 "sys.mem.swapused")
ACTIVITY_FIELDS = ("sys.field.since", "sys.field.uptime", "sys.act.processes",
                   "sys.act.threads", "sys.field.openfiles")


def format_uptime(seconds: float) -> str:
    """«2 d 14 h 07 min», que se lee mejor que un número de segundos."""
    total = int(seconds)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return _("sys.uptime.dhm").format(d=days, h=hours, m=f"{minutes:02d}")
    if hours:
        return _("sys.uptime.hm").format(h=hours, m=f"{minutes:02d}")
    return _("sys.uptime.m").format(m=minutes)


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

        memory_card = Card(_("nav.memory"))
        self.bar = StackedBar(palette)
        self.memory = InfoGrid()
        for name in MEMORY_FIELDS:
            self.memory.add(_(name))
        memory_card.body.addWidget(self.bar)
        memory_card.body.addWidget(self.memory)
        layout.addWidget(memory_card)

        row = ResponsiveRow(min_item_width=270)
        self.os = self._grid_card(row, _("sys.card.os"), OS_FIELDS)
        self.kernel = self._grid_card(row, _("sys.card.kernel"), KERNEL_FIELDS)
        layout.addWidget(row)

        activity_card = Card("Actividad")
        self.activity = InfoGrid()
        for name in ACTIVITY_FIELDS:
            self.activity.add(_(name))
        activity_card.body.addWidget(self.activity)
        layout.addWidget(activity_card)

        layout.addStretch(1)
        self._badge_signature: tuple = ()

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
        self.title = QLabel(_("sys.loading"))
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
            _("sys.subtitle").format(
                equipo=system.hostname or d,
                tiempo=format_uptime(system.uptime_seconds))
        )
        self._apply_badges(system)

        # Los tres segmentos más el hueco del fondo suman exactamente el
        # total, por eso se usa `apps_bytes` y no `used_bytes`: la segunda
        # incluye caché no recuperable y haría que la barra se pasara.
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

        m = self.memory.set
        m(_("sys.mem.total"), render.size(memory.total_bytes))
        m(_("sys.mem.used"), _("sys.value.pct").format(
            valor=render.size(memory.used_bytes),
            pct=f"{memory.used_percent:.0f}"),
          tooltip="Total menos disponible. No se resta solo la libre porque en "
                  "Linux el kernel usa como caché toda la que sobra y la "
                  "devuelve en cuanto un programa la pide.")
        m(_("sys.mem.available"), render.size(memory.available_bytes))
        m(_("sys.mem.apps"), render.size(memory.apps_bytes),
          tooltip="Total menos libre, buffers y caché recuperable. Sale algo "
                  "menor que «Usada» porque esa incluye la caché que el kernel "
                  "no puede devolver, como tmpfs y la memoria compartida.")
        m(_("sys.mem.cache"), render.size(memory.cache_bytes),
          tooltip=_("sys.tip.cache"))
        m(_("sys.mem.buffers"), render.size(memory.buffers_bytes))
        m(_("sys.mem.shared"), render.size(memory.shared_bytes))
        m(_("sys.mem.free"), render.size(memory.free_bytes))
        hay_swap = bool(memory.swap_total_bytes)
        m(_("sys.mem.swap"), render.size(memory.swap_total_bytes) if hay_swap else _("sys.noswap"))
        # Sin swap, «Intercambio usado: —» se lee como si faltara un dato. No
        # falta: es que no hay nada de lo que decir cuánto se usa.
        self.memory.set_visible(_("sys.mem.swapused"), hay_swap)
        if hay_swap:
            m(_("sys.mem.swapused"),
              _("sys.value.pct").format(
                  valor=render.size(memory.swap_used_bytes),
                  pct=f"{memory.swap_used_percent:.0f}"))

        o = self.os.set
        o(_("sys.field.distro"), system.distribution or d)
        o(_("sys.field.version"), system.version_id or d)
        o(_("sys.os.variant"), system.variant or d)
        o(_("sys.os.id"), system.distribution_id or d)
        o(_("sys.field.hostname"), system.hostname or d)

        k = self.kernel.set
        k(_("sys.kernel.name"), system.kernel or d)
        k(_("sys.kernel.arch"), system.architecture or d)
        k(_("sys.field.build"), system.kernel_build or d)
        k(_("sys.kernel.init"), system.init or d)
        k(_("sys.kernel.desktop"), system.desktop or d)
        k(_("sys.field.session"), system.session_type or d)
        k(_("sys.kernel.shell"), system.shell or d)

        a = self.activity.set
        a(_("sys.field.since"), system.boot_time or d)
        a(_("sys.field.uptime"), format_uptime(system.uptime_seconds))
        a(_("sys.act.processes"), f"{system.processes:,}".replace(",", " "))
        a(_("sys.act.threads"), f"{system.threads:,}".replace(",", " "))
        a(_("sys.field.openfiles"), f"{system.open_files:,}".replace(",", " "))

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
