"""Una imagen con el resumen del equipo, para pegar donde sea.

La gente comparte capturas de la ventana, y eso tiene dos problemas. Uno es
que sale lo que haya en pantalla en ese momento, recortado a mano y de un
tamaño distinto cada vez, así que dos capturas de dos personas no se pueden
poner una al lado de otra. El otro es peor: una captura de la ventana lleva
dentro el nombre del equipo, las direcciones y los números de serie, y quien la
pega en un canal público casi nunca se acuerda.

Esto dibuja una tarjeta aparte, con los datos ya anonimizados por el mismo
camino que el informe. No es una captura: es una composición, así que sale
igual en todos los equipos y se lee igual de lejos.

Sin logos de fabricante a propósito. Los de AMD, Intel y NVIDIA son marcas
registradas y meterlos en un programa GPL trae más problemas de los que
resuelve; lo que identifica a una pieza es su nombre, que ya está escrito.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap

from .. import __version__, render, updates
from ..i18n import _
from ..model import Snapshot
from ..privacidad import anonymize
from . import theme
from .theme import Palette

# Fija y generosa: lo que se comparte en un chat se ve en miniatura hasta que
# alguien lo abre, así que el texto tiene que aguantar el encogido. Y fija
# también para que dos tarjetas de dos equipos se puedan comparar sin
# escalarlas.
ANCHO = 900
MARGEN = 36
ALTO_FILA = 54
# Where the values start, and the least room between a label and its value.
VALUE_COLUMN = 150
LABEL_GAP = 12
# From a row's edge to its text: a row's band stays inside the margins.
PADDING = 12
# The line under the title, and where the rows start.
HEADER_LINE = MARGEN + 76
BODY_TOP = HEADER_LINE + 12


def _fila(snapshot: Snapshot) -> list[tuple[str, str, str]]:
    """Qué se enseña y en qué orden: etiqueta, lo principal, el detalle.

    El orden es el mismo que el de la barra lateral, que es el que la gente ya
    tiene aprendido: primero lo que identifica la pieza, después lo que la
    describe.
    """
    filas: list[tuple[str, str, str]] = []
    d = render.DASH

    if snapshot.cpu.types:
        tipo = snapshot.cpu.types[0]
        top_hz = tipo.clocks.max_turbo_hz or tipo.clocks.max_hz
        # What is missing goes, not a dash between two data.
        detalle = " · ".join(x for x in (
            render.counted("share.cores", snapshot.cpu.total_cores),
            render.counted("share.threads", snapshot.cpu.total_threads),
            render.hz(top_hz) if top_hz else "",
            tipo.codename or "",
        ) if x)
        filas.append((_("nav.cpu"), render.cpu_short_name(tipo.brand), detalle))

    for gpu in snapshot.gpus:
        memoria = gpu.memory.total_bytes if gpu.memory else None
        detalle = " · ".join(x for x in (
            render.size(memoria) if memoria else "",
            gpu.memory.kind if gpu.memory and gpu.memory.kind else "",
            gpu.driver or "",
        ) if x)
        filas.append((_("nav.graphics"), render.gpu_name(gpu), detalle))

    memoria = snapshot.system.memory
    if memoria.total_bytes:
        modulos = [m for m in snapshot.modules if m.size_bytes]
        detalle = ""
        if modulos:
            primero = modulos[0]
            detalle = " · ".join(x for x in (
                render.counted("share.modules", len(modulos)),
                primero.type or "",
                f"{render.memory_speed(primero.speed_mts)} MT/s" if primero.speed_mts else "",
            ) if x)
        elif snapshot.spd:
            spd = snapshot.spd[0]
            detalle = " · ".join(x for x in (
                render.counted("share.modules", len(snapshot.spd)),
                spd.dram_type or "",
            ) if x)
        elif memoria.swap_total_bytes:
            # The modules need permissions; the swap is known, and the row
            # keeps the two lines of the others.
            detalle = _("share.memory.swap").format(size=render.size(memoria.swap_total_bytes))
        filas.append((_("nav.memory"), render.size(memoria.total_bytes), detalle))

    if (nombre := snapshot.board.display_name):
        filas.append((_("nav.board"), nombre, render.bios_summary(snapshot.board)))

    if snapshot.disks:
        total = sum(disco.size_bytes or 0 for disco in snapshot.disks)
        detalle = " · ".join(render.disk_kinds(snapshot.disks))
        filas.append((_("nav.storage"),
                      render.counted("share.units", len(snapshot.disks),
                                     tam=render.decimal_size(total)),
                      detalle))

    sistema = snapshot.system
    if sistema.distribution or sistema.kernel:
        detalle = " · ".join(x for x in (sistema.kernel or "",
                                         sistema.desktop or "") if x)
        filas.append((_("nav.system"), sistema.distribution or d, detalle))

    return filas


def dibujar(snapshot: Snapshot, palette: Palette,
            anonimo: bool = True) -> QPixmap:
    """La tarjeta, lista para guardar o para el portapapeles.

    Anónima por omisión, y no como opción escondida: esto existe para pegarlo
    en un sitio público, así que lo seguro es lo que pasa si nadie toca nada.
    """
    if anonimo:
        snapshot = anonymize(snapshot)
    subtitle = f"{_('share.card.machine')} · {time.strftime('%d/%m/%Y')}"
    return _compose(_machine_summary(snapshot), subtitle, _fila(snapshot), palette)


def _machine_summary(snapshot: Snapshot) -> str:
    """The machine in one line, without its name: that is exactly what
    isn't published."""
    parts = []
    if snapshot.cpu.types:
        parts.append(render.cpu_short_name(snapshot.cpu.types[0].brand))
    if snapshot.gpus:
        parts.append(render.gpu_name(snapshot.gpus[snapshot.working_gpu]))
    return " · ".join(parts)


def _card(title: str, subtitle: str, body_height: int, paint_body,
          palette: Palette) -> QPixmap:
    """Every card: the mark, `title` and `subtitle` above, what
    `paint_body(painter, top)` draws, and the version below."""
    height = BODY_TOP + body_height + MARGEN + 28

    pixmap = QPixmap(ANCHO, height)
    pixmap.fill(QColor(palette.bg))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    _cabecera(painter, palette, title, subtitle)
    paint_body(painter, BODY_TOP)
    _pie(painter, palette, height)

    painter.end()
    return pixmap


def _compose(title: str, subtitle: str, rows: list[tuple[str, str, str]],
             palette: Palette) -> QPixmap:
    """A card with one line per row: its label, its value and a detail."""
    column = value_column(rows)

    def body(painter: QPainter, top: int) -> None:
        for index, (label, value, detail) in enumerate(rows):
            _renglon(painter, palette, top + index * ALTO_FILA, label, value, detail,
                     index, column)

    return _card(title, subtitle, len(rows) * ALTO_FILA, body, palette)


def _cabecera(pintor: QPainter, p: Palette, title: str, subtitle: str) -> None:
    # La marca delante del nombre: la misma de la barra lateral, para que la
    # imagen se reconozca como de este programa donde acabe pegada.
    from . import icons

    marca = icons.mark(p.bg == theme.DARK.bg, 28)
    left = MARGEN
    if not marca.isNull():
        pintor.drawPixmap(QRectF(MARGEN, MARGEN + 2, 28, 28), marca, QRectF(marca.rect()))
        left = MARGEN + 40
    width = ANCHO - MARGEN - left

    big = QFont()
    big.setPointSize(20)
    big.setWeight(QFont.Weight.DemiBold)
    pintor.setFont(big)
    pintor.setPen(QColor(p.ink))
    pintor.drawText(QPointF(left, MARGEN + 26),
                    QFontMetrics(big).elidedText(title, Qt.TextElideMode.ElideRight, width))

    small = QFont()
    small.setPointSize(11)
    pintor.setFont(small)
    pintor.setPen(QColor(p.ink_dim))
    pintor.drawText(QPointF(left, MARGEN + 56),
                    QFontMetrics(small).elidedText(subtitle, Qt.TextElideMode.ElideRight, width))

    _rule(pintor, p, HEADER_LINE)


def _rule(pintor: QPainter, p: Palette, y: int) -> None:
    """A line from margin to margin, one pixel exactly: drawn as a line it
    blurred over two and its ends went into the margins."""
    pintor.fillRect(QRectF(MARGEN, y, ANCHO - MARGEN * 2, 1), QColor(p.line))


def value_column(rows: list[tuple[str, str, str]]) -> int:
    """Where the values start: `VALUE_COLUMN`, or further right when a label
    would reach them."""
    metrics = QFontMetrics(_label_font())
    return max([VALUE_COLUMN] + [metrics.horizontalAdvance(label.upper()) + LABEL_GAP
                                 for label, _value, _detail in rows])


def _label_font() -> QFont:
    font = QFont()
    font.setPointSize(10)
    font.setWeight(QFont.Weight.DemiBold)
    return font


def _sized(points: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setPointSize(points)
    font.setWeight(weight)
    return font


def _band(pintor: QPainter, p: Palette, top: float, indice: int) -> None:
    # Una banda muy tenue en las alternas: con seis filas de texto seguidas, la
    # vista se pierde de renglón al saltar de la etiqueta al valor.
    if indice % 2:
        pintor.fillRect(QRectF(MARGEN, top, ANCHO - MARGEN * 2, ALTO_FILA), QColor(p.surface))


def _renglon(pintor: QPainter, p: Palette, top: float, etiqueta: str,
             valor: str, detalle: str, indice: int, column: int = VALUE_COLUMN) -> None:
    """A row from `top`, its label, value and detail centred in its height."""
    _band(pintor, p, top, indice)
    value_font, detail_font = _sized(13), _sized(10)
    value_metrics, detail_metrics = QFontMetrics(value_font), QFontMetrics(detail_font)
    block = value_metrics.height() + (2 + detail_metrics.height() if detalle else 0)
    baseline = top + (ALTO_FILA - block) / 2 + value_metrics.ascent()

    pintor.setFont(_label_font())
    pintor.setPen(QColor(p.accent))
    pintor.drawText(QPointF(MARGEN + PADDING, baseline), etiqueta.upper())

    pintor.setFont(value_font)
    pintor.setPen(QColor(p.ink))
    pintor.drawText(QPointF(MARGEN + PADDING + column, baseline), valor or render.DASH)

    if detalle:
        pintor.setFont(detail_font)
        pintor.setPen(QColor(p.ink_dim))
        pintor.drawText(QPointF(MARGEN + PADDING + column,
                                baseline + value_metrics.descent() + 2 + detail_metrics.ascent()),
                        detalle)


def footer_text() -> str:
    """The version and where Silux is: what situates the card and says where
    to get the program."""
    return f"Silux {render.version(__version__)} · github.com/{updates.REPO}"


def _pie(pintor: QPainter, p: Palette, alto: int) -> None:
    _rule(pintor, p, alto - MARGEN - 12)
    pintor.setFont(_sized(9))
    pintor.setPen(QColor(p.muted))
    pintor.drawText(QPointF(MARGEN, alto - MARGEN + 6), footer_text())


def guardar(snapshot: Snapshot, palette: Palette, ruta: str,
            anonimo: bool = True) -> bool:
    """Escribe la tarjeta en un PNG. Devuelve si se pudo."""
    return dibujar(snapshot, palette, anonimo).save(ruta, "PNG")


# -- a test's result -----------------------------------------------------------
#
# A disk or memory test, to paste where people compare them. Only what the
# result measured, its disk's model or its processor, and when: never where
# it ran (a pen drive's mount carries its owner's name and its label), the
# name someone gave the run, or the machine's name.

# The disk table: its header, each figure's box and a line of notes.
TABLE_HEAD = 30
BOX = 28
NOTE_LINE = 20
# A bar's thickness, the room between a bar and its figure, and between the
# two columns.
BAR = 14
FIGURE_GAP = 12
CELL_GAP = 24
COLUMN_NAMES = {"read": "disktest.col.read", "write": "disktest.col.write"}
# Its unit, said once, over the tests' names.
DISK_UNIT = "MB/s"


def disk_cells(result) -> list[tuple[str, dict[str, tuple[str, Optional[float], str]]]]:
    """A row per test, and in it each direction's figure as the page writes
    it (marked when it varied between laps), how full its bar is on the
    page's scale, and its requests per second where the test is a random
    one."""
    from .pages.disktest import SCALE, VARIED_MARK, megabytes
    from .widgets import log_fraction

    rows = []
    for name in dict.fromkeys(m.name for m in result.measures):
        cells = {}
        for direction in COLUMN_NAMES:
            measure = result.measure(name, direction)
            middle = measure.median if measure is not None else None
            if middle is None:
                continue
            cells[direction] = (
                megabytes(middle.bytes_per_second) + (VARIED_MARK if measure.noisy else ""),
                log_fraction(middle.bytes_per_second, *SCALE),
                _("share.test.iops").format(n=render.thousands(round(middle.requests_per_second)))
                if measure.pattern == "random" else "")
        if cells:
            rows.append((name, cells))
    return rows


def disk_notes(result) -> list[str]:
    """Under the table: the profile, its laps and the engine; and what the
    mark on a figure means, when one has it."""
    from .pages.disktest import ENGINES, PROFILE_NAMES, VARIED_MARK

    profile = _(PROFILE_NAMES[result.profile]) if result.profile in PROFILE_NAMES \
        else result.profile
    laps = render.counted("share.test.laps", result.laps, s=f"{result.lap_seconds:g}") \
        if result.laps else ""
    engine = _(ENGINES[result.engine]) if result.engine in ENGINES else ""
    notes = [" · ".join(x for x in (profile, laps, engine) if x)]
    if any(m.noisy for m in result.measures):
        notes.append(f"{VARIED_MARK} {_('share.test.varied')}")
    return notes


def disk_title(result) -> str:
    return result.model or " + ".join(result.disks)


def disk_subtitle(result) -> str:
    """The test, its file system as the page says it, and when."""
    from .pages.disktest import when

    filesystem = result.filesystem or ""
    if result.no_cow:
        filesystem = _("disktest.conditions.nocow").format(filesystem=filesystem)
    return " · ".join(x for x in (_("share.test.disk"), filesystem, when(result.timestamp)) if x)


def memory_rows(result) -> list[tuple[str, str, str]]:
    """A row per level, with its latency and its cycles; one per operation,
    with the figure the page's grid gives (the fastest kind, every thread)
    and the same kind with one; and the share of the memory's theoretical
    peak, where it is known."""
    from .. import memtest
    from .pages.memtest import GRID_COLUMNS, level_name

    rows = []
    for level in result.levels:
        cycles = render.core_cycles(level.nanoseconds, level.frequency_hz)
        rows.append((level_name(level.level), render.nanoseconds(level.nanoseconds),
                     _("memtest.grid.cycles").format(n=f"{cycles:.1f}") if cycles else ""))
    threads = max((r.threads for r in result.rates), default=1)
    for operation, key, _colour in GRID_COLUMNS:
        every, one = result.fastest(operation, threads)
        if every is None:
            continue
        detail = [render.counted("memtest.threads", every.threads)]
        if every.non_temporal:
            detail.append(_("memtest.grid.nt"))
        if threads > 1 and one is not None:
            detail.append(_("share.test.one").format(
                rate=render.bandwidth(one.bytes_per_second, 1)))
        rows.append((_(key), render.bandwidth(every.bytes_per_second, 1), " · ".join(detail)))
    share = memtest.share_of_theoretical(result)
    if share is not None:
        rows.append((_("share.test.share"), render.whole_percent(share),
                     _("share.test.share.detail").format(
                         channels=render.counted("memtest.channels", result.channels or 0),
                         mts=render.memory_speed(result.speed_mts),
                         total=render.bandwidth(result.theoretical_bytes_per_second, 1))))
    return rows


def memory_subtitle(result) -> str:
    """The test, the memory's speed and channels, and when."""
    from .pages.memtest import when

    return " · ".join(x for x in (
        _("share.test.memory"),
        f"{render.memory_speed(result.speed_mts)} MT/s" if result.speed_mts else "",
        render.counted("memtest.channels", result.channels) if result.channels else "",
        when(result.timestamp)) if x)


def shareable(result) -> bool:
    """A result that finished. One that stopped halfway isn't shared: its
    figures would pass for the disk's or the memory's."""
    return result.measured and not result.reason


def draw_disk_test(result, palette: Palette) -> QPixmap:
    """A disk test's card: a table as CrystalDiskMark's, a column per
    direction with each figure over its bar."""
    cells = disk_cells(result)
    notes = disk_notes(result)
    directions = [d for d in COLUMN_NAMES if any(d in row for _name, row in cells)]
    height = TABLE_HEAD + len(cells) * ALTO_FILA + (8 + len(notes) * NOTE_LINE if notes else 0)

    def body(painter: QPainter, top: int) -> None:
        _disk_table(painter, palette, top, cells, directions)
        y = top + TABLE_HEAD + len(cells) * ALTO_FILA + 8
        painter.setFont(_sized(10))
        painter.setPen(QColor(palette.ink_dim))
        for note in notes:
            painter.drawText(QPointF(MARGEN + PADDING, y + 14), note)
            y += NOTE_LINE

    return _card(disk_title(result), disk_subtitle(result), height, body, palette)


def _figure_font() -> QFont:
    return _sized(17, QFont.Weight.Bold)


def disk_cell_geometry(cells, directions):
    """Where each cell's bar and figure go, in the card: for a row's index,
    each direction's (bar, figure). The figure has a room of its own, as
    wide as the widest figure of the table, beside its bar and never over
    it: drawn over it, the bar ran under «6 592»."""
    column = value_column([(name, "", "") for name, _row in cells])
    left = MARGEN + PADDING + column
    width = (ANCHO - MARGEN - PADDING - left - CELL_GAP * (len(directions) - 1)) \
        / max(len(directions), 1)
    metrics = QFontMetrics(_figure_font())
    figure_width = max((metrics.horizontalAdvance(cell[0]) for _name, row in cells
                        for cell in row.values()), default=0) + 2

    def at(index: int) -> dict:
        box_top = BODY_TOP + TABLE_HEAD + index * ALTO_FILA + 6
        places = {}
        for place, direction in enumerate(directions):
            x = left + place * (width + CELL_GAP)
            bar = QRectF(x, box_top + (BOX - BAR) / 2, width - figure_width - FIGURE_GAP, BAR)
            places[direction] = (bar, QRectF(x + width - figure_width, box_top,
                                             figure_width, BOX))
        return places

    return at


def _disk_table(painter: QPainter, p: Palette, top: int, cells, directions) -> None:
    from .pages.disktest import TONES

    column = value_column([(name, "", "") for name, _row in cells])
    geometry = disk_cell_geometry(cells, directions)
    heads = geometry(0)

    painter.setFont(_sized(9))
    painter.setPen(QColor(p.muted))
    painter.drawText(QPointF(MARGEN + PADDING, top + 20), DISK_UNIT)
    painter.setFont(_label_font())
    painter.setPen(QColor(p.accent))
    for direction in directions:
        painter.drawText(QPointF(heads[direction][0].left(), top + 20),
                         _(COLUMN_NAMES[direction]).upper())

    centred = Qt.AlignmentFlag.AlignVCenter
    right = Qt.AlignmentFlag.AlignRight
    for index, (name, row) in enumerate(cells):
        row_top = top + TABLE_HEAD + index * ALTO_FILA
        _band(painter, p, row_top, index)
        painter.setFont(_label_font())
        painter.setPen(QColor(p.accent))
        painter.drawText(QRectF(MARGEN + PADDING, row_top + 6, column, BOX),
                         Qt.AlignmentFlag.AlignLeft | centred, name.upper())
        for direction, (track, room) in geometry(index).items():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.track))
            painter.drawRoundedRect(track, BAR / 2, BAR / 2)
            cell = row.get(direction)
            if cell is None:
                continue
            figure, fraction, iops = cell
            if fraction is not None:
                painter.setBrush(_blend(p.q("accent"), TONES[direction], p.q("track")))
                painter.drawRoundedRect(QRectF(track.left(), track.top(),
                                               max(track.width() * fraction, BAR), BAR),
                                        BAR / 2, BAR / 2)
            painter.setFont(_figure_font())
            painter.setPen(QColor(p.ink))
            painter.drawText(room, right | centred, figure)
            if iops:
                painter.setFont(_sized(9))
                painter.setPen(QColor(p.ink_dim))
                painter.drawText(QRectF(track.left(), room.bottom() + 1,
                                        room.right() - track.left(), 16),
                                 right | Qt.AlignmentFlag.AlignTop, iops)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _blend(colour: QColor, alpha: float, under: QColor) -> QColor:
    """`colour` at `alpha` over `under`, as one opaque colour: the tab's
    bar, drawn see-through over its track."""
    return QColor(*(round(alpha * a + (1 - alpha) * b) for a, b in (
        (colour.red(), under.red()), (colour.green(), under.green()),
        (colour.blue(), under.blue()))))


def draw_memory_test(result, cpu: str, palette: Palette) -> QPixmap:
    """A memory test's card, with the processor, `cpu`, as its title."""
    return _compose(cpu or _("share.test.memory"), memory_subtitle(result),
                    memory_rows(result), palette)


def marked(pixmap: QPixmap):
    """The image with the mark that says it covers what identifies the
    machine, which `tools/comprobar_privacidad.py` asks of a PNG."""
    image = pixmap.toImage()
    image.setText("silux-anonimo", "anonima")
    return image


def save_image(pixmap: QPixmap, path: str) -> bool:
    """A card in a PNG, with its mark. Whether it could."""
    return marked(pixmap).save(path, "PNG")
