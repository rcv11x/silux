"""SMBIOS table parser.

The table is a list of binary structures, each with a four-byte header
(type, length, handle), a fixed-size field area and, after it, the text
strings separated by zeros. Text fields don't hold the string but its
position in that list.

Only the types needed are interpreted: 4 (the processor's socket), 9 (the
board's slots), 16 (memory array) and 17 (each module). The rest is passed
over untouched.

Reference: DMTF DSP0134, «System Management BIOS (SMBIOS) Reference
Specification».
"""

from __future__ import annotations

import re
import struct
from typing import Iterator, Optional

from ..model import LOGICAL_NON_VOLATILE

TYPE_PROCESSOR = 4
TYPE_PHYSICAL_MEMORY_ARRAY = 16
TYPE_MEMORY_DEVICE = 17

# Table 76 of the specification: memory type. The names of a technology, the
# same in every language; 01h «Other» and 02h «Unknown» are no type.
# The Processor Upgrade field of type 4, as DSP0134 3.9.0 names it. Codes
# 01h to 07h (other, unknown, daughter board, ZIF, piggy back, none, LIF)
# name no socket. dmidecode prints 24h as «Socket BGA1155»: the
# specification says LGA1155, the desktop Sandy and Ivy Bridge socket.
PROCESSOR_UPGRADES = {
    0x08: "Slot 1",
    0x09: "Slot 2",
    0x0A: "370-pin socket",
    0x0B: "Slot A",
    0x0C: "Slot M",
    0x0D: "Socket 423",
    0x0E: "Socket A (Socket 462)",
    0x0F: "Socket 478",
    0x10: "Socket 754",
    0x11: "Socket 940",
    0x12: "Socket 939",
    0x13: "Socket mPGA604",
    0x14: "Socket LGA771",
    0x15: "Socket LGA775",
    0x16: "Socket S1",
    0x17: "Socket AM2",
    0x18: "Socket F (1207)",
    0x19: "Socket LGA1366",
    0x1A: "Socket G34",
    0x1B: "Socket AM3",
    0x1C: "Socket C32",
    0x1D: "Socket LGA1156",
    0x1E: "Socket LGA1567",
    0x1F: "Socket PGA988A",
    0x20: "Socket BGA1288",
    0x21: "Socket rPGA988B",
    0x22: "Socket BGA1023",
    0x23: "Socket BGA1224",
    0x24: "Socket LGA1155",
    0x25: "Socket LGA1356",
    0x26: "Socket LGA2011",
    0x27: "Socket FS1",
    0x28: "Socket FS2",
    0x29: "Socket FM1",
    0x2A: "Socket FM2",
    0x2B: "Socket LGA2011-3",
    0x2C: "Socket LGA1356-3",
    0x2D: "Socket LGA1150",
    0x2E: "Socket BGA1168",
    0x2F: "Socket BGA1234",
    0x30: "Socket BGA1364",
    0x31: "Socket AM4",
    0x32: "Socket LGA1151",
    0x33: "Socket BGA1356",
    0x34: "Socket BGA1440",
    0x35: "Socket BGA1515",
    0x36: "Socket LGA3647-1",
    0x37: "Socket SP3",
    0x38: "Socket SP3r2",
    0x39: "Socket LGA2066",
    0x3A: "Socket BGA1392",
    0x3B: "Socket BGA1510",
    0x3C: "Socket BGA1528",
    0x3D: "Socket LGA4189",
    0x3E: "Socket LGA1200",
    0x3F: "Socket LGA4677",
    0x40: "Socket LGA1700",
    0x41: "Socket BGA1744",
    0x42: "Socket BGA1781",
    0x43: "Socket BGA1211",
    0x44: "Socket BGA2422",
    0x45: "Socket LGA1211",
    0x46: "Socket LGA2422",
    0x47: "Socket LGA5773",
    0x48: "Socket BGA5773",
    0x49: "Socket AM5",
    0x4A: "Socket SP5",
    0x4B: "Socket SP6",
    0x4C: "Socket BGA883",
    0x4D: "Socket BGA1190",
    0x4E: "Socket BGA4129",
    0x4F: "Socket LGA4710",
    0x50: "Socket LGA7529",
    0x51: "Socket BGA1964",
    0x52: "Socket BGA1792",
    0x53: "Socket BGA2049",
    0x54: "Socket BGA2551",
    0x55: "Socket LGA1851",
    0x56: "Socket BGA2114",
    0x57: "Socket BGA2833",
}

MEMORY_TYPES = {
    0x03: "DRAM", 0x04: "EDRAM",
    0x05: "VRAM", 0x06: "SRAM", 0x07: "RAM", 0x08: "ROM", 0x09: "Flash",
    0x0A: "EEPROM", 0x0B: "FEPROM", 0x0C: "EPROM", 0x0D: "CDRAM",
    0x0E: "3DRAM", 0x0F: "SDRAM", 0x10: "SGRAM", 0x11: "RDRAM",
    0x12: "DDR", 0x13: "DDR2", 0x14: "DDR2 FB-DIMM",
    0x18: "DDR3", 0x19: "FBD2", 0x1A: "DDR4", 0x1B: "LPDDR",
    0x1C: "LPDDR2", 0x1D: "LPDDR3", 0x1E: "LPDDR4", 0x1F: LOGICAL_NON_VOLATILE,
    0x20: "HBM", 0x21: "HBM2", 0x22: "DDR5", 0x23: "LPDDR5", 0x24: "HBM3",
}

# The form factor (table 75), the error correction (table 78) and the type
# detail bits (table 77) travel as the specification's codes: what decides
# on them compares codes, and their names are said when painting
# (`render.memory_form_factor`…), in the interface's language.
NOT_A_VALUE = (0x00, 0x01, 0x02)        # none, «Other», «Unknown»

# The bit numbers are the specification's, not a numbering of our own:
# getting them wrong announces an unbuffered module as registered.
TYPE_DETAIL_BITS = (3, 6, 7, 9, 12, 13, 14, 15)

PLACEHOLDERS = frozenset({
    "", "unknown", "not specified", "none", "n/a", "no module installed",
    "to be filled by o.e.m.", "default string", "empty", "undefined",
    "array1_asset_tag", "not available",
})


class Structure:
    """A table structure, already split into fields and strings."""

    __slots__ = ("type", "handle", "data", "strings")

    def __init__(self, type_: int, handle: int, data: bytes, strings: list[str]):
        self.type = type_
        self.handle = handle
        self.data = data
        self.strings = strings

    def byte(self, offset: int) -> Optional[int]:
        return self.data[offset] if offset < len(self.data) else None

    def word(self, offset: int) -> Optional[int]:
        if offset + 2 > len(self.data):
            return None
        return struct.unpack_from("<H", self.data, offset)[0]

    def dword(self, offset: int) -> Optional[int]:
        if offset + 4 > len(self.data):
            return None
        return struct.unpack_from("<I", self.data, offset)[0]

    def text(self, offset: int) -> Optional[str]:
        """Text fields hold the string's number, not the string."""
        index = self.byte(offset)
        if not index or index > len(self.strings):
            return None
        value = self.strings[index - 1].strip()
        return None if value.lower() in PLACEHOLDERS else value


def parse_table(raw: bytes) -> Iterator[Structure]:
    """Walk the whole table, yielding structures."""
    offset = 0
    total = len(raw)
    while offset + 4 <= total:
        type_, length, handle = struct.unpack_from("<BBH", raw, offset)
        if length < 4:
            break                            # corrupt table: better stop
        formatted = raw[offset:offset + length]

        cursor = offset + length
        strings: list[str] = []
        # Each string ends in a zero and the whole area in one more. With no
        # strings the area is two zeros in a row, and counting only one leaves
        # the cursor halfway: from there on everything read is shifted a byte
        # and the following structures are lost.
        while cursor < total and raw[cursor] != 0:
            end = raw.find(b"\x00", cursor)
            if end == -1:
                end = total
            strings.append(raw[cursor:end].decode("utf-8", "replace"))
            cursor = end + 1

        cursor += 1                          # the zero that closes the area
        if not strings:
            cursor += 1                      # and the second, if there were no strings
        cursor = min(cursor, total)

        yield Structure(type_, handle, formatted, strings)

        if type_ == 127:                     # type 127 = end of table
            break
        offset = cursor


def _size_bytes(structure: Structure) -> int:
    """The module's size, with the detour the specification requires.

    The 16-bit field fell short with modules of 32 GB and up: when it's
    0x7FFF the 32-bit extended field must be read.
    """
    size = structure.word(0x0C)
    if size is None or size == 0:
        return 0
    if size == 0x7FFF:
        extended = structure.dword(0x1C) or 0
        return extended * 1024 * 1024
    # Bit 15 says whether the unit is kibibytes instead of mebibytes.
    if size & 0x8000:
        return (size & 0x7FFF) * 1024
    return size * 1024 * 1024


def _rank(structure: Structure) -> Optional[int]:
    attributes = structure.byte(0x1B)
    if attributes is None:
        return None
    rank = attributes & 0x0F
    return rank or None


def _code(value: Optional[int]) -> Optional[int]:
    """An enumeration's code, or None for the ones that are no value."""
    return None if value is None or value in NOT_A_VALUE else value


def _details(structure: Structure) -> list[int]:
    detail = structure.word(0x13)
    if detail is None:
        return []
    return [bit for bit in TYPE_DETAIL_BITS if detail & (1 << bit)]


def memory_devices(structures: list[Structure]) -> list[dict]:
    """Extract the memory modules, empty slots included."""
    modules = []
    for structure in structures:
        if structure.type != TYPE_MEMORY_DEVICE:
            continue
        size = _size_bytes(structure)
        modules.append({
            "locator": structure.text(0x10),
            "bank": structure.text(0x11),
            "size_bytes": size,
            "populated": size > 0,
            "type": MEMORY_TYPES.get(structure.byte(0x12) or 0),
            "form_factor": _code(structure.byte(0x0E)),
            "details": _details(structure),
            "speed_mts": structure.word(0x15) or None,
            "configured_mts": structure.word(0x20) or None,
            "manufacturer": structure.text(0x17),
            "part_number": structure.text(0x1A),
            "rank": _rank(structure),
            "data_width": structure.word(0x0A) or None,
            "total_width": structure.word(0x08) or None,
            "voltage_min_mv": structure.word(0x22) or None,
            "voltage_max_mv": structure.word(0x24) or None,
            "voltage_configured_mv": structure.word(0x26) or None,
            # The serial number is left out on purpose: it identifies the
            # machine and adds nothing to what the program shows.
        })
    return modules


def memory_arrays(structures: list[Structure]) -> list[dict]:
    arrays = []
    for structure in structures:
        if structure.type != TYPE_PHYSICAL_MEMORY_ARRAY:
            continue
        capacity = structure.dword(0x07)
        if capacity == 0x8000_0000:          # sentinel: use the extended field
            extended = structure.data[0x0F:0x17]
            capacity_bytes = struct.unpack("<Q", extended)[0] if len(extended) == 8 else 0
        else:
            capacity_bytes = (capacity or 0) * 1024
        arrays.append({
            # The slot count is two bytes, not one: a board with more than 255
            # slots is rare but the specification allows it.
            "slots": structure.word(0x0D),
            "max_capacity_bytes": capacity_bytes,
            "error_correction": _code(structure.byte(0x06)),
        })
    return arrays


def system_slots(structures: list[Structure]) -> dict[str, str]:
    """The board's slots (type 9): PCI address → slot name.

    Only those carrying an address (SMBIOS 2.6 and later) not marked
    unknown. Firmware fills this table poorly: slots that don't exist, or
    all with the same address. Whoever uses it keeps only those matching a
    device that really exists.
    """
    slots: dict[str, str] = {}
    for structure in structures:
        if structure.type != 9:
            continue
        name = structure.text(0x04)
        segment, bus, devfn = structure.word(0x0D), structure.byte(0x0F), structure.byte(0x10)
        if not name or segment is None or bus is None or devfn is None:
            continue
        if segment == 0xFFFF or bus == 0xFF or devfn == 0xFF:
            continue                         # «unknown», per the standard
        slots[f"{segment:04x}:{bus:02x}:{devfn >> 3:02x}.{devfn & 7:x}"] = name
    return slots


def package_name(spec_name: str) -> str:
    """«Socket LGA1155» as the CPU table writes it: «LGA 1155». A bare
    number or letter keeps its «Socket»."""
    name = spec_name.removeprefix("Socket ")
    if name == spec_name or not re.match(r"[A-Za-z]{2}", name):
        return spec_name
    return re.sub(r"^(r?[LBP]GA|[mu]PGA)(\d)", r"\1 \2", name)


def processor_socket(structures: list[Structure]) -> Optional[str]:
    """The socket the firmware declares for the first populated processor.

    Type 4's Processor Upgrade field, not its Socket Designation: that one is
    free text, and boards write «CPU 1» or «SOCKET 0» in it.
    """
    for structure in structures:
        if structure.type != TYPE_PROCESSOR:
            continue
        status = structure.byte(0x18)
        if status is not None and not status & 0x40:
            continue                         # bit 6: socket populated
        code = structure.byte(0x19)
        return package_name(PROCESSOR_UPGRADES[code]) if code in PROCESSOR_UPGRADES else None
    return None
