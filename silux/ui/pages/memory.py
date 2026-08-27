"""Página de memoria.

Sin permisos solo se sabe el total, así que la página no finge: enseña lo que
puede y explica exactamente qué falta, cuánto se ganaría y con un botón para
pedirlo. Nada de diálogos de contraseña al arrancar.

Los zócalos vacíos se enseñan igual que los ocupados. Saber que quedan dos
libres es la mitad de la razón por la que alguien abre esta pestaña.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import render
from ...model import MemoryModule, Snapshot
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..widgets import (
    Card, ChipRow, InfoGrid, Notice, ResponsiveRow, StackedBar, Table,
    clear_layout,
)

from ...model import Need

NEED_TITLES = {
    Need.ROOT: "Hace falta elevar permisos",
    Need.DATABASE: "Falta en la base de datos",
    Need.HARDWARE: "Este equipo no lo expone",
    Need.DRIVER: "Falta un módulo del kernel",
    Need.PLATFORM: "Todavía no está implementado",
    Need.ERROR: "Falló al leerse",
}

MODULE_FIELDS = ("Fabricante", "Chips", "Referencia", "Tipo", "Capacidad",
                 "Catalogado a", "Funcionando a", "Rangos", "Voltaje",
                 "Formato", "Perfiles", "Fabricado", "Banco")

TIMING_HEADERS = ("Perfil", "Velocidad", "CL", "tRCD", "tRP", "tRAS", "tRC", "Voltaje")


class MemoryPage(QScrollArea):
    elevation_requested = Signal()

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
        self.elevation = self._build_elevation()
        layout.addWidget(self.elevation)

        self._slots_host = ResponsiveRow(min_item_width=290)
        layout.addWidget(self._slots_host)

        self.timings_card = Card("Perfiles y temporizaciones")
        self.timings = Table(TIMING_HEADERS,
                             numeric=(False, True, True, True, True, True, True, True))
        explanation = QLabel(
            "El SPD es un chip que lleva cada módulo con sus características. "
            "Dice a qué velocidad puede ir, mientras que la BIOS decide a cuál "
            "va de verdad: sin XMP activado se queda en los valores "
            "conservadores de JEDEC."
        )
        explanation.setObjectName("Muted")
        explanation.setWordWrap(True)
        explanation.setFont(ui_font(theme.METRICS.small_pt))
        self.timings_card.body.addWidget(self.timings)
        self.timings_card.body.addWidget(explanation)
        layout.addWidget(self.timings_card)

        self._notices_host = QVBoxLayout()
        self._notices_host.setSpacing(6)
        layout.addLayout(self._notices_host)

        layout.addStretch(1)

        self._module_signature: tuple = ()
        self._notice_signature: tuple = ()
        self._slot_grids: list[InfoGrid] = []

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> QWidget:
        card = Card()
        self.title = QLabel("Leyendo la memoria…")
        self.title.setObjectName("Headline")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subhead")
        self.badges = ChipRow()
        self.bar = StackedBar(self._p)

        card.body.addWidget(self.title)
        card.body.addWidget(self.subtitle)
        card.body.addWidget(self.badges)
        card.body.addWidget(self.bar)
        return card

    def _build_elevation(self) -> QWidget:
        card = Card("Detalle de los módulos")

        self.elevation_text = QLabel("")
        self.elevation_text.setObjectName("NoticeBody")
        self.elevation_text.setWordWrap(True)
        self.elevation_text.setFont(ui_font(theme.METRICS.small_pt))

        self.elevation_hint = QLabel("")
        self.elevation_hint.setObjectName("Muted")
        self.elevation_hint.setWordWrap(True)
        self.elevation_hint.setFont(ui_font(theme.METRICS.small_pt))

        self.elevation_button = QPushButton("Leer con permisos de administrador")
        self.elevation_button.setToolTip(
            "Lanza un ayudante mínimo mediante polkit que solo sabe leer la "
            "tabla SMBIOS y unos registros del procesador.\n"
            "No ejecuta órdenes ni escribe nada."
        )
        self.elevation_button.clicked.connect(self.elevation_requested)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.elevation_button)
        row.addStretch(1)

        card.body.addWidget(self.elevation_text)
        card.body.addWidget(self.elevation_hint)
        card.body.addLayout(row)
        return card

    # -- actualización ------------------------------------------------------

    def apply(self, snapshot: Snapshot) -> None:
        memory = snapshot.system.memory
        array = snapshot.memory_array
        modules = snapshot.modules

        self.title.setText(f"{render.size(memory.total_bytes)} de memoria")
        self.subtitle.setText(self._subtitle(snapshot))
        self._apply_badges(snapshot)

        self.bar.set_segments(
            [
                ("Aplicaciones", memory.apps_bytes, "accent"),
                ("Caché", memory.cache_bytes, "info"),
                ("Buffers", memory.buffers_bytes, "warn"),
                ("Libre", memory.free_bytes, "line"),
            ],
            total=memory.total_bytes,
            formatter=render.size,
        )

        display = self._display_modules(snapshot)
        self._apply_elevation(snapshot)
        self._apply_modules(tuple(display), array)
        self._apply_timings(display)
        self._apply_notices(snapshot)

    def _apply_notices(self, snapshot: Snapshot) -> None:
        # La tarjeta de elevación ya explica lo de los permisos, así que aquí
        # solo van las notas que no cubre: por ejemplo, un SPD que no se sabe
        # interpretar todavía.
        notes = [n for n in snapshot.notes
                 if n.path.startswith("spd")
                 or (n.path.startswith("modules") and snapshot.modules)]
        signature = tuple((n.path, n.need) for n in notes)
        if signature == self._notice_signature:
            return
        self._notice_signature = signature

        clear_layout(self._notices_host)
        for note in notes:
            self._notices_host.addWidget(
                Notice(NEED_TITLES.get(note.need, note.need.value), note.message, note.hint)
            )

    def _subtitle(self, snapshot: Snapshot) -> str:
        array = snapshot.memory_array
        modules = snapshot.modules
        if not modules:
            if snapshot.spd:
                catalogados = {i.rated_mts for i in snapshot.spd if i.rated_mts}
                velocidad = f" a {max(catalogados)} MT/s" if catalogados else ""
                cuantos = len(snapshot.spd)
                return (f"{cuantos} {render.plural(cuantos, 'módulo', 'módulos')} "
                        f"{render.plural(cuantos, 'leído', 'leídos')} de su chip SPD"
                        f"{velocidad} · el zócalo y la capacidad necesitan permisos")
            return "El detalle por módulo necesita permisos de administrador"
        ocupados = sum(1 for m in modules if m.populated)
        partes = [f"{ocupados} de {len(modules)} zócalos ocupados"]
        if array and array.max_capacity_bytes:
            partes.append(f"admite hasta {render.size(array.max_capacity_bytes)}")
        if array and array.error_correction:
            partes.append(f"ECC: {array.error_correction.lower()}")
        return " · ".join(partes)

    def _apply_badges(self, snapshot: Snapshot) -> None:
        modules = [m for m in self._display_modules(snapshot) if m.populated]
        wanted = []
        if modules:
            tipos = {m.type for m in modules if m.type}
            wanted.extend(sorted(tipos))
            catalogadas = {m.rated_mts for m in modules}
            catalogadas.discard(None)
            wanted.extend(f"{v} MT/s" for v in sorted(catalogadas))
            if any(m.underclocked for m in modules):
                wanted.append("por debajo de su velocidad")
            if any(m.has_ecc for m in modules):
                wanted.append("ECC")
        self.badges.set_chips(wanted, highlight_first=True)

    def _apply_elevation(self, snapshot: Snapshot) -> None:
        state = snapshot.privileged
        if snapshot.modules:
            self.elevation.hide()
            return

        self.elevation.show()
        if state.already_root:
            self.elevation_text.setText(
                "El programa ya corre como administrador pero la tabla SMBIOS "
                "no se pudo leer."
            )
            self.elevation_button.hide()
        elif not state.supported:
            self.elevation_text.setText(
                "No se encuentra pkexec, así que no hay forma de pedir permisos."
            )
            self.elevation_hint.setText(
                "Se instala con el paquete polkit de la distribución. "
                "También funciona lanzando el programa entero como root."
            )
            self.elevation_button.hide()
        else:
            leidos = len(snapshot.spd)
            if leidos:
                cabecera = ("El módulo de arriba sale" if leidos == 1
                            else f"Los {leidos} módulos de arriba salen")
                self.elevation_text.setText(
                    f"{cabecera} de su propio chip SPD, que se lee sin permisos. "
                    "La capacidad de cada uno, en qué zócalo va, cuántos quedan "
                    "libres y a qué velocidad los ha puesto la BIOS están en la "
                    "tabla SMBIOS, que el kernel reserva al administrador."
                )
            else:
                self.elevation_text.setText(
                    "El detalle de los módulos está en la tabla SMBIOS, que el "
                    "kernel reserva al administrador porque junto a esos campos "
                    "van los números de serie del equipo."
                )
            self.elevation_hint.setText(
                state.message or
                "El ayudante que se lanza solo sabe leer esa tabla y unos "
                "registros del procesador: no ejecuta órdenes ni escribe nada."
            )
            self.elevation_button.show()

    @staticmethod
    def _display_modules(snapshot: Snapshot) -> list[MemoryModule]:
        """Los módulos a enseñar, vengan de donde vengan.

        Con permisos manda SMBIOS, que sabe el zócalo y la capacidad. Sin
        ellos se fabrican tarjetas a partir del SPD, que se lee sin pedir
        nada: menos campos, pero fabricante, referencia y velocidad
        catalogada ya están ahí.
        """
        if snapshot.modules:
            return list(snapshot.modules)
        return [
            MemoryModule(
                locator=f"Zócalo {info.slot}",
                populated=True,
                type=info.dram_type,
                form_factor=info.module_type,
                manufacturer=info.manufacturer,
                part_number=info.part_number,
                rank=info.ranks,
                data_width=info.bus_width,
                total_width=(info.bus_width or 0) + info.ecc_bits or None,
                spd=info,
            )
            for info in snapshot.spd
        ]

    def _apply_modules(self, modules: tuple[MemoryModule, ...], array) -> None:
        signature = tuple((m.locator, m.part_number, m.size_bytes,
                           m.spd.address if m.spd else None) for m in modules)
        if signature == self._module_signature:
            return
        self._module_signature = signature

        clear_layout(self._slots_host.layout())
        self._slots_host._items.clear()
        self._slot_grids.clear()

        for module in modules:
            card = Card(module.locator or "Zócalo")
            if not module.populated:
                empty = QLabel("Vacío")
                empty.setObjectName("Muted")
                empty.setFont(ui_font(theme.METRICS.small_pt))
                card.body.addWidget(empty)
                self._slots_host.add(card)
                continue

            grid = InfoGrid()
            for name in MODULE_FIELDS:
                grid.add(name)
            card.body.addWidget(grid)
            self._fill(grid, module)
            self._slot_grids.append(grid)
            self._slots_host.add(card)

    @staticmethod
    def _fill(grid: InfoGrid, module: MemoryModule) -> None:
        d = render.DASH
        spd = module.spd

        grid.set("Fabricante", module.manufacturer or (spd.manufacturer if spd else None) or d)
        grid.set("Chips", (spd.dram_manufacturer if spd else None) or d,
                 tooltip="Quién fabricó el silicio, que a menudo no es quien "
                         "vende el módulo. Lo dice el SPD, no la tabla SMBIOS.")
        grid.set("Referencia", module.part_number or (spd.part_number if spd else None) or d)
        grid.set("Tipo", module.type or (spd.dram_type if spd else None) or d)
        # La capacidad sale de SMBIOS, que pide permisos, pero el SPD de DDR5
        # la trae en la densidad de sus chips y ese se lee sin pedir nada.
        capacidad = module.size_bytes or (spd.capacity_bytes if spd else None)
        grid.set("Capacidad", render.size(capacidad) if capacidad else d,
                 tooltip="Calculada desde el propio chip SPD del módulo."
                 if not module.size_bytes and capacidad else "")

        rated = module.rated_mts
        grid.set("Catalogado a", f"{rated} MT/s" if rated else d,
                 tooltip="Lo que el módulo declara saber dar, según su propio "
                         "chip SPD." if spd else "")

        actual = module.configured_mts or module.speed_mts
        funcionando = f"{actual} MT/s" if actual else d
        if module.underclocked:
            funcionando += "   ⚠"
        grid.set("Funcionando a", funcionando,
                 tooltip=(f"Va a {actual} MT/s de los {rated} que admite. Puede "
                          "ser el perfil XMP sin activar, o el límite oficial "
                          "de memoria del procesador, que en muchos modelos "
                          "está por debajo de lo que aguantan los módulos.")
                 if module.underclocked else "")

        rangos = str(module.rank) if module.rank else d
        if module.has_ecc:
            rangos += "   con ECC"
        grid.set("Rangos", rangos)

        voltaje = (f"{module.voltage_configured_mv / 1000:.2f} V"
                   if module.voltage_configured_mv
                   else (f"{spd.jedec.voltage_v:.2f} V" if spd and spd.jedec
                         and spd.jedec.voltage_v else d))
        grid.set("Voltaje", voltaje)
        grid.set("Formato", module.form_factor or (spd.module_type if spd else None) or d)

        perfiles = spd.overclock_profiles if spd else ()
        grid.set("Perfiles", ", ".join(perfiles) if perfiles else d,
                 tooltip="Temporizaciones que el fabricante garantiza por "
                         "encima de las de JEDEC. Se reconoce que están, pero "
                         "sus formatos no son públicos y sus cifras no se "
                         "interpretan: darlas a ojo sería inventarlas."
                 if perfiles else "")
        grid.set("Fabricado", (spd.manufactured if spd else None) or d)
        grid.set("Banco", module.bank or d)

    def _apply_timings(self, modules: list[MemoryModule]) -> None:
        rows: list[list[str]] = []
        tooltips: list[str] = []
        # Los zócalos de una placa se llaman casi igual —«Controller0-ChannelA»
        # y «Controller0-ChannelB»— y lo que los distingue está al final, que
        # es justo lo que se recorta cuando no cabe: las dos filas salían como
        # «Controller0-C…» y no había forma de saber cuál era cuál.
        corto = _sin_el_prefijo_comun(
            [m.locator or (m.spd.address if m.spd else "") for m in modules])
        for module in modules:
            spd = module.spd
            if spd is None:
                continue
            etiqueta = corto.get(module.locator or spd.address) or \
                module.locator or spd.address
            for timing in (spd.jedec, *spd.profiles):
                if timing is None:
                    continue
                rows.append([
                    f"{etiqueta} · {timing.name}",
                    f"{timing.speed_mts} MT/s",
                    str(timing.cl or render.DASH),
                    str(timing.trcd or render.DASH),
                    str(timing.trp or render.DASH),
                    str(timing.tras or render.DASH),
                    str(timing.trc or render.DASH),
                    f"{timing.voltage_v:.2f} V" if timing.voltage_v else render.DASH,
                ])
                tooltips.append(f"{spd.part_number or ''} · {spd.address}".strip(" ·"))

        self.timings_card.setVisible(bool(rows))
        if rows:
            self.timings.set_rows(rows, tooltips=tooltips)


def _sin_el_prefijo_comun(nombres: list[str]) -> dict[str, str]:
    """Quita a todos el trozo de nombre que comparten, si queda algo detrás.

    Con un solo módulo no hay nada que comparar y se devuelve tal cual.
    """
    utiles = [n for n in nombres if n]
    if len(utiles) < 2:
        return {}
    # Solo se toca lo que de verdad no cabe. «Zócalo 0» y «Zócalo 2» entran
    # enteros, y dejarlos en «0» y «2» quitaría contexto en vez de darlo.
    if max(len(n) for n in utiles) <= 14:
        return {}
    comun = utiles[0]
    for nombre in utiles[1:]:
        while not nombre.startswith(comun):
            comun = comun[:-1]
            if not comun:
                return {}
    # Se corta por el último separador, para no partir una palabra por la mitad.
    corte = max(comun.rfind(c) for c in "-_ .") + 1
    if corte <= 0:
        return {}
    recortados = {n: n[corte:] for n in utiles}
    # Si alguno se queda sin nada, el prefijo era todo el nombre: mejor dejarlo.
    return recortados if all(recortados.values()) else {}
