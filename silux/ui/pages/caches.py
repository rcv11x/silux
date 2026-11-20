"""Página de cachés.

CPU-X enseña aquí tamaños y un benchmark de ancho de banda. El benchmark no se
puede hacer en Python de forma honesta, así que esta página apuesta por otra
cosa que sysfs sí sabe y nadie enseña: **quién comparte qué**. Que la L2 sea
privada de cada núcleo y la L3 común a los doce hilos es información que
cambia cómo se reparte trabajo entre hilos, y en una tabla de tamaños no se ve.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...i18n import _
from ... import render
from ...model import Cache, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..cachemap import CacheMap
from ..widgets import Card, ChipRow, ResponsiveRow, Table, ScrollPage




def cache_axis(snapshot: Snapshot) -> list[int]:
    """CPUs ordenadas por núcleo físico, no por índice.

    En un procesador con SMT, las CPUs 0 y 6 pueden ser el mismo núcleo. Con el
    orden natural, su L1 compartida saldría partida en dos bloques separados;
    ordenando por (socket, núcleo) quedan juntas y el mapa se lee.
    """
    return [
        cpu.index
        for cpu in sorted(snapshot.cpu.logical,
                          key=lambda c: (c.package_id, c.core_id, c.index))
    ]


class CachesPage(ScrollPage):
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

        # -- resumen --------------------------------------------------------
        summary = Card()
        self.total = QLabel("—")
        self.total.setObjectName("Headline")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.chips = ChipRow()
        # Que la L3 no sea igual en todo el procesador es la razón de ser de un
        # X3D de dos chiplets, y en una tabla de tamaños se lee como dos filas
        # cualesquiera. Va escrito.
        self.reparto = QLabel()
        self.reparto.setObjectName("Muted")
        self.reparto.setWordWrap(True)
        self.reparto.hide()
        summary.body.addWidget(self.total)
        summary.body.addWidget(self.subtitle)
        summary.body.addWidget(self.chips)
        summary.body.addWidget(self.reparto)
        layout.addWidget(summary)

        # -- mapa -----------------------------------------------------------
        map_card = Card(_("caches.card.map"))
        self.map = CacheMap(palette)
        legend = QLabel(
            _("caches.map.note")
        )
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        legend.setFont(ui_font(m.small_pt))
        map_card.body.addWidget(self.map)
        map_card.body.addWidget(legend)
        layout.addWidget(map_card)

        # -- detalle --------------------------------------------------------
        detail = Card(_("caches.card.detail"))
        self._detail = detail
        self.table = self._tabla(con_latencia=False)
        detail.body.addWidget(self.table)
        # De dónde sale la columna de latencia, cuando la hay.
        self.latency_note = QLabel(_("caches.latency.note"))
        self.latency_note.setObjectName("Muted")
        self.latency_note.setWordWrap(True)
        self.latency_note.setFont(ui_font(theme.METRICS.small_pt))
        self.latency_note.hide()
        detail.body.addWidget(self.latency_note)
        layout.addWidget(detail)
        # La latencia medida en Memoria, por nivel («L1», «L2», «L3», «RAM»),
        # en nanosegundos. Vacío hasta que alguien mide.
        self._latencias: dict[str, float] = {}
        self._ultima: Optional[Snapshot] = None

        # -- explicación ----------------------------------------------------
        notes = ResponsiveRow(min_item_width=250)
        notes.add(self._glossary(
            _("caches.card.ways"),
            _("caches.ways.note"),
        ))
        notes.add(self._glossary(
            _("caches.col.line"),
            _("caches.line.note"),
        ))
        layout.addWidget(notes)
        layout.addStretch(1)

        self._signature: tuple = ()

    @staticmethod
    def _glossary(title: str, body: str) -> Card:
        card = Card(title, flat=True)
        text = QLabel(body)
        text.setObjectName("Muted")
        text.setWordWrap(True)
        text.setFont(ui_font(theme.METRICS.small_pt))
        card.body.addWidget(text)
        return card

    @staticmethod
    def _tabla(con_latencia: bool) -> Table:
        cabeceras = [_("caches.col.level"), _("caches.col.size"), _("caches.col.count"),
                     _("caches.col.total"), _("caches.col.ways"), _("caches.col.line"),
                     _("caches.col.sets"), _("caches.col.shared")]
        if con_latencia:
            cabeceras.append(_("caches.col.latency"))
        return Table(cabeceras, numeric=(False,) + (True,) * (len(cabeceras) - 1))

    # -- actualización ------------------------------------------------------

    def set_latencies(self, por_nivel: dict) -> None:
        """Lo que tarda un acceso a cada nivel, recién medido en Memoria.

        Pone cada cifra en la fila de su nivel, que es donde se compara con
        el tamaño y las vías. Mientras no se haya medido la columna no
        existe: nada de guiones.
        """
        nuevas = {nivel: ns for nivel, ns in (por_nivel or {}).items() if ns is not None}
        if nuevas == self._latencias:
            return
        con_antes, con_ahora = bool(self._latencias), bool(nuevas)
        self._latencias = nuevas
        if con_antes != con_ahora:
            nueva = self._tabla(con_ahora)
            self._detail.body.replaceWidget(self.table, nueva)
            self.table.setParent(None)
            self.table.deleteLater()
            self.table = nueva
        self.latency_note.setVisible(con_ahora)
        self._signature = ()
        if self._ultima is not None:
            self.apply(self._ultima)

    def apply(self, snapshot: Snapshot) -> None:
        cpu = snapshot.cpu
        if not cpu.types:
            return
        self._ultima = snapshot

        grouped = self._group(snapshot)
        signature = tuple(
            (level, kind, cache.size_bytes, cache.instances, key)
            for (level, kind, key, _tam), cache in grouped.items()
        ) + (tuple(sorted(self._latencias.items())),)
        if signature == self._signature:
            return
        self._signature = signature

        total = sum(cache.total_bytes for cache in grouped.values())
        self.total.setText(_("caches.total").format(tam=render.size(total)))
        self.subtitle.setText(
            _("caches.subtitle").format(n=len(grouped),
                                        nucleos=cpu.total_cores,
                                        hilos=cpu.total_threads)
        )
        etiquetas = [
            f"{self._label(level, kind, key, cpu.hybrid)} {render.size(cache.total_bytes)}"
            for (level, kind, key, _tam), cache in grouped.items()
        ]
        if (marca := render.vcache(cpu.types[0])):
            etiquetas.insert(0, marca)
        self.chips.set_chips(etiquetas)

        if (reparto := render.l3_asimetrica(cpu.types[0])):
            self.reparto.setText(reparto)
            self.reparto.show()
        else:
            self.reparto.hide()

        self.map.set_data(cache_axis(snapshot), [
            {
                "label": self._label(level, kind, key, cpu.hybrid),
                "level": level,
                "instances": [(cpus, render.size(cache.size_bytes))
                              for cpus in cache.instance_cpus],
            }
            for (level, kind, key, _tam), cache in grouped.items()
            if cache.instance_cpus
        ])

        def latencia(level: int, kind: str) -> list[str]:
            if not self._latencias:
                return []
            # La medida es de leer datos: no dice nada de la caché de
            # instrucciones, y esa celda se queda vacía.
            if "nstr" in (kind or ""):
                return [""]
            ns = self._latencias.get(f"L{level}")
            return [render.nanoseconds(ns) if ns is not None else ""]

        filas = [
            [
                self._label(level, kind, key, cpu.hybrid),
                render.size(cache.size_bytes),
                str(cache.instances),
                render.size(cache.total_bytes),
                str(cache.ways or render.DASH),
                f"{cache.line_bytes} B" if cache.line_bytes else render.DASH,
                str(cache.sets or render.DASH),
                _("caches.shared.one" if cache.shared_by == 1
                  else "caches.shared.many").format(n=cache.shared_by),
            ] + latencia(level, kind)
            for (level, kind, key, _tam), cache in grouped.items()
        ]
        if self._latencias.get("RAM") is not None:
            # Y debajo de la última caché, lo que cuesta salirse de todas.
            filas.append([_("caches.row.ram"), "", "", "", "", "", "", "",
                          render.nanoseconds(self._latencias["RAM"])])
        self.table.set_rows(
            filas,
            tooltips=[
                _("caches.tip.cpus")
                + " | ".join(",".join(str(c) for c in group) for group in cache.instance_cpus)
                for cache in grouped.values()
            ],
        )

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _group(snapshot: Snapshot) -> dict[tuple, Cache]:
        """Una entrada por nivel, tipo, tamaño y (si es híbrida) tipo de núcleo.

        En una CPU homogénea todos los tipos de núcleo describen las mismas
        cachés, así que agrupar evita repetir cada fila.

        El tamaño entra en la clave por los Ryzen de dos chiplets con V-Cache
        en uno solo: un 7950X3D lleva 96 MB de L3 en la mitad de sus núcleos y
        32 en la otra, las dos del mismo nivel y el mismo tipo. Sin el tamaño
        se quedaba la primera que llegara y la página enseñaba 96 MB para todo
        el procesador, que es justo el dato por el que alguien compra esa
        pieza y justo la mitad del chip donde no es cierto.
        """
        grouped: dict[tuple, Cache] = {}
        hybrid = snapshot.cpu.hybrid
        for cpu_type in snapshot.cpu.types:
            for cache in cpu_type.caches:
                key = (cache.level, cache.kind, cpu_type.key if hybrid else "",
                       cache.size_bytes)
                grouped.setdefault(key, cache)
        return dict(sorted(grouped.items(),
                           key=lambda item: (item[0][0], item[0][1], -item[0][3])))

    @staticmethod
    def _label(level: int, kind: str, key: str, hybrid: bool) -> str:
        name = f"L{level}"
        if kind in ("data", "instruction"):
            name += " " + _("caches.kind.data" if kind == "data"
                            else "caches.kind.instr")
        if hybrid and key:
            name += " " + ("P" if key == "performance" else "E")
        return name
