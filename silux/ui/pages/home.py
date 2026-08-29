"""La portada: qué equipo es esto y qué está haciendo, en una pantalla.

Antes el programa abría en la ficha del procesador, que es la respuesta a una
pregunta que nadie ha hecho todavía. Lo primero que quiere ver quien abre esto
—sobre todo la primera vez— es de qué equipo se trata: qué lleva dentro y si
algo está caliente o a tope ahora mismo.

Cada tarjeta lleva a su sección al pulsarla, así que esta página hace además
de índice: se mira, se elige y se entra.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ...i18n import _
from ... import render
from ...model import Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, ChipRow, ResponsiveRow, Sparkline, StackedBar
from ..widgets import ui_font


class _TarjetaResumen(Card):
    """Una pieza del equipo: qué es, cómo está y una curva de su historia."""

    pulsada = Signal(str)

    def __init__(self, titulo: str, seccion: str, palette: Palette,
                 con_grafica: bool = True, parent: Optional[QWidget] = None):
        super().__init__(titulo, parent)
        self._seccion = seccion
        self._p = palette
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_("home.goto").format(seccion=seccion))

        m = theme.METRICS
        self.nombre = QLabel("—")
        self.nombre.setObjectName("Headline")
        self.nombre.setWordWrap(True)
        self.detalle = QLabel("")
        self.detalle.setObjectName("Subhead")
        self.detalle.setWordWrap(True)

        self.cifras = QLabel("")
        self.cifras.setObjectName("FieldValue")
        self.cifras.setFont(ui_font(m.base_pt + 3))

        self.body.addWidget(self.nombre)
        self.body.addWidget(self.detalle)
        self.body.addWidget(self.cifras)

        self.grafica = Sparkline(palette) if con_grafica else None
        self.barra = None if con_grafica else StackedBar(palette)
        self.body.addWidget(self.grafica or self.barra)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.pulsada.emit(self._seccion)
        super().mouseReleaseEvent(event)

    def poner(self, nombre: str, detalle: str, cifras: str) -> None:
        for etiqueta, texto in ((self.nombre, nombre), (self.detalle, detalle),
                                (self.cifras, cifras)):
            if etiqueta.text() != texto:
                etiqueta.setText(texto)


class HomePage(QScrollArea):
    seccion_pedida = Signal(str)

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
        layout.setContentsMargins(m.page_margin, m.page_margin,
                                  m.page_margin, m.page_margin)
        layout.setSpacing(m.section_gap)

        layout.addWidget(self._cabecera())

        arriba = ResponsiveRow(min_item_width=300)
        self.cpu = self._tarjeta(arriba, _("home.card.cpu"), _("nav.cpu"))
        self.gpu = self._tarjeta(arriba, _("home.card.gpu"), _("nav.graphics"))
        layout.addWidget(arriba)

        abajo = ResponsiveRow(min_item_width=300)
        self.memoria = self._tarjeta(abajo, _("nav.memory"), _("nav.memory"), grafica=False)
        self.discos = self._tarjeta(abajo, _("nav.storage"), _("nav.storage"),
                                    grafica=False)
        layout.addWidget(abajo)

        layout.addStretch(1)
        self._chips: tuple = ()

    def _tarjeta(self, host: ResponsiveRow, titulo: str, seccion: str,
                 grafica: bool = True) -> _TarjetaResumen:
        tarjeta = _TarjetaResumen(titulo, seccion, self._p, con_grafica=grafica)
        tarjeta.pulsada.connect(self.seccion_pedida)
        host.add(tarjeta)
        return tarjeta

    def _cabecera(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("home.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.subtitle.setWordWrap(True)
        self.badges = ChipRow()

        # Quien abre esto por primera vez no sabe qué está mirando ni qué
        # puede esperar. Una línea al principio ahorra la pregunta.
        self.pitch = QLabel(
            _("home.tagline"))
        self.pitch.setObjectName("Muted")
        self.pitch.setWordWrap(True)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        card.body.addWidget(self.pitch)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self._cabecera_con(snapshot)
        self._procesador(snapshot)
        self._grafica(snapshot)
        self._memoria(snapshot)
        self._almacenamiento(snapshot)

    def _cabecera_con(self, snapshot: Snapshot) -> None:
        from .system import format_uptime

        sistema = snapshot.system
        equipo = snapshot.board.display_name if snapshot.board else None
        self.title.setText(equipo or sistema.hostname or _("home.thispc"))

        partes = [sistema.distribution, sistema.kernel]
        if sistema.desktop:
            partes.append(f"{sistema.desktop} · {sistema.session_type or ''}".strip(" ·"))
        if sistema.uptime_seconds:
            partes.append(_("home.uptime").format(
                tiempo=format_uptime(sistema.uptime_seconds)))
        self.subtitle.setText(" · ".join(p for p in partes if p))

        chips = []
        if sistema.hostname:
            chips.append(sistema.hostname)
        if snapshot.cpu.types:
            chips.append(snapshot.cpu.types[0].architecture or "")
        pendientes = sum(1 for n in snapshot.notes if n.need.value == "root")
        if pendientes:
            chips.append(_("home.unread.one" if pendientes == 1
                           else "home.unread.many").format(n=pendientes))

        # Lo que está fuera de umbral se dice en la portada, que es donde se
        # entra. Enterarse de que la GPU va a 100 grados solo si se abre la
        # pestaña de sensores y se despliega su rama es enterarse tarde.
        niveles = [s.alarm_level for s in snapshot.sensors if s.alarm_level != "ok"]
        if niveles:
            criticos = niveles.count("crítico")
            chips.append(
                "⚠ " + (_("home.alarm.crit.one" if criticos == 1
                          else "home.alarm.crit.many").format(n=criticos)
                        if criticos else
                        _("home.alarm.high.one" if len(niveles) == 1
                          else "home.alarm.high.many").format(n=len(niveles))))
        chips = [c for c in chips if c]
        if tuple(chips) != self._chips:
            self._chips = tuple(chips)
            self.badges.set_chips(chips, highlight_first=True)

    def _procesador(self, snapshot: Snapshot) -> None:
        cpu = snapshot.cpu
        if not cpu.types:
            self.cpu.poner("—", "", "")
            return
        principal = cpu.types[0]
        nucleos = sum(t.cores for t in cpu.types)
        hilos = sum(t.threads for t in cpu.types)
        detalle = " · ".join((
            _("home.cores.one" if nucleos == 1
              else "home.cores.many").format(n=nucleos),
            _("home.threads.one" if hilos == 1
              else "home.threads.many").format(n=hilos)))
        if principal.codename:
            detalle += f" · {principal.codename}"

        piezas = []
        if cpu.usage_percent is not None:
            piezas.append(render.percent(cpu.usage_percent))
            self.cpu.grafica.push(cpu.usage_percent)
            self.cpu.grafica.set_range(0.0, 100.0)
        if principal.clocks.current_hz:
            piezas.append(render.hz(principal.clocks.current_hz))
        if (temp := self._temperatura_cpu(snapshot)) is not None:
            piezas.append(render.temperature(temp, self._prefs.fahrenheit))
        self.cpu.poner(render.cpu_short_name(principal.brand), detalle,
                       "   ".join(piezas))

    @staticmethod
    def _temperatura_cpu(snapshot: Snapshot) -> Optional[float]:
        for sensor in snapshot.sensors:
            if sensor.kind.value == "temperature" and sensor.value is not None:
                if "package" in (sensor.label or "").lower() or "tctl" in (sensor.label or "").lower():
                    return sensor.value
        return None

    def _grafica(self, snapshot: Snapshot) -> None:
        if not snapshot.gpus:
            self.gpu.poner(_("home.gpu.none"), "", "")
            return
        gpu = snapshot.gpus[0]
        detalle = " · ".join(p for p in (
            render.vram_kind(gpu.memory) if gpu.memory.total_bytes else None,
            render.pcie_link(gpu.link) if gpu.link.current_speed_gts else None,
        ) if p)

        piezas = []
        if gpu.busy_percent is not None:
            piezas.append(render.percent(gpu.busy_percent))
            self.gpu.grafica.push(gpu.busy_percent)
            self.gpu.grafica.set_range(0.0, 100.0)
        if gpu.temp_c is not None:
            piezas.append(render.temperature(gpu.temp_c, self._prefs.fahrenheit))
        if gpu.power_w is not None:
            piezas.append(render.watts(gpu.power_w))
        self.gpu.poner(gpu.display_name, detalle, "   ".join(piezas))

    def _memoria(self, snapshot: Snapshot) -> None:
        memoria = snapshot.system.memory
        if not memoria.total_bytes:
            self.memoria.poner("—", "", "")
            return
        detalle = " · ".join(p for p in (
            render.size(memoria.total_bytes),
            _tipo_de_memoria(snapshot),
        ) if p)
        usada = memoria.used_bytes
        self.memoria.poner(
            _("home.mem.inuse").format(tam=render.size(usada)), detalle,
            _("home.mem.used").format(
                pct=f"{usada / memoria.total_bytes * 100:.0f}"))
        self.memoria.barra.set_segments(
            [(_("home.mem.seg.inuse"), usada, "accent"),
             (_("sys.mem.cache"), memoria.cache_bytes, "line"),
             (_("sys.mem.free"),
              max(0, memoria.total_bytes - usada - memoria.cache_bytes), "muted")],
            total=memoria.total_bytes, formatter=render.size)

    def _almacenamiento(self, snapshot: Snapshot) -> None:
        discos = snapshot.disks
        if not discos:
            self.discos.poner(_("home.storage.none"), "", "")
            return
        total = sum(d.size_bytes or 0 for d in discos)
        usado = sum(d.used_bytes or 0 for d in discos)
        libre = sum(p.free_bytes or 0 for d in discos for p in d.mounted_partitions)
        tipos = [f"{sum(1 for d in discos if d.kind == k)} × {k}"
                 for k in ("NVMe", "SSD", "HDD")
                 if any(d.kind == k for d in discos)]
        self.discos.poner(
            _("home.storage.total.one" if len(discos) == 1
              else "home.storage.total").format(tam=render.size(total),
                                                n=len(discos)),
            " · ".join(tipos),
            _("home.storage.free").format(tam=render.size(libre)))
        sin_montar = max(0, total - usado - libre)
        segmentos = [(_("home.bar.used"), usado, "accent"),
                     (_("home.bar.free"), libre, "line")]
        if sin_montar:
            segmentos.append((_("home.bar.unmounted"), sin_montar, "muted"))
        self.discos.barra.set_segments(segmentos, total=total,
                                       formatter=render.size)


def _tipo_de_memoria(snapshot: Snapshot) -> Optional[str]:
    """«DDR4-3200», si se sabe de qué son los módulos."""
    for modulo in snapshot.modules:
        if modulo.type:
            return (f"{modulo.type}-{modulo.speed_mts}" if modulo.speed_mts
                    else modulo.type)
    return None
