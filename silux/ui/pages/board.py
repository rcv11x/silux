"""Página de placa base.

Junta tres orígenes que responden a la misma pregunta: sobre qué está montado
esto. La tabla SMBIOS da la placa y la BIOS, el bus PCI identifica el chipset,
y `/sys/firmware` cuenta cómo arranca la máquina.

CPU-X enseña aquí seis campos. Aquí hay veinte, y ninguno inventado: todos
salen de ficheros que el kernel expone sin pedir permisos. Los que el
fabricante deja sin rellenar no se enseñan en vez de mostrar el «Default
string» que trae la BIOS de fábrica.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...i18n import _
from ... import render
from ...model import Board, Need, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (Card, ChipRow, InfoGrid, Notice, ResponsiveRow, Table,
                       clear_layout, tone_for, ScrollPage)

BOARD_FIELDS = ("memory.field.vendor", "storage.col.model",
                "board.field.revision", "board.field.chassistype",
                "board.field.chassis")
FIRMWARE_FIELDS = ("memory.field.type", "memory.field.vendor",
                   "sys.field.version", "board.field.date",
                   "board.field.smbios", "board.field.secureboot", "TPM")
CHIPSET_FIELDS = ("board.field.chipset", "board.field.pciid",
                  "board.field.memctl")
SYSTEM_FIELDS = ("memory.field.vendor", "storage.col.model",
                 "sys.field.version", "cpu.field.family", "SKU")

NEED_TITLES = {
    Need.ROOT: "note.needsroot",
    Need.DATABASE: "note.database",
    Need.HARDWARE: "note.hardware",
    Need.DRIVER: "note.needsmodule",
    Need.PLATFORM: "note.platform",
    Need.ERROR: "note.failed",
    Need.KERNEL: "note.kernel",
}


PCI_HEADERS = ("board.pci.kind", "board.pci.device", "gpu.clock.link", "board.pci.max",
               "gpu.field.driver")
PCI_KINDS = {
    "gpu": "board.pci.kind.gpu", "nvme": "board.pci.kind.nvme", "sata": "board.pci.kind.sata",
    "ethernet": "board.pci.kind.ethernet", "wifi": "board.pci.kind.wifi",
    "usb": "board.pci.kind.usb", "audio": "board.pci.kind.audio",
}
PLATFORM_FIELDS = ("board.plat.iommu", "board.plat.virt", "board.plat.above4g",
                   "board.plat.sensors", "board.plat.codec")

# Cómo se nombra, en la frase del pie, cada campo que el firmware calla.
NO_DICE = {
    "memory.field.vendor": "board.na.vendor",
    "storage.col.model": "board.na.model",
    "board.field.revision": "board.na.revision",
    "board.field.chassistype": "board.na.chassistype",
    "board.field.chassis": "board.na.chassis",
}


class BoardPage(ScrollPage):
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

        # Todas en una fila que se reparte sola: tres columnas cuando hay
        # sitio, dos y la última a lo ancho cuando no. En dos filas fijas, a
        # 2560 px la página era dos tarjetas medio vacías y otra debajo.
        top = bottom = ResponsiveRow(min_item_width=400, span_last=True)
        self.board = self._grid_card(top, _("nav.board"), BOARD_FIELDS)
        self.firmware = self._grid_card(top, _("storage.field.firmware"), FIRMWARE_FIELDS)
        self.chipset = self._grid_card(bottom, _("board.field.chipset"),
                                       CHIPSET_FIELDS)
        self.board_pie = QLabel("")
        self.board_pie.setObjectName("Muted")
        self.board_pie.setWordWrap(True)
        self.board_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.board_pie.hide()
        self.board.parentWidget().body.addWidget(self.board_pie)
        self.firmware_pie = QLabel("")
        self.firmware_pie.setObjectName("Muted")
        self.firmware_pie.setWordWrap(True)
        self.firmware_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.firmware_pie.hide()
        self.firmware.parentWidget().body.addWidget(self.firmware_pie)
        self.system = self._grid_card(bottom, _("board.card.system"),
                                      SYSTEM_FIELDS)
        self.system_card = self.system.parentWidget()
        layout.addWidget(bottom)

        # Lo que cuelga del bus PCI: una sola tabla, con lo que va en una
        # ranura primero y los controladores de la placa después.
        self.pci_card = Card(_("board.card.pci"))
        self.pci = Table([_(h) for h in PCI_HEADERS], cede=(1,))
        self.pci_card.body.addWidget(self.pci)
        self._pci_con_ranura = False
        self.pci_pie = QLabel("")
        self.pci_pie.setObjectName("Muted")
        self.pci_pie.setWordWrap(True)
        self.pci_pie.setFont(ui_font(theme.METRICS.small_pt))
        self.pci_card.body.addWidget(self.pci_pie)
        self.pci_card.hide()
        layout.addWidget(self.pci_card)

        self.platform_card = Card(_("board.card.platform"))
        self.platform = InfoGrid()
        for name in PLATFORM_FIELDS:
            self.platform.add(_(name))
        self.platform_card.body.addWidget(self.platform)
        bottom.add(self.platform_card)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        layout.addLayout(self._notices_host)
        layout.addStretch(1)

        self._badge_signature: tuple = ()
        self._notice_signature: tuple = ()

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
        self.title = QLabel(_("board.loading"))
        self.title.setObjectName("Headline")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        board = snapshot.board

        self.title.setText(render.board_name(board))
        self.subtitle.setText(self._subtitle(board))
        self._apply_badges(board)

        d = render.DASH
        # Lo que el firmware no rellena no es un dato por leer: no está. La
        # fila se va y el pie de la tarjeta dice cuáles, en vez de una columna
        # de guiones (regla 5).
        sin_rellenar = []
        for clave, valor in (
                ("memory.field.vendor", render.maker(board.vendor)),
                ("storage.col.model", board.name),
                ("board.field.revision", board.version),
                ("board.field.chassistype", _(board.chassis) if board.chassis else None),
                ("board.field.chassis", render.maker(board.chassis_vendor))):
            self.board.set(_(clave), valor or d)
            self.board.set_visible(_(clave), bool(valor))
            if not valor:
                sin_rellenar.append(_(NO_DICE[clave]))
        if snapshot.cpu.in_virtual_machine:
            pie = [_("board.virtual")]
        else:
            pie = ([_("board.unfilled").format(campos=render.enumeration(sin_rellenar, "list.nor"))]
                   if sin_rellenar else [])

        f = self.firmware.set
        f(_("memory.field.type"), board.firmware or d)
        f(_("memory.field.vendor"), render.maker(board.bios_vendor) or d)
        f(_("sys.field.version"), board.bios_version or d)
        f(_("board.field.date"), render.bios_date(board.bios_date) or d)
        f(_("board.field.smbios"), board.bios_release or d,
          tooltip=_("board.tip.bios"))
        f(_("board.field.secureboot"), self._secure_boot(board))
        # Secure Boot is UEFI's: with a legacy BIOS there is none to read.
        heredada = board.secure_boot is None and not (board.firmware or "").startswith("UEFI")
        self.firmware.set_visible(_("board.field.secureboot"), not heredada)
        self.firmware_pie.setText(_("board.na.secureboot.legacy") if heredada else "")
        self.firmware_pie.setVisible(heredada)
        f("TPM", board.tpm_version or _("board.notdetected"))

        c = self.chipset.set
        c(_("board.field.chipset"), board.chipset or d)
        c(_("board.field.pciid"), board.chipset_full or d,
          tooltip=_("board.tip.chipset"))
        c(_("board.field.memctl"), board.host_bridge or d,
          tooltip=_("board.tip.memctl"))

        # «Equipo» es para los de marca, donde el firmware dice qué equipo es
        # («ThinkCentre M80q»). En una placa suelta esos campos son códigos de
        # fábrica («-CF», «MS-7D23», «1.0») que repiten la placa o no dicen
        # nada: la tarjeta se va y se dice por qué. En crudo siguen en el
        # informe, que es donde sirven.
        de_marca = bool(board.system_display_name)
        self.system_card.setVisible(de_marca)
        if de_marca:
            for clave, valor in (
                    ("memory.field.vendor", render.maker(board.system_vendor)),
                    ("storage.col.model", board.system_name),
                    ("sys.field.version", board.system_version),
                    ("cpu.field.family", board.system_family),
                    ("SKU", board.system_sku)):
                nombre = _(clave) if clave != "SKU" else clave
                self.system.set(nombre, valor or d)
                self.system.set_visible(nombre, bool(valor))
        else:
            pie.append(_("board.nosystem"))
        self.board_pie.setText(" ".join(pie))
        self.board_pie.setVisible(bool(pie))

        self._apply_pci(snapshot)
        self._apply_platform(snapshot)
        self._apply_notices(snapshot)

    def _apply_pci(self, snapshot: Snapshot) -> None:
        dispositivos = snapshot.pci_devices
        self.pci_card.setVisible(bool(dispositivos))
        if not dispositivos:
            return
        # La columna «Ranura» solo existe cuando hay algún nombre que poner:
        # sale de la tabla del firmware, que pide permisos. Sin ellos, una
        # línea al pie en vez de una columna de guiones o de candados.
        con_ranura = any(d.slot_name for d in dispositivos)
        if con_ranura != self._pci_con_ranura:
            self._pci_con_ranura = con_ranura
            cabeceras = PCI_HEADERS + (("board.pci.slot",) if con_ranura else ())
            nueva = Table([_(h) for h in cabeceras], cede=(1,))
            self.pci_card.body.replaceWidget(self.pci, nueva)
            self.pci.setParent(None)
            self.pci.deleteLater()
            self.pci = nueva
        # El sonido que comparte tarjeta con una gráfica (misma dirección,
        # otra función) es su salida HDMI: no está «en la placa».
        de_graficas = {d.slot.rsplit(".", 1)[0] for d in dispositivos if d.kind == "gpu"}
        # What a hypervisor emulates is not on a board or in a processor.
        virtual = snapshot.cpu.in_virtual_machine
        graficas = {g.pci_slot: g for g in snapshot.gpus}
        filas, pistas = [], []
        for d in dispositivos:
            grafica = graficas.get(d.slot)
            if virtual:
                donde = _("board.pci.virtual")
            elif grafica is not None and grafica.suspended:
                # A laptop's dedicated card asleep: its link is not read so as
                # not to wake it. It used to say «en el procesador».
                donde = _("board.pci.asleep")
            elif d.kind == "gpu":
                # Una gráfica sin enlace es la integrada: va en el procesador.
                donde = _("board.pci.oncpu")
            elif d.slot.rsplit(".", 1)[0] in de_graficas:
                donde = _("board.pci.ongpu")
            else:
                donde = _("board.pci.onboard")
            nombre = d.name or render.pci_unnamed(d) or render.DASH
            if d.kind in ("ethernet", "wifi") and d.name:
                nombre = render.with_maker(d.vendor, d.name)
            fila = [_(PCI_KINDS[d.kind]), nombre,
                    render.pcie_link(d.link) if d.link else donde,
                    render.pcie_link(d.link, maximum=True) if d.link else "",
                    d.driver or render.DASH]
            if con_ranura:
                fila.append(d.slot_name or "")
            filas.append(fila)
            pistas.append(_("board.pci.address").format(direccion=d.slot))
        self.pci.set_rows(filas, tooltips=pistas)
        if con_ranura:
            pie = ""
        elif snapshot.permission_notes:
            pie = _("board.pci.slots.locked")
        elif snapshot.privileged.connected:
            pie = _("board.pci.slots.unknown")
        else:
            pie = ""
        self.pci_pie.setText(pie)
        self.pci_pie.setVisible(bool(pie))

    def _apply_platform(self, snapshot: Snapshot) -> None:
        plataforma = snapshot.platform
        chip = render.chip_name(plataforma.sensor_chip).upper() if plataforma.sensor_chip else None
        filas = (
            ("board.plat.iommu", render.iommu(plataforma)),
            ("board.plat.virt", render.virtualization(plataforma)),
            ("board.plat.above4g", render.above_4g(plataforma)),
            ("board.plat.sensors", chip),
            ("board.plat.codec", plataforma.audio_codec),
        )
        for clave, valor in filas:
            self.platform.set(_(clave), valor or render.DASH)
            self.platform.set_visible(_(clave), bool(valor))

    @staticmethod
    def _subtitle(board: Board) -> str:
        parts = [board.chipset, board.firmware,
                 _(board.chassis) if board.chassis else None]
        return " · ".join(p for p in parts if p) or _("board.nofirmware")

    @staticmethod
    def _secure_boot(board: Board) -> str:
        return {True: _("board.on"), False: _("board.off"),
                None: _("board.unreadable")}[board.secure_boot]

    def _apply_badges(self, board: Board) -> None:
        wanted = tuple(x for x in (
            board.chipset,
            board.firmware,
            board.tpm_version,
            _("board.field.secureboot") if board.secure_boot else None,
        ) if x)
        if wanted == self._badge_signature:
            return
        self._badge_signature = wanted
        self.badges.set_chips(wanted, highlight_first=True)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        notes = snapshot.notes_for("board")
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(_(NEED_TITLES.get(note.need, note.need.value)),
                       note.message, note.hint, tone=tone_for(note.need))
            )
