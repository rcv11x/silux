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
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import render
from ...i18n import _
from ...model import Snapshot, System
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
    Table,
    clear_layout,
    let_go,
    tone_for,
)
from .board import NEED_TITLES

# Claves, no texto ni `_()`: estas tuplas se evalúan al importar el módulo,
# cuando todavía no se sabe qué idioma quiere el usuario. La traducción ocurre
# al montar cada rejilla.
OS_FIELDS = ("sys.field.distro", "sys.field.version", "sys.os.variant",
             "sys.os.id", "sys.field.hostname", "sys.os.packages", "sys.os.timezone",
             "sys.os.locale")
KERNEL_FIELDS = ("sys.kernel.name", "sys.kernel.arch", "sys.field.build",
                 "sys.kernel.init", "sys.kernel.desktop", "sys.field.session",
                 "sys.kernel.shell", "sys.kernel.graphics", "sys.kernel.access",
                 "sys.kernel.tainted")
ACTIVITY_FIELDS = ("sys.field.since", "sys.field.uptime", "sys.act.load", "sys.act.processes",
                   "sys.act.threads", "sys.field.openfiles", "sys.act.failed",
                   "sys.act.kernelerrors")
# The kernel's errors listed, the most repeated first.
KERNEL_ERRORS_SHOWN = 12
SECURITY_FIELDS = ("sys.vuln.known", "sys.vuln.unaffected", "sys.vuln.mitigated",
                   "sys.vuln.open", "sys.vuln.unknown")
BOOT_FIELDS = ("sys.boot.loader", "sys.boot.entry") + tuple(
    clave for clave, _campo in render.BOOT_PHASES) + ("sys.boot.cmdline",)


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


class SystemPage(ScrollPage):
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
        # Las tres en una fila que se reparte sola (ver `BoardPage`).
        row = ResponsiveRow(min_item_width=400, span_last=True)
        self.os = self._grid_card(row, _("sys.card.os"), OS_FIELDS)
        self.os_pie = QLabel("")
        self.os_pie.setObjectName("Muted")
        self.os_pie.setWordWrap(True)
        self.os_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.os_pie.hide()
        self.os.parentWidget().body.addWidget(self.os_pie)
        self.kernel = self._grid_card(row, _("sys.card.kernel"), KERNEL_FIELDS)
        self.kernel_pie = QLabel("")
        self.kernel_pie.setObjectName("Muted")
        self.kernel_pie.setWordWrap(True)
        self.kernel_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.kernel_pie.hide()
        self.kernel.parentWidget().body.addWidget(self.kernel_pie)
        activity_card = Card(_("sys.card.activity"))
        self.activity = InfoGrid()
        for name in ACTIVITY_FIELDS:
            self.activity.add(_(name))
        activity_card.body.addWidget(self.activity)
        row.add(activity_card)
        layout.addWidget(row)

        self.kernel_errors_card = Card(_("sys.card.kernelerrors"))
        # The message cut where it doesn't fit; whole in its tooltip.
        self.kernel_errors = Table([_("sys.kerr.message"), _("sys.kerr.times")],
                                   numeric=(False, True), cede=(0,))
        self.kernel_errors_card.body.addWidget(self.kernel_errors)
        self.kernel_errors_pie = QLabel("")
        self.kernel_errors_pie.setObjectName("Muted")
        self.kernel_errors_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.kernel_errors_pie.hide()
        self.kernel_errors_card.body.addWidget(self.kernel_errors_pie)
        self.kernel_errors_card.hide()
        layout.addWidget(self.kernel_errors_card)

        # Las mitigaciones del procesador: el resumen a la vista y la lista,
        # con el texto del kernel tal cual, plegada.
        self.security_card = Card(_("sys.card.security"))
        self.security = InfoGrid()
        for name in SECURITY_FIELDS:
            self.security.add(_(name))
        self.security_card.body.addWidget(self.security)
        self.vuln_fold = Plegable(_("sys.vuln.list"))
        self.vulns = InfoGrid()
        self.vuln_fold.body.addWidget(self.vulns)
        self.security_card.body.addWidget(self.vuln_fold)
        self.security_card.hide()
        self._vuln_signature: tuple = ()

        # The vulnerabilities and swap, one over the other beside the boot:
        # the swap alone took half the width for one line.
        abajo = ResponsiveRow(min_item_width=400, span_last=True)
        self.swap_card = Card(_("sys.card.swap"))
        self.swap = InfoGrid()
        self.swap_card.body.addWidget(self.swap)
        self._swap_signature: tuple = ()
        column = QWidget()
        stacked = QVBoxLayout(column)
        stacked.setContentsMargins(0, 0, 0, 0)
        stacked.setSpacing(m.section_gap)
        stacked.addWidget(self.security_card)
        stacked.addWidget(self.swap_card)
        stacked.addStretch(1)
        abajo.add(column)
        self.boot_card = Card(_("sys.card.boot"))
        self.boot = InfoGrid()
        for name in BOOT_FIELDS:
            self.boot.add(_(name))
        self.boot_card.body.addWidget(self.boot)
        abajo.add(self.boot_card)
        layout.addWidget(abajo)
        # Lo que este equipo no publica, dicho: el arranque de un GRUB.
        self.extra_pie = QLabel("")
        self.extra_pie.setObjectName("Muted")
        self.extra_pie.setWordWrap(True)
        self.extra_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.extra_pie.hide()
        layout.addWidget(self.extra_pie)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        layout.addLayout(self._notices_host)
        self._notice_signature: tuple = ()

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
        self.subtitle.setWordWrap(True)
        self.badges = ChipRow()

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        system = snapshot.system
        d = render.DASH

        self.title.setText(system.distribution or _("sys.unknown"))
        self.subtitle.setText(
            _("sys.subtitle").format(
                equipo=system.hostname or d,
                tiempo=format_uptime(system.uptime_seconds))
        )
        self._apply_badges(system)
        self._apply_notices(snapshot)

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
        for key, value in (("sys.os.packages", render.packages(system.packages)),
                           ("sys.os.timezone", system.timezone),
                           ("sys.os.locale", system.locale)):
            o(_(key), value or d)
            self.os.set_visible(_(key), bool(value))

        k = self.kernel.set
        k(_("sys.kernel.name"), system.kernel or d)
        k(_("sys.kernel.arch"), system.architecture or d)
        k(_("sys.field.build"), system.kernel_build or d)
        k(_("sys.kernel.init"), system.init or d)
        k(_("sys.kernel.desktop"), render.desktop(system.desktop, system.desktop_version) or d)
        k(_("sys.field.session"), system.session_type or d)
        # Neither declared by this program's environment: hidden and said.
        unknown = [key for key, value in (("sys.kernel.desktop", system.desktop),
                                          ("sys.field.session", system.session_type))
                   if not value]
        for key in ("sys.kernel.desktop", "sys.field.session"):
            self.kernel.set_visible(_(key), key not in unknown)
        sentence = {2: "sys.na.desktop.both", 1: "sys.na.desktop.one"}.get(len(unknown))
        self.kernel_pie.setText(_(sentence).format(
            what=_("sys.na.what.desktop" if "sys.kernel.desktop" in unknown
                   else "sys.na.what.session")) if sentence else "")
        self.kernel_pie.setVisible(bool(unknown))
        k(_("sys.kernel.shell"), system.shell or d)
        graficos = render.graphics_stack(snapshot)
        k(_("sys.kernel.graphics"), graficos or d)
        self.kernel.set_visible(_("sys.kernel.graphics"), bool(graficos))
        access = render.access_control(system.access_control)
        k(_("sys.kernel.access"), access or d, tooltip=_("sys.access.tip"))
        self.kernel.set_visible(_("sys.kernel.access"), access is not None)
        k(_("sys.kernel.tainted"), render.tainted(system.tainted, system.tainting_modules),
          tooltip=_("sys.taint.tip").format(mask=system.tainted or 0))
        self.kernel.set_visible(_("sys.kernel.tainted"), system.tainted is not None)

        a = self.activity.set
        a(_("sys.field.since"), system.boot_time or d)
        a(_("sys.field.uptime"), format_uptime(system.uptime_seconds))
        a(_("sys.act.processes"), render.thousands(system.processes))
        a(_("sys.act.threads"), render.thousands(system.threads))
        a(_("sys.field.openfiles"), render.thousands(system.open_files))
        cpu = snapshot.cpu
        load = (render.load_average(cpu.load_average, cpu.total_threads)
                if cpu is not None and cpu.load_average else None)
        for key, value, tip in (
                ("sys.act.load", load, "sys.load.tip"),
                ("sys.act.failed", render.failed_units(system.failed_units), ""),
                ("sys.act.kernelerrors", render.kernel_errors(system.kernel_errors), "")):
            a(_(key), value or d, tooltip=_(tip) if tip else "")
            self.activity.set_visible(_(key), value is not None)
        self._apply_kernel_errors(system)

        self._apply_security(system)
        self._apply_swap(system)
        self._apply_boot(system)

    def _apply_kernel_errors(self, system: System) -> None:
        groups = sorted(system.kernel_errors or (), key=lambda g: -g[1])
        self.kernel_errors_card.setVisible(bool(groups))
        if not groups:
            return
        rows = [(text, render.thousands(times)) for text, times in groups[:KERNEL_ERRORS_SHOWN]]
        self.kernel_errors.set_rows(rows, tooltips=[text for text, _times in rows])
        rest = len(groups) - KERNEL_ERRORS_SHOWN
        self.kernel_errors_pie.setText(render.counted("sys.kerr.more", rest) if rest > 0 else "")
        self.kernel_errors_pie.setVisible(rest > 0)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        notes = snapshot.notes_for("system")
        signature = tuple((n.path, n.need, n.title, n.message, n.hint) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature
        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(render.note_title(note, NEED_TITLES),
                       note.message, note.hint, tone=tone_for(note.need)))

    def _apply_security(self, system: System) -> None:
        todas = system.vulnerabilities
        self.security_card.setVisible(bool(todas))
        if not todas:
            return
        cuenta = {estado: sum(1 for v in todas if v.state == estado)
                  for estado in ("unaffected", "mitigated", "vulnerable", "unknown")}
        s = self.security.set
        s(_("sys.vuln.known"), str(len(todas)))
        s(_("sys.vuln.unaffected"), str(cuenta["unaffected"]))
        s(_("sys.vuln.mitigated"), str(cuenta["mitigated"]))
        s(_("sys.vuln.open"), str(cuenta["vulnerable"]) if cuenta["vulnerable"]
          else _("sys.vuln.none"))
        # What the kernel itself does not know («Unknown: No mitigations» in a
        # QEMU guest) counted nowhere: 17 known, 8 + 6 + 2 said.
        s(_("sys.vuln.unknown"), str(cuenta["unknown"]))
        self.security.set_visible(_("sys.vuln.unknown"), bool(cuenta["unknown"]))
        # En la lista, las que tienen algo que contar: las que no afectan a
        # este procesador ya están contadas arriba.
        firma = tuple((v.name, v.status) for v in todas if v.state != "unaffected")
        if firma != self._vuln_signature:
            self._vuln_signature = firma
            self.vulns = self._rejilla_nueva(self.vuln_fold.body, self.vulns, firma)
        self.vuln_fold.setVisible(bool(firma))

    def _apply_swap(self, system: System) -> None:
        filas = tuple((render.swap_name(s), render.swap_summary(s)) for s in system.swaps)
        if not filas:
            filas = ((_("sys.swap.label"), _("sys.swap.none")),)
        nombres = tuple(n for n, _v in filas)
        if nombres != self._swap_signature:
            self._swap_signature = nombres
            self.swap = self._rejilla_nueva(self.swap_card.body, self.swap, filas)
        else:
            for nombre, valor in filas:
                self.swap.set(nombre, valor)

    def _apply_boot(self, system: System) -> None:
        arranque = system.boot
        fases = dict(render.boot_phases(arranque))
        hay = bool(arranque.loader or arranque.entry or fases or arranque.cmdline)
        self.boot_card.setVisible(hay)
        # Solo lo que falta de verdad. El GRUB de Fedora no publica sus
        # tiempos, pero el firmware sí (FPDT), y lo del kernel en adelante lo
        # da systemd con cualquier gestor: con él no falta nada.
        pies = []
        if not hay:
            pies.append(_("sys.boot.unpublished"))
        else:
            if arranque.firmware_s is None:
                # Without a loader's name, not «Gestor de arranque no lo
                # publica» with the generic word standing in for one.
                pies.append(_("sys.boot.nofirmware").format(gestor=arranque.loader)
                            if arranque.loader else _("sys.boot.nofirmware.unknown"))
            if arranque.kernel_s is None:
                # Only systemd measures those: on OpenRC there is nobody that
                # «did not answer».
                pies.append(_("sys.boot.nosystemd") if system.init in (None, "systemd")
                            else _("sys.boot.notsystemd").format(init=system.init))
            elif arranque.userspace_s is None:
                pies.append(_("sys.boot.unfinished"))
        pie = " ".join(pies)
        self.extra_pie.setText(pie)
        self.extra_pie.setVisible(bool(pie))
        # Una fila por fase: en una sola línea, las seis cifras no cabían en
        # la tarjeta y se cortaban.
        valores = {"sys.boot.loader": arranque.loader, "sys.boot.entry": arranque.entry, **fases,
                   "sys.boot.cmdline": " ".join(arranque.cmdline)}
        for clave in BOOT_FIELDS:
            valor = valores.get(clave)
            self.boot.set(_(clave), valor or render.DASH)
            self.boot.set_visible(_(clave), bool(valor))

    @staticmethod
    def _rejilla_nueva(donde, vieja: InfoGrid, filas) -> InfoGrid:
        """Una rejilla con esas filas en el sitio de la que había.

        Para las listas que cambian de forma: un intercambio que se activa,
        una entrada que desaparece. Se rehace solo cuando cambian los nombres.
        """
        nueva = InfoGrid()
        for nombre, valor in filas:
            nueva.add(nombre)
            nueva.set(nombre, valor)
        donde.replaceWidget(vieja, nueva)
        let_go(vieja)
        return nueva

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
