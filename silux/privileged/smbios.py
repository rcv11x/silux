"""Analizador de la tabla SMBIOS.

La tabla es una lista de estructuras binarias, cada una con una cabecera de
cuatro bytes (tipo, longitud, identificador), una zona de campos de tamaño
fijo y, detrás, las cadenas de texto separadas por ceros. Los campos de texto
no guardan la cadena sino su número de orden dentro de esa lista.

Solo se interpretan los tipos que hacen falta: el 16 (conjunto de memoria) y
el 17 (cada módulo). El resto se deja pasar sin tocar.

Referencia: DMTF DSP0134, «System Management BIOS (SMBIOS) Reference
Specification».
"""

from __future__ import annotations

import struct
from typing import Iterator, Optional

TYPE_PHYSICAL_MEMORY_ARRAY = 16
TYPE_MEMORY_DEVICE = 17

# Tabla 76 de la especificación: tipo de memoria.
MEMORY_TYPES = {
    0x01: "Otro", 0x02: "Desconocido", 0x03: "DRAM", 0x04: "EDRAM",
    0x05: "VRAM", 0x06: "SRAM", 0x07: "RAM", 0x08: "ROM", 0x09: "Flash",
    0x0A: "EEPROM", 0x0B: "FEPROM", 0x0C: "EPROM", 0x0D: "CDRAM",
    0x0E: "3DRAM", 0x0F: "SDRAM", 0x10: "SGRAM", 0x11: "RDRAM",
    0x12: "DDR", 0x13: "DDR2", 0x14: "DDR2 FB-DIMM",
    0x18: "DDR3", 0x19: "FBD2", 0x1A: "DDR4", 0x1B: "LPDDR",
    0x1C: "LPDDR2", 0x1D: "LPDDR3", 0x1E: "LPDDR4", 0x1F: "Lógica no volátil",
    0x20: "HBM", 0x21: "HBM2", 0x22: "DDR5", 0x23: "LPDDR5", 0x24: "HBM3",
}

# Tabla 75: factor de forma.
FORM_FACTORS = {
    0x01: "Otro", 0x02: "Desconocido", 0x03: "SIMM", 0x04: "SIP", 0x05: "Chip",
    0x06: "DIP", 0x07: "ZIP", 0x08: "Placa propietaria", 0x09: "DIMM",
    0x0A: "TSOP", 0x0B: "Fila de chips", 0x0C: "RIMM", 0x0D: "SODIMM",
    0x0E: "SRIMM", 0x0F: "FB-DIMM", 0x10: "Die",
}

# Tabla 78: corrección de errores del conjunto de memoria.
ERROR_CORRECTION = {
    0x01: "Otra", 0x02: "Desconocida", 0x03: "Ninguna", 0x04: "Paridad",
    0x05: "ECC de bit único", 0x06: "ECC de varios bits", 0x07: "CRC",
}

# Bits de «type detail» (tabla 77) que merece la pena traducir. Los números
# son los de la especificación, no una numeración propia: equivocarse aquí
# hace que un módulo sin buffer se anuncie como registrado.
TYPE_DETAILS = {
    3: "Paginado rápido", 6: "RAMBUS", 7: "Síncrona", 9: "EDO",
    12: "No volátil", 13: "Registrada", 14: "Sin registrar", 15: "LRDIMM",
}

PLACEHOLDERS = frozenset({
    "", "unknown", "not specified", "none", "n/a", "no module installed",
    "to be filled by o.e.m.", "default string", "empty", "undefined",
    "array1_asset_tag", "not available",
})


class Structure:
    """Una estructura de la tabla, ya separada en campos y cadenas."""

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
        """Los campos de texto guardan el número de la cadena, no la cadena."""
        index = self.byte(offset)
        if not index or index > len(self.strings):
            return None
        value = self.strings[index - 1].strip()
        return None if value.lower() in PLACEHOLDERS else value


def parse_table(raw: bytes) -> Iterator[Structure]:
    """Recorre la tabla entera y va soltando estructuras."""
    offset = 0
    total = len(raw)
    while offset + 4 <= total:
        type_, length, handle = struct.unpack_from("<BBH", raw, offset)
        if length < 4:
            break                            # tabla corrupta: mejor parar
        formatted = raw[offset:offset + length]

        cursor = offset + length
        strings: list[str] = []
        # Cada cadena acaba en un cero y la zona entera en otro más. Cuando no
        # hay ninguna cadena la zona son dos ceros seguidos, y contar solo uno
        # deja el cursor a mitad de camino: a partir de ahí todo lo que se lee
        # está desplazado un byte y las estructuras siguientes se pierden.
        while cursor < total and raw[cursor] != 0:
            end = raw.find(b"\x00", cursor)
            if end == -1:
                end = total
            strings.append(raw[cursor:end].decode("utf-8", "replace"))
            cursor = end + 1

        cursor += 1                          # el cero que cierra la zona
        if not strings:
            cursor += 1                      # y el segundo, si no había cadenas
        cursor = min(cursor, total)

        yield Structure(type_, handle, formatted, strings)

        if type_ == 127:                     # tipo 127 = fin de la tabla
            break
        offset = cursor


def _size_bytes(structure: Structure) -> int:
    """El tamaño del módulo, con el rodeo que exige la especificación.

    El campo de 16 bits se quedó corto con los módulos de 32 GB en adelante:
    cuando vale 0x7FFF hay que leer el campo extendido de 32 bits.
    """
    size = structure.word(0x0C)
    if size is None or size == 0:
        return 0
    if size == 0x7FFF:
        extended = structure.dword(0x1C) or 0
        return extended * 1024 * 1024
    # El bit 15 dice si la unidad son kibibytes en vez de mebibytes.
    if size & 0x8000:
        return (size & 0x7FFF) * 1024
    return size * 1024 * 1024


def _rank(structure: Structure) -> Optional[int]:
    attributes = structure.byte(0x1B)
    if attributes is None:
        return None
    rank = attributes & 0x0F
    return rank or None


def _details(structure: Structure) -> list[str]:
    detail = structure.word(0x13)
    if detail is None:
        return []
    return [name for bit, name in TYPE_DETAILS.items() if detail & (1 << bit)]


def memory_devices(structures: list[Structure]) -> list[dict]:
    """Extrae los módulos de memoria, incluidos los zócalos vacíos."""
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
            "form_factor": FORM_FACTORS.get(structure.byte(0x0E) or 0),
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
            # El número de serie se deja fuera a propósito: identifica el
            # equipo y no aporta nada a lo que enseña el programa.
        })
    return modules


def memory_arrays(structures: list[Structure]) -> list[dict]:
    arrays = []
    for structure in structures:
        if structure.type != TYPE_PHYSICAL_MEMORY_ARRAY:
            continue
        capacity = structure.dword(0x07)
        if capacity == 0x8000_0000:          # centinela: usar el campo extendido
            extended = structure.data[0x0F:0x17]
            capacity_bytes = struct.unpack("<Q", extended)[0] if len(extended) == 8 else 0
        else:
            capacity_bytes = (capacity or 0) * 1024
        arrays.append({
            # El número de zócalos son dos bytes, no uno: una placa con más de
            # 255 ranuras es rara pero la especificación lo contempla.
            "slots": structure.word(0x0D),
            "max_capacity_bytes": capacity_bytes,
            "error_correction": ERROR_CORRECTION.get(structure.byte(0x06) or 0),
        })
    return arrays
