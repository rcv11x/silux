"""Interpreta los datos de diagnóstico que devuelve un disco.

El ayudante privilegiado pide los bytes y no los mira; el análisis se hace
aquí, sin privilegios, porque analizar formatos binarios es de donde salen la
mayoría de los fallos de memoria y hacerlo como root sería regalar el problema.

Los dos formatos no se parecen:

- **NVMe** tiene un registro fijo y bien definido: cada campo está en su sitio
  y significa lo mismo en cualquier disco. Es de los pocos formatos de esta
  industria en los que uno puede fiarse sin comprobar el fabricante.
- **SATA** tiene una tabla de atributos numerados donde cada fabricante decide
  qué guarda en cuáles. Los números que importan son los mismos desde hace
  veinte años, pero el valor «en crudo» de un atributo puede significar horas
  en un disco y minutos en otro, así que aquí solo se leen los que tienen un
  significado acordado.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
import struct
from typing import Optional

from .model import DiskHealth

# Una «unidad de datos» de NVMe son mil sectores de 512 bytes.
NVME_DATA_UNIT = 1000 * 512
# Los sectores lógicos con los que SATA cuenta lo escrito.
ATA_SECTOR = 512

# Cuánto vale una unidad del atributo 241 según quién fabrique el disco.
#
# El atributo se llama «LBAs escritas» y casi todo el mundo cuenta sectores de
# 512 bytes, pero no es obligatorio y algunos fabricantes cuentan bloques
# mucho mayores. Kioxia usa bloques de 32 MiB: dando por hecho los 512 bytes,
# un disco con 23 TiB escritos declaraba 367 MB, que son 65 536 veces menos.
#
# Ni siquiera las herramientas de referencia coinciden. `smartctl` etiqueta
# ese atributo como «Lifetime_Writes_GiB» —que daría 735 TiB, más de lo que
# el disco aguantaría— y libatasmart asume 32 MiB. Como no hay forma de
# deducirlo del propio atributo, aquí solo se apunta lo que se ha medido
# contra hardware real: se escribe una cantidad conocida y se mira cuánto
# sube el contador.
#
# Lo que no esté en esta tabla se cuenta en sectores de 512 bytes, que es lo
# que hace la inmensa mayoría y lo que el programa venía haciendo.
ATA_WRITE_UNIT: dict[str, int] = {
    # Comprobado en un KIOXIA-EXCERIA SATA de 240 GB: escritos 4,09 GiB, el
    # contador subió 133 unidades → 31,5 MiB por unidad, o sea 32 MiB.
    "kioxia": 32 * 1024 * 1024,
    # Toshiba vendía estos mismos discos antes de que la división de memorias
    # pasara a llamarse Kioxia, y comparten firmware.
    "toshiba": 32 * 1024 * 1024,
}


DRIVEDB = pathlib.Path(__file__).resolve().parent / "db" / "smart_units.json"


@functools.lru_cache(maxsize=1)
def _drivedb() -> tuple[tuple[re.Pattern, Optional[re.Pattern], dict[int, Optional[int]]], ...]:
    """smartmontools' units per model (`tools/gen_smart_units.py`), compiled.

    Its patterns are matched against the whole model, as smartctl does, and
    the first entry that matches is the one that counts.
    """
    try:
        rows = json.loads(DRIVEDB.read_text(encoding="utf-8"))["drives"]
    except (OSError, ValueError, KeyError):
        return ()
    return tuple((re.compile(r["model"]),
                  re.compile(r["firmware"]) if r.get("firmware") else None,
                  {int(k): v for k, v in r["units"].items()})
                 for r in rows)


def _write_unit(vendor: Optional[str], model: Optional[str],
                      firmware: Optional[str] = None, attribute: int = 241) -> Optional[int]:
    """Cuánto vale una unidad de este contador en este disco.

    What was measured first; then smartmontools' drive database, which needs
    the whole model (sysfs cuts it to 16 characters); then 512-byte sectors.
    None when the counter is the flash's and not what the computer wrote.
    """
    for text in (vendor, model):
        if not text:
            continue
        lowered = text.lower()
        for brand, unit in ATA_WRITE_UNIT.items():
            if brand in lowered:
                return unit
    if model:
        for pattern, firmware_pattern, units in _drivedb():
            if pattern.fullmatch(model) and (
                    firmware_pattern is None or (firmware and firmware_pattern.fullmatch(firmware))):
                return units.get(attribute, ATA_SECTOR)
    return ATA_SECTOR

ABSOLUTE_ZERO = 273.15


class _Nvme:
    """Posiciones del registro de salud de NVMe. Son fijas por especificación."""

    CRITICAL_WARNING = 0
    TEMPERATURE = 1
    AVAILABLE_SPARE = 3
    PERCENTAGE_USED = 5
    DATA_UNITS_READ = 32
    DATA_UNITS_WRITTEN = 48
    POWER_CYCLES = 112
    POWER_ON_HOURS = 128
    UNSAFE_SHUTDOWNS = 144
    MEDIA_ERRORS = 160


# Los atributos de SATA que significan lo mismo en todos los fabricantes.
ATA_POWER_ON_HOURS = 9
ATA_POWER_CYCLES = 12
ATA_TEMPERATURE = 194
# El de siempre y el que usan Crucial y Micron para lo mismo.
ATA_WRITTEN = (241, 246)
ATA_READ = (242, 247)

# Contadores que caben de sobra en 32 bits y donde varios fabricantes usan los
# dos bytes altos del contador para otra cosa. Un Seagate declaraba 132 billones
# de horas de encendido —quince mil millones de años— porque ahí guarda algo
# suyo; leídos los 32 bits bajos son 13 147 horas, que es un disco de año y
# medio. Es exactamente lo que avisa la cabecera de este módulo, y pasó igual.
ATA_32_BITS = (ATA_POWER_ON_HOURS, ATA_POWER_CYCLES)

# Ningún disco fabricado ha estado encendido doscientos años. Si sale más, el
# contador no significa lo que se cree y es mejor no enseñarlo.
PLAUSIBLE_HOURS = 200 * 365 * 24
ATA_REALLOCATED = 5
ATA_PENDING = 197
ATA_UNCORRECTABLE = 198
# El desgaste de un SSD lo publican con tres números distintos según la marca;
# los tres guardan lo mismo: cuánta vida queda, de 100 a 0.
ATA_LIFE_LEFT = (231, 233, 177, 202)


def parse(data: bytes, kind: str, vendor: Optional[str] = None,
          model: Optional[str] = None, firmware: Optional[str] = None) -> Optional[DiskHealth]:
    """Devuelve None si los datos no tienen la pinta que deberían.

    El fabricante y el modelo hacen falta solo en SATA, y solo para saber en
    qué unidades cuenta el disco lo que lleva escrito. NVMe no los necesita:
    su registro de salud está definido por la especificación y significa lo
    mismo en cualquier disco.
    """
    if kind == "nvme":
        return _parse_nvme(data)
    if kind == "ata":
        return _parse_ata(data, vendor, model, firmware)
    return None


def _u128(data: bytes, offset: int) -> Optional[int]:
    """NVMe guarda los contadores en 128 bits. Nadie llega ni de lejos."""
    if offset + 16 > len(data):
        return None
    low, high = struct.unpack_from("<QQ", data, offset)
    return low | (high << 64)


def _parse_nvme(data: bytes) -> Optional[DiskHealth]:
    if len(data) < 512:
        return None

    kelvin = struct.unpack_from("<H", data, _Nvme.TEMPERATURE)[0]
    written = _u128(data, _Nvme.DATA_UNITS_WRITTEN)
    read_units = _u128(data, _Nvme.DATA_UNITS_READ)
    hours = _u128(data, _Nvme.POWER_ON_HOURS)
    used = data[_Nvme.PERCENTAGE_USED]

    health = DiskHealth(
        power_on_hours=hours or None,
        power_cycles=_u128(data, _Nvme.POWER_CYCLES) or None,
        written_bytes=written * NVME_DATA_UNIT if written else None,
        read_bytes=read_units * NVME_DATA_UNIT if read_units else None,
        # Un disco puede pasar del 100 %: sigue funcionando, solo que ya ha
        # gastado toda la vida que el fabricante garantizaba.
        percentage_used=used,
        spare_percent=data[_Nvme.AVAILABLE_SPARE],
        unsafe_shutdowns=_u128(data, _Nvme.UNSAFE_SHUTDOWNS) or None,
        media_errors=_u128(data, _Nvme.MEDIA_ERRORS),
        critical_warning=data[_Nvme.CRITICAL_WARNING],
    )
    # Un registro entero a ceros es un disco que no lo implementa, no uno
    # recién estrenado con cero horas.
    if not any((health.power_on_hours, health.written_bytes, kelvin)):
        return None
    return health


def nvme_temperature(data: bytes) -> Optional[float]:
    """La temperatura del registro, que NVMe da en kelvin."""
    if len(data) < 3:
        return None
    kelvin = struct.unpack_from("<H", data, _Nvme.TEMPERATURE)[0]
    if not kelvin:
        return None
    return round(kelvin - ABSOLUTE_ZERO, 1)


def _attributes(data: bytes) -> dict[int, tuple[int, int]]:
    """Los treinta atributos de la tabla: {id: (normalizado, en crudo)}.

    El normalizado va de 100 a 0 y lo interpreta el disco; el crudo es el
    contador de verdad. Cuál de los dos vale depende del atributo.
    """
    found: dict[int, tuple[int, int]] = {}
    for index in range(30):
        start = 2 + index * 12
        if start + 12 > len(data):
            break
        attr_id = data[start]
        if attr_id == 0:                 # entrada vacía
            continue
        normalized = data[start + 3]
        raw_bytes = data[start + 5:start + 11]
        width = 4 if attr_id in ATA_32_BITS else 6
        raw = int.from_bytes(raw_bytes[:width], "little")
        found[attr_id] = (normalized, raw)
    return found


def _parse_ata(data: bytes, vendor: Optional[str] = None,
               model: Optional[str] = None,
               firmware: Optional[str] = None) -> Optional[DiskHealth]:
    if len(data) < 362:
        return None
    table = _attributes(data)
    if not table:
        return None

    def raw(*attr_ids: int) -> Optional[int]:
        """El primero de estos atributos que el disco publique.

        Varios fabricantes guardan lo mismo en números distintos, así que se
        prueban en orden en vez de dar por hecho uno solo.
        """
        for attr_id in attr_ids:
            entry = table.get(attr_id)
            if entry:
                return entry[1]
        return None

    def in_bytes(*attr_ids: int) -> Optional[int]:
        """The first of these counters, in bytes, with its own unit."""
        for attr_id in attr_ids:
            entry = table.get(attr_id)
            if entry:
                unit = _write_unit(vendor, model, firmware, attr_id)
                return entry[1] * unit if entry[1] and unit else None
        return None

    life_left = next((table[i][0] for i in ATA_LIFE_LEFT if i in table), None)
    hours = raw(ATA_POWER_ON_HOURS)
    if hours is not None and hours > PLAUSIBLE_HOURS:
        hours = None

    return DiskHealth(
        power_on_hours=hours,
        power_cycles=raw(ATA_POWER_CYCLES),
        written_bytes=in_bytes(*ATA_WRITTEN),
        read_bytes=in_bytes(*ATA_READ),
        # El atributo guarda la vida que queda; el modelo la guarda gastada.
        percentage_used=100 - life_left if life_left is not None else None,
        # Un sector reasignado es un trozo de disco que ya se estropeó y se
        # sustituyó por uno de repuesto. Que haya alguno no es fatal; que
        # crezcan con el tiempo sí.
        media_errors=(raw(ATA_REALLOCATED) or 0) + (raw(ATA_PENDING) or 0)
        + (raw(ATA_UNCORRECTABLE) or 0),
        attributes=tuple((attr_id, normalized, raw_value)
                         for attr_id, (normalized, raw_value) in sorted(table.items())),
    )


def ata_temperature(data: bytes) -> Optional[float]:
    """La temperatura de la tabla de atributos, si el disco la publica."""
    if len(data) < 362:
        return None
    entry = _attributes(data).get(ATA_TEMPERATURE)
    if not entry:
        return None
    # Los bits altos del crudo llevan mínimos y máximos en muchos discos; la
    # temperatura actual está en el byte bajo.
    degrees = entry[1] & 0xFF
    return float(degrees) if 0 < degrees < 120 else None
