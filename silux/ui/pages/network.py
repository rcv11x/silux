"""Página de red: qué interfaces hay y cuánto están moviendo.

Es la única sección cuyo dato principal no es un estado sino un ritmo, y por
eso las dos cifras grandes de arriba llevan su gráfica: en una red lo que
importa no es cuánto va ahora mismo sino la forma que dibuja (si sube en picos,
si se mantiene plana, si se ha caído del todo). El resto de la página es la
ficha de cada interfaz, que sí es información estable.

Las interfaces virtuales de Docker, libvirt o una VPN se enseñan igual que las
de verdad, pero después y marcadas: quien las tiene quiere verlas, y quien no,
no las tiene.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ...i18n import _
from ... import render
from ...model import NetworkInterface, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, ChipRow, InfoGrid, ResponsiveRow, StatTile, Table, clear_layout

INTERFACE_FIELDS = (
    _("gpu.sensor.state"), _("memory.field.type"), _("net.field.ipv4"), _("net.field.mask"), "net.field.gateway",
    "net.field.ipv6", "net.field.mac", _("net.field.speed"), "MTU",
    "Controlador", _("storage.col.model"), _("net.field.slot"),
)

TRAFFIC_HEADERS = ("Interfaz", "Bajando", "Subiendo", "Recibido", "Enviado",
                   "Paquetes", "Perdidos")

# En qué orden se enseñan: primero la que da servicio, al final lo virtual.
PRIORIDAD = {"ethernet": 0, "wifi": 1, "puente": 2, "virtual": 3,
             "otro": 4, "loopback": 5}


def _orden(interfaz: NetworkInterface) -> tuple:
    return (not interfaz.default_route, not interfaz.active,
            PRIORIDAD.get(interfaz.kind, 9), interfaz.name)


class NetworkPage(QScrollArea):
    # La unidad se cambia desde aquí y no desde Ajustes: se decide mirando la
    # cifra, comparándola con lo que dice otro programa, y hacer ese viaje a
    # otra pestaña para volver rompe la comparación.
    unit_changed = Signal(str)

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

        traffic_card = Card(_("net.card.traffic"))
        traffic_card.body.addLayout(self._build_unit_switch())
        self.traffic = Table([_(h) for h in TRAFFIC_HEADERS],
                             numeric=(False, True, True, True, True, True, True))
        traffic_card.body.addWidget(self.traffic)
        layout.addWidget(traffic_card)

        self._cards_host = QVBoxLayout()
        self._cards_host.setSpacing(m.section_gap)
        layout.addLayout(self._cards_host)

        layout.addStretch(1)

        self._bits = prefs.network_unit == "bits"
        self._grids: dict[str, InfoGrid] = {}
        self._cards: dict[str, Card] = {}
        self._chip_signature: tuple = ()

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel(_("net.loading"))
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

    def _build_unit_switch(self) -> QHBoxLayout:
        """Dos botones para pasar de bytes a bits y al revés."""
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(6)

        explicacion = QLabel(_("net.units.note"))
        explicacion.setObjectName("Muted")
        explicacion.setWordWrap(True)
        fila.addWidget(explicacion, 1)

        self._unit_buttons: dict[str, QPushButton] = {}
        for etiqueta, valor in (("MB/s", "bytes"), ("Mb/s", "bits")):
            boton = QPushButton(etiqueta)
            boton.setCheckable(True)
            boton.setChecked(self._prefs.network_unit == valor)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.clicked.connect(lambda _checked, v=valor: self._pick_unit(v))
            fila.addWidget(boton)
            self._unit_buttons[valor] = boton
        return fila

    def _pick_unit(self, unidad: str) -> None:
        for valor, boton in self._unit_buttons.items():
            boton.setChecked(valor == unidad)
        if unidad != self._prefs.network_unit:
            self.unit_changed.emit(unidad)

    def _build_tiles(self) -> QWidget:
        fila = ResponsiveRow(min_item_width=150)
        self.tile_down = StatTile("Bajando", "", self._p)
        self.tile_up = StatTile("Subiendo", "", self._p)
        self.tile_rx = StatTile("Recibido", "", self._p)
        self.tile_tx = StatTile("Enviado", "", self._p)
        for tile in (self.tile_down, self.tile_up, self.tile_rx, self.tile_tx):
            fila.add(tile)
        # Las dos de totales no llevan gráfica: son contadores que solo suben,
        # y su curva sería siempre la misma recta sin decir nada.
        self.tile_rx.chart.hide()
        self.tile_tx.chart.hide()
        return fila

    def _refresh_formatters(self) -> None:
        """Que la cifra bajo el cursor lleve la misma unidad que la de arriba."""
        intervalo = self._prefs.interval_s
        for tile in (self.tile_down, self.tile_up):
            tile.chart.set_formatter(
                lambda valor: render.rate(valor, self._bits), intervalo)

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        self._bits = self._prefs.network_unit == "bits"
        for valor, boton in getattr(self, "_unit_buttons", {}).items():
            boton.setChecked(valor == self._prefs.network_unit)
        self._refresh_formatters()
        interfaces = sorted(snapshot.network, key=_orden)
        principal = next((i for i in interfaces if i.default_route),
                         next((i for i in interfaces if i.active), None))

        self._apply_header(principal, interfaces)
        self._apply_tiles(principal)
        self._apply_traffic(interfaces)
        self._apply_cards(interfaces)

    def _apply_header(self, principal, interfaces) -> None:
        if principal is None:
            self.title.setText(_("net.none"))
            self.subtitle.setText(_("net.none.body"))
            return
        self.title.setText(principal.display_name)
        self.subtitle.setText(" · ".join(p for p in (
            principal.name, principal.ipv4, principal.link_summary) if p))

        activas = sum(1 for i in interfaces if i.active)
        chips = [c for c in (
            principal.name,
            principal.link_summary,
            (_("net.gateway2").format(ip=principal.gateway)
             if principal.gateway else None),
            _("net.active2").format(n=activas, total=len(interfaces)),
        ) if c]
        if tuple(chips) != self._chip_signature:
            self._chip_signature = tuple(chips)
            self.badges.set_chips(chips, highlight_first=True)

    def _apply_tiles(self, principal) -> None:
        trafico = principal.traffic if principal else None
        bajada = trafico.rx_rate_bps if trafico else None
        subida = trafico.tx_rate_bps if trafico else None

        # La cifra y la unidad van juntas porque la unidad cambia sola: pasar de
        # KB/s a MB/s en mitad de una descarga es lo normal.
        self.tile_down.update_value(render.rate(bajada, self._bits), bajada)
        self.tile_up.update_value(render.rate(subida, self._bits), subida)
        self.tile_rx.update_value(render.size(trafico.rx_bytes) if trafico else render.DASH)
        self.tile_tx.update_value(render.size(trafico.tx_bytes) if trafico else render.DASH)

        if trafico:
            self.tile_rx.set_detail(_("net.packets2").format(
                n=f"{trafico.rx_packets:n}"))
            self.tile_tx.set_detail(f"{trafico.tx_packets:n} paquetes")
            perdidos = trafico.problems
            self.tile_down.set_detail(
                f"{perdidos:n} paquetes perdidos" if perdidos else "sin pérdidas")

    def _apply_traffic(self, interfaces) -> None:
        d = render.DASH
        filas = [
            (interfaz.name,
             render.rate(interfaz.traffic.rx_rate_bps, self._bits),
             render.rate(interfaz.traffic.tx_rate_bps, self._bits),
             render.size(interfaz.traffic.rx_bytes),
             render.size(interfaz.traffic.tx_bytes),
             f"{interfaz.traffic.rx_packets + interfaz.traffic.tx_packets:n}",
             f"{interfaz.traffic.problems:n}" if interfaz.traffic.problems else "—")
            for interfaz in interfaces
        ]
        self.traffic.set_rows(filas or [("Sin interfaces", d, d, d, d, d, d)])

    def _apply_cards(self, interfaces) -> None:
        # Una tarjeta por interfaz, creadas una vez y reescritas después: esta
        # página se repinta cada segundo como todas las demás.
        nombres = tuple(i.name for i in interfaces)
        if nombres != tuple(self._cards):
            clear_layout(self._cards_host)
            self._grids.clear()
            self._cards.clear()
            fila = ResponsiveRow(min_item_width=300)
            for interfaz in interfaces:
                card = Card(interfaz.name)
                grid = InfoGrid()
                for campo in INTERFACE_FIELDS:
                    grid.add(_(campo))
                card.body.addWidget(grid)
                fila.add(card)
                self._grids[interfaz.name] = grid
                self._cards[interfaz.name] = card
            self._cards_host.addWidget(fila)

        d = render.DASH
        for interfaz in interfaces:
            grid = self._grids.get(interfaz.name)
            if grid is None:
                continue
            f = grid.set
            f(_("gpu.sensor.state"), render.interface_state(interfaz))
            f(_("memory.field.type"), interfaz.kind)
            f(_("net.field.ipv4"), interfaz.ipv4 or d)
            f(_("net.field.mask"), interfaz.netmask or d)
            f(_("net.field.gateway"), interfaz.gateway or d)
            f(_("net.field.ipv6"), interfaz.ipv6[0] if interfaz.ipv6 else d,
              tooltip="\n".join(interfaz.ipv6) if len(interfaz.ipv6) > 1 else "")
            f(_("net.field.mac"), interfaz.mac or d)
            f(_("net.field.speed"), interfaz.link_summary or d)
            f("MTU", str(interfaz.mtu) if interfaz.mtu else d)
            f("Controlador", interfaz.driver or d)
            f(_("storage.col.model"), interfaz.model or d)
            f(_("net.field.slot"), interfaz.pci_slot or d)
