"""Página de almacenamiento: qué unidades hay y qué están haciendo.

El orden responde a las preguntas por frecuencia: primero cuánto espacio queda,
que es lo que trae aquí a casi todo el mundo; después qué unidades hay y de qué
tipo; y al final la ficha de cada una.

Las particiones van en su propia tabla y no dentro de cada disco. Un equipo con
cinco unidades y doce particiones se vuelve ilegible si cada una cuelga de su
disco, y la pregunta «dónde está montado /home» no se hace por disco.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ... import render, thermal
from ...i18n import _
from ...model import DISK_KINDS, Disk, Snapshot
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
    Series,
    StackedBar,
    StatTile,
    Table,
    boton_de_permiso_permanente,
    clear_layout,
    dismiss_buttons,
    paint_level,
)

DISK_HEADERS = ("storage.col.unit", "storage.col.model", "gpu.vram.type", "storage.col.size", "storage.col.used",
                "gpu.sensor.temp", "storage.tile.reading", "storage.tile.writing")
PART_HEADERS = ("storage.col.part", "storage.col.fs", "storage.col.mount", "storage.col.size2", "storage.col.used2", "storage.col.free")

# Dónde va la temperatura en la tabla de unidades (`DISK_HEADERS`).
COLUMNA_CAPACIDAD = 3
COLUMNA_OCUPADO = 4
COLUMNA_TEMPERATURA = 5

# Qué disco es y cómo está: lo que se mira. La salud va detrás de la
# identidad y no al final de catorce filas.
DISK_FIELDS = ("storage.col.model", "gpu.field.vendor", "gpu.vram.type", "storage.field.bus",
               "gpu.clock.link", "storage.col.size",
               "gpu.sensor.temp", "storage.field.templimits", "storage.field.hours",
               "storage.field.written", "storage.field.life")
# Cómo lo ve el kernel: se consulta una vez, si acaso. Va plegado.
DISK_DETAIL_FIELDS = ("storage.field.firmware", "storage.field.logical",
                      "storage.field.physical", "storage.field.scheduler",
                      "storage.field.trim")

# Los discos se ordenan por lo que le importa a quien mira: primero el que
# lleva el sistema, luego por tipo y al final los que se pueden desenchufar.
PRIORIDAD = {tipo: orden for orden, tipo in enumerate(DISK_KINDS)}


def _orden(disco: Disk) -> tuple:
    arranque = not any(p.mountpoint == "/" for p in disco.partitions)
    return (disco.removable, arranque, PRIORIDAD.get(disco.kind or "", 9), disco.name)


def _sum_known(rates) -> Optional[float]:
    """The sum of the rates measured, or None if none was: a disk with no
    rate yet is not «0 B/s»."""
    known = [r for r in rates if r is not None]
    return sum(known) if known else None


class StoragePage(ScrollPage):
    # El diagnóstico de los discos exige permisos, igual que el detalle de la
    # memoria. Sin un botón aquí, los campos aparecían vacíos y sin explicación
    # y no había forma de adivinar que la contraseña se pedía en otra pestaña.
    elevation_requested = Signal()
    permanent_requested = Signal()
    explain_requested = Signal()
    permission_snoozed = Signal()
    permission_dismissed = Signal()

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._candado = None
        # La última foto que ya pasó por las fichas (`record`).
        self._contada: Optional[Snapshot] = None
        self._first_reading = False
        self._details: dict = {}
        self._folds: dict = {}
        self._pies: dict = {}
        self._smart: dict = {}
        self._smart_signature: dict = {}
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
        self.module_notices = ModuleNotices(frozenset({"drivetemp"}))
        layout.addWidget(self.module_notices)

        disk_card = Card(_("storage.card.disks"))
        self.disks = Table([_(h) for h in DISK_HEADERS],
                           numeric=(False, False, False, True, True, True, True, True),
                           cede=(1,))      # el modelo, antes que cortar las cifras
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
        self._sin_avisos_de_permisos = False
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
        self.subtitle.setWordWrap(True)
        self.badges = ChipRow()
        self.total_bar = StackedBar(self._p)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        # Un hueco de verdad entre las insignias de tipo y la barra: en
        # compacto quedaban a cinco píxeles y, con la leyenda debajo, la barra
        # parecía una insignia más entre dos filas de insignias. Un widget y
        # no un `addSpacing`, que Qt comprime cuando falta alto.
        hueco = QWidget()
        hueco.setFixedHeight(4)
        card.body.addWidget(hueco)
        card.body.addWidget(self.total_bar)
        return card

    def _build_tiles(self) -> QWidget:
        fila = ResponsiveRow(min_item_width=150)
        self.tile_read = StatTile(_("storage.tile.reading"), "", self._p)
        self.tile_write = StatTile(_("storage.tile.writing"), "", self._p)
        self.tile_free = StatTile(_("storage.tile.free"), "", self._p)
        self.tile_temp = StatTile(_("storage.tile.hottest"), render.temperature_unit(), self._p)
        for tile in (self.tile_read, self.tile_write, self.tile_free, self.tile_temp):
            fila.add(tile)
        # Lo más ancho que puede escribir cada una: un ritmo hasta lo de un
        # NVMe de quinta generación, un espacio hasta petabytes y tres
        # cifras de grados (también en Fahrenheit).
        for tile in (self.tile_read, self.tile_write):
            tile.reserve(render.possible_texts(render.rate, 16e9))
        self.tile_free.reserve(render.possible_texts(render.decimal_size, 1000 ** 5))
        self.tile_temp.reserve([render.figure(999)])
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
        # «Qué hace esto», como en el aviso de Inicio: lo que pasa al dar
        # permisos y cómo darlos para siempre se cuenta en un sitio solo.
        self.explain_button = QPushButton(_("perm.notice.explain"))
        self.explain_button.setObjectName("GhostButton")
        self.explain_button.clicked.connect(self.explain_requested)

        # Los mismos dos botones que el aviso de Inicio, y hacen lo mismo.
        self.snooze_button, self.dismiss_button = dismiss_buttons()
        self.snooze_button.clicked.connect(self.permission_snoozed)
        self.dismiss_button.clicked.connect(self.permission_dismissed)

        fila = FoldingRow()
        fila.add_widget(self.elevation_button)
        fila.add_widget(self.explain_button)
        fila.add_stretch(1)
        fila.add_widget(self.snooze_button)
        fila.add_widget(self.dismiss_button)

        card.body.addWidget(self.elevation_text)
        card.body.addWidget(detalle)
        card.body.addWidget(fila)
        # El de sustituir un ayudante atrasado va en su renglón. Sale pocas
        # veces, y en la fila de los otros cuatro no cabe: en compacto a
        # 900 px la tarjeta se salía por la derecha y arrastraba la página.
        card.body.addWidget(self.permanent_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.elevation_card = card
        return card

    # -- actualización ------------------------------------------------------

    def hide_permission_notices(self, ocultos: bool) -> None:
        """Deja de enseñar la tarjeta que pide permisos, o la vuelve a enseñar."""
        self._sin_avisos_de_permisos = ocultos

    def apply(self, snapshot: Snapshot) -> None:
        discos = sorted(snapshot.disks, key=_orden)
        self._swaps = snapshot.system.swaps
        self._first_reading = snapshot.first_reading
        # El diagnóstico (SMART) lo guarda un permiso mientras exista esta
        # nota; de él salen las horas, lo escrito, la vida y, en un SATA sin
        # `drivetemp`, la temperatura.
        self._candado = snapshot.permission_note("disks.health")
        self._apply_header(discos)
        self.record(snapshot)
        self._apply_tables(discos)
        self._apply_cards(discos)
        self._apply_avisos(discos)
        self.module_notices.apply(snapshot.driver_hints)
        # La tarjeta solo estorba cuando ya no hace falta.
        # A virtual disk has no diagnosis to unlock.
        reales = [x for x in discos if x.kind != "Virtual"]
        leidos = sum(1 for x in reales if x.health.power_on_hours is not None)
        self.elevation_card.setVisible(bool(reales) and leidos < len(reales)
                                       and not self._sin_avisos_de_permisos)
        # En los dos sentidos: si el diagnóstico deja de estar (los permisos
        # eran de esta sesión y el ayudante se fue), la tarjeta vuelve a decir
        # lo del principio y no «leídos 2 de 5».
        outdated = snapshot.privileged.outdated
        self.elevation_text.setText(
            _("perm.outdated.body") if outdated
            else _("storage.health.read").format(n=leidos, total=len(reales)) if leidos
            else _("storage.health.body"))
        # Updating the helper is what brings it back: its button is the one left.
        self.elevation_button.setVisible(not outdated)

    def record(self, snapshot: Snapshot) -> None:
        """Las fichas de arriba, que guardan la historia de la lectura y la
        escritura: con la página cerrada, la ventana llama solo a esto, y las
        tarjetas y tablas de cada disco se ponen al día al abrirla. Una vez
        por foto, o la gráfica tendría el mismo punto dos veces."""
        if snapshot is self._contada:
            return
        self._contada = snapshot
        self._first_reading = snapshot.first_reading
        self._apply_tiles(sorted(snapshot.disks, key=_orden))

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
        if not discos:
            self.title.setText(_("storage.none"))
            self.subtitle.setText("")
            self.total_bar.hide()
            return

        total = sum(x.size_bytes or 0 for x in discos)
        usado = sum(x.used_bytes or 0 for x in discos)
        self.title.setText(_("storage.title.one" if len(discos) == 1
                             else "storage.title").format(
            tam=render.decimal_size(total), n=len(discos)))
        self.title.setToolTip(render.size(total))
        montadas = sum(len(x.mounted_partitions) for x in discos)
        self.subtitle.setText(
            _("storage.subtitle.one" if montadas == 1
              else "storage.subtitle").format(tam=render.decimal_size(usado), n=montadas)
        )
        self.subtitle.setToolTip(render.size(usado))

        chips = []
        chips.extend(render.disk_kinds(discos))
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
            self.total_bar.set_segments(
                self._segmentos(discos), total=total, formatter=render.decimal_size,
                hover=render.size)
            self.total_bar.show()
        else:
            self.total_bar.hide()

    def _segmentos(self, discos) -> list:
        usado, libre, reservado, swap, sin_montar = render.space(
            discos, getattr(self, "_swaps", ()))
        segmentos = [render.Segment("used", _("storage.col.used"), usado, "accent"),
                     render.Segment("free", _("storage.col.free"), libre, "line")]
        if reservado:
            segmentos.append(render.Segment("reserved", _("storage.bar.reserved"), reservado,
                                            "muted/0.45", _("storage.bar.reserved.tip")))
        if swap:
            segmentos.append(render.Segment("swap", _("storage.bar.swap"), swap,
                                            "accent/0.45", _("storage.bar.swap.tip")))
        if sin_montar:
            segmentos.append(render.Segment("unmounted", _("storage.bar.unmounted"),
                                            sin_montar, "muted"))
        return segmentos

    def _apply_tiles(self, discos) -> None:
        # La suma de todas las unidades, no la del disco del sistema: en un
        # equipo con cinco discos, la cifra que interesa es cuánto se está
        # moviendo en total. Cuál se mueve va en la tabla de abajo.
        lectura = _sum_known(x.io.read_rate_bps for x in discos)
        escritura = _sum_known(x.io.write_rate_bps for x in discos)
        primera = self._first_reading
        self.tile_read.update_value(render.first_or(lectura, render.rate(lectura), primera),
                                    lectura, word=lectura is None and primera,
                                    series=Series("disks/read", "B/s"))
        self.tile_write.update_value(render.first_or(escritura, render.rate(escritura), primera),
                                     escritura, word=escritura is None and primera,
                                     series=Series("disks/write", "B/s"))
        cuantos = _("storage.tile.sum.one" if len(discos) == 1
                    else "storage.tile.sum").format(n=len(discos))
        self.tile_read.set_detail(cuantos)
        self.tile_write.set_detail(cuantos)

        libres = [p.free_bytes for x in discos for p in x.mounted_partitions
                  if p.free_bytes is not None]
        self.tile_free.update_value(render.decimal_size(sum(libres)) if libres else render.DASH)
        self.tile_free.setToolTip(render.size(sum(libres)) if libres else "")
        # Also cleared: with the last mounted partition gone, its count stayed.
        self.tile_free.set_detail(
            _("storage.tile.inparts.one" if len(libres) == 1
              else "storage.tile.inparts").format(n=len(libres)) if libres else "")

        temperaturas = [(x.temp_c, x) for x in discos if x.temp_c is not None]
        # The unit with or without a figure: it kept «°C» in °F when no disk
        # gave its temperature.
        self.tile_temp.set_unit(render.temperature_unit(self._prefs.fahrenheit))
        if temperaturas:
            # Por la clave, no por la tupla entera: con dos discos a la misma
            # temperatura Python pasa a comparar el segundo elemento, que es un
            # Disk, y un Disk no sabe si es mayor o menor que otro. Reventaba
            # solo cuando las cifras coincidían, que es cuando el equipo lleva
            # un rato encendido y todo se estabiliza.
            valor, disco = max(temperaturas, key=lambda par: par[0])
            mostrado = render.in_temperature_unit(valor, self._prefs.fahrenheit)
            unidad = render.temperature_unit(self._prefs.fahrenheit)
            # The hottest disk's: when another one is, the chart starts over.
            self.tile_temp.update_value(render.figure(mostrado), mostrado,
                                        series=Series(f"disk:{disco.name}/temp", unidad))
            self.tile_temp.set_detail(disco.name)
            paint_level(self.tile_temp.value, disco.temp_level)
        else:
            self.tile_temp.update_value(render.DASH)
            self.tile_temp.set_detail(_("storage.notemp"))
            paint_level(self.tile_temp.value, thermal.OK)

    def _apply_tables(self, discos) -> None:
        d = render.DASH
        self.disks.set_rows([
            (x.name,
             (x.model or d)[:30],
             render.disk_kind(x.kind),
             render.decimal_size(x.size_bytes),
             render.decimal_size(x.used_bytes) if x.used_bytes else d,
             render.temperature(x.temp_c, self._prefs.fahrenheit),
             render.first_or(x.io.read_rate_bps, render.rate(x.io.read_rate_bps),
                             self._first_reading),
             render.first_or(x.io.write_rate_bps, render.rate(x.io.write_rate_bps),
                             self._first_reading))
            for x in discos
        ] or [(_("storage.none"), d, d, d, d, d, d, d)])
        for fila, x in enumerate(discos):
            self.disks.set_cell_tooltip(fila, COLUMNA_TEMPERATURA,
                                        self._por_que_sin_temperatura(x))
            self.disks.set_cell_level(fila, COLUMNA_TEMPERATURA, x.temp_level)
            # The binary figures on hover, as the capacity in a disk's card.
            self.disks.set_cell_tooltip(fila, COLUMNA_CAPACIDAD, render.size(x.size_bytes))
            self.disks.set_cell_tooltip(fila, COLUMNA_OCUPADO,
                                        render.size(x.used_bytes) if x.used_bytes else "")

        filas = [
            (p.name, p.filesystem or d, p.mountpoint or d,
             render.decimal_size(p.size_bytes),
             _("sys.value.pct").format(valor=render.decimal_size(p.used_bytes),
                                       pct=f"{p.used_percent:.0f}")
             if p.used_percent is not None else d,
             render.decimal_size(p.free_bytes))
            for x in discos for p in x.mounted_partitions
        ]
        self.parts.set_rows(filas or [(_("storage.nomounted"), d, d, d, d, d)])
        montadas = [p for x in discos for p in x.mounted_partitions]
        for fila, p in enumerate(montadas):
            for columna, valor in ((3, p.size_bytes), (4, p.used_bytes), (5, p.free_bytes)):
                self.parts.set_cell_tooltip(fila, columna, render.size(valor) if valor else "")

    def _apply_cards(self, discos) -> None:
        nombres = tuple(x.name for x in discos)
        if nombres != self._orden_actual:
            self._orden_actual = nombres
            clear_layout(self._cards_host)
            self._grids.clear()
            self._details.clear()
            self._folds.clear()
            self._bars.clear()
            fila = ResponsiveRow(min_item_width=360)
            for disco in discos:
                card = Card(disco.name)
                barra = StackedBar(self._p)
                grid = InfoGrid()
                for campo in DISK_FIELDS:
                    grid.add(_(campo))
                card.body.addWidget(barra)
                card.body.addWidget(grid)
                grid.locked_clicked.connect(self.elevation_requested)
                # Lo que este disco no tiene, dicho en vez de un guion.
                pie = QLabel("")
                pie.setObjectName("Muted")
                pie.setWordWrap(True)
                pie.setFont(ui_font(theme.METRICS.small_pt))
                pie.hide()
                card.body.addWidget(pie)
                self._pies[disco.name] = pie
                pliegue = Plegable(_("storage.card.details"))
                detalle = InfoGrid()
                for campo in DISK_DETAIL_FIELDS:
                    detalle.add(_(campo))
                pliegue.body.addWidget(detalle)
                card.body.addWidget(pliegue)
                self._details[disco.name] = detalle
                self._folds[disco.name] = pliegue
                # El diagnóstico entero, cuando se ha leído. Nace escondido:
                # sin permisos no hay nada que plegar.
                completo = Plegable(_("storage.card.smart"))
                completo.body.addWidget(InfoGrid())
                completo.hide()
                card.body.addWidget(completo)
                self._smart[disco.name] = completo
                self._smart_signature[disco.name] = ()
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
            # The same split as the bar above: the rest of the disk was all
            # «Libre» here, and above it was not.
            barra.set_segments(self._segmentos([disco]), total=disco.size_bytes,
                               formatter=render.decimal_size, hover=render.size)
            barra.show()
        else:
            barra.hide()

        f = grid.set
        f(_("storage.col.model"), disco.model or d)
        f(_("gpu.field.vendor"), disco.vendor or d)
        grid.set_visible(_("gpu.field.vendor"), bool(disco.vendor))
        f(_("gpu.vram.type"), render.disk_kind(disco.kind),
          tooltip=_("storage.tip.kind"))
        # Over USB a fixed disk's kind can't be known: hidden, and said below.
        kind_unknown = disco.kind is None and disco.transport == "usb"
        grid.set_visible(_("gpu.vram.type"), not kind_unknown)
        f(_("storage.field.bus"), render.disk_bus(disco.transport))
        f(_("storage.col.size"), render.decimal_size(disco.size_bytes),
          tooltip=render.size(disco.size_bytes))
        # El enlace PCIe es del NVMe. Un SATA no tiene uno propio —negocia su
        # controladora, que comparte con los demás—, así que ahí la fila no
        # es un dato que falte: no existe, y no sale.
        f(_("gpu.clock.link"), render.pcie_link(disco.link) if disco.link else d)
        grid.set_visible(_("gpu.clock.link"), bool(disco.link))
        t = self._details[disco.name].set
        t(_("storage.field.firmware"), disco.firmware or d)
        t(_("storage.field.logical"), f"{disco.logical_sector} B" if disco.logical_sector else d)
        t(_("storage.field.physical"), f"{disco.physical_sector} B" if disco.physical_sector else d,
          tooltip=_("storage.tip.physical"))
        t(_("storage.field.scheduler"), disco.scheduler or d,
          tooltip=_("storage.tip.scheduler"))
        descartes = render.trim(disco)
        t(_("storage.field.trim"), descartes or d, tooltip=_("storage.tip.trim"))
        self._details[disco.name].set_visible(_("storage.field.trim"), bool(descartes))
        self._fill_smart(disco)
        # Cada campo lleva su dato o su candado, no los dos en la misma
        # muestra: quitarlo y volverlo a poner recolocaba la página entera
        # cada segundo.
        bloqueados = self._candados_de(disco)

        def g(clave: str, valor: str, tooltip: Optional[str] = None) -> None:
            if clave in bloqueados:
                grid.set_locked(_(clave), self._p.info, render.lock_tooltip(self._candado))
            else:
                grid.set(_(clave), valor, tooltip=tooltip)

        g("gpu.sensor.temp", render.temperature(disco.temp_c, self._prefs.fahrenheit),
          tooltip=self._por_que_sin_temperatura(disco))
        paint_level(grid.value_label(_("gpu.sensor.temp")), disco.temp_level)
        limits = render.temperature_limits(disco.temp_high_c, disco.temp_critical_c,
                                           self._prefs.fahrenheit)
        grid.set(_("storage.field.templimits"), limits or d,
                 tooltip=_("storage.tip.templimits"))
        grid.set_visible(_("storage.field.templimits"), bool(limits))

        salud = disco.health
        g("storage.field.hours", f"{render.thousands(salud.power_on_hours)} h" if salud.power_on_hours else d)
        g("storage.field.written",
          render.decimal_size(salud.written_bytes) if salud.written_bytes else d,
          tooltip=_("storage.tip.written"))
        g("storage.field.life",
          f"{salud.life_left_percent} %" if salud.life_left_percent is not None else d,
          tooltip=_("storage.tip.life"))
        # La vida restante es el desgaste de las celdas de un SSD. Un disco
        # de platos no lleva esa cuenta: ni guion ni candado, no existe.
        de_platos = disco.kind == "HDD"
        # A virtual disk has no diagnosis, temperature or wear: what QEMU
        # answers is made up.
        virtual = disco.kind == "Virtual"
        grid.set_visible(_("storage.field.life"), not (de_platos or virtual))
        # A counter in a unit nobody knows is not shown: it said less was
        # written than the disk holds.
        sin_unidad = salud.counters_unit_unknown
        # With its SMART read and no such counter, the disk does not keep it:
        # rule 5, hidden and named below instead of a dash.
        no_lo_cuenta = (salud.power_on_hours is not None and salud.written_bytes is None
                        and not sin_unidad)
        # A flash drive over USB answered no diagnosis with the permissions
        # given: it keeps none, so its rows aren't dashes but absent.
        flash_sin_smart = (disco.kind == "Flash" and not bloqueados
                           and salud.power_on_hours is None and disco.temp_c is None)
        grid.set_visible(_("storage.field.written"),
                         not (sin_unidad or virtual or no_lo_cuenta or flash_sin_smart))
        for clave in ("gpu.sensor.temp", "storage.field.hours"):
            grid.set_visible(_(clave), not (virtual or flash_sin_smart))
        if flash_sin_smart:
            grid.set_visible(_("storage.field.life"), False)
        if (pie := self._pies.get(disco.name)) is not None:
            texto = " ".join(t for t in (
                _("storage.na.vendor") if not disco.vendor and not virtual else "",
                _("storage.na.hdd.life") if de_platos else "",
                _("storage.na.virtual") if virtual else "",
                _("storage.na.flash") if flash_sin_smart else "",
                _("storage.na.kind.usb") if disco.kind is None and disco.transport == "usb" else "",
                _("storage.na.written.unit") if sin_unidad else "",
                _("storage.na.written") if no_lo_cuenta and not virtual else "") if t)
            pie.setText(texto)
            pie.setVisible(bool(texto))

    def _fill_smart(self, disco: Disk) -> None:
        """La tabla entera del diagnóstico, plegada, cuando hay permisos."""
        pliegue = self._smart.get(disco.name)
        if pliegue is None:
            return
        filas = tuple(render.smart_rows(disco.health)) \
            if disco.health.power_on_hours is not None else ()
        pliegue.setVisible(bool(filas))
        nombres = tuple(n for n, _v in filas)
        vieja = pliegue.body.itemAt(0).widget()
        if nombres != self._smart_signature.get(disco.name):
            self._smart_signature[disco.name] = nombres
            nueva = InfoGrid()
            for nombre, valor in filas:
                nueva.add(nombre)
                nueva.set(nombre, valor)
            pliegue.body.replaceWidget(vieja, nueva)
            vieja.setParent(None)
            vieja.deleteLater()
        else:
            for nombre, valor in filas:
                vieja.set(nombre, valor)

    def _por_que_sin_temperatura(self, disco: Disk) -> str:
        """Lo que explica el guion de un disco que no da su temperatura, o
        que la que da no lleva color: no declara límites."""
        if disco.temp_c is not None:
            return ("" if disco.temp_high_c is not None or disco.temp_critical_c is not None
                    else _("storage.tip.nolimits"))
        return _("storage.tip.notemp.nvme" if disco.kind == "NVMe" else "storage.tip.notemp")

    def _candados_de(self, disco: Disk) -> set[str]:
        """Los campos que llevan candado, y no guion: lo que el diagnóstico
        daría con permisos.

        Mientras no se haya leído el de este disco: después, lo que siga
        faltando es que el disco no lo cuenta, y se esconde y se dice al pie.
        """
        if self._candado is None or disco.health.power_on_hours is not None:
            return set()
        salud = disco.health
        faltan = {
            "gpu.sensor.temp": disco.temp_c is None,
            "storage.field.hours": True,
            "storage.field.written": not salud.written_bytes,
            # The kind, not `rotational`: the kernel sets it on almost
            # anything over USB.
            "storage.field.life": salud.life_left_percent is None
            and disco.kind != "HDD",
        }
        return {clave for clave, falta in faltan.items() if falta}
