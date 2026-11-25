"""Builds a pasteable report, for when someone reports a bug.

«The chart doesn't show» can't be diagnosed: it takes knowing the hardware,
the kernel, which data sources answered and which didn't. This module
produces all of that in Markdown, ready to paste into an issue or a forum.

Meant to be read by whoever sends it first: nothing is hidden. Serial
numbers and the machine's unique identifiers are replaced by a mark, since
a bug report doesn't need to know which exact machine is yours, and whoever
pastes it online shouldn't have to remember.
"""

from __future__ import annotations

import platform
import sys
from typing import Optional

from . import __version__, build_id, privacidad, render
from .i18n import in_spanish
from .model import Need, SensorKind, Snapshot

HIDDEN = "«omitido»"

NEED_REASONS = {
    Need.ROOT: "report.need.root",
    Need.DATABASE: "report.need.database",
    Need.HARDWARE: "report.need.hardware",
    Need.DRIVER: "report.need.driver",
    Need.PLATFORM: "report.need.platform",
    Need.ERROR: "report.need.error",
    Need.KERNEL: "report.need.kernel",
    Need.PACKAGE: "report.need.package",
}


def build(snapshot: Snapshot, anonymous: bool = True) -> str:
    """The whole report. `anonymous` covers what identifies the machine.

    Anonymous, the snapshot first goes through `privacidad.anonymize`, which
    decides what identifies someone: the machine's name doesn't live only in
    its field, and repeating that decision here is how it leaked through
    network names and the sensor tree. Each section's «omitted» marks stay,
    since they say something was covered instead of showing a fake value.
    """
    if anonymous:
        snapshot = privacidad.anonymize(snapshot)
    parts = [
        _header(snapshot, anonymous),
        _processor(snapshot),
        _memory(snapshot),
        _board(snapshot, anonymous),
        _graphics(snapshot, anonymous),
        _storage(snapshot),
        _battery(snapshot),
        _network(snapshot, anonymous),
        _sensors(snapshot),
        _benchmark(),
        _diagnosis(snapshot),
    ]
    return "\n".join(part for part in parts if part).strip() + "\n"


# -- sections ----------------------------------------------------------------

def _header(snapshot: Snapshot, anonymous: bool, translate=in_spanish) -> str:
    """The report's first lines. `translate` is the language: Spanish for
    the short report, the interface's for the full one."""
    t = translate
    system = snapshot.system
    qt = _qt_version()
    unknown = render.DASH
    # The desktop and the session, as far as they're known: «?» read as a
    # fault of the report.
    desktop = " · ".join(p for p in (system.desktop, system.session_type) if p)
    # A list and not a table: a key-value table has no header to give it,
    # and an empty one was the first thing the report showed.
    lines = [
        f"# {t('report.head.title')} {render.version(__version__)}"
        + (f" ({build_id()})" if build_id() else ""),
        "",
        f"- **{t('report.head.distro')}:** "
        f"{system.distribution or unknown} {system.version_id or ''}".rstrip(),
        f"- **{t('report.head.kernel')}:** {system.kernel or unknown}",
        # What the kernel was built with: some distributions use clang and
        # most gcc, which changes what a machine looks like when something
        # goes odd.
        f"- **{t('report.head.built')}:** {system.kernel_build or unknown}",
        f"- **{t('report.head.arch')}:** {system.architecture or unknown}",
        f"- **{t('report.head.desktop')}:** {desktop or t('report.head.desktop.none')}",
        f"- **Init:** {system.init or unknown}",
        f"- **Python:** {platform.python_version()}",
        f"- **Qt (PySide6):** {qt or t('report.head.qt.none')}",
        f"- **{t('report.head.sources')}:** "
        f"{', '.join(sorted(snapshot.capabilities)) or t('report.head.sources.none')}",
        f"- **{t('report.head.from')}:** {_provenance(t)}",
    ]
    # In the header, not the processor's section, because it isn't about the
    # processor: it changes how the whole file reads. Without this row, a VM's
    # report describes a virtual board and processor with nothing saying
    # there's no such machine.
    if virt := _hypervisor(snapshot, t):
        lines.append(f"- **{t('report.head.vm')}:** {virt}")
    if not anonymous and system.hostname:
        lines.append(f"- **{t('report.head.host')}:** {system.hostname}")
    return "\n".join(lines)


def _hypervisor(snapshot: Snapshot, translate=in_spanish) -> str:
    """Who's underneath, for the header. Empty on bare metal."""
    for cpu_type in snapshot.cpu.types:
        if cpu_type.in_virtual_machine:
            return cpu_type.hypervisor or translate("report.head.vm.unknown")
    return ""


def _processor(snapshot: Snapshot) -> str:
    cpu = snapshot.cpu
    if not cpu.types:
        return ""
    lines = ["", "## Procesador", ""]
    # On a hybrid, each core type is a block with the same brand repeated, so
    # the report listed two sections of cores and threads without saying
    # which was which or how many there are in all.
    if cpu.hybrid:
        lines += [
            f"**{cpu.types[0].brand or '?'}** — "
            f"{cpu.total_cores} núcleos · {cpu.total_threads} hilos",
            "",
        ]
    for cpu_type in cpu.types:
        clocks = cpu_type.clocks
        lines += [
            f"### {render.core_type_label(cpu_type, cpu.hybrid, in_spanish)}"
            if cpu.hybrid else f"**{cpu_type.brand or '?'}**",
            "",
            f"- Nombre en clave: {render.from_cpu_table(cpu_type.codename, in_spanish)}"
            f" · {render.from_cpu_table(cpu_type.technology, in_spanish)}",
            f"- Encapsulado: {render.from_cpu_table(cpu_type.socket, in_spanish)}",
            f"- Núcleos / hilos: {cpu_type.cores} / {cpu_type.threads}",
            f"- Familia {render.dec(cpu_type.disp_family)} · "
            f"modelo {render.dec(cpu_type.disp_model)} · "
            f"stepping {render.dec(cpu_type.stepping)} · "
            f"firma {render.signature(cpu_type.signature)}",
            f"- Microcódigo: {cpu_type.microcode or '—'}",
            f"- Relojes: base {render.hz(clocks.base_hz)} · "
            f"máx kernel {render.kernel_ceiling(clocks, in_spanish)} · "
            f"máx silicio {render.hz(clocks.max_turbo_hz)} · "
            f"bus {render.hz(clocks.bus_hz, 0)}",
            f"- Driver: {clocks.driver or '—'} · {clocks.governor or '—'}",
            f"- Cachés: {_caches(cpu_type)}",
            "",
        ]
    return "\n".join(lines)


def _caches(cpu_type) -> str:
    if not cpu_type.caches:
        return "—"
    return " · ".join(
        f"{render.cache_label(cache)} {render.cache_size(cache.size_bytes)}"
        + (f" ×{cache.instances}" if cache.instances > 1 else "")
        for cache in cpu_type.caches
    )


def _memory(snapshot: Snapshot) -> str:
    memory = snapshot.system.memory
    lines = ["", "## Memoria", "",
              f"- Total: {render.size(memory.total_bytes)}"]

    # The controller's traffic is from one instant and that must be said: the
    # report is written with the machine doing anything, so a high number
    # here says nothing bad and a low one nothing good.
    if (traffic := snapshot.memory_traffic) is not None:
        parts = [f"lectura {render.rate(traffic.read_bytes_s)}",
                  f"escritura {render.rate(traffic.write_bytes_s)}"]
        if traffic.cpu_bytes_s is not None:
            parts.append(f"del procesador {render.rate(traffic.cpu_bytes_s)}")
        lines.append("- Tráfico del controlador en este instante: "
                      + " · ".join(parts))
    if (array := snapshot.memory_array) is not None:
        detail = [f"{array.slots} ranuras" if array.slots else ""]
        if array.max_capacity_bytes:
            detail.append(f"hasta {render.size(array.max_capacity_bytes)}")
        if ecc := render.memory_error_correction(array.error_correction, in_spanish):
            detail.append(ecc)
        if any(detail):
            lines.append("- Placa: " + " · ".join(d for d in detail if d))

    if snapshot.modules:
        for module in snapshot.modules:
            lines.append(
                f"- {module.locator or '?'}: {render.size(module.size_bytes)} "
                f"{render.memory_type(module.type, in_spanish) or ''} {module.speed_mts or ''} MT/s "
                f"{module.manufacturer or ''} {module.part_number or ''}".rstrip()
            )
    else:
        lines.append("- Detalle por módulo: no leído (requiere permisos)")

    # The SPD is another source than DMI and says what DMI doesn't: who made
    # the chips as well as the module, the XMP profiles and the week of
    # manufacture. It goes apart because, when both are there, they complete
    # each other, and which one is missing is a datum in itself.
    for spd in snapshot.spd:
        parts = [f"- SPD {render.dec(spd.slot) if spd.slot is not None else '?'}:"]
        parts.append(spd.dram_type or spd.module_type or "?")
        if spd.capacity_bytes:
            parts.append(render.size(spd.capacity_bytes))
        for text in (render.maker(spd.manufacturer), spd.part_number):
            if text:
                parts.append(text)
        if spd.dram_manufacturer and spd.dram_manufacturer != spd.manufacturer:
            parts.append(f"chips {render.maker(spd.dram_manufacturer)}")
        if date := render.made(spd.manufactured_year, spd.manufactured_week, in_spanish):
            parts.append(f"fabricado {date}")
        if spd.ranks:
            parts.append(f"{spd.ranks} rangos")
        if spd.overclock_profiles:
            parts.append(f"{len(spd.overclock_profiles)} perfiles XMP/EXPO")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _board(snapshot: Snapshot, anonymous: bool) -> str:
    board = snapshot.board
    return "\n".join([
        "", "## Placa base", "",
        f"- {render.board_name(board)}",
        f"- BIOS: {render.bios_summary(board)}",
        f"- Chipset: {_chipset(board)}",
        f"- Firmware: {render.firmware_type(board, in_spanish) or '—'} · arranque seguro: "
        f"{'sí' if board.secure_boot else 'no'} · TPM: {board.tpm_version or 'no'}",
        # Raw and all five, since the headline above comes from here and each
        # maker writes the machine's name wherever it likes. Without this, «I
        # get an odd name» meant asking for a separate dmidecode.
        f"- DMI de la placa: {board.vendor or '—'} · {board.name or '—'}"
        f" · versión {board.version or '—'}",
        f"- DMI del sistema: {board.system_vendor or '—'}"
        f" · nombre {board.system_name or '—'}"
        f" · versión {board.system_version or '—'}"
        f" · familia {board.system_family or '—'}",
        f"- Chasis: {in_spanish(board.chassis) if board.chassis else '—'}",
    ])


def _chipset(board) -> str:
    """The chipset and, next to it, what `pci.ids` says of bus 0's bridge.

    Both, because on AMD the second is «FCH LPC Bridge» on every board and
    the first comes from the board's name: if it fails, it shows from what.
    """
    if board.chipset and board.chipset_full and board.chipset_full not in board.chipset:
        return f"{board.chipset} ({board.chipset_full})"
    return board.chipset or board.chipset_full or "—"


def _graphics(snapshot: Snapshot, anonymous: bool) -> str:
    if not snapshot.gpus:
        return "\n## Gráficos\n\nNo se detectó ninguna tarjeta.\n"
    lines = ["", "## Gráficos", ""]
    for gpu in snapshot.gpus:
        lines += [
            f"### {render.gpu_name(gpu)}",
            "",
            f"- Fabricante: {gpu.vendor or '—'} · tarjeta de "
            f"{gpu.subsystem_name or '—'} · {gpu.codename or '—'}",
            f"- Identificador: {gpu.pci_id or '—'} · subsistema {gpu.subsystem_id or '—'}",
            f"- Driver: {gpu.driver or '—'} {gpu.driver_version or ''}".rstrip(),
        ]
        # The telemetry version the program can't interpret yet. With it and
        # the model its offset table can be written without the part at hand,
        # the only way to add it without guessing: reading it with another
        # version's offsets gives no error, only believable wrong numbers.
        if gpu.metrics_version:
            lines.append(
                f"- Telemetría sin interpretar: gpu_metrics v{gpu.metrics_version}")
        lines += [
            f"- BIOS de video: {gpu.vbios or '—'}",
            f"- Memoria: {render.size(gpu.memory.total_bytes)} "
            f"{render.vram_kind(gpu.memory)} · {render.vram_bus(gpu.memory)} · "
            f"{render.bandwidth(gpu.memory.bandwidth_bytes)}",
            f"- Unidades: {render.compute_units(gpu)} · {gpu.rops or '—'} ROP",
            f"- Enlace: {render.pcie_link(gpu.link)} (máx {render.pcie_link(gpu.link, True)})",
            f"- APIs: {', '.join(f'{a.name} {a.version}' for a in gpu.apis) or '—'}",
        ]
        if not anonymous and render.unique_id(gpu.unique_id):
            lines.append(f"- Identificador único: {render.unique_id(gpu.unique_id)}")
        for display in gpu.connected_displays:
            monitor = display.monitor
            detail = (f"{render.monitor_name(monitor)} · {render.display_mode(display)}"
                       if monitor else render.display_summary(display))
            lines.append(f"- {display.connector}: {detail}")
        lines.append("")
    return "\n".join(lines)


def _storage(snapshot: Snapshot) -> str:
    """The disks, which the program gets wrong most often.

    The exact model and the health counters are text and fit here; without
    them, checking a disk meant asking for a screenshot as well.

    The serial number isn't written: `privacidad.anonymize` covers it before
    it arrives, as with the graphics card's.
    """
    if not snapshot.disks:
        return "\n## Almacenamiento\n\nNo se detectó ningún disco.\n"

    lines = ["", "## Almacenamiento", ""]
    for disk in snapshot.disks:
        title = _disk_title(disk)
        lines.append(f"**{title}**")
        lines.append("")
        # The bus only when it adds something: on NVMe it's the same as the type.
        bus = render.disk_bus(disk.transport) if disk.transport else None
        kind = " · ".join(p for p in (disk.kind, bus if bus != disk.kind else None)
                          if p) or "—"
        lines.append(f"- Tipo: {kind} · {render.decimal_size(disk.size_bytes)}")
        if disk.firmware:
            lines.append(f"- Firmware: {disk.firmware}")
        # Only NVMe disks have a link: on SATA the controller negotiates, and
        # shares it with the cable's other disks.
        if disk.link:
            lines.append(f"- Enlace: {render.pcie_link(disk.link)}")
        sectors = [f"lógico {disk.logical_sector}" if disk.logical_sector else "",
                    f"físico {disk.physical_sector}" if disk.physical_sector else ""]
        if any(sectors):
            lines.append("- Sectores: "
                          + " · ".join(s for s in sectors if s) + " bytes")
        if disk.scheduler:
            lines.append(f"- Planificador: {disk.scheduler}")
        if disk.temp_c is not None:
            lines.append(f"- Temperatura: {render.temperature(disk.temp_c)}")
        if (health := disk.health) is not None:
            lines += _disk_health(health)
        if disk.partitions:
            lines.append(f"- Particiones: {_partitions(disk)}")
        lines.append("")
    return "\n".join(lines)


def _disk_title(disk) -> str:
    """Maker and model without saying the same thing twice.

    The maker comes from the model itself, since sysfs says «ATA» on SATA
    and nothing on NVMe. So once the model starts with it, joining them gives
    «Samsung Samsung SSD 970 EVO Plus».
    """
    model = (disk.model or "").strip()
    brand = (disk.vendor or "").strip()
    if not model:
        return brand or disk.name
    if brand and not model.lower().startswith(brand.lower()):
        return f"{brand} {model}"
    return model


def _disk_health(health) -> list[str]:
    """The counters that say how much life the drive has left."""
    lines = []
    used = []
    if health.percentage_used is not None:
        used.append(f"{health.percentage_used:.0f} % de vida consumida")
    if health.spare_percent is not None:
        used.append(f"{health.spare_percent:.0f} % de reserva")
    if used:
        lines.append("- Desgaste: " + " · ".join(used))

    usage = []
    if health.power_on_hours is not None:
        usage.append(f"{health.power_on_hours} h encendido")
    if health.power_cycles is not None:
        usage.append(f"{health.power_cycles} arranques")
    if usage:
        lines.append("- Uso: " + " · ".join(usage))

    traffic = []
    if health.written_bytes is not None:
        traffic.append(f"{render.decimal_size(health.written_bytes)} escritos")
    if health.read_bytes is not None:
        traffic.append(f"{render.decimal_size(health.read_bytes)} leídos")
    if traffic:
        lines.append("- Total: " + " · ".join(traffic))

    # What really needs looking at. `critical_warning` is the field an NVMe
    # warns through that it's on its way to losing data; unsafe shutdowns
    # count power cuts and aren't a fault.
    warnings = []
    if health.critical_warning:
        warnings.append(f"aviso crítico: {health.critical_warning}")
    if health.media_errors:
        warnings.append(f"{health.media_errors} errores de medio")
    for attribute, count in ((5, health.reallocated_sectors), (197, health.pending_sectors),
                             (198, health.uncorrectable_sectors)):
        if count:
            warnings.append(f"{count} en el atributo {attribute}")
    if health.unsafe_shutdowns:
        warnings.append(f"{health.unsafe_shutdowns} apagones bruscos")
    if warnings:
        lines.append("- Avisos: " + " · ".join(warnings))
    return lines


def _partitions(disk) -> str:
    """How many there are and how much of what's mounted is free.

    No mount points: a path can carry the user's name inside
    (`/media/<user>/USB`), and this file is meant to be pasted in public.
    What diagnosis needs is the layout, not where each one hangs.

    And what's mounted is told apart from the capacity on purpose: taking
    the used space off the total assumes the whole disk is mounted, and with
    Windows alongside, a foreign 570 GB partition counted as free.
    """
    mounted = [p for p in disk.partitions if p.mountpoint]
    summary = f"{len(disk.partitions)}"
    if mounted:
        free = sum(p.free_bytes for p in mounted if p.free_bytes is not None)
        filesystems = sorted({p.filesystem for p in mounted if p.filesystem})
        plural = "montada" if len(mounted) == 1 else "montadas"
        summary += (f" ({len(mounted)} {plural}, {render.decimal_size(free)} libres"
                    + (f", {', '.join(filesystems)}" if filesystems else "") + ")")
    return summary


def _battery(snapshot: Snapshot) -> str:
    """The battery, the part that ages worst in a laptop.

    No section if there's none: a desktop without a battery isn't a gap that
    needs explaining.

    The cell's serial number isn't written, as with the disks' and the
    graphics card's.
    """
    if not snapshot.batteries:
        return ""

    lines = ["", "## Batería", ""]
    for battery in snapshot.batteries:
        title = " ".join(x for x in (battery.manufacturer, battery.model)
                          if x) or battery.name
        lines.append(f"**{title}**")
        lines.append("")
        if (health := battery.health_percent) is not None:
            lines.append(
                f"- Salud: {health:.0f} % ({render.watt_hours(battery.full_wh)} de "
                f"{render.watt_hours(battery.design_wh)} de diseño)")
        if battery.cycles:
            lines.append(f"- Ciclos de carga: {battery.cycles}")
        status = []
        if battery.percent is not None:
            status.append(f"{battery.percent:.0f} %")
        if battery.status:
            status.append(in_spanish(battery.status).lower())
        if battery.power_settling:
            status.append(in_spanish("bat.calculating").lower())
        elif battery.power_w is not None:
            status.append(render.watts(battery.power_w))
        if status:
            lines.append("- Estado: " + " · ".join(status))
        if battery.technology:
            lines.append(f"- Tecnología: {battery.technology}")
        voltages = []
        if battery.voltage_v:
            voltages.append(f"{battery.voltage_v:.2f} V")
        if battery.design_voltage_v:
            voltages.append(f"nominal {battery.design_voltage_v:.2f} V")
        if voltages:
            lines.append("- Tensión: " + " · ".join(voltages))
        if battery.impossible_voltage_v:
            lines.append(f"- Tensión descartada: {battery.impossible_voltage_v:.2f} V, "
                         f"imposible con esa nominal")
        # The thresholds only when set. A laptop without a limit publishes 0
        # and 100, the whole range: that is no threshold, and writing it made
        # it look as if something were configured.
        start = battery.charge_start_percent
        end = battery.charge_end_percent
        fitted = ((start is not None or end is not None)
                   and not ((start or 0) <= 0
                            and (end if end is not None else 100) >= 100))
        if fitted:
            lines.append(
                f"- Topes de carga: "
                f"{battery.charge_start_percent if battery.charge_start_percent is not None else '—'}"
                f" – "
                f"{battery.charge_end_percent if battery.charge_end_percent is not None else '—'} %")
        lines.append("")
    return "\n".join(lines)


def _network(snapshot: Snapshot, anonymous: bool) -> str:
    if not snapshot.network:
        return ""
    lines = ["", "## Red", ""]
    for interface in snapshot.network:
        if interface.kind == "loopback":
            continue
        # Addresses are covered whenever possible: they identify the sender's
        # network and aren't needed to diagnose anything.
        address = HIDDEN if (anonymous and interface.ipv4) else (interface.ipv4 or "—")
        mac = HIDDEN if (anonymous and interface.mac) else (interface.mac or "—")
        lines.append(
            f"- **{interface.name}** ({interface.kind}): "
            f"{render.interface_state(interface)} · {render.link_summary(interface) or '—'} · "
            f"{render.with_maker(interface.vendor, interface.model) or interface.driver or '—'} · IP {address} · MAC {mac}"
        )
    return "\n".join(lines)


def _sensors(snapshot: Snapshot) -> str:
    if not snapshot.sensors:
        return "\n## Sensores\n\nNinguno detectado.\n"
    tree = snapshot.sensor_tree()
    lines = ["", "## Sensores", "",
              f"{len(snapshot.sensors)} lecturas en {len(tree)} dispositivos.", ""]
    for categories in tree.values():
        device = Snapshot.device_name(categories)
        count = sum(len(s) for s in categories.values())
        # The categories are keys («cat.temperature»), since the names that
        # group sensors are the program's own and part of the interface.
        # Translated, and into Spanish rather than the language of whoever
        # generates it, like the rest of the report: otherwise an English
        # report would show «Procesador» and «temperatures» on one page.
        summary = ", ".join(f"{in_spanish(name).lower()} ({len(s)})"
                            for name, s in categories.items())
        lines.append(f"- **{device}**, {count}: {summary}")
        # With their names and values too. The count only says how many there
        # are, and what's checked on someone else's machine is just that: what
        # each sensor is called and whether the number is believable. A chip
        # naming its inputs «temp1, temp2, temp3», or a board declaring a
        # 127-degree minimum, show here and nowhere else in this file.
        for name, sensors in categories.items():
            values = " · ".join(
                (f"{s.label} {render.temperature(s.value)}"
                 if s.kind is SensorKind.TEMPERATURE
                 else f"{s.label} {render.sensor_value(s.value, s.kind)} {s.unit}".strip())
                # Whoever checks a foreign machine looks at whether the number
                # is believable: let 16.8 °C say what it is.
                + (" (relleno del firmware, no es una medida)" if s.placeholder else "")
                for s in sensors)
            lines.append(f"  - {in_spanish(name).lower()}: {values}")
    return "\n".join(lines)


def _benchmark() -> str:
    """The latest run that scores, if any.

    In the report because it lets measurements of parts not at hand be
    gathered: without it, whoever sends a report sends their hardware but not
    how it performs, and the score table never fills.

    Only the latest comparable one: a whole history belongs to the sender's
    machine and adds nothing here, and runs on another scale would show a
    difference that doesn't exist.
    """
    from . import benchmark, history, score

    entries = [e for e in history.load()
                if e.score_version == score.VERSION and score.comparable(e.seconds)]
    if not entries:
        return ""
    latest = max(entries, key=lambda e: e.timestamp)
    points = score.compute(latest.scores, latest.threads)
    if points is None:
        return ""
    single, multi = points

    lines = [
        "\n## Rendimiento\n",
        "| | |",
        "|---|---|",
        f"| Puntuación (todos los hilos) | {multi} |",
        f"| Puntuación (un hilo) | {single} |",
        f"| Hilos | {latest.threads} |",
        f"| Escala | v{score.VERSION} |",
        # Which workloads count towards the figure. Without this, two reports
        # on different scales read the same and the difference drawn from them
        # doesn't exist: the same machine's score moves between scales because
        # of which workloads count.
        ("| Cargas que puntúan | "
         + " · ".join(c.name for c in benchmark.WORKLOADS if score.is_scored(c.key))
         + " |"),
    ]
    # The conditions are half of what makes a figure comparable: without
    # them, there's no telling whether two scores separate two machines or
    # two moments of the same one.
    if latest.governor:
        lines.append(f"| Gobernador | {latest.governor} |")
    if latest.frequency_avg_hz:
        lines.append(f"| Frecuencia media | {render.hz(latest.frequency_avg_hz)} |")
    if latest.temperature_peak_c is not None:
        lines.append(f"| Temperatura máxima | {render.temperature_whole(latest.temperature_peak_c)} |")
    if latest.background_load is not None:
        lines.append(f"| Carga de fondo | {latest.background_load:.1f} % |")
    # The peak of foreign load explains a low figure that would otherwise
    # seem the machine's.
    if latest.background_peak is not None:
        lines.append(f"| Otro programa, como mucho | {latest.background_peak:.1f} % |")
    # The libraries it was measured with. They no longer explain the score
    # (the workloads that depend on the system were taken out of it for
    # that), but they are still needed to read those three figures: the same
    # part's verification differs ×9.7 with the distribution's zlib. Version
    # and extensions go together because neither reads alone: a classic zlib
    # uses no flag, so the CPU's say nothing there.
    if latest.zlib_version or latest.openssl_version:
        parts = []
        if latest.zlib_version:
            simd = " · ".join(latest.zlib_simd) or "ninguna de las que usa"
            parts.append(f"zlib {latest.zlib_version} ({simd})")
        if latest.openssl_version:
            parts.append(latest.openssl_version)
        lines.append("| Bibliotecas | " + " · ".join(parts) + " |")
    # And why two and not five; otherwise the row above looks like a cut,
    # when it's the opposite: it is what makes the figure the sender's
    # processor's rather than their distribution's.
    lines.append(
        "\nLas otras tres cargas se miden y se enseñan en el programa, pero no"
        " entran en la puntuación: las calcula una biblioteca del sistema y"
        " cambian con la distribución en vez de con el procesador.")
    return "\n".join(lines) + "\n"


def _diagnosis(snapshot: Snapshot, translate=in_spanish) -> str:
    """What couldn't be read and why. The useful part of a bug report."""
    t = translate
    lines = ["", f"## {t('report.diag.title')}", ""]

    if snapshot.driver_hints:
        lines.append(f"**{t('report.diag.modules')}**")
        lines.append("")
        for hint in snapshot.driver_hints:
            name = "Super I/O" if hint.module == "(Super I/O)" else f"`{hint.module}`"
            lines.append(f"- {name}: {hint.provides}")
            if hint.command:
                lines.append(f"  `{hint.command}`")
        lines.append("")

    if snapshot.notes:
        lines.append(f"**{t('report.diag.missing')}**")
        lines.append("")
        for note in snapshot.notes:
            if note.title:
                reason = note.title[:1].lower() + note.title[1:]
            else:
                reason = t(NEED_REASONS[note.need]) if note.need in NEED_REASONS else note.need.value
            # What's missing for a package says which: the hint is the datum.
            hint = f" {note.hint}" if note.need is Need.PACKAGE and note.hint else ""
            lines.append(f"- `{note.path}` ({reason}): {note.message}{hint}"
                          + (f" ({note.detail})" if note.detail else ""))
    else:
        lines.append(t("report.diag.nothing"))

    lines += _gpu_power_answers(snapshot, t)

    if snapshot.failures:
        lines += ["", f"**{t('report.diag.failures')}**", ""]
        for failure in snapshot.failures:
            times = (" " + t("report.diag.times").format(n=failure.count)
                     if failure.count > 1 else "")
            lines += [f"- `{failure.where}`{times}: {failure.error}", "",
                       "```text", failure.trace, "```", ""]
    return "\n".join(lines)


def _gpu_power_answers(snapshot: Snapshot, t) -> list[str]:
    """What each of NVML's ways of reading the power answered, with the card's
    runtime PM state: what had to be asked for by hand to tell a sensor from
    an estimate, or a sleeping card from a broken reading."""
    cards = [g for g in snapshot.gpus if g.power_answers or g.runtime_status]
    if not cards:
        return []
    lines = ["", f"**{t('report.diag.gpupower')}**", ""]
    for gpu in cards:
        lines.append(f"- {render.gpu_name(gpu)} ({gpu.pci_slot or render.DASH})")
        if gpu.runtime_status:
            lines.append(f"  - runtime_status: {gpu.runtime_status}")
        if gpu.power_source:
            lines.append(f"  - {t('report.diag.gpupower.source')}: {gpu.power_source}")
        lines += [f"  - {way}: {answer}" for way, answer in gpu.power_answers]
    return lines


def _provenance(translate=in_spanish) -> str:
    """Whether it runs from an AppImage or from source.

    It matters more than it seems: from an AppImage the privileged helper
    needs a detour, and «it won't let me elevate» without this goes nowhere.
    """
    import os

    if os.environ.get("APPIMAGE") or "/.mount_" in sys.executable:
        return "AppImage"
    return translate("report.head.from.source")


def _qt_version() -> Optional[str]:
    try:
        import PySide6
        return PySide6.__version__
    except Exception:                                  # noqa: BLE001
        return None
