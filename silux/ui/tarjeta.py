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

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

from .. import __version__, build_id, render
from ..i18n import _
from ..model import Snapshot
from ..privacidad import anonimizar
from .theme import Palette

# Fija y generosa: lo que se comparte en un chat se ve en miniatura hasta que
# alguien lo abre, así que el texto tiene que aguantar el encogido. Y fija
# también para que dos tarjetas de dos equipos se puedan comparar sin
# escalarlas.
ANCHO = 900
MARGEN = 36
ALTO_FILA = 54


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
        detalle = " · ".join(x for x in (
            _("share.cores").format(n=snapshot.cpu.total_cores,
                                    h=snapshot.cpu.total_threads),
            render.hz(tipo.clocks.max_turbo_hz or tipo.clocks.max_hz),
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
        filas.append((_("nav.graphics"), gpu.display_name, detalle))

    memoria = snapshot.system.memory
    if memoria.total_bytes:
        modulos = [m for m in snapshot.modules if m.size_bytes]
        detalle = ""
        if modulos:
            primero = modulos[0]
            detalle = " · ".join(x for x in (
                _("share.modules").format(n=len(modulos)),
                primero.type or "",
                f"{primero.speed_mts} MT/s" if primero.speed_mts else "",
            ) if x)
        elif snapshot.spd:
            spd = snapshot.spd[0]
            detalle = " · ".join(x for x in (
                _("share.modules").format(n=len(snapshot.spd)),
                spd.dram_type or "",
            ) if x)
        filas.append((_("nav.memory"), render.size(memoria.total_bytes), detalle))

    if (nombre := snapshot.board.display_name):
        filas.append((_("nav.board"), nombre, snapshot.board.bios_summary or ""))

    if snapshot.disks:
        total = sum(disco.size_bytes or 0 for disco in snapshot.disks)
        tipos: dict[str, int] = {}
        for disco in snapshot.disks:
            if disco.kind:
                tipos[disco.kind] = tipos.get(disco.kind, 0) + 1
        detalle = " · ".join(f"{n} × {k}" for k, n in sorted(tipos.items()))
        filas.append((_("nav.storage"),
                      _("share.units").format(tam=render.size(total),
                                              n=len(snapshot.disks)),
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
        snapshot = anonimizar(snapshot)

    filas = _fila(snapshot)
    alto = MARGEN * 2 + 96 + len(filas) * ALTO_FILA + 30

    lienzo = QPixmap(ANCHO, alto)
    lienzo.fill(QColor(palette.bg))
    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    _cabecera(pintor, palette, snapshot)
    y = MARGEN + 96
    for indice, (etiqueta, valor, detalle) in enumerate(filas):
        _renglon(pintor, palette, y, etiqueta, valor, detalle, indice)
        y += ALTO_FILA
    _pie(pintor, palette, alto)

    pintor.end()
    return lienzo


def _cabecera(pintor: QPainter, p: Palette, snapshot: Snapshot) -> None:
    pintor.setPen(QColor(p.accent))
    fuente = QFont()
    fuente.setPointSize(20)
    fuente.setWeight(QFont.Weight.DemiBold)
    pintor.setFont(fuente)
    pintor.drawText(MARGEN, MARGEN + 26, "silux")

    # Debajo, de qué equipo se está hablando en una línea. Sin el nombre de la
    # máquina: eso es justo lo que no se publica.
    resumen = []
    if snapshot.cpu.types:
        resumen.append(render.cpu_short_name(snapshot.cpu.types[0].brand))
    if snapshot.gpus:
        resumen.append(snapshot.gpus[0].display_name)
    pintor.setPen(QColor(p.ink_dim))
    pequena = QFont()
    pequena.setPointSize(11)
    pintor.setFont(pequena)
    pintor.drawText(MARGEN, MARGEN + 56, " · ".join(resumen))

    pintor.setPen(QColor(p.line))
    pintor.drawLine(MARGEN, MARGEN + 76, ANCHO - MARGEN, MARGEN + 76)


def _renglon(pintor: QPainter, p: Palette, y: int, etiqueta: str,
             valor: str, detalle: str, indice: int) -> None:
    # Una banda muy tenue en las alternas: con seis filas de texto seguidas, la
    # vista se pierde de renglón al saltar de la etiqueta al valor.
    if indice % 2:
        pintor.fillRect(QRectF(MARGEN - 12, y - 27, ANCHO - MARGEN * 2 + 24,
                               ALTO_FILA - 2),
                        QColor(p.surface))

    etiquetas = QFont()
    etiquetas.setPointSize(10)
    etiquetas.setWeight(QFont.Weight.DemiBold)
    pintor.setFont(etiquetas)
    pintor.setPen(QColor(p.accent))
    pintor.drawText(MARGEN, y, etiqueta.upper())

    principal = QFont()
    principal.setPointSize(13)
    pintor.setFont(principal)
    pintor.setPen(QColor(p.ink))
    pintor.drawText(MARGEN + 150, y, valor or render.DASH)

    if detalle:
        pintor.setFont(QFont())
        pequena = pintor.font()
        pequena.setPointSize(10)
        pintor.setFont(pequena)
        pintor.setPen(QColor(p.ink_dim))
        pintor.drawText(MARGEN + 150, y + 19, detalle)


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
    marca = f"silux {__version__}"
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
