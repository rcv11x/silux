"""Interprets the diagnostic data a disk returns.

The privileged helper fetches the bytes without looking at them; they are
parsed here, without privileges, since parsing binary formats is where most
memory bugs come from, and doing it as root would hand the problem over.

The two formats have little in common:

- **NVMe** has a fixed, well-defined log: every field has its place and
  means the same on any disk. One of the few formats in this industry that
  can be trusted without checking the maker.
- **SATA** has a table of numbered attributes, and each maker decides what
  goes in which. The numbers that matter have been the same for twenty
  years, but an attribute's raw value can mean hours on one disk and
  minutes on another, so only those with an agreed meaning are read.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
import struct
from typing import Optional

from .model import DiskHealth

# An NVMe «data unit» is a thousand 512-byte sectors.
NVME_DATA_UNIT = 1000 * 512
# The logical sectors SATA counts what was written in.
ATA_SECTOR = 512

# What one unit of attribute 241 is worth, by the disk's maker.
#
# The attribute is called «LBAs written» and almost everyone counts 512-byte
# sectors, but nothing requires it and some makers count much larger
# blocks. Kioxia uses 32 MiB blocks: assuming 512 bytes, a disk with 23 TiB
# written claimed 367 MB, 65 536 times less.
#
# Not even the reference tools agree. `smartctl` labels the attribute
# «Lifetime_Writes_GiB», which would give 735 TiB, more than the disk could
# take, and libatasmart assumes 32 MiB. Since the attribute itself can't
# tell, only what was measured on real hardware goes here: write a known
# amount and see how much the counter rises.
#
# Anything not in this table counts 512-byte sectors, as nearly every disk
# does.
ATA_WRITE_UNIT: dict[str, int] = {
    # Checked on a 240 GB KIOXIA-EXCERIA SATA: 4.09 GiB written, the counter
    # rose 133 units → 31.5 MiB per unit, so 32 MiB.
    "kioxia": 32 * 1024 * 1024,
    # Toshiba sold these same disks before its memory division was renamed
    # Kioxia, and they share firmware.
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
    """What one unit of this counter is worth on this disk.

    What was measured first; then smartmontools' drive database, which needs
    the whole model (sysfs cuts it to 16 characters); then 512-byte sectors,
    as the standard counts them. None when the counter is the flash's and
    not what the computer wrote, or when the disk's own model isn't known
    (a USB bridge that doesn't pass it): the unit depends on the maker.
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
    return ATA_SECTOR if model else None

ABSOLUTE_ZERO = 273.15


class _Nvme:
    """Offsets in the NVMe health log, fixed by the specification."""

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


# SATA attributes that mean the same for every maker.
ATA_POWER_ON_HOURS = 9
ATA_POWER_CYCLES = 12
ATA_TEMPERATURE = 194
# The usual one, and the one Crucial and Micron use for the same thing.
ATA_WRITTEN = (241, 246)
ATA_READ = (242, 247)

# Counters that fit in 32 bits with room to spare, where several makers use
# the top two bytes for something else. A Seagate claimed 132 trillion
# power-on hours, fifteen billion years, because it keeps something of its
# own there; its low 32 bits are 13 147 hours, a disk a year and a half
# old.
ATA_32_BITS = (ATA_POWER_ON_HOURS, ATA_POWER_CYCLES)

# No disk ever made has been on for two hundred years. Above that, the
# counter doesn't mean what it seems and is better not shown.
PLAUSIBLE_HOURS = 200 * 365 * 24
ATA_REALLOCATED = 5
ATA_PENDING = 197
ATA_UNCORRECTABLE = 198
# Makers publish an SSD's wear under three different numbers; all three hold
# the same thing: how much life is left, from 100 to 0.
ATA_LIFE_LEFT = (231, 233, 177, 202)


def parse(data: bytes, kind: str, vendor: Optional[str] = None,
          model: Optional[str] = None, firmware: Optional[str] = None) -> Optional[DiskHealth]:
    """None if the data doesn't look as it should.

    The vendor and model are only needed on SATA, and only to know which
    units the disk counts what it wrote in. NVMe doesn't need them: its
    health log is defined by the specification and means the same on any
    disk.
    """
    if kind == "nvme":
        return _parse_nvme(data)
    if kind == "ata":
        return _parse_ata(data, vendor, model, firmware)
    return None


def _u128(data: bytes, offset: int) -> Optional[int]:
    """NVMe keeps its counters in 128 bits. Nothing comes close."""
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
        # A disk can go past 100 %: it still works, it has just used all the
        # life the maker guaranteed.
        percentage_used=used,
        spare_percent=data[_Nvme.AVAILABLE_SPARE],
        unsafe_shutdowns=_u128(data, _Nvme.UNSAFE_SHUTDOWNS) or None,
        media_errors=_u128(data, _Nvme.MEDIA_ERRORS),
        critical_warning=data[_Nvme.CRITICAL_WARNING],
    )
    # A log that is all zeros is a disk that doesn't implement it, not a
    # brand-new one with zero hours.
    if not any((health.power_on_hours, health.written_bytes, kelvin)):
        return None
    return health


def nvme_temperature(data: bytes) -> Optional[float]:
    """The log's temperature, which NVMe gives in kelvin."""
    if len(data) < 3:
        return None
    kelvin = struct.unpack_from("<H", data, _Nvme.TEMPERATURE)[0]
    if not kelvin:
        return None
    return round(kelvin - ABSOLUTE_ZERO, 1)


def _attributes(data: bytes) -> dict[int, tuple[int, int]]:
    """The table's thirty attributes: {id: (normalized, raw)}.

    The normalized value goes from 100 to 0 and the disk interprets it; the
    raw one is the actual counter. Which one counts depends on the attribute.
    """
    found: dict[int, tuple[int, int]] = {}
    for index in range(30):
        start = 2 + index * 12
        if start + 12 > len(data):
            break
        attr_id = data[start]
        if attr_id == 0:                 # empty slot
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
        """The first of these attributes the disk publishes.

        Several makers keep the same thing under different numbers, so they
        are tried in order rather than assuming one.
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

    written = in_bytes(*ATA_WRITTEN)
    return DiskHealth(
        power_on_hours=hours,
        power_cycles=raw(ATA_POWER_CYCLES),
        written_bytes=written,
        read_bytes=in_bytes(*ATA_READ),
        # Counted, but in a unit that isn't known for this disk.
        counters_unit_unknown=written is None and any(
            table.get(attr_id, (0, 0))[1] for attr_id in ATA_WRITTEN),
        # The attribute keeps the life left; the model keeps it used.
        percentage_used=100 - life_left if life_left is not None else None,
        # Each by its own name: a reallocated sector already failed and was
        # replaced by a spare; a pending one can't be read now; an
        # uncorrectable one couldn't be read in the disk's offline scan.
        reallocated_sectors=raw(ATA_REALLOCATED),
        pending_sectors=raw(ATA_PENDING),
        uncorrectable_sectors=raw(ATA_UNCORRECTABLE),
        attributes=tuple((attr_id, normalized, raw_value)
                         for attr_id, (normalized, raw_value) in sorted(table.items())),
    )


def ata_temperature(data: bytes) -> Optional[float]:
    """The temperature from the attribute table, if the disk publishes it."""
    if len(data) < 362:
        return None
    entry = _attributes(data).get(ATA_TEMPERATURE)
    if not entry:
        return None
    # Many disks keep minimums and maximums in the raw value's high bytes;
    # the current temperature is in the low byte.
    degrees = entry[1] & 0xFF
    return float(degrees) if 0 < degrees < 120 else None
