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
from ...model import Disk, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import (Card, ChipRow, InfoGrid, Notice, ResponsiveRow,
                       StackedBar, StatTile, Table,
                       boton_de_permiso_permanente, clear_layout)

DISK_HEADERS = ("Unidad", "Modelo", "Tipo", "Capacidad", "Ocupado",
                "Temperatura", "Leyendo", "Escribiendo")
PART_HEADERS = ("Partición", "Sistema", "Montada en", "Tamaño", "Usado", "Libre")

DISK_FIELDS = ("Modelo", "Fabricante", "Tipo", "Conexión", "Capacidad",
               "Firmware", "Sector lógico", "Sector físico", "Planificador",
               "Enlace", "Temperatura", "Horas encendido", "Escrito en total",
               "Vida restante")

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

        disk_card = Card("Unidades")
        self.disks = Table(DISK_HEADERS,
                           numeric=(False, False, False, True, True, True, True, True))
        disk_card.body.addWidget(self.disks)
        layout.addWidget(disk_card)

        part_card = Card("Particiones montadas")
        self.parts = Table(PART_HEADERS, numeric=(False, False, False, True, True, True))
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
        self.title = QLabel("Leyendo los discos…")
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
        self.tile_read = StatTile("Leyendo", "", self._p)
        self.tile_write = StatTile("Escribiendo", "", self._p)
        self.tile_free = StatTile("Espacio libre", "", self._p)
        self.tile_temp = StatTile("Más caliente", "°C", self._p)
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
        card = Card("Estado de los discos")
        self.elevation_text = QLabel(
            "Las horas de encendido, los terabytes escritos y el desgaste los "
            "guarda cada disco en sus propios contadores de diagnóstico. El "
            "kernel reserva esos comandos al administrador porque son los "
            "mismos que sirven para borrar un disco."
        )
        self.elevation_text.setObjectName("NoticeBody")
        self.elevation_text.setWordWrap(True)

        detalle = QLabel(
            "El ayudante que se lanza solo sabe pedir diagnóstico y leer unas "
            "tablas del sistema: no ejecuta órdenes ni escribe nada."
        )
        detalle.setObjectName("Muted")
        detalle.setWordWrap(True)

        self.elevation_button = QPushButton("Leer con permisos de administrador")
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
                f"Leído el diagnóstico de {leidos} de {len(discos)} unidades. "
                "Las que faltan no lo publican o no respondieron."
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
                hint="Lo dice el propio disco en su registro de diagnóstico. "
                     "Conviene tener una copia de lo que haya dentro.",
                tone="bad" if nivel == "crítico" else "warn",
            ))

    def _apply_header(self, discos) -> None:
        d = render.DASH
        if not discos:
            self.title.setText("Sin unidades de almacenamiento")
            self.subtitle.setText("")
            self.total_bar.hide()
            return

        total = sum(x.size_bytes or 0 for x in discos)
        usado = sum(x.used_bytes or 0 for x in discos)
        self.title.setText(f"{render.size(total)} en {len(discos)} "
                           f"{render.plural(len(discos), 'unidad', 'unidades')}")
        montadas = sum(len(x.mounted_partitions) for x in discos)
        self.subtitle.setText(
            f"{render.size(usado)} ocupados en {montadas} "
            f"{render.plural(montadas, 'partición montada', 'particiones montadas')}"
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
            segmentos = [("Ocupado", usado, "accent"), ("Libre", libre, "line")]
            if sin_montar:
                segmentos.append(("Sin montar", sin_montar, "muted"))
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
        cuantos = f"suma de {len(discos)} {render.plural(len(discos), 'unidad', 'unidades')}"
        self.tile_read.set_detail(cuantos)
        self.tile_write.set_detail(cuantos)

        libres = [p.free_bytes for x in discos for p in x.mounted_partitions
                  if p.free_bytes is not None]
        self.tile_free.update_value(render.size(sum(libres)) if libres else render.DASH)
        if libres:
            self.tile_free.set_detail(f"en {len(libres)} "
                                      f"{render.plural(len(libres), 'partición', 'particiones')}")

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
            self.tile_temp.set_detail("ningún disco publica su temperatura")

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
        ] or [("Sin unidades", d, d, d, d, d, d, d)])

        filas = [
            (p.name, p.filesystem or d, p.mountpoint or d,
             render.size(p.size_bytes),
             f"{render.size(p.used_bytes)}   ({p.used_percent:.0f} %)"
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
                    grid.add(campo)
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
                [("Ocupado", usado, "accent"),
                 ("Libre", max(0, disco.size_bytes - usado), "line")],
                total=disco.size_bytes, formatter=render.size,
            )
            barra.show()
        else:
            barra.hide()

        f = grid.set
        f("Modelo", disco.model or d)
        f("Fabricante", disco.vendor or d)
        f("Tipo", disco.kind or d,
          tooltip="No hay ningún campo que lo diga: se deduce de si el kernel "
                  "considera que el disco gira y de por qué bus va conectado.")
        f("Conexión", (disco.transport or d).upper() if disco.transport else d)
        f("Capacidad", render.size(disco.size_bytes))
        f("Firmware", disco.firmware or d)
        f("Sector lógico", f"{disco.logical_sector} B" if disco.logical_sector else d)
        f("Sector físico", f"{disco.physical_sector} B" if disco.physical_sector else d,
          tooltip="Los discos modernos trabajan en sectores de 4 KB por dentro "
                  "aunque le digan al sistema que son de 512 B.")
        f("Planificador", disco.scheduler or d,
          tooltip="Cómo ordena el kernel las peticiones antes de mandarlas al "
                  "disco. En un NVMe suele estar desactivado porque el propio "
                  "disco lo hace mejor.")
        f("Enlace", render.pcie_link(disco.link) if disco.link else d)
        f("Temperatura", render.temperature(disco.temp_c, self._prefs.fahrenheit))

        salud = disco.health
        f("Horas encendido", f"{salud.power_on_hours:n} h" if salud.power_on_hours else d)
        f("Escrito en total", render.size(salud.written_bytes) if salud.written_bytes else d,
          tooltip="El TBW: cuántos datos se han escrito en este disco desde que "
                  "salió de fábrica. Es lo que consume la vida de un SSD.")
        f("Vida restante",
          f"{salud.life_left_percent} %" if salud.life_left_percent is not None else d,
          tooltip="Lo que el propio disco calcula que le queda, según su "
                  "contador de desgaste.")
