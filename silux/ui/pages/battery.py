"""Página de batería: cuánta vida le queda a la celda.

La pregunta que trae a alguien aquí es una sola —«¿se me está muriendo la
batería?»— y la responde un número: lo que conserva de la capacidad con la que
salió de fábrica. Por eso es lo primero y lo más grande, y el resto de la
página está para dar contexto a ese número.

Los ciclos van al lado porque son su explicación: un 82 % con 600 ciclos es una
batería que ha trabajado, y un 82 % con 80 ciclos es una que se ha estropeado.

La autonomía se enseña junto al consumo de ahora y no sola. Con el equipo en
reposo salen nueve horas y compilando dos, y las dos cifras son ciertas: sin el
consumo al lado, la primera parece una promesa que el equipo no cumple.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...i18n import _
from ...model import Battery, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import (Card, ChipRow, InfoGrid, ResponsiveRow, StatTile,
                       clear_layout)

CELDA = ("bat.vendor", "bat.model", "bat.tech", "bat.voltage",
         "bat.voltage.design", "bat.capacity", "bat.design")


def _hay_topes(bateria: Battery) -> bool:
    """Si el portátil tiene un tope de carga puesto, no solo si los publica.

    Un ThinkPad sin límite configurado publica 0 y 100, que es el rango
    entero: eso es no tener tope. Un Dell con 50 y 90 sí lo tiene. Enseñar
    «0 – 100 %» hacía creer que había algo configurado.
    """
    inicio, fin = bateria.charge_start_percent, bateria.charge_end_percent
    if inicio is None and fin is None:
        return False
    return not ((inicio or 0) <= 0 and (fin if fin is not None else 100) >= 100)


def _duracion(segundos: int) -> str:
    """«3 h 20 min». Sin segundos: en una batería no significan nada."""
    horas, resto = divmod(max(segundos, 0), 3600)
    minutos = resto // 60
    if horas:
        return _("bat.hm").format(h=horas, m=f"{minutos:02d}")
    return _("bat.m").format(m=minutos)


class _SeccionBateria(QWidget):
    """Una batería. Casi siempre hay una, pero hay portátiles con dos."""

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._prefs = prefs
        m = theme.METRICS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(m.section_gap)

        self.title = QLabel("")
        self.title.setObjectName("Headline")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()
        cabecera = Card()
        cabecera.body.addWidget(self.title)
        cabecera.body.addWidget(self.subtitle)
        cabecera.body.addWidget(self.badges)
        layout.addWidget(cabecera)

        # Lo que responde a la pregunta, arriba y en grande.
        self.tiles = ResponsiveRow(min_item_width=210)
        self.salud = StatTile(_("bat.health"), "%", palette)
        self.salud.setToolTip(_("bat.health.hint"))
        self.carga = StatTile(_("bat.charge"), "%", palette)
        self.potencia = StatTile(_("bat.power"), "W", palette)
        self.autonomia = StatTile(_("bat.left"), "", palette)
        self.autonomia.setToolTip(_("bat.left.hint"))
        for tile in (self.salud, self.carga, self.potencia, self.autonomia):
            self.tiles.add(tile)
        layout.addWidget(self.tiles)

        columnas = ResponsiveRow(min_item_width=280)
        celda = Card(_("bat.card.cell"))
        self.celda = InfoGrid()
        for campo in CELDA:
            self.celda.add(_(campo))
        celda.body.addWidget(self.celda)
        columnas.add(celda)

        self.limites_card = Card(_("bat.card.limits"))
        self.limites = InfoGrid()
        self.limites.add(_("bat.limit.start"))
        self.limites.add(_("bat.limit.end"))
        self.limites_card.body.addWidget(self.limites)
        pista = QLabel(_("bat.limit.hint"))
        pista.setObjectName("Muted")
        pista.setWordWrap(True)
        self.limites_card.body.addWidget(pista)
        columnas.add(self.limites_card)
        layout.addWidget(columnas)

    def apply(self, bateria: Battery) -> None:
        d = render.DASH
        self.title.setText(bateria.model or bateria.name)
        self.subtitle.setText(" · ".join(x for x in (
            bateria.manufacturer or "", _(bateria.status or "bat.status.unknown"),
        ) if x))

        insignias = []
        if bateria.technology:
            insignias.append(bateria.technology)
        if bateria.cycles:
            insignias.append(_("bat.cycles.n").format(n=bateria.cycles))
        if bateria.design_wh:
            insignias.append(f"{bateria.design_wh:.0f} Wh")
        self.badges.set_chips(insignias)

        salud = bateria.health_percent
        self.salud.update_value(f"{salud:.0f}" if salud is not None else d)
        if salud is not None and bateria.full_wh and bateria.design_wh:
            self.salud.set_detail(_("bat.health.of").format(
                full=f"{bateria.full_wh:.1f} Wh",
                design=f"{bateria.design_wh:.1f} Wh"))

        self.carga.update_value(f"{bateria.percent:.0f}"
                             if bateria.percent is not None else d)
        if bateria.now_wh is not None:
            self.carga.set_detail(f"{bateria.now_wh:.1f} Wh")

        self.potencia.update_value(f"{bateria.power_w:.1f}"
                                if bateria.power_w is not None else d)
        self.potencia.set_detail(_(bateria.status or "bat.status.unknown"))

        # La etiqueta cambia según lo que se esté midiendo: lo que queda de
        # autonomía y lo que falta para llenarse no son la misma cifra.
        restante = bateria.seconds_left
        cargando = bateria.status == "bat.status.charging"
        # Lo que queda de autonomía y lo que falta para llenarse no son la
        # misma cifra ni se llaman igual, así que cambia el nombre del
        # recuadro. El detalle dice a qué ritmo está medido, que es lo que
        # hace creíble el número: en reposo y compilando salen cifras muy
        # distintas y las dos son ciertas.
        self.autonomia.set_label(_("bat.tofull") if cargando else _("bat.left"))
        self.autonomia.update_value(_duracion(restante) if restante else d)
        # El ritmo solo cuando hay cuenta atrás. Con la batería llena y a cero
        # vatios salía «— · a 0.0 W de ahora», que no dice nada de nada.
        self.autonomia.set_detail(
            _("bat.atrate").format(w=f"{bateria.power_w:.1f}")
            if restante and bateria.power_w else "")

        c = self.celda.set
        c(_("bat.vendor"), bateria.manufacturer or d)
        c(_("bat.model"), bateria.model or d)
        c(_("bat.tech"), bateria.technology or d)
        c(_("bat.voltage"), f"{bateria.voltage_v:.2f} V"
          if bateria.voltage_v else d)
        c(_("bat.voltage.design"), f"{bateria.design_voltage_v:.2f} V"
          if bateria.design_voltage_v else d)
        c(_("bat.capacity"), f"{bateria.full_wh:.1f} Wh"
          if bateria.full_wh else d)
        c(_("bat.design"), f"{bateria.design_wh:.1f} Wh"
          if bateria.design_wh else d)

        # La tarjeta de límites solo si el portátil los trae y están puestos.
        # Un ThinkPad publica 0 y 100 cuando no hay tope configurado, y
        # enseñarlo así da a entender que hay algo puesto: 0 y 100 es
        # justamente no tener límite. Un Dell con 50 y 90 sí los tiene.
        tiene = _hay_topes(bateria)
        self.limites_card.setVisible(tiene)
        if tiene:
            l = self.limites.set  # noqa: E741
            l(_("bat.limit.start"),
              f"{bateria.charge_start_percent} %"
              if bateria.charge_start_percent is not None else d)
            l(_("bat.limit.end"),
              f"{bateria.charge_end_percent} %"
              if bateria.charge_end_percent is not None else d)


class BatteryPage(QScrollArea):
    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._prefs = prefs
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        cuerpo = QWidget()
        self._layout = QVBoxLayout(cuerpo)
        m = theme.METRICS
        self._layout.setContentsMargins(m.page_margin, m.page_margin,
                                        m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        self.vacio = QLabel(_("bat.none"))
        self.vacio.setObjectName("Muted")
        self.vacio.setWordWrap(True)
        self._layout.addWidget(self.vacio)

        self._host = QVBoxLayout()
        self._host.setSpacing(m.section_gap)
        self._layout.addLayout(self._host)
        self._layout.addStretch(1)
        self.setWidget(cuerpo)

        self._secciones: list[_SeccionBateria] = []

    def apply(self, snapshot: Snapshot) -> None:
        baterias = snapshot.batteries
        self.vacio.setVisible(not baterias)

        # Se crean una vez y se reutilizan, como el resto de páginas que se
        # refrescan cada segundo: recrear widgets en cada muestreo deja miles
        # vivos y hace parpadear la ventana.
        while len(self._secciones) < len(baterias):
            seccion = _SeccionBateria(self._palette, self._prefs)
            self._secciones.append(seccion)
            self._host.addWidget(seccion)
        for indice, seccion in enumerate(self._secciones):
            visible = indice < len(baterias)
            seccion.setVisible(visible)
            if visible:
                seccion.apply(baterias[indice])
