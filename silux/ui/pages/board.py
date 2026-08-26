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
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...model import Board, Need, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, ChipRow, InfoGrid, Notice, ResponsiveRow, clear_layout

BOARD_FIELDS = ("Fabricante", "Modelo", "Revisión", "Chasis", "Fabricante del chasis")
FIRMWARE_FIELDS = ("Tipo", "Fabricante", "Versión", "Fecha", "Revisión SMBIOS",
                   "Arranque seguro", "TPM")
CHIPSET_FIELDS = ("Chipset", "Identificación PCI", "Controlador de memoria")
SYSTEM_FIELDS = ("Fabricante", "Modelo", "Versión", "Familia", "SKU")

NEED_TITLES = {
    Need.ROOT: "Hace falta elevar permisos",
    Need.DATABASE: "Falta en la base de datos",
    Need.HARDWARE: "Este equipo no lo expone",
    Need.DRIVER: "Falta un módulo del kernel",
    Need.PLATFORM: "No aplica a esta plataforma",
}


class BoardPage(QScrollArea):
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

        top = ResponsiveRow(min_item_width=270)
        self.board = self._grid_card(top, "Placa base", BOARD_FIELDS)
        self.firmware = self._grid_card(top, "Firmware", FIRMWARE_FIELDS)
        layout.addWidget(top)

        bottom = ResponsiveRow(min_item_width=270)
        self.chipset = self._grid_card(bottom, "Chipset", CHIPSET_FIELDS)
        self.system = self._grid_card(bottom, "Equipo", SYSTEM_FIELDS)
        layout.addWidget(bottom)

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
            grid.add(name)
        card.body.addWidget(grid)
        host.add(card)
        return grid

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel("Leyendo la placa…")
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

        self.title.setText(board.display_name)
        self.subtitle.setText(self._subtitle(board))
        self._apply_badges(board)

        d = render.DASH
        b = self.board.set
        b("Fabricante", board.vendor or d)
        b("Modelo", board.name or d)
        b("Revisión", board.version or d)
        b("Chasis", board.chassis or d)
        b("Fabricante del chasis", board.chassis_vendor or d)

        f = self.firmware.set
        f("Tipo", board.firmware or d)
        f("Fabricante", board.bios_vendor or d)
        f("Versión", board.bios_version or d)
        f("Fecha", board.bios_date or d)
        f("Revisión SMBIOS", board.bios_release or d,
          tooltip="El campo «System BIOS Release» de la tabla SMBIOS. No es la "
                  "versión que publica el fabricante, sino la que declara el "
                  "firmware, y a menudo no coinciden.")
        f("Arranque seguro", self._secure_boot(board))
        f("TPM", board.tpm_version or "no detectado")

        c = self.chipset.set
        c("Chipset", board.chipset or d)
        c("Identificación PCI", board.chipset_full or d,
          tooltip="El nombre completo con el que pci.ids identifica al puente "
                  "LPC/eSPI del bus 0, que es lo que define al chipset.")
        c("Controlador de memoria", board.host_bridge or d,
          tooltip="En los procesadores modernos va integrado en la propia CPU, "
                  "no en el chipset.")

        s = self.system.set
        s("Fabricante", board.system_vendor or d)
        s("Modelo", board.system_name or d)
        s("Versión", board.system_version or d)
        s("Familia", board.system_family or d)
        s("SKU", board.system_sku or d)

        self._apply_notices(snapshot)

    @staticmethod
    def _subtitle(board: Board) -> str:
        parts = [board.chipset, board.firmware, board.chassis]
        return " · ".join(p for p in parts if p) or "Sin información de firmware"

    @staticmethod
    def _secure_boot(board: Board) -> str:
        return {True: "activado", False: "desactivado", None: "no se puede leer"}[
            board.secure_boot
        ]

    def _apply_badges(self, board: Board) -> None:
        wanted = tuple(x for x in (
            board.chipset,
            board.firmware,
            board.tpm_version,
            "Arranque seguro" if board.secure_boot else None,
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
                Notice(NEED_TITLES.get(note.need, note.need.value), note.message, note.hint)
            )
