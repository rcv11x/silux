"""Página de almacenamiento: qué unidades hay y qué están haciendo.

El orden responde a las preguntas por frecuencia: primero cuánto espacio queda,
que es lo que trae aquí a casi todo el mundo; después qué unidades hay y de qué
tipo; y al final la ficha de cada una.

Las particiones van en su propia tabla y no dentro de cada disco. Un equipo con
cinco unidades y doce particiones se vuelve ilegible si cada una cuelga de su
disco, y la pregunta «dónde está montado /home» no se hace por disco.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ... import render
from ...i18n import _
from ...model import Disk, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import (Card, ChipRow, InfoGrid, Notice, ResponsiveRow,
                       StackedBar, StatTile, Table,
                       boton_de_permiso_permanente, clear_layout)

DISK_HEADERS = ("storage.col.unit", "storage.col.model", "gpu.vram.type", "storage.col.size", "storage.col.used",
                "gpu.sensor.temp", "storage.tile.reading", "storage.tile.writing")
PART_HEADERS = ("storage.col.part", "storage.col.fs", "storage.col.mount", "storage.col.size2", "storage.col.used2", "storage.col.free")

DISK_FIELDS = ("storage.col.model", "gpu.field.vendor", "gpu.vram.type", "storage.field.bus", "storage.col.size",
               "storage.field.firmware", "storage.field.logical", "storage.field.physical", "storage.field.scheduler",
               "gpu.clock.link", "gpu.sensor.temp", "storage.field.hours", "storage.field.written",
               "storage.field.life")

# Los discos se ordenan por lo que le importa a quien mira: primero el que
# lleva el sistema, luego por tipo y al final los que se pueden desenchufar.
PRIORIDAD = {"NVMe": 0, "SSD": 1, "HDD": 2}


def _orden(disco: Disk) -> tuple:
    arranque = not any(p.mountpoint == "/" for p in disco.partitions)
    return (disco.removable, arranque, PRIORIDAD.get(disco.kind or "", 9), disco.name)


class StoragePage(QScrollArea):
    # El diagnóstico de los discos exige permisos, igual que el detalle de la
    # memoria. Sin un botón aquí, los campos aparecían vacíos y sin explicación
    # y no había forma de adivinar que la contraseña se pedía en otra pestaña.
    elevation_requested = Signal()
    permanent_requested = Signal()

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

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_tiles())
        layout.addWidget(self._build_elevation())

        # Los avisos de los discos van antes que las tablas: un disco que dice
        # que se está quedando sin reserva no puede salir por debajo de su
        # temperatura y sus gigabytes libres.
        self._avisos_host = QVBoxLayout()
        self._avisos_host.setSpacing(6)
        layout.addLayout(self._avisos_host)

        disk_card = Card(_("storage.card.disks"))
        self.disks = Table([_(h) for h in DISK_HEADERS],
                           numeric=(False, False, False, True, True, True, True, True))
        disk_card.body.addWidget(self.disks)
        layout.addWidget(disk_card)

        part_card = Card(_("storage.card.parts"))
        self.parts = Table([_(h) for h in PART_HEADERS], numeric=(False, False, False, True, True, True))
        part_card.body.addWidget(self.parts)
        layout.addWidget(part_card)

        self._cards_host = QVBoxLayout()
        self._cards_host.setSpacing(m.section_gap)
        layout.addLayout(self._cards_host)
        layout.addStretch(1)

        self._grids: dict[str, InfoGrid] = {}
        self._bars: dict[str, StackedBar] = {}
        self._orden_actual: tuple = ()
        self._chip_signature: tuple = ()
        self._avisos_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("storage.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()
        self.total_bar = StackedBar(self._p)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        card.body.addWidget(self.total_bar)
        return card

    def _build_tiles(self) -> QWidget:
        fila = ResponsiveRow(min_item_width=150)
        self.tile_read = StatTile(_("storage.tile.reading"), "", self._p)
        self.tile_write = StatTile(_("storage.tile.writing"), "", self._p)
        self.tile_free = StatTile(_("storage.tile.free"), "", self._p)
        self.tile_temp = StatTile(_("storage.tile.hottest"), "°C", self._p)
        for tile in (self.tile_read, self.tile_write, self.tile_free, self.tile_temp):
            fila.add(tile)
        # El espacio libre no se mueve de un segundo a otro: su curva sería una
        # recta que no dice nada.
        self.tile_free.chart.hide()
        intervalo = self._prefs.interval_s
        self.tile_read.chart.set_formatter(render.rate, intervalo)
        self.tile_write.chart.set_formatter(render.rate, intervalo)
        self.tile_temp.chart.set_formatter(
            lambda v: render.temperature(v, self._prefs.fahrenheit), intervalo)
        return fila

    def _build_elevation(self) -> Card:
        """La tarjeta que explica qué falta y por qué, con su botón."""
        card = Card(_("storage.card.health"))
        self.elevation_text = QLabel(
            _("storage.health.body")
        )
        self.elevation_text.setObjectName("NoticeBody")
        self.elevation_text.setWordWrap(True)

        detalle = QLabel(
            _("storage.health.hint")
        )
        detalle.setObjectName("Muted")
        detalle.setWordWrap(True)

        self.elevation_button = QPushButton(_("perm.read.button"))
        self.elevation_button.clicked.connect(self.elevation_requested)
        self.permanent_button = boton_de_permiso_permanente()
        self.permanent_button.clicked.connect(self.permanent_requested)

        fila = QHBoxLayout()
        fila.addWidget(self.elevation_button)
        fila.addWidget(self.permanent_button)
        fila.addStretch(1)

        card.body.addWidget(self.elevation_text)
        card.body.addWidget(detalle)
        card.body.addLayout(fila)
        self.elevation_card = card
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        discos = sorted(snapshot.disks, key=_orden)
        self._apply_header(discos)
        self._apply_tiles(discos)
        self._apply_tables(discos)
        self._apply_cards(discos)
        self._apply_avisos(discos)
        # La tarjeta solo estorba cuando ya no hace falta.
        leidos = sum(1 for x in discos if x.health.power_on_hours is not None)
        self.elevation_card.setVisible(bool(discos) and leidos < len(discos))
        if leidos:
            self.elevation_text.setText(
                _("storage.health.read").format(n=leidos, total=len(discos))
            )

    def _apply_avisos(self, discos) -> None:
        """Lo que cada disco dice de sí mismo, si es que dice algo.

        El registro de salud se leía entero y no salía ni una línea: el campo
        por el que un NVMe avisa de que va camino de perder datos estaba ahí
        sin que lo mirara nadie.
        """
        filas = [(disco, nivel, texto)
                 for disco in discos
                 for nivel, texto in render.disk_warnings(disco.health)]
        firma = tuple((d.name, n, t) for d, n, t in filas)
        if firma == self._avisos_signature:
            return
        self._avisos_signature = firma

        clear_layout(self._avisos_host)
        for disco, nivel, texto in filas:
            self._avisos_host.addWidget(Notice(
                disco.display_name if hasattr(disco, "display_name") else disco.name,
                texto,
                hint=_("storage.warn.hint"),
                tone="bad" if nivel == "crítico" else "warn",
            ))

    def _apply_header(self, discos) -> None:
        d = render.DASH
        if not discos:
            self.title.setText(_("storage.none"))
            self.subtitle.setText("")
            self.total_bar.hide()
            return

        total = sum(x.size_bytes or 0 for x in discos)
        usado = sum(x.used_bytes or 0 for x in discos)
        self.title.setText(_("storage.title.one" if len(discos) == 1
                             else "storage.title").format(
            tam=render.size(total), n=len(discos)))
        montadas = sum(len(x.mounted_partitions) for x in discos)
        self.subtitle.setText(
            _("storage.subtitle.one" if montadas == 1
              else "storage.subtitle").format(tam=render.size(usado), n=montadas)
        )

        chips = []
        for tipo in ("NVMe", "SSD", "HDD"):
            cuantos = sum(1 for x in discos if x.kind == tipo)
            if cuantos:
                chips.append(f"{cuantos} × {tipo}")
        if tuple(chips) != self._chip_signature:
            self._chip_signature = tuple(chips)
            self.badges.set_chips(chips, highlight_first=True)

        if total and usado:
            # Tres trozos, no dos. Restarle lo ocupado a la capacidad da un
            # «libre» que se cree que todo el disco está montado, y en un
            # equipo con Windows al lado eso son cientos de gigas contados
            # como libres que no lo están. Lo libre de verdad es lo que dicen
            # las particiones montadas; el resto del disco es otra cosa y se
            # dice aparte.
            libre = sum(p.free_bytes or 0 for x in discos
                        for p in x.mounted_partitions)
            sin_montar = max(0, total - usado - libre)
            segmentos = [(_("storage.col.used"), usado, "accent"),
                         (_("storage.col.free"), libre, "line")]
            if sin_montar:
                segmentos.append((_("storage.bar.unmounted"), sin_montar, "muted"))
            self.total_bar.set_segments(
                segmentos, total=total, formatter=render.size,
            )
            self.total_bar.show()
        else:
            self.total_bar.hide()

    def _apply_tiles(self, discos) -> None:
        # La suma de todas las unidades, no la del disco del sistema: en un
        # equipo con cinco discos, la cifra que interesa es cuánto se está
        # moviendo en total. Cuál se mueve va en la tabla de abajo.
        lectura = sum(x.io.read_rate_bps or 0 for x in discos) if discos else None
        escritura = sum(x.io.write_rate_bps or 0 for x in discos) if discos else None
        self.tile_read.update_value(render.rate(lectura), lectura)
        self.tile_write.update_value(render.rate(escritura), escritura)
        cuantos = _("storage.tile.sum.one" if len(discos) == 1
                    else "storage.tile.sum").format(n=len(discos))
        self.tile_read.set_detail(cuantos)
        self.tile_write.set_detail(cuantos)

        libres = [p.free_bytes for x in discos for p in x.mounted_partitions
                  if p.free_bytes is not None]
        self.tile_free.update_value(render.size(sum(libres)) if libres else render.DASH)
        if libres:
            self.tile_free.set_detail(
                _("storage.tile.inparts.one" if len(libres) == 1
                  else "storage.tile.inparts").format(n=len(libres)))

        temperaturas = [(x.temp_c, x) for x in discos if x.temp_c is not None]
        if temperaturas:
            # Por la clave, no por la tupla entera: con dos discos a la misma
            # temperatura Python pasa a comparar el segundo elemento, que es un
            # Disk, y un Disk no sabe si es mayor o menor que otro. Reventaba
            # solo cuando las cifras coincidían, que es cuando el equipo lleva
            # un rato encendido y todo se estabiliza.
            valor, disco = max(temperaturas, key=lambda par: par[0])
            mostrado = valor * 9 / 5 + 32 if self._prefs.fahrenheit else valor
            self.tile_temp.set_unit("°F" if self._prefs.fahrenheit else "°C")
            self.tile_temp.update_value(f"{mostrado:.0f}", mostrado)
            self.tile_temp.set_detail(disco.name)
        else:
            self.tile_temp.update_value(render.DASH)
            self.tile_temp.set_detail(_("storage.notemp"))

    def _apply_tables(self, discos) -> None:
        d = render.DASH
        self.disks.set_rows([
            (x.name,
             (x.model or d)[:30],
             x.kind or d,
             render.size(x.size_bytes),
             render.size(x.used_bytes) if x.used_bytes else d,
             render.temperature(x.temp_c, self._prefs.fahrenheit),
             render.rate(x.io.read_rate_bps),
             render.rate(x.io.write_rate_bps))
            for x in discos
        ] or [(_("storage.none"), d, d, d, d, d, d, d)])

        filas = [
            (p.name, p.filesystem or d, p.mountpoint or d,
             render.size(p.size_bytes),
             _("sys.value.pct").format(valor=render.size(p.used_bytes),
                                       pct=f"{p.used_percent:.0f}")
             if p.used_percent is not None else d,
             render.size(p.free_bytes))
            for x in discos for p in x.mounted_partitions
        ]
        self.parts.set_rows(filas or [("Ninguna montada", d, d, d, d, d)])

    def _apply_cards(self, discos) -> None:
        nombres = tuple(x.name for x in discos)
        if nombres != self._orden_actual:
            self._orden_actual = nombres
            clear_layout(self._cards_host)
            self._grids.clear()
            self._bars.clear()
            fila = ResponsiveRow(min_item_width=320)
            for disco in discos:
                card = Card(disco.name)
                barra = StackedBar(self._p)
                grid = InfoGrid()
                for campo in DISK_FIELDS:
                    grid.add(_(campo))
                card.body.addWidget(barra)
                card.body.addWidget(grid)
                fila.add(card)
                self._grids[disco.name] = grid
                self._bars[disco.name] = barra
            self._cards_host.addWidget(fila)

        for disco in discos:
            self._fill(disco)

    def _fill(self, disco: Disk) -> None:
        d = render.DASH
        grid = self._grids.get(disco.name)
        if grid is None:
            return

        barra = self._bars[disco.name]
        usado = disco.used_bytes
        if disco.size_bytes and usado:
            barra.set_segments(
                [(_("storage.col.used"), usado, "accent"),
                 (_("storage.col.free"), max(0, disco.size_bytes - usado), "line")],
                total=disco.size_bytes, formatter=render.size,
            )
            barra.show()
        else:
            barra.hide()

        f = grid.set
        f(_("storage.col.model"), disco.model or d)
        f(_("gpu.field.vendor"), disco.vendor or d)
        f(_("gpu.vram.type"), disco.kind or d,
          tooltip=_("storage.tip.kind"))
        f(_("storage.field.bus"), (disco.transport or d).upper() if disco.transport else d)
        f(_("storage.col.size"), render.size(disco.size_bytes))
        f(_("storage.field.firmware"), disco.firmware or d)
        f(_("storage.field.logical"), f"{disco.logical_sector} B" if disco.logical_sector else d)
        f(_("storage.field.physical"), f"{disco.physical_sector} B" if disco.physical_sector else d,
          tooltip=_("storage.tip.physical"))
        f(_("storage.field.scheduler"), disco.scheduler or d,
          tooltip=_("storage.tip.scheduler"))
        f(_("gpu.clock.link"), render.pcie_link(disco.link) if disco.link else d)
        f(_("gpu.sensor.temp"), render.temperature(disco.temp_c, self._prefs.fahrenheit))

        salud = disco.health
        f(_("storage.field.hours"), f"{salud.power_on_hours:n} h" if salud.power_on_hours else d)
        f(_("storage.field.written"), render.size(salud.written_bytes) if salud.written_bytes else d,
          tooltip=_("storage.tip.written"))
        f(_("storage.field.life"),
          f"{salud.life_left_percent} %" if salud.life_left_percent is not None else d,
          tooltip=_("storage.tip.life"))
