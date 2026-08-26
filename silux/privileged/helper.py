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

VERSION = 1

DMI_TABLE = "/sys/firmware/dmi/tables/DMI"
DMI_ENTRY_POINT = "/sys/firmware/dmi/tables/smbios_entry_point"

MAX_TABLE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024

# Nombres de disco admitidos. Estricto a propósito: sin esto, un nombre como
# «../../dev/mem» le haría abrir cualquier cosa.
DISK_NAME = re.compile(r"^(nvme\d+n\d+|nvme\d+|sd[a-z]{1,2}|hd[a-z])$")
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
})

MAX_CPUS = 4096


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
