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
from ..theme import Palette, ui_font
from ..widgets import Card, ChipRow, InfoGrid, ResponsiveRow

# Claves, no texto ni `_()`: estas tuplas se evalúan al importar el módulo,
# cuando todavía no se sabe qué idioma quiere el usuario. La traducción ocurre
# al montar cada rejilla.
OS_FIELDS = ("sys.field.distro", "sys.field.version", "sys.os.variant",
             "sys.os.id", "sys.field.hostname")
KERNEL_FIELDS = ("sys.kernel.name", "sys.kernel.arch", "sys.field.build",
                 "sys.kernel.init", "sys.kernel.desktop", "sys.field.session",
                 "sys.kernel.shell")
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

        # La memoria no está aquí: tenía su barra y su tabla entera, las
        # mismas que la página de Memoria, y era la tercera vez que salían.
        # Esta página empieza por lo que es suyo: qué sistema es.
        row = ResponsiveRow(min_item_width=270)
        self.os = self._grid_card(row, _("sys.card.os"), OS_FIELDS)
        self.os_pie = QLabel("")
        self.os_pie.setObjectName("Muted")
        self.os_pie.setWordWrap(True)
        self.os_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.os_pie.hide()
        self.os.parentWidget().body.addWidget(self.os_pie)
        self.kernel = self._grid_card(row, _("sys.card.kernel"), KERNEL_FIELDS)
        layout.addWidget(row)

        activity_card = Card(_("sys.card.activity"))
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

        o = self.os.set
        o(_("sys.field.distro"), system.distribution or d)
        # Una distribución de publicación continua no tiene versión, y casi
        # ninguna declara variante: no es un dato que falte. La fila se va y
        # se dice al pie cuál.
        o(_("sys.field.version"), system.version_id or d)
        o(_("sys.os.variant"), system.variant or d)
        self.os.set_visible(_("sys.field.version"), bool(system.version_id))
        self.os.set_visible(_("sys.os.variant"), bool(system.variant))
        faltan = [_(clave).lower() for clave, valor in (
            ("sys.field.version", system.version_id), ("sys.os.variant", system.variant))
            if not valor]
        self.os_pie.setText(_("sys.os.undeclared").format(campos=_("sys.and").join(faltan))
                            if faltan else "")
        self.os_pie.setVisible(bool(faltan))
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
        # El kernel y la sesión, que es lo que se pregunta de un sistema. La
        # arquitectura y el init están dos renglones más abajo, en su ficha.
        wanted = tuple(x for x in (system.kernel, session) if x)
        if wanted == self._badge_signature:
            return
        self._badge_signature = wanted
        self.badges.set_chips(wanted, highlight_first=True)
