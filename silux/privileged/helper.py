#!/usr/bin/env python3
"""Ayudante privilegiado de silux. Se ejecuta como root, y solo hace esto.

Está escrito para poder leerse entero de una sentada, porque un programa que
corre con privilegios hay que poder auditarlo. De ahí tres decisiones:

* **No importa nada del propio silux**, solo la biblioteca estándar. Un fallo
  en cualquier otro módulo del programa no puede llegar hasta aquí.
* **No interpreta lo que lee.** Devuelve los bytes crudos de la tabla SMBIOS
  y deja que el proceso sin privilegios los analice. Analizar formatos
  binarios es de donde salen la mayoría de los fallos de memoria, y hacerlo
  como root sería regalar el problema.
* **No acepta rutas ni órdenes.** Las dos rutas que abre están escritas aquí
  como constantes, los registros MSR que admite son una lista cerrada y los
  nombres de disco tienen que encajar en un patrón que solo deja pasar
  `sda`, `nvme0n1` y parecidos.
* **De los discos solo pide diagnóstico.** Los dos comandos SMART que manda
  son de lectura y están fijados aquí; no hay forma de pedirle uno de
  escritura ni de borrado, que van por el mismo camino.
* **Del PMU solo cuenta, no muestrea.** Los eventos que abre son contadores
  de ocupación del motor gráfico y de tráfico del controlador de memoria,
  agregados de toda la máquina y sin periodo de muestreo: no hay búfer de
  muestras, ni pila de llamadas, ni nada de ningún proceso concreto. Es lo
  mismo que enseña `intel_gpu_top`. Los nombres los enumera el propio
  ayudante; el cliente pide una familia —la gráfica o la memoria— y nunca un
  nombre de PMU ni un número de evento.

Habla JSON por líneas: una petición por línea en la entrada, una respuesta
por línea en la salida. Termina cuando la entrada se cierra.
"""

from __future__ import annotations

import base64
import ctypes
import fcntl
import json
import os
import re
import struct
import sys
import time

# Sube cuando cambia lo que el ayudante sabe hacer: acciones nuevas, o
# registros nuevos en la lista blanca. El cliente la compara al conectar,
# porque una copia instalada en /usr/local/libexec se queda congelada en la
# fecha en que se instaló y no la actualiza nadie.
VERSION = 3

DMI_TABLE = "/sys/firmware/dmi/tables/DMI"
DMI_ENTRY_POINT = "/sys/firmware/dmi/tables/smbios_entry_point"

MAX_TABLE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024

# Nombres de disco admitidos. Estricto a propósito: sin esto, un nombre como
# «../../dev/mem» le haría abrir cualquier cosa.
DISK_NAME = re.compile(r"^(nvme\d+n\d+|nvme\d+|sd[a-z]{1,2}|hd[a-z])$")

# Las zonas de powercap que se dejan leer. El nombre lo pone el kernel y no
# tiene rutas dentro: se comprueba igualmente, porque lo que llega viene del
# proceso sin privilegios y aquí se es root.
RAPL_ZONE = re.compile(r"^[a-z]+-rapl:\d+$")
POWERCAP = "/sys/class/powercap"
SMART_BYTES = 512

# NVMe: ioctl de administración y el registro de salud.
NVME_ADMIN_CMD = 0xC0484E41           # _IOWR('N', 0x41, struct nvme_passthru_cmd)
NVME_GET_LOG_PAGE = 0x02
NVME_LOG_SMART = 0x02

# SATA: SMART READ DATA a través de ATA PASS-THROUGH.
SG_IO = 0x2285
SG_DXFER_FROM_DEV = -3
ATA_16 = 0x85
ATA_SMART = 0xB0
ATA_SMART_READ_DATA = 0xD0

# Lista cerrada de registros MSR. Todos son de solo lectura y documentados en
# los manuales de Intel y AMD; ninguno tiene efectos secundarios al leerlo.
MSR_ALLOWED = frozenset({
    0x0198, 0x0199, 0x019C, 0x01A2, 0x01AD,
    0x00CE, 0x0610, 0x0606,
    0xC0010293, 0xC0010299,
    # El voltaje del núcleo en AMD: qué P-state está activo y la definición de
    # los tres primeros, que llevan el VID en los bits 21:14. En Intel ese dato
    # va en 0x198, que ya estaba. Solo lectura y sin efectos, como los demás.
    0xC0010063,
    0xC0010064, 0xC0010065, 0xC0010066,
})

MAX_CPUS = 4096

# El PMU de las gráficas Intel: la ocupación por motor, que ni i915 ni xe
# publican en sysfs. El nombre del PMU y el de cada evento se enumeran aquí
# dentro y se filtran contra estos patrones; no hay forma de pedir otro.
PMU_ROOT = "/sys/bus/event_source/devices"
PMU_GPU = re.compile(r"^(i915|xe_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f])$")
PMU_EVENT = re.compile(r"^(rcs|bcs|vcs|vecs|ccs)\d+-busy$")

# El plano de energía de la gráfica integrada, que en los Intel de escritorio
# solo asoma por aquí: /sys/class/powercap publica package, core, uncore y
# dram, y ninguno de los cuatro es la gráfica. Se admite este evento y ninguno
# más del PMU de RAPL; los otros tres ya se leen por powercap sin privilegios.
PMU_POWER = "power"
PMU_POWER_EVENT = re.compile(r"^energy-gpu$")

# El controlador de memoria, que publica cuánto tráfico mueve hacia la RAM.
# Intel le cambia el nombre según la generación y hay que aceptar los tres:
# `uncore_imc` de Sandy Bridge a Comet Lake, `uncore_imc_free_running_N` de
# Ice Lake en adelante y `uncore_imc_N` en los de servidor, que además llaman
# a sus eventos por el comando de la DRAM en vez de por la dirección.
#
# `ia_requests` es el mismo tráfico visto por origen —lo que piden los
# núcleos— y está aquí porque se midió: contra 10 GiB leídos a propósito
# marcó 9,92. Sus hermanos `gt_requests` e `io_requests` no están, y no por
# falta de sitio: el segundo marca la misma cifra en reposo que bajo carga.
PMU_IMC = re.compile(r"^uncore_imc(_free_running)?(_\d+)?$")
PMU_IMC_EVENT = re.compile(
    r"^(data_reads?|data_writes?|cas_count_read|cas_count_write|ia_requests)$")

# Las dos familias que el cliente puede pedir. Son lo único que viaja por el
# protocolo: dentro de cada una, qué PMU y qué evento se abre lo decide este
# archivo.
FAMILIA_GPU = "gpu"
FAMILIA_IMC = "imc"

# Cuántos descriptores se abren como mucho, por familia. El del IMC es más
# alto porque un servidor tiene un PMU por canal de memoria y hay que abrirlos
# todos: quedarse a medias no daría un error, daría una cifra corta y creíble.
MAX_PMU_FDS = 32
MAX_IMC_FDS = 64

# perf_event_open no tiene envoltorio en libc: se invoca por número, y el
# número depende de la arquitectura. Donde no se sepa, no se intenta.
PERF_EVENT_OPEN = {"x86_64": 298, "aarch64": 241, "i686": 336, "armv7l": 364}


def _fail(message: str, code: str = "error") -> dict:
    return {"ok": False, "error": code, "message": message}


def read_smbios() -> dict:
    """Los bytes tal cual de la tabla SMBIOS y de su punto de entrada."""
    try:
        size = os.path.getsize(DMI_TABLE)
        if size > MAX_TABLE_BYTES:
            return _fail(f"la tabla mide {size} bytes, más de lo razonable", "too_large")
        with open(DMI_TABLE, "rb") as handle:
            table = handle.read(MAX_TABLE_BYTES)
    except FileNotFoundError:
        return _fail("este equipo no expone la tabla SMBIOS", "unsupported")
    except OSError as exc:
        return _fail(f"no se pudo leer la tabla SMBIOS: {exc}", "io")

    entry = b""
    try:
        with open(DMI_ENTRY_POINT, "rb") as handle:
            entry = handle.read(64)
    except OSError:
        pass                                  # el punto de entrada es opcional

    return {
        "ok": True,
        "table": base64.b64encode(table).decode("ascii"),
        "entry_point": base64.b64encode(entry).decode("ascii"),
    }


def read_msr(cpu: object, registers: object) -> dict:
    """Lee registros de la lista blanca en una CPU concreta."""
    if not isinstance(cpu, int) or not 0 <= cpu < MAX_CPUS:
        return _fail("número de CPU no válido", "bad_request")
    if not isinstance(registers, list) or not registers:
        return _fail("hacen falta registros que leer", "bad_request")

    rejected = [r for r in registers
                if not isinstance(r, int) or r not in MSR_ALLOWED]
    if rejected:
        return _fail(f"registros no permitidos: {rejected}", "forbidden")

    path = f"/dev/cpu/{cpu}/msr"
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return _fail("falta /dev/cpu/N/msr; hay que cargar el módulo «msr»", "no_module")
    except OSError as exc:
        return _fail(f"no se pudo abrir {path}: {exc}", "io")

    values: dict[str, int] = {}
    try:
        for register in registers:
            try:
                raw = os.pread(descriptor, 8, register)
            except OSError:
                continue                      # ese MSR no existe en esta CPU
            if len(raw) == 8:
                values[str(register)] = struct.unpack("<Q", raw)[0]
    finally:
        os.close(descriptor)

    return {"ok": True, "cpu": cpu, "values": values}


def read_smart(name) -> dict:
    """Los 512 bytes del registro de salud de un disco, sin interpretarlos.

    Los dos comandos que se mandan (`Get Log Page` en NVMe y `SMART READ DATA`
    en SATA) son de diagnóstico y de solo lectura. Interpretar lo que devuelven
    es trabajo del proceso sin privilegios: aquí solo se leen bytes.
    """
    if not isinstance(name, str) or not DISK_NAME.match(name):
        return _fail(f"nombre de disco no admitido: {name!r}", "bad_request")

    ruta = f"/dev/{name}"
    try:
        descriptor = os.open(ruta, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as error:
        return _fail(f"no se pudo abrir {ruta}: {error.strerror}", "io_error")

    try:
        if name.startswith("nvme"):
            datos, familia = _smart_nvme(descriptor), "nvme"
        else:
            datos, familia = _smart_ata(descriptor), "ata"
    except OSError as error:
        return _fail(f"el disco no respondió al diagnóstico: {error.strerror}",
                     "io_error")
    finally:
        os.close(descriptor)

    if datos is None:
        return _fail("el disco no devolvió datos de diagnóstico", "io_error")
    return {"ok": True, "device": name, "kind": familia,
            "data": base64.b64encode(datos).decode("ascii")}


def _smart_nvme(descriptor: int):
    """`Get Log Page` del registro 0x02, que es el de salud."""
    buffer = ctypes.create_string_buffer(SMART_BYTES)
    # struct nvme_passthru_cmd, 72 bytes. El número de dobles palabras va
    # menos uno, como manda la especificación.
    numd = SMART_BYTES // 4 - 1
    peticion = bytearray(struct.pack(
        "<BBHIIIQQIIIIIIIIII",
        NVME_GET_LOG_PAGE, 0, 0,          # opcode, flags, reservado
        0xFFFFFFFF,                       # nsid: el controlador entero
        0, 0,                             # cdw2, cdw3
        0,                                # metadata
        ctypes.addressof(buffer),         # addr
        0, SMART_BYTES,                   # metadata_len, data_len
        NVME_LOG_SMART | (numd << 16),    # cdw10
        0, 0, 0, 0, 0,                    # cdw11 a cdw15
        5000, 0,                          # timeout_ms, result
    ))
    fcntl.ioctl(descriptor, NVME_ADMIN_CMD, peticion)
    return buffer.raw


class _SgIoHdr(ctypes.Structure):
    """`struct sg_io_hdr`, la petición genérica del subsistema SCSI.

    Se declara con ctypes y no con `struct.pack` porque lleva punteros mezclados
    con enteros cortos, y el compilador inserta relleno para alinearlos. Con un
    formato empaquetado a mano los campos caen desplazados y el kernel lee
    basura donde espera un puntero.
    """

    _fields_ = [
        ("interface_id", ctypes.c_int),
        ("dxfer_direction", ctypes.c_int),
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]


def _smart_ata(descriptor: int):
    """`SMART READ DATA` por ATA PASS-THROUGH, que es como se pide en SATA."""
    orden = bytes((
        ATA_16,
        0x08,                     # protocolo 4: entrada de datos PIO
        0x0E,                     # dirección desde el disco, cuenta en sectores
        0x00, ATA_SMART_READ_DATA,
        0x00, 0x01,               # un sector
        0x00, 0x00,
        0x00, 0x4F,               # la firma que SMART exige en LBA medio
        0x00, 0xC2,               # y en LBA alto
        0x00, ATA_SMART, 0x00,
    ))
    buffer = ctypes.create_string_buffer(SMART_BYTES)
    sentido = ctypes.create_string_buffer(32)
    cmd = ctypes.create_string_buffer(orden, len(orden))

    cabecera = _SgIoHdr(
        interface_id=ord("S"),
        dxfer_direction=SG_DXFER_FROM_DEV,
        cmd_len=len(orden),
        mx_sb_len=len(sentido),
        dxfer_len=SMART_BYTES,
        dxferp=ctypes.cast(buffer, ctypes.c_void_p),
        cmdp=ctypes.cast(cmd, ctypes.c_void_p),
        sbp=ctypes.cast(sentido, ctypes.c_void_p),
        timeout=5000,
    )
    fcntl.ioctl(descriptor, SG_IO, cabecera)
    if cabecera.status not in (0, 2):      # 2 es «con información de sentido»
        return None
    return buffer.raw


class _PerfEventAttr(ctypes.Structure):
    """`struct perf_event_attr`, tal cual la espera el kernel.

    Se declara entera aunque solo se usen cuatro campos: el kernel comprueba
    el campo `size` contra las versiones que conoce, así que no vale con
    mandar un trozo. Todo lo demás va a cero, y eso es justo lo que interesa:
    `sample_period` a cero significa que el evento **cuenta** y no muestrea,
    o sea que no hay búfer, ni direcciones, ni registros de nadie.
    """

    _fields_ = [
        ("type", ctypes.c_uint32), ("size", ctypes.c_uint32),
        ("config", ctypes.c_uint64), ("sample_period", ctypes.c_uint64),
        ("sample_type", ctypes.c_uint64), ("read_format", ctypes.c_uint64),
        ("flags", ctypes.c_uint64), ("wakeup_events", ctypes.c_uint32),
        ("bp_type", ctypes.c_uint32), ("config1", ctypes.c_uint64),
        ("config2", ctypes.c_uint64), ("branch_sample_type", ctypes.c_uint64),
        ("sample_regs_user", ctypes.c_uint64),
        ("sample_stack_user", ctypes.c_uint32), ("clockid", ctypes.c_int32),
        ("sample_regs_intr", ctypes.c_uint64), ("aux_watermark", ctypes.c_uint32),
        ("sample_max_stack", ctypes.c_uint16), ("__reserved_2", ctypes.c_uint16),
        ("aux_sample_size", ctypes.c_uint32), ("__reserved_3", ctypes.c_uint32),
    ]


# Descriptores abiertos del PMU, por familia, PMU y evento. Se abren una sola
# vez y se dejan vivos: los contadores son acumulativos desde que se abren, así
# que cerrarlos y volver a abrirlos entre muestreos perdería la referencia.
_PMU_FDS: dict[str, dict[str, dict[str, int]]] = {}
_PMU_FALLO: dict[str, str] = {}
# Si el tope de descriptores dejó eventos sin abrir. Solo importa en el IMC,
# donde los contadores se suman entre canales y faltar uno rebaja el total.
_PMU_TRUNCADO: dict[str, bool] = {}


def _pmu_admitido(familia: str, pmu: str):
    """Qué eventos se dejan abrir en ese PMU, o None si no es de la familia.

    Aquí está la lista entera de lo que este ayudante puede contar. El cliente
    pide una familia y nada más: ni el nombre del PMU ni el número de evento
    llegan nunca de fuera.
    """
    if familia == FAMILIA_GPU:
        if PMU_GPU.match(pmu):
            return PMU_EVENT
        if pmu == PMU_POWER:
            return PMU_POWER_EVENT
    elif familia == FAMILIA_IMC:
        if PMU_IMC.match(pmu):
            return PMU_IMC_EVENT
    return None


def _pmu_campo(pmu: str, campo: str):
    """En qué bit de `config` empieza un campo, según el propio kernel.

    Cada PMU publica su formato: «config:0-7» quiere decir que ese campo son
    los ocho bits bajos. i915 lo llama `i915_eventid` y RAPL `event`, y por
    eso hay que mirarlo en vez de darlo por sabido.
    """
    if campo == "config":
        return 0
    try:
        with open(f"{PMU_ROOT}/{pmu}/format/{campo}", encoding="ascii") as handle:
            crudo = handle.read(32).strip()
    except OSError:
        return None
    if not crudo.startswith("config:"):
        return None
    try:
        return int(crudo[len("config:"):].split("-")[0])
    except ValueError:
        return None


def _pmu_config(pmu: str, evento: str):
    """El número de evento que el kernel publica, leído del propio sysfs.

    El cliente manda nombres, nunca números: quien traduce de un nombre de la
    lista a un `config` es este fichero del kernel. El contenido es
    «config=0x2000» en i915 y «event=0x04» en RAPL, que no es lo mismo: el
    segundo hay que colocarlo en los bits que diga el formato del PMU.
    """
    try:
        with open(f"{PMU_ROOT}/{pmu}/events/{evento}", encoding="ascii") as handle:
            crudo = handle.read(64).strip()
    except OSError:
        return None
    if "," in crudo or "=" not in crudo:
        return None            # si trae parámetros de sobra, no se toca
    campo, _, valor = crudo.partition("=")
    desplazamiento = _pmu_campo(pmu, campo.strip())
    if desplazamiento is None:
        return None
    try:
        return int(valor.strip(), 0) << desplazamiento
    except ValueError:
        return None


def _abrir_pmu(familia: str) -> None:
    """Abre los contadores de esa familia que esta máquina publique."""
    tope = MAX_IMC_FDS if familia == FAMILIA_IMC else MAX_PMU_FDS
    vacio = ("no hay ningún controlador de memoria con contadores"
             if familia == FAMILIA_IMC
             else "no hay ninguna gráfica con contadores de ocupación")
    fds: dict[str, dict[str, int]] = {}
    fallo = ""

    numero = PERF_EVENT_OPEN.get(os.uname().machine)
    if numero is None:
        _PMU_FALLO[familia] = f"perf_event_open no está mapeado en {os.uname().machine}"
        return
    try:
        nombres = sorted(os.listdir(PMU_ROOT))
    except OSError:
        _PMU_FALLO[familia] = "este kernel no publica ningún PMU"
        return

    libc = ctypes.CDLL(None, use_errno=True)
    abiertos = 0
    truncado = False
    for pmu in nombres:
        patron = _pmu_admitido(familia, pmu)
        if patron is None:
            continue
        try:
            with open(f"{PMU_ROOT}/{pmu}/type", encoding="ascii") as handle:
                tipo = int(handle.read(16).strip())
            eventos = sorted(os.listdir(f"{PMU_ROOT}/{pmu}/events"))
        except (OSError, ValueError):
            continue

        for evento in eventos:
            if not patron.match(evento):
                continue
            if abiertos >= tope:
                # Quedarse a medias en el IMC no da un error, da una suma
                # corta: se avisa para que nadie publique esa cifra.
                truncado = True
                continue
            config = _pmu_config(pmu, evento)
            if config is None:
                continue
            attr = _PerfEventAttr()
            attr.type = tipo
            attr.size = ctypes.sizeof(_PerfEventAttr)
            attr.config = config
            # pid=-1 y cpu=0: es un PMU de dispositivo, no uno por núcleo, y
            # cuenta lo que hace la máquina entera. No se ata a ningún proceso.
            descriptor = libc.syscall(numero, ctypes.byref(attr), -1, 0, -1, 0)
            if descriptor < 0:
                if not fallo:
                    fallo = os.strerror(ctypes.get_errno())
                continue
            fds.setdefault(pmu, {})[evento] = descriptor
            abiertos += 1

    if fds:
        _PMU_FDS[familia] = fds
        _PMU_TRUNCADO[familia] = truncado
    if not fds and not fallo:
        fallo = vacio
    if fallo:
        _PMU_FALLO[familia] = fallo


def _pmu_escala(pmu: str, evento: str):
    """El factor que el kernel publica para convertir el contador a su unidad.

    Solo lo traen los de energía. Devolverlo es pasar un dato del kernel tal
    cual; interpretarlo es cosa del proceso sin privilegios.
    """
    try:
        with open(f"{PMU_ROOT}/{pmu}/events/{evento}.scale", encoding="ascii") as h:
            return float(h.read(64).strip())
    except (OSError, ValueError):
        return None


def _pmu_unidad(pmu: str, evento: str):
    """La unidad que el kernel publica para un contador, si publica alguna.

    Va con la escala y por el mismo motivo: es un dato del kernel y aquí se
    pasa tal cual. Que el contador del controlador de memoria cuente MiB y no
    otra cosa lo comprueba el proceso sin privilegios, que es quien va a
    convertirlo en bytes por segundo.
    """
    try:
        with open(f"{PMU_ROOT}/{pmu}/events/{evento}.unit", encoding="ascii") as h:
            return h.read(32).strip()
    except OSError:
        return None


def _leer_familia(familia: str, con_unidad: bool = False) -> dict:
    """Lee de una vez todos los contadores abiertos de una familia.

    Ocho bytes por descriptor y nada más. Restar contra la vuelta anterior y
    convertir a porcentajes, vatios o bytes por segundo es cosa del proceso
    sin privilegios: aquí no se interpreta ninguna cifra.

    La unidad solo se busca donde hace falta. Los de la gráfica no la usan y
    pedirla serían ocho aperturas de sysfs por segundo, como root, para tirar
    lo leído.
    """
    contadores: dict[str, dict[str, int]] = {}
    escalas: dict[str, dict[str, float]] = {}
    unidades: dict[str, dict[str, str]] = {}
    for pmu, eventos in _PMU_FDS.get(familia, {}).items():
        for evento, descriptor in eventos.items():
            try:
                # os.read y no os.pread: un descriptor de perf no es
                # posicionable y pread devolvería ESPIPE.
                crudo = os.read(descriptor, 8)
            except OSError:
                continue
            if len(crudo) != 8:
                continue
            contadores.setdefault(pmu, {})[evento] = struct.unpack("<Q", crudo)[0]
            escala = _pmu_escala(pmu, evento)
            if escala is not None:
                escalas.setdefault(pmu, {})[evento] = escala
            unidad = _pmu_unidad(pmu, evento) if con_unidad else None
            if unidad:
                unidades.setdefault(pmu, {})[evento] = unidad
    return {"counters": contadores, "scales": escalas, "units": unidades}


def read_gpu_pmu() -> dict:
    """Los contadores de ocupación por motor, en crudo y con su reloj.

    Devuelve nanosegundos acumulados desde que se abrió cada contador. Quién
    los reste y los convierta en un porcentaje es el proceso sin privilegios;
    aquí solo se leen ocho bytes por descriptor.
    """
    if FAMILIA_GPU not in _PMU_FDS:
        _abrir_pmu(FAMILIA_GPU)
    if FAMILIA_GPU not in _PMU_FDS:
        return _fail("no se pudo leer el PMU de la gráfica: "
                     f"{_PMU_FALLO.get(FAMILIA_GPU, '')}", "unsupported")

    leido = _leer_familia(FAMILIA_GPU)
    if not leido["counters"]:
        return _fail("los contadores dejaron de responder", "io")
    return {"ok": True, "monotonic_ns": time.monotonic_ns(),
            "engines": leido["counters"], "scales": leido["scales"]}


def read_imc() -> dict:
    """Cuánto tráfico mueve el controlador de memoria, en crudo.

    Cada cuenta es una línea de caché movida entre el controlador y la RAM
    desde que se abrió el contador; cuántos bytes son lo dice la escala que
    publica el kernel, y por eso viaja al lado. Es lo mismo que enseña
    `intel_gpu_top` junto a la gráfica, aunque el dato no sea de la gráfica:
    es el controlador entero, con el tráfico del procesador dentro.
    """
    if FAMILIA_IMC not in _PMU_FDS:
        _abrir_pmu(FAMILIA_IMC)
    if FAMILIA_IMC not in _PMU_FDS:
        return _fail("no se pudo leer el PMU del controlador de memoria: "
                     f"{_PMU_FALLO.get(FAMILIA_IMC, '')}", "unsupported")

    leido = _leer_familia(FAMILIA_IMC, con_unidad=True)
    if not leido["counters"]:
        return _fail("los contadores dejaron de responder", "io")
    return {"ok": True, "monotonic_ns": time.monotonic_ns(),
            "counters": leido["counters"], "scales": leido["scales"],
            "units": leido["units"],
            "truncated": _PMU_TRUNCADO.get(FAMILIA_IMC, False)}


def read_rapl() -> dict:
    """Los contadores de energía del procesador, en microjulios.

    Desde el kernel 5.10 `energy_uj` no se lee sin privilegios: se restringió
    porque muestrearlo a mucha frecuencia deja ver el patrón de consumo de otro
    proceso. Leerlo una vez por segundo, que es lo que hace esta ventana, es lo
    mismo que hacen `powertop` o `s-tui`.

    Sin esto, en las máquinas donde el kernel lo restringe —AMD sobre todo— el
    aviso de «requiere permisos» del consumo del procesador no se iba nunca:
    el usuario daba los permisos, el ayudante arrancaba, y nadie leía esto.

    Se devuelven los microjulios en crudo. Los vatios son su derivada y eso lo
    calcula el proceso sin privilegios, que es quien guarda la lectura
    anterior.
    """
    zonas = {}
    try:
        nombres = sorted(os.listdir(POWERCAP))
    except OSError as error:
        return _fail(f"no se pudo leer {POWERCAP}: {error.strerror}", "io_error")

    for nombre in nombres:
        if not RAPL_ZONE.match(nombre):
            continue
        try:
            with open(f"{POWERCAP}/{nombre}/energy_uj", encoding="ascii") as fh:
                zonas[nombre] = int(fh.read().strip())
        except (OSError, ValueError):
            continue
    if not zonas:
        return _fail("ninguna zona de powercap respondió", "io_error")
    return {"ok": True, "zones": zonas}


def handle(request: dict) -> dict:
    action = request.get("action")
    if action == "ping":
        return {"ok": True, "version": VERSION, "uid": os.geteuid()}
    if action == "smbios":
        return read_smbios()
    if action == "msr":
        return read_msr(request.get("cpu"), request.get("registers"))
    if action == "smart":
        return read_smart(request.get("device"))
    if action == "gpu_pmu":
        return read_gpu_pmu()
    if action == "imc":
        return read_imc()
    if action == "rapl":
        return read_rapl()
    return _fail(f"acción desconocida: {action!r}", "bad_request")


def main() -> int:
    if os.geteuid() != 0:
        print(json.dumps(_fail("el ayudante tiene que ejecutarse como root", "not_root")),
              flush=True)
        return 1

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if len(line) > MAX_REQUEST_BYTES:
            response = _fail("petición demasiado larga", "bad_request")
        else:
            try:
                request = json.loads(line)
            except ValueError:
                response = _fail("la petición no es JSON válido", "bad_request")
            else:
                response = handle(request) if isinstance(request, dict) else \
                    _fail("la petición tiene que ser un objeto", "bad_request")
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
