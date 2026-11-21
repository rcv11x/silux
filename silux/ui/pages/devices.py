"""Dispositivos: lo que hay enchufado al equipo.

USB, sonido, cámaras y el adaptador Bluetooth. No es hardware del equipo
sino de alrededor, y por eso no va en Placa base.

El USB es un árbol: cada cosa cuelga del concentrador al que está enchufada,
que es como se entiende por qué un disco va lento (cuelga de un concentrador
de USB 2). Los concentradores están en el árbol pero no cuentan como
dispositivos: nadie tiene «diecisiete dispositivos USB» por tener dos.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import render
from ...i18n import _
from ...model import Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font, value_font
from ..widgets import Card, ChipRow, InfoGrid, ResponsiveRow, ScrollPage, Table

USB_HEADERS = ("dev.col.device", "dev.col.maker", "dev.col.kind", "dev.col.speed")
SOUND_HEADERS = ("dev.col.card", "dev.col.where")
CAMERA_HEADERS = ("dev.col.camera", "dev.col.type")
DONDE_SUENA = {"hdmi": "dev.sound.where.gpu", "board": "dev.sound.where.board",
               "usb": "dev.sound.where.usb"}


class DevicesPage(ScrollPage):

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

        cabecera = Card()
        self.title = QLabel(_("dev.title.none"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()
        for widget in (self.title, self.subtitle, self.badges):
            cabecera.body.addWidget(widget)
        layout.addWidget(cabecera)

        self.usb_card = Card(_("dev.card.usb"))
        self.usb = QTreeWidget()
        self.usb.setObjectName("DeviceTree")
        self.usb.setColumnCount(len(USB_HEADERS))
        # En mayúsculas pequeñas, como los títulos de columna de las demás
        # tablas de la página (`QLabel#ColumnTitle`).
        self.usb.setHeaderLabels([_(h).upper() for h in USB_HEADERS])
        # Sin flechas: el árbol va siempre abierto. Lo que cuelga de un
        # concentrador se ve por el sangrado, y plegarlo no ahorra nada.
        self.usb.setRootIsDecorated(False)
        self.usb.setItemsExpandable(False)
        self.usb.setIndentation(22)
        self.usb.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.usb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.usb.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.usb.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.usb.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.usb.header().setStretchLastSection(True)
        # El árbol crece con lo que lleva, sin barra propia: dos zonas de
        # desplazamiento anidadas hacen cosas distintas con la misma rueda.
        self.usb.itemExpanded.connect(lambda _item: self._ajustar_alto())
        self.usb.itemCollapsed.connect(lambda _item: self._ajustar_alto())
        self.usb_card.body.addWidget(self.usb)
        self.usb_pie = QLabel(_("dev.usb.pie"))
        self.usb_pie.setObjectName("Muted")
        self.usb_pie.setWordWrap(True)
        self.usb_pie.setFont(ui_font(m.small_pt))
        self.usb_card.body.addWidget(self.usb_pie)
        layout.addWidget(self.usb_card)
        self._usb_signature: tuple | None = None
        self._usb_items: dict[str, QTreeWidgetItem] = {}

        fila = ResponsiveRow(min_item_width=320, span_last=True)
        sonido = Card(_("dev.card.sound"))
        self.sound = Table([_(h) for h in SOUND_HEADERS], cede=(0,))
        sonido.body.addWidget(self.sound)
        self.sound_card = sonido
        fila.add(sonido)

        camaras = Card(_("dev.card.cameras"))
        self.cameras = Table([_(h) for h in CAMERA_HEADERS], cede=(0,))
        camaras.body.addWidget(self.cameras)
        self.cameras_none = self._nota(_("dev.camera.none"))
        camaras.body.addWidget(self.cameras_none)
        fila.add(camaras)

        bluetooth = Card(_("dev.card.bluetooth"))
        self.bluetooth = InfoGrid()
        bluetooth.body.addWidget(self.bluetooth)
        self._bt_host = bluetooth.body
        self._bt_signature: tuple = ()
        self.bluetooth_none = self._nota(_("dev.bt.none.long"))
        bluetooth.body.addWidget(self.bluetooth_none)
        self.bluetooth_pie = self._nota(_("dev.bt.pie"))
        bluetooth.body.addWidget(self.bluetooth_pie)
        fila.add(bluetooth)
        layout.addWidget(fila)
        layout.addStretch(1)

    @staticmethod
    def _nota(texto: str) -> QLabel:
        etiqueta = QLabel(texto)
        etiqueta.setObjectName("Muted")
        etiqueta.setWordWrap(True)
        etiqueta.setFont(ui_font(theme.METRICS.small_pt))
        return etiqueta

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        usb = snapshot.usb_devices
        aparatos = [u for u in usb if not u.is_hub]
        concentradores = len(usb) - len(aparatos)
        lentos = [u for u in aparatos if u.slower_than_capable]

        n = len(aparatos)
        self.title.setText(_("dev.title.none") if not n else
                           _("dev.title.one" if n == 1 else "dev.title.many").format(n=n))
        camaras = len(snapshot.cameras)
        tarjetas = len(snapshot.sound_cards)
        self.subtitle.setText(_("dev.subtitle").format(
            sonido=_("dev.sound.one" if tarjetas == 1 else "dev.sound.many").format(n=tarjetas),
            camaras=_("dev.cameras.one" if camaras == 1 else "dev.cameras.many").format(n=camaras),
            bluetooth=_("dev.bt.one").format(n=len(snapshot.bluetooth)) if snapshot.bluetooth
            else _("dev.bt.none")))
        insignias = []
        if lentos:
            insignias.append(_("dev.chip.slow").format(n=len(lentos)))
        if concentradores:
            insignias.append(_("dev.chip.hubs.one" if concentradores == 1
                               else "dev.chip.hubs.many").format(n=concentradores))
        self.badges.set_chips(insignias, highlight_first=bool(lentos))
        self.badges.setVisible(bool(insignias))

        self._apply_usb(usb)
        self.sound.set_rows([(render.sound_card(s), _(DONDE_SUENA.get(s.kind, "dev.sound.where.board")))
                             for s in snapshot.sound_cards])
        self.sound_card.setVisible(bool(snapshot.sound_cards))

        self.cameras.set_rows([
            (c.name or _("dev.camera.generic"),
             _("dev.camera.virtual" if c.virtual else "dev.camera.real"))
            for c in snapshot.cameras])
        self.cameras.setVisible(bool(snapshot.cameras))
        self.cameras_none.setVisible(not snapshot.cameras)

        self._apply_bluetooth(snapshot.bluetooth)

    def _apply_usb(self, usb) -> None:
        self.usb_card.setVisible(bool(usb))
        signature = tuple(usb)
        if signature == self._usb_signature:
            return
        self._usb_signature = signature
        # Rows are updated in place, never cleared and rebuilt: `clear()`
        # followed by `expandAll()` is where Qt aborted twice in the CI, and
        # in the app that runs every time something is plugged or unplugged.
        devices = sorted(usb, key=lambda u: [int(x) for x in u.port.replace("-", ".").split(".")])
        present = {u.port for u in devices}
        for port in set(self._usb_items) - present:
            self._detach_usb(self._usb_items.pop(port), keep_children=True)
        placed: dict[str, int] = {}
        for device in devices:
            item = self._usb_items.get(device.port)
            if item is None:
                item = self._usb_items[device.port] = self._new_usb_row()
            self._fill_usb_row(item, device)
            parent_port = device.parent if device.parent in present else ""
            index = placed.get(parent_port, 0)
            placed[parent_port] = index + 1
            self._place_usb(item, self._usb_items.get(parent_port), index)
        for item in self._usb_items.values():
            if item.childCount() and not item.isExpanded():
                item.setExpanded(True)
        # Lo que no dice nada en ninguna fila no se enseña (regla 5). Pasa con
        # la foto anónima, que no lleva marcas ni modelos de lo enchufado: el
        # fabricante se queda vacío y «Qué es» repite el nombre («Teclado /
        # teclado»), porque el nombre ya es lo que es.
        self.usb.setColumnHidden(1, not any(u.vendor for u in usb))
        self.usb.setColumnHidden(2, not any(u.product for u in usb))
        self._ajustar_alto()

    @staticmethod
    def _new_usb_row() -> QTreeWidgetItem:
        row = QTreeWidgetItem()
        row.setFont(0, ui_font(theme.METRICS.small_pt))
        for column in range(1, len(USB_HEADERS)):
            row.setFont(column, value_font())
        return row

    def _fill_usb_row(self, row: QTreeWidgetItem, device) -> None:
        texts = [render.usb_name(device), device.vendor or "",
                 render.usb_kind(device), render.usb_speed(device.speed_mbps)]
        tip = _("dev.usb.tip").format(puerto=device.port, id=device.usb_id or render.DASH)
        speed_tone = "ink_dim"
        if device.slower_than_capable:
            # El aviso, solo cuando algo rápido negocia despacio.
            slow = _("dev.usb.slow").format(
                version=device.version, velocidad=render.usb_speed(device.speed_mbps))
            tip = f"{slow}\n\n{tip}"
            speed_tone = "warn"
            texts[3] = f"{texts[3]}  ⚠"
        tones = ["muted" if device.is_hub else "ink", "ink_dim", "ink_dim", speed_tone]
        # Qt ignores a value equal to the one the cell already has.
        for column, (text, tone) in enumerate(zip(texts, tones)):
            row.setText(column, text)
            row.setToolTip(column, tip)
            row.setForeground(column, QBrush(self._p.q(tone)))

    def _detach_usb(self, row: QTreeWidgetItem, keep_children: bool = False) -> None:
        """Takes the row out of the tree; its children, if kept, go out first
        so they can be placed again under whatever now holds them.

        `removeChild` and not `takeChild`: PySide keeps the parent's reference
        to a child taken with `takeChild`, so every unplugged row stayed alive.
        """
        if keep_children:
            for child in [row.child(i) for i in range(row.childCount())]:
                row.removeChild(child)
        parent = row.parent()
        if parent is not None:
            parent.removeChild(row)
        elif (index := self.usb.indexOfTopLevelItem(row)) >= 0:
            self.usb.takeTopLevelItem(index)

    def _place_usb(self, row: QTreeWidgetItem, parent, index: int) -> None:
        if parent is None:
            if self.usb.indexOfTopLevelItem(row) == index and row.parent() is None:
                return
            self._detach_usb(row)
            self.usb.insertTopLevelItem(index, row)
        else:
            if row.parent() is parent and parent.indexOfChild(row) == index:
                return
            self._detach_usb(row)
            parent.insertChild(index, row)

    def _ajustar_alto(self) -> None:
        visibles = 0
        pendientes = [self.usb.topLevelItem(i) for i in range(self.usb.topLevelItemCount())]
        while pendientes:
            item = pendientes.pop()
            visibles += 1
            if item.isExpanded():
                pendientes.extend(item.child(i) for i in range(item.childCount()))
        alto_fila = max(self.usb.sizeHintForRow(0), 20) if visibles else 20
        extra = self.usb.header().sizeHint().height() + 6
        self.usb.setFixedHeight(visibles * alto_fila + extra)

    def _apply_bluetooth(self, adaptadores) -> None:
        filas = tuple(
            (a.name, _("dev.bt.row").format(
                producto=a.product or _("dev.bt.generic"),
                donde=_("dev.sound.where.usb" if a.bus == "usb" else "dev.sound.where.board"),
                estado=_("dev.bt.on" if a.powered else "dev.bt.off")))
            for a in adaptadores)
        nombres = tuple(n for n, _v in filas)
        if nombres != self._bt_signature:
            self._bt_signature = nombres
            nueva = InfoGrid()
            for nombre, valor in filas:
                nueva.add(nombre)
                nueva.set(nombre, valor)
            self._bt_host.replaceWidget(self.bluetooth, nueva)
            self.bluetooth.setParent(None)
            self.bluetooth.deleteLater()
            self.bluetooth = nueva
        else:
            for nombre, valor in filas:
                self.bluetooth.set(nombre, valor)
        self.bluetooth.setVisible(bool(filas))
        self.bluetooth_pie.setVisible(bool(filas))
        self.bluetooth_none.setVisible(not filas)
