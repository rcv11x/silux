"""Genera un informe pegable, para cuando alguien reporta un fallo.

Un «no me sale la gráfica» no se puede diagnosticar: hace falta saber qué
hardware hay, qué kernel, qué fuentes de datos respondieron y cuáles no. Este
módulo produce todo eso en Markdown, listo para pegar en un issue o en un foro.

Está pensado para que quien lo envía pueda leerlo antes: no hay nada oculto.
Los números de serie y los identificadores únicos del equipo se sustituyen por
una marca, porque un informe de un fallo no necesita saber cuál es tu máquina
en concreto y quien lo pega en internet no debería tener que acordarse.
"""

from __future__ import annotations

import platform
import sys
from typing import Iterable, Optional

from . import __version__, render
from .model import Need, Snapshot

OCULTO = "«omitido»"

MOTIVOS = {
    Need.ROOT: "requiere permisos de administrador",
    Need.DATABASE: "falta en la base de datos",
    Need.HARDWARE: "este equipo no lo expone",
    Need.DRIVER: "falta un módulo del kernel",
    Need.PLATFORM: "no aplica a esta plataforma",
}


def build(snapshot: Snapshot, anonymous: bool = True) -> str:
    """El informe entero. `anonymous` tapa lo que identifica al equipo."""
    partes = [
        _cabecera(snapshot, anonymous),
        _procesador(snapshot),
        _memoria(snapshot),
        _placa(snapshot, anonymous),
        _graficas(snapshot, anonymous),
        _red(snapshot, anonymous),
        _sensores(snapshot),
        _diagnostico(snapshot),
    ]
    return "\n".join(parte for parte in partes if parte).strip() + "\n"


# -- secciones ---------------------------------------------------------------

def _cabecera(snapshot: Snapshot, anonymous: bool) -> str:
    sistema = snapshot.system
    qt = _version_de_qt()
    lineas = [
        f"# Informe de cpuz {__version__}",
        "",
        "| | |",
        "|---|---|",
        f"| Distribución | {sistema.distribution or '?'} {sistema.version_id or ''} |",
        f"| Kernel | {sistema.kernel or '?'} |",
        f"| Arquitectura | {sistema.architecture or '?'} |",
        f"| Escritorio | {sistema.desktop or '?'} · {sistema.session_type or '?'} |",
        f"| Python | {platform.python_version()} |",
        f"| Qt (PySide6) | {qt or 'no instalado'} |",
        f"| Fuentes activas | {', '.join(sorted(snapshot.capabilities)) or 'ninguna'} |",
    ]
    if not anonymous and sistema.hostname:
        lineas.append(f"| Equipo | {sistema.hostname} |")
    return "\n".join(lineas)


def _procesador(snapshot: Snapshot) -> str:
    cpu = snapshot.cpu
    if not cpu.types:
        return ""
    lineas = ["", "## Procesador", ""]
    for tipo in cpu.types:
        relojes = tipo.clocks
        lineas += [
            f"**{tipo.brand or '?'}**",
            "",
            f"- Nombre en clave: {tipo.codename or '—'} · {tipo.technology or '—'}",
            f"- Encapsulado: {tipo.socket or '—'}",
            f"- Núcleos / hilos: {tipo.cores} / {tipo.threads}",
            f"- Familia {tipo.disp_family} · modelo {tipo.disp_model} · "
            f"stepping {tipo.stepping} · firma {render.signature(tipo.signature)}",
            f"- Microcódigo: {tipo.microcode or '—'}",
            f"- Relojes: base {render.hz(relojes.base_hz)} · "
            f"máx kernel {render.hz(relojes.max_hz)} · "
            f"máx silicio {render.hz(relojes.max_turbo_hz)} · "
            f"bus {render.hz(relojes.bus_hz, 0)}",
            f"- Driver: {relojes.driver or '—'} · {relojes.governor or '—'}",
            f"- Cachés: {_caches(tipo)}",
            "",
        ]
    return "\n".join(lineas)


def _caches(tipo) -> str:
    if not tipo.caches:
        return "—"
    return " · ".join(
        f"{render.cache_label(cache)} {render.size(cache.size_bytes)}"
        + (f" ×{cache.instances}" if cache.instances > 1 else "")
        for cache in tipo.caches
    )


def _memoria(snapshot: Snapshot) -> str:
    memoria = snapshot.system.memory
    lineas = ["", "## Memoria", "",
              f"- Total: {render.size(memoria.total_bytes)}"]
    if snapshot.modules:
        for modulo in snapshot.modules:
            lineas.append(
                f"- {modulo.locator or '?'}: {render.size(modulo.size_bytes)} "
                f"{modulo.type or ''} {modulo.speed_mts or ''} MT/s "
                f"{modulo.manufacturer or ''} {modulo.part_number or ''}".rstrip()
            )
    else:
        lineas.append("- Detalle por módulo: no leído (requiere permisos)")
    return "\n".join(lineas)


def _placa(snapshot: Snapshot, anonymous: bool) -> str:
    board = snapshot.board
    return "\n".join([
        "", "## Placa base", "",
        f"- {board.display_name or '?'}",
        f"- BIOS: {board.bios_summary or '?'}",
        f"- Chipset: {board.chipset_full or board.chipset or '—'}",
        f"- Firmware: {board.firmware or '—'} · arranque seguro: "
        f"{'sí' if board.secure_boot else 'no'} · TPM: {board.tpm_version or 'no'}",
    ])


def _graficas(snapshot: Snapshot, anonymous: bool) -> str:
    if not snapshot.gpus:
        return "\n## Gráficos\n\nNo se detectó ninguna tarjeta.\n"
    lineas = ["", "## Gráficos", ""]
    for gpu in snapshot.gpus:
        lineas += [
            f"**{gpu.display_name}**",
            "",
            f"- Fabricante: {gpu.vendor or '—'} · tarjeta de "
            f"{gpu.subsystem_name or '—'} · {gpu.codename or '—'}",
            f"- Identificador: {gpu.pci_id or '—'} · subsistema {gpu.subsystem_id or '—'}",
            f"- Driver: {gpu.driver or '—'} {gpu.driver_version or ''}".rstrip(),
            f"- BIOS de vídeo: {gpu.vbios or '—'}",
            f"- Memoria: {render.size(gpu.memory.total_bytes)} "
            f"{render.vram_kind(gpu.memory)} · {render.bandwidth(gpu.memory.bandwidth_bytes)}",
            f"- Unidades: {gpu.compute_units or '—'} CU · {gpu.rops or '—'} ROP",
            f"- Enlace: {render.pcie_link(gpu.link)} (máx {render.pcie_link(gpu.link, True)})",
            f"- APIs: {', '.join(f'{a.name} {a.version}' for a in gpu.apis) or '—'}",
        ]
        if not anonymous and gpu.unique_id:
            lineas.append(f"- Identificador único: {gpu.unique_id}")
        for salida in gpu.connected_displays:
            monitor = salida.monitor
            detalle = (f"{render.monitor_name(monitor)} · {render.display_mode(salida)}"
                       if monitor else render.display_summary(salida))
            lineas.append(f"- {salida.connector}: {detalle}")
        lineas.append("")
    return "\n".join(lineas)


def _red(snapshot: Snapshot, anonymous: bool) -> str:
    if not snapshot.network:
        return ""
    lineas = ["", "## Red", ""]
    for interfaz in snapshot.network:
        if interfaz.kind == "loopback":
            continue
        # Las direcciones se tapan siempre que se pueda: identifican la red de
        # quien envía el informe y no hacen falta para diagnosticar nada.
        direccion = OCULTO if (anonymous and interfaz.ipv4) else (interfaz.ipv4 or "—")
        mac = OCULTO if (anonymous and interfaz.mac) else (interfaz.mac or "—")
        lineas.append(
            f"- **{interfaz.name}** ({interfaz.kind}): "
            f"{render.interface_state(interfaz)} · {interfaz.link_summary or '—'} · "
            f"{interfaz.model or interfaz.driver or '—'} · IP {direccion} · MAC {mac}"
        )
    return "\n".join(lineas)


def _sensores(snapshot: Snapshot) -> str:
    if not snapshot.sensors:
        return "\n## Sensores\n\nNinguno detectado.\n"
    arbol = snapshot.sensor_tree()
    lineas = ["", "## Sensores", "",
              f"{len(snapshot.sensors)} lecturas en {len(arbol)} aparatos.", ""]
    for aparato, categorias in arbol.items():
        cuantos = sum(len(s) for s in categorias.values())
        resumen = ", ".join(f"{nombre.lower()} ({len(s)})"
                            for nombre, s in categorias.items())
        lineas.append(f"- **{aparato}** — {cuantos}: {resumen}")
    return "\n".join(lineas)


def _diagnostico(snapshot: Snapshot) -> str:
    """Lo que no se pudo leer y por qué. Es la parte útil de un informe de fallo."""
    lineas = ["", "## Diagnóstico", ""]

    if snapshot.driver_hints:
        lineas.append("**Módulos del kernel que ampliarían lo que se ve:**")
        lineas.append("")
        for pista in snapshot.driver_hints:
            lineas.append(f"- `{pista.module}` — {pista.reason}")
        lineas.append("")

    if snapshot.notes:
        lineas.append("**Datos que faltan:**")
        lineas.append("")
        for nota in snapshot.notes:
            lineas.append(f"- `{nota.path}` ({MOTIVOS.get(nota.need, nota.need.value)}): "
                          f"{nota.message}")
    else:
        lineas.append("Sin datos ausentes: todo lo que el equipo expone se ha leído.")
    return "\n".join(lineas)


def _version_de_qt() -> Optional[str]:
    try:
        import PySide6
        return PySide6.__version__
    except Exception:                                  # noqa: BLE001
        return None
