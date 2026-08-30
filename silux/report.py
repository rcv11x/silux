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

from . import __version__, build_id, render
from .i18n import en_español
from .model import Need, Snapshot

OCULTO = "«omitido»"

MOTIVOS = {
    Need.ROOT: "requiere permisos de administrador",
    Need.DATABASE: "falta en la base de datos",
    Need.HARDWARE: "este equipo no lo expone",
    Need.DRIVER: "falta un módulo del kernel",
    Need.PLATFORM: "no aplica a esta plataforma",
    Need.ERROR: "falló al leerse",
}


def build(snapshot: Snapshot, anonymous: bool = True) -> str:
    """El informe entero. `anonymous` tapa lo que identifica al equipo."""
    partes = [
        _cabecera(snapshot, anonymous),
        _procesador(snapshot),
        _memoria(snapshot),
        _placa(snapshot, anonymous),
        _graficas(snapshot, anonymous),
        _almacenamiento(snapshot),
        _bateria(snapshot),
        _red(snapshot, anonymous),
        _sensores(snapshot),
        _rendimiento(),
        _diagnostico(snapshot),
    ]
    return "\n".join(parte for parte in partes if parte).strip() + "\n"


# -- secciones ---------------------------------------------------------------

def _cabecera(snapshot: Snapshot, anonymous: bool) -> str:
    sistema = snapshot.system
    qt = _version_de_qt()
    lineas = [
        f"# Informe de silux {__version__}"
        + (f" ({build_id()})" if build_id() else ""),
        "",
        "| | |",
        "|---|---|",
        f"| Distribución | {sistema.distribution or '?'} {sistema.version_id or ''} |",
        f"| Kernel | {sistema.kernel or '?'} |",
        # Con qué se compiló el kernel: CachyOS usa clang y la mayoría gcc, y
        # eso cambia a qué se parece un equipo cuando algo va raro.
        f"| Compilado | {sistema.kernel_build or '?'} |",
        f"| Arquitectura | {sistema.architecture or '?'} |",
        f"| Escritorio | {sistema.desktop or '?'} · {sistema.session_type or '?'} |",
        f"| Init | {sistema.init or '?'} |",
        f"| Python | {platform.python_version()} |",
        f"| Qt (PySide6) | {qt or 'no instalado'} |",
        f"| Fuentes activas | {', '.join(sorted(snapshot.capabilities)) or 'ninguna'} |",
        f"| Ejecutado desde | {_procedencia()} |",
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
            f"- Familia {render.dec(tipo.disp_family)} · "
            f"modelo {render.dec(tipo.disp_model)} · "
            f"stepping {render.dec(tipo.stepping)} · "
            f"firma {render.signature(tipo.signature)}",
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
    if (array := snapshot.memory_array) is not None:
        detalle = [f"{array.slots} ranuras" if array.slots else ""]
        if array.max_capacity_bytes:
            detalle.append(f"hasta {render.size(array.max_capacity_bytes)}")
        if array.error_correction:
            detalle.append(array.error_correction)
        if any(detalle):
            lineas.append("- Placa: " + " · ".join(d for d in detalle if d))

    if snapshot.modules:
        for modulo in snapshot.modules:
            lineas.append(
                f"- {modulo.locator or '?'}: {render.size(modulo.size_bytes)} "
                f"{modulo.type or ''} {modulo.speed_mts or ''} MT/s "
                f"{modulo.manufacturer or ''} {modulo.part_number or ''}".rstrip()
            )
    else:
        lineas.append("- Detalle por módulo: no leído (requiere permisos)")

    # El SPD es otra fuente que el DMI y dice cosas que aquel no: quién fabricó
    # los chips además del módulo, los perfiles XMP y la semana de fabricación.
    # Sale aparte porque cuando los dos están, no se contradicen sino que se
    # completan, y cuál falta es en sí un dato para diagnosticar.
    for spd in snapshot.spd:
        partes = [f"- SPD {render.dec(spd.slot) if spd.slot is not None else '?'}:"]
        partes.append(spd.dram_type or spd.module_type or "?")
        if spd.capacity_bytes:
            partes.append(render.size(spd.capacity_bytes))
        for texto in (spd.manufacturer, spd.part_number):
            if texto:
                partes.append(texto)
        if spd.dram_manufacturer and spd.dram_manufacturer != spd.manufacturer:
            partes.append(f"chips {spd.dram_manufacturer}")
        if spd.manufactured:
            partes.append(f"fabricado {spd.manufactured}")
        if spd.ranks:
            partes.append(f"{spd.ranks} rangos")
        if spd.overclock_profiles:
            partes.append(f"{len(spd.overclock_profiles)} perfiles XMP/EXPO")
        lineas.append(" ".join(partes))
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
        ]
        # La versión de la telemetría que el programa todavía no interpreta.
        # Con esto y el modelo se puede escribir su tabla de posiciones sin
        # tener la pieza delante, que es la única forma de añadirla sin
        # adivinar: leerla con las posiciones de otra versión no da error, da
        # cifras creíbles y equivocadas.
        if gpu.metrics_version:
            lineas.append(
                f"- Telemetría sin interpretar: gpu_metrics v{gpu.metrics_version}")
        lineas += [
            f"- BIOS de video: {gpu.vbios or '—'}",
            f"- Memoria: {render.size(gpu.memory.total_bytes)} "
            f"{render.vram_kind(gpu.memory)} · {render.vram_bus(gpu.memory)} · "
            f"{render.bandwidth(gpu.memory.bandwidth_bytes)}",
            f"- Unidades: {render.compute_units(gpu)} · {gpu.rops or '—'} ROP",
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


def _almacenamiento(snapshot: Snapshot) -> str:
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

    lineas = ["", "## Almacenamiento", ""]
    for disco in snapshot.disks:
        titulo = _titulo_del_disco(disco)
        lineas.append(f"**{titulo}**")
        lineas.append("")
        tipo = " · ".join(p for p in (disco.kind, disco.transport) if p) or "—"
        lineas.append(f"- Tipo: {tipo} · {render.size(disco.size_bytes)}")
        if disco.firmware:
            lineas.append(f"- Firmware: {disco.firmware}")
        # El enlace solo lo tienen los NVMe: en SATA quien negocia es la
        # controladora y la comparte con los demás discos del cable.
        if disco.link:
            lineas.append(f"- Enlace: {render.pcie_link(disco.link)}")
        sectores = [f"lógico {disco.logical_sector}" if disco.logical_sector else "",
                    f"físico {disco.physical_sector}" if disco.physical_sector else ""]
        if any(sectores):
            lineas.append("- Sectores: "
                          + " · ".join(s for s in sectores if s) + " bytes")
        if disco.scheduler:
            lineas.append(f"- Planificador: {disco.scheduler}")
        if disco.temp_c is not None:
            lineas.append(f"- Temperatura: {render.temperature(disco.temp_c)}")
        if (salud := disco.health) is not None:
            lineas += _salud_del_disco(salud)
        if disco.partitions:
            lineas.append(f"- Particiones: {_particiones(disco)}")
        lineas.append("")
    return "\n".join(lineas)


def _titulo_del_disco(disco) -> str:
    """Fabricante y modelo sin decir dos veces lo mismo.

    El fabricante se saca del propio modelo, porque sysfs dice «ATA» en SATA y
    nada en NVMe. Así que en cuanto el modelo ya empieza por él, juntarlos da
    «Samsung Samsung SSD 970 EVO Plus».
    """
    modelo = (disco.model or "").strip()
    marca = (disco.vendor or "").strip()
    if not modelo:
        return marca or disco.name
    if marca and not modelo.lower().startswith(marca.lower()):
        return f"{marca} {modelo}"
    return modelo


def _salud_del_disco(salud) -> list[str]:
    """Los contadores que dicen cuánta vida le queda a la unidad."""
    lineas = []
    gastado = []
    if salud.percentage_used is not None:
        gastado.append(f"{salud.percentage_used:.0f} % de vida consumida")
    if salud.spare_percent is not None:
        gastado.append(f"{salud.spare_percent:.0f} % de reserva")
    if gastado:
        lineas.append("- Desgaste: " + " · ".join(gastado))

    uso = []
    if salud.power_on_hours is not None:
        uso.append(f"{salud.power_on_hours} h encendido")
    if salud.power_cycles is not None:
        uso.append(f"{salud.power_cycles} arranques")
    if uso:
        lineas.append("- Uso: " + " · ".join(uso))

    trafico = []
    if salud.written_bytes is not None:
        trafico.append(f"{render.size(salud.written_bytes)} escritos")
    if salud.read_bytes is not None:
        trafico.append(f"{render.size(salud.read_bytes)} leídos")
    if trafico:
        lineas.append("- Total: " + " · ".join(trafico))

    # Lo que de verdad hay que mirar. `critical_warning` es el campo por el que
    # un NVMe avisa de que va camino de perder datos; los apagones bruscos, en
    # cambio, cuentan cortes de luz y no son una avería.
    avisos = []
    if salud.critical_warning:
        avisos.append(f"aviso crítico: {salud.critical_warning}")
    if salud.media_errors:
        avisos.append(f"{salud.media_errors} errores de medio")
    if salud.unsafe_shutdowns:
        avisos.append(f"{salud.unsafe_shutdowns} apagones bruscos")
    if avisos:
        lineas.append("- Avisos: " + " · ".join(avisos))
    return lineas


def _particiones(disco) -> str:
    """Cuántas hay y cuánto queda libre de lo que está montado.

    Sin puntos de montaje: una ruta puede llevar dentro el nombre de quien usa
    el equipo —`/media/pepe/USB`—, y este archivo está pensado para pegarlo en
    público. Lo que hace falta para diagnosticar es el reparto, no dónde
    cuelga cada una.

    Y lo montado se dice aparte de la capacidad a propósito: restarle lo
    ocupado al total da por montado todo el disco, y con un Windows al lado
    eso contaba como libre una partición ajena de 570 GB.
    """
    montadas = [p for p in disco.partitions if p.mountpoint]
    resumen = f"{len(disco.partitions)}"
    if montadas:
        libre = sum(p.free_bytes for p in montadas if p.free_bytes is not None)
        sistemas = sorted({p.filesystem for p in montadas if p.filesystem})
        plural = "montada" if len(montadas) == 1 else "montadas"
        resumen += (f" ({len(montadas)} {plural}, {render.size(libre)} libres"
                    + (f", {', '.join(sistemas)}" if sistemas else "") + ")")
    return resumen


def _bateria(snapshot: Snapshot) -> str:
    """La batería, que en un portátil es la pieza que peor envejece.

    Sin sección si no hay ninguna: que un sobremesa no tenga batería no es una
    carencia que haya que explicar.

    El número de serie de la celda no se escribe, como el de los discos y el de
    la gráfica.
    """
    if not snapshot.batteries:
        return ""

    lineas = ["", "## Batería", ""]
    for bateria in snapshot.batteries:
        titulo = " ".join(x for x in (bateria.manufacturer, bateria.model)
                          if x) or bateria.name
        lineas.append(f"**{titulo}**")
        lineas.append("")
        if (salud := bateria.health_percent) is not None:
            lineas.append(
                f"- Salud: {salud:.0f} % ({bateria.full_wh:.1f} Wh de "
                f"{bateria.design_wh:.1f} Wh de diseño)")
        if bateria.cycles:
            lineas.append(f"- Ciclos de carga: {bateria.cycles}")
        estado = []
        if bateria.percent is not None:
            estado.append(f"{bateria.percent:.0f} %")
        if bateria.status:
            estado.append(en_español(bateria.status).lower())
        if bateria.power_w is not None:
            estado.append(f"{bateria.power_w:.1f} W")
        if estado:
            lineas.append("- Estado: " + " · ".join(estado))
        if bateria.technology:
            lineas.append(f"- Tecnología: {bateria.technology}")
        voltajes = []
        if bateria.voltage_v:
            voltajes.append(f"{bateria.voltage_v:.2f} V")
        if bateria.design_voltage_v:
            voltajes.append(f"nominal {bateria.design_voltage_v:.2f} V")
        if voltajes:
            lineas.append("- Tensión: " + " · ".join(voltajes))
        # Los topes de carga solo si el portátil los trae: son de ASUS,
        # Lenovo y poco más, y en los demás dos guiones darían a entender que
        # falta algo.
        if (bateria.charge_start_percent is not None
                or bateria.charge_end_percent is not None):
            lineas.append(
                f"- Topes de carga: "
                f"{bateria.charge_start_percent if bateria.charge_start_percent is not None else '—'}"
                f" – "
                f"{bateria.charge_end_percent if bateria.charge_end_percent is not None else '—'} %")
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
              f"{len(snapshot.sensors)} lecturas en {len(arbol)} dispositivos.", ""]
    for aparato, categorias in arbol.items():
        cuantos = sum(len(s) for s in categorias.values())
        # Las categorías son claves —«cat.temperature»—, porque los nombres que
        # agrupan los inventa el programa y son interfaz. Sin traducirlas, el
        # informe enseñaba la clave cruda a quien lo abriera. Y va en español y
        # no en el idioma de quien lo genera, como el resto del informe: si no,
        # un informe en inglés saldría con «Procesador» y «temperatures» en la
        # misma página.
        resumen = ", ".join(f"{en_español(nombre).lower()} ({len(s)})"
                            for nombre, s in categorias.items())
        lineas.append(f"- **{aparato}**, {cuantos}: {resumen}")
        # Y con sus nombres y valores. El recuento solo dice cuántos hay, y lo
        # que se revisa de un equipo ajeno es justo lo otro: cómo se llama cada
        # sensor y si el número es creíble. Un chip que bautiza sus entradas
        # «temp1, temp2, temp3» y una placa que declara un mínimo de 127 grados
        # se ven aquí y en ningún otro sitio de este archivo.
        for nombre, sensores in categorias.items():
            valores = " · ".join(
                f"{s.label} {render.sensor_value(s.value, s.kind)} {s.unit}".strip()
                for s in sensores)
            lineas.append(f"  - {en_español(nombre).lower()}: {valores}")
    return "\n".join(lineas)


def _rendimiento() -> str:
    """La última prueba que puntúa, si la hay.

    Va en el informe porque es lo que permite juntar medidas de piezas que no
    están a mano. Sin esto, quien manda un informe manda su hardware y no lo
    que rinde, y la tabla de puntuaciones no se llena nunca.

    Solo la última comparable: un historial entero es del equipo de quien lo
    manda y aquí no aporta, y las de otra escala dirían una diferencia que no
    existe.
    """
    from . import history, score

    entradas = [e for e in history.load()
                if e.score_version == score.VERSION and score.comparable(e.seconds)]
    if not entradas:
        return ""
    ultima = max(entradas, key=lambda e: e.timestamp)
    puntos = score.puntuar(ultima.scores, ultima.threads)
    if puntos is None:
        return ""
    un_hilo, multi = puntos

    lineas = [
        "\n## Rendimiento\n",
        "| | |",
        "|---|---|",
        f"| Puntuación (todos los hilos) | {multi} |",
        f"| Puntuación (un hilo) | {un_hilo} |",
        f"| Hilos | {ultima.threads} |",
        f"| Escala | v{score.VERSION} |",
    ]
    # Las condiciones son la mitad de lo que hace comparable una cifra: sin
    # ellas, dos puntuaciones distintas no se sabe si separan a dos equipos o
    # a dos momentos del mismo.
    if ultima.governor:
        lineas.append(f"| Gobernador | {ultima.governor} |")
    if ultima.frequency_avg_hz:
        lineas.append(f"| Frecuencia media | {render.hz(ultima.frequency_avg_hz)} |")
    if ultima.temperature_peak_c is not None:
        lineas.append(f"| Temperatura máxima | {ultima.temperature_peak_c:.0f} °C |")
    if ultima.background_load is not None:
        lineas.append(f"| Carga de fondo | {ultima.background_load:.1f} % |")
    # El pico de lo ajeno explica una cifra baja que si no parece del equipo.
    if ultima.background_peak is not None:
        lineas.append(f"| Otro programa, como mucho | {ultima.background_peak:.1f} % |")
    return "\n".join(lineas) + "\n"


def _diagnostico(snapshot: Snapshot) -> str:
    """Lo que no se pudo leer y por qué. Es la parte útil de un informe de fallo."""
    lineas = ["", "## Diagnóstico", ""]

    if snapshot.driver_hints:
        lineas.append("**Módulos del kernel que ampliarían lo que se ve:**")
        lineas.append("")
        for pista in snapshot.driver_hints:
            lineas.append(f"- `{pista.module}`: {pista.provides}")
            if pista.command:
                lineas.append(f"  `{pista.command}`")
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


def _procedencia() -> str:
    """Si corre desde un AppImage o desde el código.

    Importa más de lo que parece: desde un AppImage el ayudante privilegiado
    necesita un rodeo, y un «no me deja elevar permisos» sin este dato no lleva
    a ninguna parte.
    """
    import os
    import sys

    if os.environ.get("APPIMAGE") or "/.mount_" in sys.executable:
        return "AppImage"
    return "código fuente o paquete del sistema"


def _version_de_qt() -> Optional[str]:
    try:
        import PySide6
        return PySide6.__version__
    except Exception:                                  # noqa: BLE001
        return None
