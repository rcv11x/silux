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

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap

from .. import __version__, build_id, render
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
    return _compose(_machine_summary(snapshot), _fila(snapshot), palette)


def _machine_summary(snapshot: Snapshot) -> str:
    """The machine in one line, without its name: that is exactly what
    isn't published."""
    parts = []
    if snapshot.cpu.types:
        parts.append(render.cpu_short_name(snapshot.cpu.types[0].brand))
    if snapshot.gpus:
        parts.append(render.gpu_name(snapshot.gpus[snapshot.working_gpu]))
    return " · ".join(parts)


def _compose(summary: str, rows: list[tuple[str, str, str]], palette: Palette) -> QPixmap:
    """A card: the brand and `summary` above, one line per row, the version
    below."""
    height = MARGEN * 2 + 96 + len(rows) * ALTO_FILA + 30

    pixmap = QPixmap(ANCHO, height)
    pixmap.fill(QColor(palette.bg))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    _cabecera(painter, palette, summary)
    column = value_column(rows)
    y = MARGEN + 96
    for index, (label, value, detail) in enumerate(rows):
        _renglon(painter, palette, y, label, value, detail, index, column)
        y += ALTO_FILA
    _pie(painter, palette, height)

    painter.end()
    return pixmap


def _cabecera(pintor: QPainter, p: Palette, summary: str) -> None:
    pintor.setPen(QColor(p.accent))
    fuente = QFont()
    fuente.setPointSize(20)
    fuente.setWeight(QFont.Weight.DemiBold)
    pintor.setFont(fuente)
    # La marca delante del nombre: la misma de la barra lateral, para que la
    # imagen se reconozca como de este programa donde acabe pegada.
    from . import icons

    marca = icons.mark(p.bg == theme.DARK.bg, 28)
    desplazado = 0
    if not marca.isNull():
        pintor.drawPixmap(QRectF(MARGEN, MARGEN + 2, 28, 28), marca, QRectF(marca.rect()))
        desplazado = 36
    pintor.drawText(MARGEN + desplazado, MARGEN + 26, "Silux")

    pintor.setPen(QColor(p.ink_dim))
    pequena = QFont()
    pequena.setPointSize(11)
    pintor.setFont(pequena)
    pintor.drawText(MARGEN, MARGEN + 56, summary)

    pintor.setPen(QColor(p.line))
    pintor.drawLine(MARGEN, MARGEN + 76, ANCHO - MARGEN, MARGEN + 76)


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


def _renglon(pintor: QPainter, p: Palette, y: int, etiqueta: str,
             valor: str, detalle: str, indice: int, column: int = VALUE_COLUMN) -> None:
    # Una banda muy tenue en las alternas: con seis filas de texto seguidas, la
    # vista se pierde de renglón al saltar de la etiqueta al valor.
    if indice % 2:
        pintor.fillRect(QRectF(MARGEN - 12, y - 27, ANCHO - MARGEN * 2 + 24,
                               ALTO_FILA - 2),
                        QColor(p.surface))

    pintor.setFont(_label_font())
    pintor.setPen(QColor(p.accent))
    pintor.drawText(MARGEN, y, etiqueta.upper())

    principal = QFont()
    principal.setPointSize(13)
    pintor.setFont(principal)
    pintor.setPen(QColor(p.ink))
    pintor.drawText(MARGEN + column, y, valor or render.DASH)

    if detalle:
        pintor.setFont(QFont())
        pequena = pintor.font()
        pequena.setPointSize(10)
        pintor.setFont(pequena)
        pintor.setPen(QColor(p.ink_dim))
        pintor.drawText(MARGEN + column, y + 19, detalle)


def _pie(pintor: QPainter, p: Palette, alto: int) -> None:
    """La versión y de qué copia salió.

    Va aquí por lo mismo que va en la barra lateral: una captura sin versión no
    se puede situar, y estas están hechas para acabar en un canal donde alguien
    las va a mirar días después.
    """
    pintor.setPen(QColor(p.line))
    pintor.drawLine(MARGEN, alto - MARGEN - 12, ANCHO - MARGEN, alto - MARGEN - 12)

    fuente = QFont()
    fuente.setPointSize(9)
    pintor.setFont(fuente)
    pintor.setPen(QColor(p.muted))
    marca = f"Silux {render.version(__version__)}"
    if build_id():
        marca += f" · {build_id()}"
    pintor.drawText(MARGEN, alto - MARGEN + 6, marca)

    texto = _("share.footer")
    ancho = pintor.fontMetrics().horizontalAdvance(texto)
    pintor.drawText(ANCHO - MARGEN - ancho, alto - MARGEN + 6, texto)


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


def disk_rows(result) -> list[tuple[str, str, str]]:
    """A row per test: its read and write figures, marked as the page marks
    one that varied between laps, and its requests per second where it is a
    random one; then the profile and its laps."""
    from .pages.disktest import ENGINES, PROFILE_NAMES, VARIED_MARK

    rows = []
    for name in dict.fromkeys(m.name for m in result.measures):
        parts, requests = [], []
        for direction, key in (("read", "disktest.col.read"), ("write", "disktest.col.write")):
            measure = result.measure(name, direction)
            middle = measure.median if measure is not None else None
            if middle is None:
                continue
            parts.append(f"{_(key)} {render.disk_rate(middle.bytes_per_second)}"
                          + (VARIED_MARK if measure.noisy else ""))
            if measure.pattern == "random":
                requests.append(_("share.test.iops").format(
                    direction=_(key), n=render.thousands(round(middle.requests_per_second))))
        if parts:
            rows.append((name, " · ".join(parts), " · ".join(requests)))
    laps = render.counted("share.test.laps", result.laps, s=f"{result.lap_seconds:g}") \
        if result.laps else ""
    varied = f"{VARIED_MARK} {_('disktest.note.varied')}" \
        if any(m.noisy for m in result.measures) else ""
    rows.append((_("share.test.profile"),
                  _(PROFILE_NAMES[result.profile]) if result.profile in PROFILE_NAMES
                  else result.profile,
                  " · ".join(x for x in (laps, _(ENGINES[result.engine])
                                         if result.engine in ENGINES else "", varied) if x)))
    return rows


def disk_summary(result) -> str:
    """The test, its disk's model, its file system as the page says it, and
    when."""
    from .pages.disktest import when

    filesystem = result.filesystem or ""
    if result.no_cow:
        filesystem = _("disktest.conditions.nocow").format(filesystem=filesystem)
    return " · ".join(x for x in (_("share.test.disk"),
                                  result.model or " + ".join(result.disks),
                                  filesystem, when(result.timestamp)) if x)


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


def memory_summary(result, cpu: str) -> str:
    """The test, the processor, the memory's speed and channels, and when."""
    from .pages.memtest import when

    return " · ".join(x for x in (
        _("share.test.memory"), cpu,
        f"{render.memory_speed(result.speed_mts)} MT/s" if result.speed_mts else "",
        render.counted("memtest.channels", result.channels) if result.channels else "",
        when(result.timestamp)) if x)


def shareable(result) -> bool:
    """A result that finished. One that stopped halfway isn't shared: its
    figures would pass for the disk's or the memory's."""
    return result.measured and not result.reason


def draw_disk_test(result, palette: Palette) -> QPixmap:
    """A disk test's card."""
    return _compose(disk_summary(result), disk_rows(result), palette)


def draw_memory_test(result, cpu: str, palette: Palette) -> QPixmap:
    """A memory test's card; `cpu`, the processor's name."""
    return _compose(memory_summary(result, cpu), memory_rows(result), palette)


def marked(pixmap: QPixmap):
    """The image with the mark that says it covers what identifies the
    machine, which `tools/comprobar_privacidad.py` asks of a PNG."""
    image = pixmap.toImage()
    image.setText("silux-anonimo", "anonima")
    return image


def save_image(pixmap: QPixmap, path: str) -> bool:
    """A card in a PNG, with its mark. Whether it could."""
    return marked(pixmap).save(path, "PNG")
