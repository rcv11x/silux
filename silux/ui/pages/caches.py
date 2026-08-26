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
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ... import render
from ...model import Cache, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import CacheMap, Card, ChipRow, ResponsiveRow, Table

KIND_LABELS = {"data": "datos", "instruction": "instrucciones", "unified": "unificada"}


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


class CachesPage(QScrollArea):
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
        summary.body.addWidget(self.total)
        summary.body.addWidget(self.subtitle)
        summary.body.addWidget(self.chips)
        layout.addWidget(summary)

        # -- mapa -----------------------------------------------------------
        map_card = Card("Quién comparte qué")
        self.map = CacheMap(palette)
        legend = QLabel(
            "Cada bloque es una instancia física de caché; su anchura son las "
            "CPUs lógicas que la comparten."
        )
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        legend.setFont(ui_font(m.small_pt))
        map_card.body.addWidget(self.map)
        map_card.body.addWidget(legend)
        layout.addWidget(map_card)

        # -- detalle --------------------------------------------------------
        detail = Card("Detalle por nivel")
        self.table = Table(
            ("Nivel", "Tamaño", "Nº", "Total", "Vías", "Línea", "Conjuntos", "Comparten"),
            numeric=(False, True, True, True, True, True, True, True),
        )
        detail.body.addWidget(self.table)
        layout.addWidget(detail)

        # -- explicación ----------------------------------------------------
        notes = ResponsiveRow(min_item_width=250)
        notes.add(self._glossary(
            "Vías y conjuntos",
            "Una caché de N vías guarda cada dirección en uno de N sitios "
            "posibles. Más vías reducen los choques entre datos que compiten "
            "por el mismo conjunto, a costa de una búsqueda más cara.",
        ))
        notes.add(self._glossary(
            "Línea",
            "La unidad mínima que viaja entre memoria y caché. Leer un solo "
            "byte trae la línea entera, y por eso recorrer datos contiguos es "
            "mucho más rápido que saltar por la memoria.",
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

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        cpu = snapshot.cpu
        if not cpu.types:
            return

        grouped = self._group(snapshot)
        signature = tuple(
            (level, kind, cache.size_bytes, cache.instances, key)
            for (level, kind, key), cache in grouped.items()
        )
        if signature == self._signature:
            return
        self._signature = signature

        total = sum(cache.total_bytes for cache in grouped.values())
        self.total.setText(f"{render.size(total)} de caché en total")
        self.subtitle.setText(
            f"{len(grouped)} cachés distintas sobre {cpu.total_cores} núcleos "
            f"y {cpu.total_threads} hilos"
        )
        self.chips.set_chips(
            f"{self._label(level, kind, key, cpu.hybrid)} {render.size(cache.total_bytes)}"
            for (level, kind, key), cache in grouped.items()
        )

        self.map.set_data(cache_axis(snapshot), [
            {
                "label": self._label(level, kind, key, cpu.hybrid),
                "level": level,
                "instances": [(cpus, render.size(cache.size_bytes))
                              for cpus in cache.instance_cpus],
            }
            for (level, kind, key), cache in grouped.items()
            if cache.instance_cpus
        ])

        self.table.set_rows(
            [
                [
                    self._label(level, kind, key, cpu.hybrid),
                    render.size(cache.size_bytes),
                    str(cache.instances),
                    render.size(cache.total_bytes),
                    str(cache.ways or render.DASH),
                    f"{cache.line_bytes} B" if cache.line_bytes else render.DASH,
                    str(cache.sets or render.DASH),
                    f"{cache.shared_by} hilo{'s' if cache.shared_by != 1 else ''}",
                ]
                for (level, kind, key), cache in grouped.items()
            ],
            tooltips=[
                "CPUs por instancia: "
                + " | ".join(",".join(str(c) for c in group) for group in cache.instance_cpus)
                for cache in grouped.values()
            ],
        )

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _group(snapshot: Snapshot) -> dict[tuple, Cache]:
        """Una entrada por nivel, tipo y —si la CPU es híbrida— tipo de núcleo.

        En una CPU homogénea todos los tipos de núcleo describen las mismas
        cachés, así que agrupar evita repetir cada fila.
        """
        grouped: dict[tuple, Cache] = {}
        hybrid = snapshot.cpu.hybrid
        for cpu_type in snapshot.cpu.types:
            for cache in cpu_type.caches:
                key = (cache.level, cache.kind, cpu_type.key if hybrid else "")
                grouped.setdefault(key, cache)
        return dict(sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])))

    @staticmethod
    def _label(level: int, kind: str, key: str, hybrid: bool) -> str:
        name = f"L{level}"
        if kind in ("data", "instruction"):
            name += " " + ("datos" if kind == "data" else "instr.")
        if hybrid and key:
            name += " " + ("P" if key == "performance" else "E")
        return name
