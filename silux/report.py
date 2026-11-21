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
from typing import Optional

from . import __version__, build_id, privacidad, render
from .i18n import in_spanish
from .model import Need, Snapshot

HIDDEN = "«omitido»"

NEED_REASONS = {
    Need.ROOT: "requiere permisos de administrador",
    Need.DATABASE: "esta versión no lo conoce todavía",
    Need.HARDWARE: "este equipo no lo expone",
    Need.DRIVER: "falta un módulo del kernel",
    Need.PLATFORM: "no aplica a esta plataforma",
    Need.ERROR: "falló al leerse",
    Need.KERNEL: "el kernel es anterior al dato",
    Need.PACKAGE: "falta un paquete del sistema",
}


def build(snapshot: Snapshot, anonymous: bool = True) -> str:
    """El informe entero. `anonymous` tapa lo que identifica al equipo.

    Anónimo, la foto pasa antes por `privacidad.anonimizar`, que es quien
    decide qué identifica a alguien: el nombre del equipo no vive solo en su
    campo, y repetir aquí al lado esa decisión es como se escapaba por los
    nombres de red y por el árbol de sensores. Las marcas de «omitido» de cada
    sección se quedan, porque dicen que algo se tapó en vez de enseñar un
    valor de mentira.
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


# -- secciones ---------------------------------------------------------------

def _header(snapshot: Snapshot, anonymous: bool) -> str:
    system = snapshot.system
    qt = _qt_version()
    # A list and not a table: a key-value table has no header to give it,
    # and an empty one was the first thing the report showed.
    lines = [
        f"# Informe de Silux {render.version(__version__, in_spanish)}"
        + (f" ({build_id()})" if build_id() else ""),
        "",
        f"- **Distribución:** {system.distribution or '?'} {system.version_id or ''}".rstrip(),
        f"- **Kernel:** {system.kernel or '?'}",
        # Con qué se compiló el kernel: CachyOS usa clang y la mayoría gcc, y
        # eso cambia a qué se parece un equipo cuando algo va raro.
        f"- **Compilado:** {system.kernel_build or '?'}",
        f"- **Arquitectura:** {system.architecture or '?'}",
        f"- **Escritorio:** {system.desktop or '?'} · {system.session_type or '?'}",
        f"- **Init:** {system.init or '?'}",
        f"- **Python:** {platform.python_version()}",
        f"- **Qt (PySide6):** {qt or 'no instalado'}",
        f"- **Fuentes activas:** {', '.join(sorted(snapshot.capabilities)) or 'ninguna'}",
        f"- **Ejecutado desde:** {_provenance()}",
    ]
    # Va en la cabecera y no en el apartado del procesador porque no habla del
    # procesador: cambia cómo se lee el archivo entero. Sin esta fila, un
    # informe de una VM de VMware describe una placa 440BX y un i5-10500T de
    # dos núcleos y dos sockets sin que nada avise de que no hay tal equipo.
    if virt := _hypervisor(snapshot):
        lines.append(f"- **Máquina virtual:** {virt}")
    if not anonymous and system.hostname:
        lines.append(f"- **Equipo:** {system.hostname}")
    return "\n".join(lines)


def _hypervisor(snapshot: Snapshot) -> str:
    """Quién está debajo, para la cabecera. Vacío si esto es hierro."""
    for cpu_type in snapshot.cpu.types:
        if cpu_type.in_virtual_machine:
            return cpu_type.hypervisor or "sí, hipervisor sin identificar"
    return ""


def _processor(snapshot: Snapshot) -> str:
    cpu = snapshot.cpu
    if not cpu.types:
        return ""
    lines = ["", "## Procesador", ""]
    # En un híbrido, cada tipo de núcleo es un bloque con la misma marca
    # repetida, y así el informe de un i9-13980HX salía con dos apartados de
    # «8 / 16» y «16 / 16» sin decir cuál era cuál ni cuántos hay en total. Los
    # 24 núcleos y 32 hilos de esa pieza no aparecían en ninguna parte del
    # archivo que se pide justamente para saber qué lleva dentro un equipo.
    if cpu.hybrid:
        lines += [
            f"**{cpu.types[0].brand or '?'}** — "
            f"{cpu.total_cores} núcleos · {cpu.total_threads} hilos",
            "",
        ]
    for cpu_type in cpu.types:
        clocks = cpu_type.clocks
        lines += [
            f"**{render.core_type_label(cpu_type, cpu.hybrid, in_spanish)}**"
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
            f"máx kernel {render.hz(clocks.max_hz)} · "
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
        f"{render.cache_label(cache)} {render.size(cache.size_bytes)}"
        + (f" ×{cache.instances}" if cache.instances > 1 else "")
        for cache in cpu_type.caches
    )


def _memory(snapshot: Snapshot) -> str:
    memory = snapshot.system.memory
    lines = ["", "## Memoria", "",
              f"- Total: {render.size(memory.total_bytes)}"]

    # El tráfico del controlador es de un instante y hay que decirlo: el
    # informe se escribe con la máquina haciendo cualquier cosa, así que un
    # número alto aquí no dice nada malo y uno bajo tampoco dice nada bueno.
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

    # El SPD es otra fuente que el DMI y dice cosas que aquel no: quién fabricó
    # los chips además del módulo, los perfiles XMP y la semana de fabricación.
    # Sale aparte porque cuando los dos están, no se contradicen sino que se
    # completan, y cuál falta es en sí un dato para diagnosticar.
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
        f"- Firmware: {board.firmware or '—'} · arranque seguro: "
        f"{'sí' if board.secure_boot else 'no'} · TPM: {board.tpm_version or 'no'}",
        # En crudo y los cinco, porque de aquí sale el titular de arriba y cada
        # fabricante escribe el nombre del equipo donde le parece. Sin esto, un
        # «me sale un nombre raro» obligaba a pedir un dmidecode aparte.
        f"- DMI de la placa: {board.vendor or '—'} · {board.name or '—'}"
        f" · versión {board.version or '—'}",
        f"- DMI del sistema: {board.system_vendor or '—'}"
        f" · nombre {board.system_name or '—'}"
        f" · versión {board.system_version or '—'}"
        f" · familia {board.system_family or '—'}",
        f"- Chasis: {in_spanish(board.chassis) if board.chassis else '—'}",
    ])


def _chipset(board) -> str:
    """El chipset y, al lado, lo que `pci.ids` dice del puente del bus 0.

    Los dos, porque en un AMD el segundo es «FCH LPC Bridge» en todas las
    placas y el primero sale del nombre de la placa: si falla, se ve de qué.
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
            f"**{render.gpu_name(gpu)}**",
            "",
            f"- Fabricante: {gpu.vendor or '—'} · tarjeta de "
            f"{gpu.subsystem_name or '—'} · {gpu.codename or '—'}",
            f"- Identificador: {gpu.pci_id or '—'} · subsistema {gpu.subsystem_id or '—'}",
            f"- Driver: {gpu.driver or '—'} {gpu.driver_version or ''}".rstrip(),
        ]
        # La versión de la telemetría que el programa todavía no interpreta.
        # Con esto y el modelo se puede escribir su tabla de posiciones sin
        # tener la pieza delante, que es la única forma de añadirla sin
        # adivinar: leerla con las posiciones de otra versión no da error, da
        # cifras creíbles y equivocadas.
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
    """Los discos, que es de lo que más se equivoca el programa.

    Faltaba entera, y era la única de las once páginas que no salía por aquí.
    Se notaba al pedir informes: para revisar un disco había que pedir además
    una captura, cuando el modelo exacto y los contadores de salud son texto y
    caben aquí. Justo aquí se han corregido ya un fabricante que se sacaba del
    prefijo del modelo y un TBW que salía 65 536 veces pequeño; ninguno de los
    dos se ve sin la cifra delante.

    El número de serie no se escribe: lo tapa `privacidad.anonimizar` antes de
    llegar, como el de la gráfica.
    """
    if not snapshot.disks:
        return "\n## Almacenamiento\n\nNo se detectó ningún disco.\n"

    lines = ["", "## Almacenamiento", ""]
    for disk in snapshot.disks:
        title = _disk_title(disk)
        lines.append(f"**{title}**")
        lines.append("")
        # El bus solo cuando añade algo: en un NVMe es lo mismo que el tipo.
        bus = render.disk_bus(disk.transport) if disk.transport else None
        kind = " · ".join(p for p in (disk.kind, bus if bus != disk.kind else None)
                          if p) or "—"
        lines.append(f"- Tipo: {kind} · {render.size(disk.size_bytes)}")
        if disk.firmware:
            lines.append(f"- Firmware: {disk.firmware}")
        # El enlace solo lo tienen los NVMe: en SATA quien negocia es la
        # controladora y la comparte con los demás discos del cable.
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
    """Fabricante y modelo sin decir dos veces lo mismo.

    El fabricante se saca del propio modelo, porque sysfs dice «ATA» en SATA y
    nada en NVMe. Así que en cuanto el modelo ya empieza por él, juntarlos da
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
    """Los contadores que dicen cuánta vida le queda a la unidad."""
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
        traffic.append(f"{render.size(health.written_bytes)} escritos")
    if health.read_bytes is not None:
        traffic.append(f"{render.size(health.read_bytes)} leídos")
    if traffic:
        lines.append("- Total: " + " · ".join(traffic))

    # Lo que de verdad hay que mirar. `critical_warning` es el campo por el que
    # un NVMe avisa de que va camino de perder datos; los apagones bruscos, en
    # cambio, cuentan cortes de luz y no son una avería.
    warnings = []
    if health.critical_warning:
        warnings.append(f"aviso crítico: {health.critical_warning}")
    if health.media_errors:
        warnings.append(f"{health.media_errors} errores de medio")
    if health.unsafe_shutdowns:
        warnings.append(f"{health.unsafe_shutdowns} apagones bruscos")
    if warnings:
        lines.append("- Avisos: " + " · ".join(warnings))
    return lines


def _partitions(disk) -> str:
    """Cuántas hay y cuánto queda libre de lo que está montado.

    Sin puntos de montaje: una ruta puede llevar dentro el nombre de quien usa
    el equipo —`/media/pepe/USB`—, y este archivo está pensado para pegarlo en
    público. Lo que hace falta para diagnosticar es el reparto, no dónde
    cuelga cada una.

    Y lo montado se dice aparte de la capacidad a propósito: restarle lo
    ocupado al total da por montado todo el disco, y con un Windows al lado
    eso contaba como libre una partición ajena de 570 GB.
    """
    mounted = [p for p in disk.partitions if p.mountpoint]
    summary = f"{len(disk.partitions)}"
    if mounted:
        free = sum(p.free_bytes for p in mounted if p.free_bytes is not None)
        filesystems = sorted({p.filesystem for p in mounted if p.filesystem})
        plural = "montada" if len(mounted) == 1 else "montadas"
        summary += (f" ({len(mounted)} {plural}, {render.size(free)} libres"
                    + (f", {', '.join(filesystems)}" if filesystems else "") + ")")
    return summary


def _battery(snapshot: Snapshot) -> str:
    """La batería, que en un portátil es la pieza que peor envejece.

    Sin sección si no hay ninguna: que un sobremesa no tenga batería no es una
    carencia que haya que explicar.

    El número de serie de la celda no se escribe, como el de los discos y el de
    la gráfica.
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
        # Los topes solo si están puestos. Un ThinkPad sin límite publica 0 y
        # 100, que es el rango entero: eso es no tener tope, y escribirlo
        # hacía creer que había algo configurado.
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
        # Las direcciones se tapan siempre que se pueda: identifican la red de
        # quien envía el informe y no hacen falta para diagnosticar nada.
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
        # Las categorías son claves —«cat.temperature»—, porque los nombres que
        # agrupan los inventa el programa y son interfaz. Sin traducirlas, el
        # informe enseñaba la clave cruda a quien lo abriera. Y va en español y
        # no en el idioma de quien lo genera, como el resto del informe: si no,
        # un informe en inglés saldría con «Procesador» y «temperatures» en la
        # misma página.
        summary = ", ".join(f"{in_spanish(name).lower()} ({len(s)})"
                            for name, s in categories.items())
        lines.append(f"- **{device}**, {count}: {summary}")
        # Y con sus nombres y valores. El recuento solo dice cuántos hay, y lo
        # que se revisa de un equipo ajeno es justo lo otro: cómo se llama cada
        # sensor y si el número es creíble. Un chip que bautiza sus entradas
        # «temp1, temp2, temp3» y una placa que declara un mínimo de 127 grados
        # se ven aquí y en ningún otro sitio de este archivo.
        for name, sensors in categories.items():
            values = " · ".join(
                f"{s.label} {render.sensor_value(s.value, s.kind)} {s.unit}".strip()
                # Quien revisa un equipo ajeno mira justo si el número es
                # creíble: que 16.8 °C lleve dicho lo que es.
                + (" (relleno del firmware, no es una medida)" if s.placeholder else "")
                for s in sensors)
            lines.append(f"  - {in_spanish(name).lower()}: {values}")
    return "\n".join(lines)


def _benchmark() -> str:
    """La última prueba que puntúa, si la hay.

    Va en el informe porque es lo que permite juntar medidas de piezas que no
    están a mano. Sin esto, quien manda un informe manda su hardware y no lo
    que rinde, y la tabla de puntuaciones no se llena nunca.

    Solo la última comparable: un historial entero es del equipo de quien lo
    manda y aquí no aporta, y las de otra escala dirían una diferencia que no
    existe.
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
        # Cuáles entran en la cifra. Sin esto, dos informes de escalas
        # distintas se leen igual y la diferencia que se saca no existe: de la
        # v5 a la v6 la puntuación de un mismo equipo se mueve sin que el
        # equipo cambie, porque tres de las cinco cargas dejaron de contar.
        ("| Cargas que puntúan | "
         + " · ".join(c.name for c in benchmark.WORKLOADS if score.is_scored(c.key))
         + " |"),
    ]
    # Las condiciones son la mitad de lo que hace comparable una cifra: sin
    # ellas, dos puntuaciones distintas no se sabe si separan a dos equipos o
    # a dos momentos del mismo.
    if latest.governor:
        lines.append(f"| Gobernador | {latest.governor} |")
    if latest.frequency_avg_hz:
        lines.append(f"| Frecuencia media | {render.hz(latest.frequency_avg_hz)} |")
    if latest.temperature_peak_c is not None:
        lines.append(f"| Temperatura máxima | {latest.temperature_peak_c:.0f} °C |")
    if latest.background_load is not None:
        lines.append(f"| Carga de fondo | {latest.background_load:.1f} % |")
    # El pico de lo ajeno explica una cifra baja que si no parece del equipo.
    if latest.background_peak is not None:
        lines.append(f"| Otro programa, como mucho | {latest.background_peak:.1f} % |")
    # Con qué bibliotecas se midió. Ya no explica la puntuación —para eso se
    # quitaron de ella las cargas que dependen del sistema—, y sigue haciendo
    # falta para leer las cifras de esas tres: la misma pieza rinde un ×9,7
    # distinto en la verificación según qué zlib traiga la distribución.
    # La versión y las extensiones van juntas porque por separado no se
    # interpreta ninguna de las dos: una zlib clásica no usa ninguna bandera,
    # así que ahí las de la CPU no dicen nada.
    if latest.zlib_version or latest.openssl_version:
        parts = []
        if latest.zlib_version:
            simd = " · ".join(latest.zlib_simd) or "ninguna de las que usa"
            parts.append(f"zlib {latest.zlib_version} ({simd})")
        if latest.openssl_version:
            parts.append(latest.openssl_version)
        lines.append("| Bibliotecas | " + " · ".join(parts) + " |")
    # Y por qué son dos y no cinco, que si no la fila de arriba parece un
    # recorte y es lo contrario: es lo que hace que la cifra sea del
    # procesador de quien la manda y no de su distribución.
    lines.append(
        "\nLas otras tres cargas se miden y se enseñan en el programa, pero no"
        " entran en la puntuación: las calcula una biblioteca del sistema y"
        " cambian con la distribución en vez de con el procesador.")
    return "\n".join(lines) + "\n"


def _diagnosis(snapshot: Snapshot) -> str:
    """Lo que no se pudo leer y por qué. Es la parte útil de un informe de fallo."""
    lines = ["", "## Diagnóstico", ""]

    if snapshot.driver_hints:
        lines.append("**Módulos del kernel que ampliarían lo que se ve:**")
        lines.append("")
        for hint in snapshot.driver_hints:
            name = "Super I/O" if hint.module == "(Super I/O)" else f"`{hint.module}`"
            lines.append(f"- {name}: {hint.provides}")
            if hint.command:
                lines.append(f"  `{hint.command}`")
        lines.append("")

    if snapshot.notes:
        lines.append("**Datos que faltan:**")
        lines.append("")
        for note in snapshot.notes:
            lines.append(f"- `{note.path}` ({NEED_REASONS.get(note.need, note.need.value)}): "
                          f"{note.message}" + (f" ({note.detail})" if note.detail else ""))
    else:
        lines.append("Sin datos ausentes: todo lo que el equipo expone se ha leído.")

    if snapshot.failures:
        lines += ["", "**Fallos de Silux, con su traza:**", ""]
        for failure in snapshot.failures:
            times = f" ({failure.count} veces)" if failure.count > 1 else ""
            lines += [f"- `{failure.where}`{times}: {failure.error}", "",
                       "```text", failure.trace, "```", ""]
    return "\n".join(lines)


def _provenance() -> str:
    """Si corre desde un AppImage o desde el código.

    Importa más de lo que parece: desde un AppImage el ayudante privilegiado
    necesita un rodeo, y un «no me deja elevar permisos» sin este dato no lleva
    a ninguna parte.
    """
    import os

    if os.environ.get("APPIMAGE") or "/.mount_" in sys.executable:
        return "AppImage"
    return "código fuente o paquete del sistema"


def _qt_version() -> Optional[str]:
    try:
        import PySide6
        return PySide6.__version__
    except Exception:                                  # noqa: BLE001
        return None
