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
  como constantes, y los registros MSR que admite son una lista cerrada.

Habla JSON por líneas: una petición por línea en la entrada, una respuesta
por línea en la salida. Termina cuando la entrada se cierra.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys

VERSION = 1

DMI_TABLE = "/sys/firmware/dmi/tables/DMI"
DMI_ENTRY_POINT = "/sys/firmware/dmi/tables/smbios_entry_point"

MAX_TABLE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024

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


def handle(request: dict) -> dict:
    action = request.get("action")
    if action == "ping":
        return {"ok": True, "version": VERSION, "uid": os.geteuid()}
    if action == "smbios":
        return read_smbios()
    if action == "msr":
        return read_msr(request.get("cpu"), request.get("registers"))
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
