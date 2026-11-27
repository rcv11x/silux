"""Página de almacenamiento: qué unidades hay y qué están haciendo.

El orden responde a las preguntas por frecuencia: primero cuánto espacio queda,
que es lo que trae aquí a casi todo el mundo; después qué unidades hay y de qué
tipo; y al final la ficha de cada una.

Las particiones van en su propia tabla y no dentro de cada disco. Un equipo con
cinco unidades y doce particiones se vuelve ilegible si cada una cuelga de su
disco, y la pregunta «dónde está montado /home» no se hace por disco.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ... import disk_health, render, thermal
from ...i18n import _
from ...model import DISK_KINDS, Disk, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Button,
    Card,
    ChipRow,
    ElidingComboBox,
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
    let_go,
    paint_level,
    unbroken,
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
DISK_FIELDS = ("storage.col.model", "gpu.field.vendor", "gpu.vram.type", "storage.field.rpm",
               "storage.field.bus", "storage.field.bridge", "gpu.clock.link", "storage.col.size",
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


# The tiles' choice of every drive.
ALL_DISKS = ""


def disk_choice_key(disk: Disk, disks) -> str:
    """How a disk chosen for the tiles is found again: its model and size,
    since `sda` changes between boots and plugs; its name only between two
    alike. Its serial number isn't read."""
    base = f"{disk.model or ''}|{disk.size_bytes or 0}"
    twins = sum(1 for other in disks if f"{other.model or ''}|{other.size_bytes or 0}" == base)
    return f"{base}|{disk.name}" if twins > 1 else base


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
    # A disk's last test asked to be opened in Performance: its name.
    disk_test_requested = Signal(str)
    # The drive the tiles show was chosen: its key, ALL_DISKS for all.
    disk_chosen = Signal(str)

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
        # Each disk's line of its last disk test, and the tests to say.
        self._tests: dict = {}
        self._disk_tests: tuple = ()
        self._models: dict = {}
        # Each disk card's health: its level and why.
        self._health: dict = {}
        self._prefs = prefs
        # The drive the tiles show (its `disk_choice_key`), and each drive's
        # history since Silux opened, by name: what its tiles' charts are
        # drawn again from when it is chosen.
        self._chosen = prefs.storage_disk
        self._histories: dict[str, dict[str, deque]] = {}
        self._choices: tuple = ()
        self._discos: list = []
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
                           cede=(1,),      # el modelo, antes que cortar las cifras
                           pick_rows=True)
        self.disks.row_picked.connect(self._on_row_picked)
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
        hueco.setFixedHeight(theme.METRICS.card_gap // 2)
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
        # Which drive the tiles show, every one or one: a single list above
        # them, for all of them.
        self.choice_box = box = ElidingComboBox(widest=40)
        box.setToolTip(_("storage.disks.tip"))
        box.activated.connect(self._on_choice_box)
        caption = QLabel(_("storage.disks.label"))
        caption.setObjectName("Muted")
        caption.setFont(ui_font(theme.METRICS.base_pt))
        choice = QHBoxLayout()
        choice.setSpacing(8)
        choice.addWidget(caption)
        choice.addWidget(box)
        choice.addStretch(1)
        self.choice_row = choice
        # Said once when the drive chosen goes.
        self.chosen_gone = QLabel("")
        self.chosen_gone.setObjectName("Muted")
        self.chosen_gone.setWordWrap(True)
        self.chosen_gone.hide()
        column = QWidget()
        inside = QVBoxLayout(column)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.addLayout(self.choice_row)
        inside.addWidget(fila)
        inside.addWidget(self.chosen_gone)
        return column

    def _build_elevation(self) -> Card:
        """La tarjeta que explica qué falta y por qué, con su botón."""
        card = Card(_("storage.card.health"))
        self.elevation_text = QLabel(
            _("storage.health.body")
        )
        self.elevation_text.setObjectName("NoticeBody")
        self.elevation_text.setWordWrap(True)

        self.elevation_hint = detalle = QLabel(
            _("storage.health.hint")
        )
        detalle.setObjectName("Muted")
        detalle.setWordWrap(True)

        self.elevation_button = Button(_("perm.read.button"))
        self.elevation_button.clicked.connect(self.elevation_requested)
        self.permanent_button = boton_de_permiso_permanente()
        self.permanent_button.clicked.connect(self.permanent_requested)
        # «Qué hace esto», como en el aviso de Inicio: lo que pasa al dar
        # permisos y cómo darlos para siempre se cuenta en un sitio solo.
        self.explain_button = Button(_("perm.notice.explain"))
        self.explain_button.setObjectName("GhostButton")
        self.explain_button.clicked.connect(self.explain_requested)

        # Los mismos dos botones que el aviso de Inicio, y hacen lo mismo.
        self.snooze_button, self.dismiss_button = dismiss_buttons()
        self.snooze_button.clicked.connect(self.permission_snoozed)
        self.dismiss_button.clicked.connect(self.permission_dismissed)

        fila = FoldingRow()
        # First, where the one that gives permissions goes: with the helper
        # out of date it's the only thing to do, as in Home's notice.
        fila.add_widget(self.permanent_button)
        fila.add_widget(self.elevation_button)
        fila.add_widget(self.explain_button)
        fila.add_stretch(1)
        fila.add_widget(self.snooze_button)
        fila.add_widget(self.dismiss_button)

        card.body.addWidget(self.elevation_text)
        card.body.addWidget(detalle)
        card.body.addWidget(fila)
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
        # Updating the helper is what brings it back: its button is the one
        # left, with «Not now», as in Home's notice.
        self.elevation_button.setVisible(not outdated)
        self.elevation_hint.setVisible(not outdated)
        self.explain_button.setVisible(not outdated)
        self.dismiss_button.setVisible(not outdated)

    def record(self, snapshot: Snapshot) -> None:
        """Las fichas de arriba, que guardan la historia de la lectura y la
        escritura: con la página cerrada, la ventana llama solo a esto, y las
        tarjetas y tablas de cada disco se ponen al día al abrirla. Una vez
        por foto, o la gráfica tendría el mismo punto dos veces."""
        if snapshot is self._contada:
            return
        self._contada = snapshot
        self._first_reading = snapshot.first_reading
        discos = sorted(snapshot.disks, key=_orden)
        self._remember(discos)
        self._fill_choices(discos)
        self._apply_tiles(discos)

    # -- one drive at a time ---------------------------------------------------

    def _history(self, name: str) -> dict[str, deque]:
        capacity = self.tile_read.chart.capacity
        return self._histories.setdefault(
            name, {kind: deque(maxlen=capacity) for kind in ("read", "write", "temp")})

    def _remember(self, discos) -> None:
        """Each drive's reading, writing and temperature, and every drive's
        sum, kept for its charts whether or not it is the one shown."""
        for disco in discos:
            history = self._history(disco.name)
            history["read"].append(disco.io.read_rate_bps)
            history["write"].append(disco.io.write_rate_bps)
            history["temp"].append(disco.temp_c)
        every = self._history(ALL_DISKS)
        every["read"].append(_sum_known(x.io.read_rate_bps for x in discos))
        every["write"].append(_sum_known(x.io.write_rate_bps for x in discos))
        present = {x.name for x in discos} | {ALL_DISKS}
        for name in [n for n in self._histories if n not in present]:
            del self._histories[name]

    def _chosen_disk(self, discos) -> Optional[Disk]:
        if self._chosen == ALL_DISKS:
            return None
        return next((x for x in discos if disk_choice_key(x, discos) == self._chosen), None)

    def _fill_choices(self, discos) -> None:
        """The choice boxes: rebuilt only when the drives change."""
        choices = tuple((disk_choice_key(x, discos), render.disk_label(x)) for x in discos)
        if choices != self._choices:
            self._choices = choices
            box = self.choice_box
            box.blockSignals(True)
            box.clear()
            box.addItem(_("storage.disks.all"), ALL_DISKS)
            for key, label in choices:
                box.addItem(label, key)
            box.blockSignals(False)
            box.updateGeometry()
        chosen = self._chosen_disk(discos)
        if self._chosen != ALL_DISKS and chosen is None:
            # Gone while shown: back to every drive, said once. Not there
            # when Silux opened: every drive, without a word.
            if any(key == self._chosen for key, _label in getattr(self, "_seen", ())):
                gone = next(label for key, label in self._seen if key == self._chosen)
                self.chosen_gone.setText(_("storage.disks.gone").format(disk=gone))
                self.chosen_gone.show()
            self._chosen = ALL_DISKS
            self._replay(discos)
        self._seen = choices
        box = self.choice_box
        index = box.findData(self._chosen)
        if index >= 0 and box.currentIndex() != index:
            box.blockSignals(True)
            box.setCurrentIndex(index)
            box.blockSignals(False)

    def _on_choice_box(self, index: int) -> None:
        box = self.sender()
        self.choose(box.itemData(index) if box is not None else ALL_DISKS)

    def _on_row_picked(self, row: int) -> None:
        if 0 <= row < len(self._discos):
            key = disk_choice_key(self._discos[row], self._discos)
            # The row already chosen, pressed again: every drive.
            self.choose(ALL_DISKS if key == self._chosen else key)

    def choose(self, key: str) -> None:
        """Show `key`'s drive in the tiles, ALL_DISKS for every one, with its
        history since Silux opened; remembered by the window."""
        if key == self._chosen:
            return
        self._chosen = key
        self.chosen_gone.hide()
        discos = self._discos
        self._fill_choices(discos)
        self._replay(discos)
        self._apply_tiles(discos, push=False)
        self._mark_row(discos)
        self.disk_chosen.emit(key)

    def _replay(self, discos) -> None:
        """The tiles' charts drawn again from the history of what they show
        now: a chart draws one series, and another starts from its own."""
        chosen = self._chosen_disk(discos)
        name = chosen.name if chosen is not None else ALL_DISKS
        history = self._history(name)
        prefix = f"disk:{name}" if chosen is not None else "disks"
        self.tile_read.chart.replay(Series(f"{prefix}/read", "B/s"), history["read"])
        self.tile_write.chart.replay(Series(f"{prefix}/write", "B/s"), history["write"])
        if chosen is not None:
            unit = render.temperature_unit(self._prefs.fahrenheit)
            self.tile_temp.chart.replay(
                Series(f"disk:{name}/temp", unit),
                [render.in_temperature_unit(v, self._prefs.fahrenheit) if v is not None else None
                 for v in history["temp"]])

    def _mark_row(self, discos) -> None:
        chosen = self._chosen_disk(discos)
        self.disks.set_picked(discos.index(chosen) if chosen is not None else None)

    def _apply_avisos(self, discos) -> None:
        """Above the tables, which drives need attention and how much: why,
        and what to do, go in each drive's card, once."""
        locked = self._candado is not None
        verdicts = [(disco, disk_health.verdict(disco.health, locked=locked)) for disco in discos]
        flagged = [(disco, verdict.level) for disco, verdict in verdicts
                   if verdict.level in (disk_health.BACKUP, disk_health.WATCH)]
        firma = tuple((d.name, d.model, level) for d, level in flagged)
        if firma == self._avisos_signature:
            return
        self._avisos_signature = firma

        clear_layout(self._avisos_host)
        if not flagged:
            return
        self._avisos_host.addWidget(Notice(
            render.counted("storage.health.attention", len(flagged)),
            "\n".join(f"{render.disk_label(d)}: {render.disk_health_level(level)}"
                      for d, level in flagged),
            hint=_("storage.health.attention.hint"),
            tone="bad" if any(level == disk_health.BACKUP for _d, level in flagged) else "warn",
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

    def _apply_tiles(self, discos, push: bool = True) -> None:
        """`push`: the figures are a new sample for the charts; not when the
        drive shown changed and its charts were drawn from its history."""
        self._discos = list(discos)
        chosen = self._chosen_disk(discos)
        primera = self._first_reading
        if chosen is not None:
            lectura, escritura = chosen.io.read_rate_bps, chosen.io.write_rate_bps
            prefix = f"disk:{chosen.name}"
            # Its box already names it.
            cuantos = ""
        else:
            # La suma de todas las unidades, no la del disco del sistema: en
            # un equipo con cinco discos, la cifra que interesa es cuánto se
            # está moviendo en total. Cuál se mueve va en la tabla de abajo.
            lectura = _sum_known(x.io.read_rate_bps for x in discos)
            escritura = _sum_known(x.io.write_rate_bps for x in discos)
            prefix = "disks"
            cuantos = _("storage.tile.sum.one" if len(discos) == 1
                        else "storage.tile.sum").format(n=len(discos))
        self.tile_read.update_value(render.first_or(lectura, render.rate(lectura), primera),
                                    lectura if push else None,
                                    word=lectura is None and primera,
                                    series=Series(f"{prefix}/read", "B/s"))
        self.tile_write.update_value(render.first_or(escritura, render.rate(escritura), primera),
                                     escritura if push else None,
                                     word=escritura is None and primera,
                                     series=Series(f"{prefix}/write", "B/s"))
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

        # The hottest drive's, or the one chosen's.
        temperaturas = [(x.temp_c, x) for x in ([chosen] if chosen is not None else discos)
                        if x.temp_c is not None]
        self.tile_temp.set_label(_("storage.tile.temperature") if chosen is not None
                                 else _("storage.tile.hottest"))
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
            self.tile_temp.update_value(render.figure(mostrado), mostrado if push else None,
                                        series=Series(f"disk:{disco.name}/temp", unidad))
            self.tile_temp.set_detail(disco.name)
            paint_level(self.tile_temp.value, disco.temp_level)
        else:
            self.tile_temp.update_value(render.DASH)
            self.tile_temp.set_detail(_("storage.notemp"))
            paint_level(self.tile_temp.value, thermal.OK)

    def _apply_tables(self, discos) -> None:
        d = render.DASH
        self._discos = list(discos)
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
        self._mark_row(discos)
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
            self._health.clear()
            for disco in discos:
                card = Card(render.disk_label(disco))
                # Its health at a glance, first: a level and why.
                level = QLabel("")
                level.setFont(ui_font(theme.METRICS.base_pt, QFont.Weight.DemiBold))
                why = QLabel("")
                why.setObjectName("Muted")
                why.setWordWrap(True)
                why.setFont(ui_font(theme.METRICS.small_pt))
                card.body.addWidget(level)
                card.body.addWidget(why)
                self._health[disco.name] = (level, why)
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
                card.body.addWidget(self._last_test_line(disco.name))
                fila.add(card)
                self._grids[disco.name] = grid
                self._bars[disco.name] = barra
            self._cards_host.addWidget(fila)

        for disco in discos:
            self._fill(disco)
            self._paint_health(disco)
        self._paint_disk_tests(discos)

    # A level's colour: the palette's own for fine, watch and back it up.
    HEALTH_COLOURS = {disk_health.FINE: "ok", disk_health.WATCH: "warn",
                      disk_health.BACKUP: "crit"}

    def _paint_health(self, disco: Disk) -> None:
        """The disk's health, from what it or the specification declares,
        never a threshold of ours (`disk_health`)."""
        widgets = self._health.get(disco.name)
        if widgets is None:
            return
        level, why = widgets
        locked = self._candado is not None and disco.kind != "Virtual"
        verdict = disk_health.verdict(disco.health, locked=locked)
        text = f"● {render.disk_health_level(verdict.level)}"
        if level.text() != text:
            level.setText(text)
        colour = self.HEALTH_COLOURS.get(verdict.level, "muted")
        level.setStyleSheet(f"color: {getattr(self._p, colour)};")
        sentence = render.disk_health_text(verdict, virtual=disco.kind == "Virtual")
        if why.text() != sentence:
            why.setText(sentence)

    def _last_test_line(self, name: str) -> QWidget:
        """A disk's last disk test, in short, and the way to its tab."""
        line = QWidget()
        row = QHBoxLayout(line)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        summary = QLabel("")
        summary.setObjectName("Muted")
        summary.setWordWrap(True)
        summary.setFont(ui_font(theme.METRICS.small_pt))
        link = Button(_("memory.lasttest.open"))
        link.setObjectName("TextButton")
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.clicked.connect(lambda: self.disk_test_requested.emit(name))
        row.addWidget(summary, 1)
        row.addWidget(link, 0, Qt.AlignmentFlag.AlignTop)
        line.hide()
        self._tests[name] = (line, summary)
        return line

    def set_disk_tests(self, results) -> None:
        """The disk tests saved, newest first: each disk says its last."""
        self._disk_tests = tuple(results or ())
        self._paint_disk_tests()

    def _paint_disk_tests(self, discos=None) -> None:
        from ... import disktest
        from .disktest import PROFILE_NAMES

        models = {d.name: d.model for d in (discos or ())} or self._models
        self._models = models
        for name, (line, summary) in self._tests.items():
            last = next((r for r in self._disk_tests
                         if r.is_of((name,), models.get(name))), None)
            line.setVisible(last is not None)
            if last is None:
                continue
            figures = []
            for direction, key in (("read", "storage.lasttest.read"),
                                   ("write", "storage.lasttest.write")):
                measure = last.measure(disktest.headline_test(last.profile), direction)
                middle = measure.median if measure is not None else None
                if middle is not None:
                    figures.append(_(key).format(
                        rate=unbroken(render.disk_rate(middle.bytes_per_second))))
            # Another profile's figures aren't the standard's: it is named.
            summary.setText(_("storage.lasttest" if last.profile == "standard"
                              else "storage.lasttest.profile").format(
                figures=" · ".join(figures) or render.DASH, profile=_(PROFILE_NAMES.get(
                    last.profile, "disktest.profile.standard")).lower(),
                when=time.strftime("%d/%m/%Y %H:%M", time.localtime(last.timestamp))))

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
        # What the disk said of itself behind a USB bridge: how fast it spins
        # (a disk that doesn't spin has no row), and the bridge apart.
        spins = bool(disco.rotation_rpm)
        f(_("storage.field.rpm"), render.rpm(disco.rotation_rpm) if spins else d)
        grid.set_visible(_("storage.field.rpm"), spins)
        f(_("storage.field.bus"), render.disk_bus(disco.transport))
        f(_("storage.field.bridge"), render.maker(disco.usb_bridge) if disco.usb_bridge else d)
        grid.set_visible(_("storage.field.bridge"), bool(disco.usb_bridge))
        f(_("storage.col.size"), render.decimal_size(disco.size_bytes),
          tooltip=render.size(disco.size_bytes))
        # The link the disk runs over: an NVMe's PCIe one, a SATA port's own,
        # or the USB port's of a bridge. Without one (eMMC, a virtual disk)
        # the row doesn't exist, and doesn't show.
        link = render.disk_link(disco)
        note = render.disk_link_note(disco)
        if note and disco.sata_max_gbps:
            link += " · " + _("storage.sata.supports").format(max=f"{disco.sata_max_gbps:g} Gb/s")
        f(_("gpu.clock.link"), link, tooltip=note)
        grid.set_visible(_("gpu.clock.link"), link != d)
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
        # An SSD whose SMART was read and gives no wear the way the standard
        # counts it (a KIOXIA's 173 at 141 % says nothing): said, not a dash.
        sin_vida = (salud.power_on_hours is not None and salud.life_left_percent is None
                    and not (de_platos or virtual or flash_sin_smart))
        if flash_sin_smart or sin_vida:
            grid.set_visible(_("storage.field.life"), False)
        if (pie := self._pies.get(disco.name)) is not None:
            texto = " ".join(t for t in (
                _("storage.na.vendor") if not disco.vendor and not virtual else "",
                _("storage.na.hdd.life") if de_platos else "",
                _("storage.na.life") if sin_vida else "",
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
        filas = tuple(render.smart_rows(disco.health, self._prefs.fahrenheit)) \
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
            let_go(vieja)
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
