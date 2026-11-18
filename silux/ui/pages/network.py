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
    "gpu.sensor.state", "memory.field.type", "net.field.ipv4",
    "net.field.mask", "net.field.gateway", "net.field.ipv6",
    "net.field.mac", "net.field.speed", "MTU", "gpu.field.driver",
    "storage.col.model", "net.field.slot",
)

TRAFFIC_HEADERS = ("Interfaz", "Bajando", "Subiendo", "Recibido", "Enviado",
                   "Paquetes", "Perdidos")

# En qué orden se enseñan: primero la que da servicio, al final lo virtual.
PRIORIDAD = {"ethernet": 0, "wifi": 1, "puente": 2, "virtual": 3,
             "otro": 4, "loopback": 5}


def _orden(interfaz: NetworkInterface) -> tuple:
    return (not interfaz.default_route, not interfaz.active,
            PRIORIDAD.get(interfaz.kind, 9), interfaz.name)


def is_physical(interfaz: NetworkInterface) -> bool:
    """Si detrás de la interfaz hay una tarjeta: de cable, wifi o en el bus PCI.

    Lo demás lo crea un programa —los puentes de Docker y de libvirt, los
    `veth` de cada contenedor, el túnel de Tailscale, el bucle local—. No
    son hardware, que es de lo que va este programa, y en un equipo con
    Docker son veinte.
    """
    return interfaz.kind in ("ethernet", "wifi") or bool(interfaz.pci_slot)


def main_interface(interfaces) -> tuple:
    """La interfaz que da servicio, y todas en su orden.

    La que lleva la ruta por defecto; si ninguna, la primera con dirección.
    Lo usan esta página y la tarjeta de Inicio, para que no digan dos cosas.
    """
    ordenadas = sorted(interfaces, key=_orden)
    principal = next((i for i in ordenadas if i.default_route),
                     next((i for i in ordenadas if i.active), None))
    return principal, ordenadas


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

        # Las virtuales, debajo de las físicas y plegadas: un renglón que dice
        # cuántas hay y cuáles, y que se abre al pulsarlo.
        self.virtual_toggle = QPushButton("")
        self.virtual_toggle.setObjectName("TextButton")
        self.virtual_toggle.setFlat(True)
        self.virtual_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.virtual_toggle.clicked.connect(self._alternar_virtuales)
        self.virtual_toggle.hide()
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(self.virtual_toggle)
        fila.addStretch(1)
        layout.addLayout(fila)

        self.virtual_box = QWidget()
        caja = QVBoxLayout(self.virtual_box)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(m.section_gap)
        virtual_card = Card(_("net.card.virtual"))
        self.virtual_traffic = Table([_(h) for h in TRAFFIC_HEADERS],
                                     numeric=(False, True, True, True, True, True, True))
        virtual_card.body.addWidget(self.virtual_traffic)
        caja.addWidget(virtual_card)
        self._virtual_cards_host = QVBoxLayout()
        self._virtual_cards_host.setSpacing(m.section_gap)
        caja.addLayout(self._virtual_cards_host)
        self.virtual_box.hide()
        layout.addWidget(self.virtual_box)
        self._virtuales_abiertas = False
        self._virtuales: tuple = ()

        layout.addStretch(1)

        self._bits = prefs.network_unit == "bits"
        self._grids: dict[str, InfoGrid] = {}
        self._cards: dict[str, Card] = {}
        # Qué interfaces tiene montadas cada grupo de tarjetas.
        self._montadas: dict[str, tuple] = {}
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
        # Lo más ancho que puede escribir cada una: un ritmo hasta los cien
        # gigabits, en bytes o en bits (se cambia desde esta misma página), y
        # un total hasta petabytes.
        ritmos = [texto for bits in (False, True) for texto in render.possible_texts(
            lambda valor, bits=bits: render.rate(valor, bits), 1.25e10)]
        for tile in (self.tile_down, self.tile_up):
            tile.reserve(ritmos)
        for tile in (self.tile_rx, self.tile_tx):
            tile.reserve(render.possible_texts(render.size, 1024 ** 5))
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
        principal, interfaces = main_interface(snapshot.network)

        # La cabecera cuenta las físicas: «4 de 24 activas» contaba los
        # puentes de Docker, que no son de lo que se viene a mirar.
        self._apply_header(principal, [i for i in interfaces if is_physical(i)]
                           or interfaces)
        self._apply_tiles(principal)
        fisicas = [i for i in interfaces if is_physical(i)]
        virtuales = [i for i in interfaces if not is_physical(i)]
        self.traffic.set_rows(self._filas_de_trafico(fisicas))
        self._apply_cards(fisicas, self._cards_host, "fisicas")
        self._apply_virtuales(virtuales)

    def _apply_header(self, principal, interfaces) -> None:
        if principal is None:
            self.title.setText(_("net.none"))
            self.subtitle.setText(_("net.none.body"))
            return
        # El titular es la conexión, no el chip: por qué interfaz se sale y
        # con qué dirección. «RTL8125 2.5GbE Controller» arriba del todo era
        # el nombre de una pieza donde se busca «¿tengo red?». La pieza y su
        # enlace van debajo, y las insignias no repiten ni lo uno ni lo otro.
        self.title.setText(" · ".join(p for p in (principal.name, principal.ipv4) if p))
        self.subtitle.setText(" · ".join(p for p in (
            principal.display_name if principal.display_name != principal.name else None,
            render.link_summary(principal)) if p))

        activas = sum(1 for i in interfaces if i.active)
        chips = [c for c in (
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
                n=render.thousands(trafico.rx_packets)))
            self.tile_tx.set_detail(_("net.packets2").format(
                n=render.thousands(trafico.tx_packets)))
            perdidos = trafico.problems
            self.tile_down.set_detail(
                _("net.lost").format(n=render.thousands(perdidos)) if perdidos
                else _("net.nolost"))

    def _alternar_virtuales(self) -> None:
        self._virtuales_abiertas = not self._virtuales_abiertas
        self._apply_virtuales(self._virtuales)

    def _apply_virtuales(self, virtuales) -> None:
        self._virtuales = tuple(virtuales)
        self.virtual_toggle.setVisible(bool(virtuales))
        if not virtuales:
            self.virtual_box.hide()
            return
        nombres = ", ".join(i.name for i in virtuales[:4])
        if len(virtuales) > 4:
            nombres += "…"
        clave = "net.virtual.one" if len(virtuales) == 1 else "net.virtual.many"
        flecha = "▾" if self._virtuales_abiertas else "▸"
        texto = f"{flecha}  " + _(clave).format(n=len(virtuales), nombres=nombres)
        if self.virtual_toggle.text() != texto:
            self.virtual_toggle.setText(texto)
        self.virtual_box.setVisible(self._virtuales_abiertas)
        if self._virtuales_abiertas:
            # Solo se pintan abiertas: plegadas, veinte tarjetas que nadie ve
            # no se montan ni se reescriben cada segundo.
            self.virtual_traffic.set_rows(self._filas_de_trafico(virtuales))
            self._apply_cards(virtuales, self._virtual_cards_host, "virtuales")

    def _filas_de_trafico(self, interfaces) -> list:
        d = render.DASH
        filas = [
            (interfaz.name,
             render.rate(interfaz.traffic.rx_rate_bps, self._bits),
             render.rate(interfaz.traffic.tx_rate_bps, self._bits),
             render.size(interfaz.traffic.rx_bytes),
             render.size(interfaz.traffic.tx_bytes),
             render.thousands(interfaz.traffic.rx_packets + interfaz.traffic.tx_packets),
             render.thousands(interfaz.traffic.problems) if interfaz.traffic.problems else "—")
            for interfaz in interfaces
        ]
        return filas or [(_("net.none"), d, d, d, d, d, d)]

    def _apply_cards(self, interfaces, host, grupo: str) -> None:
        # Una tarjeta por interfaz, creadas una vez y reescritas después: esta
        # página se repinta cada segundo como todas las demás.
        nombres = tuple(i.name for i in interfaces)
        if nombres != self._montadas.get(grupo):
            self._montadas[grupo] = nombres
            clear_layout(host)
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
            host.addWidget(fila)

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
            f(_("net.field.speed"), render.link_summary(interfaz) or d)
            # Una interfaz sin enlace no tiene dirección, puerta ni velocidad:
            # no son datos por leer. Cinco guiones seguidos no decían más que
            # el «sin cable» de la primera fila.
            for clave, valor in (("net.field.ipv4", interfaz.ipv4),
                                 ("net.field.mask", interfaz.netmask),
                                 ("net.field.gateway", interfaz.gateway),
                                 ("net.field.ipv6", interfaz.ipv6),
                                 ("net.field.speed", render.link_summary(interfaz))):
                grid.set_visible(_(clave), bool(valor))
            f("MTU", str(interfaz.mtu) if interfaz.mtu else d)
            f(_("gpu.field.driver"), interfaz.driver or d)
            f(_("storage.col.model"), interfaz.model or d)
            f(_("net.field.slot"), interfaz.pci_slot or d)
