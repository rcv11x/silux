"""El analizador de SMBIOS, contra una tabla construida a mano.

La tabla real solo se puede leer como root, así que aquí se fabrica una con
valores conocidos siguiendo la especificación DSP0134. Es la única forma de
comprobar que los desplazamientos son los correctos: un campo leído dos bytes
más allá de donde toca no falla, simplemente enseña un número equivocado.
"""

import struct
import unittest

from cpuz.privileged import smbios


def _structure(type_: int, fields: bytes, strings: list[str]) -> bytes:
    """Cabecera + campos + zona de cadenas, como manda la especificación."""
    length = 4 + len(fields)
    header = struct.pack("<BBH", type_, length, 0x1000 + type_)
    if strings:
        body = b"".join(s.encode() + b"\x00" for s in strings) + b"\x00"
    else:
        body = b"\x00\x00"                  # sin cadenas: dos ceros igualmente
    return header + fields + body


def _memory_device(size_mb: int = 8192, extended_mb: int = 0) -> bytes:
    fields = bytearray(0x28 - 4)

    def put_word(offset: int, value: int) -> None:
        struct.pack_into("<H", fields, offset - 4, value)

    put_word(0x04, 0x003E)                  # handle del conjunto
    put_word(0x06, 0xFFFE)                  # sin información de errores
    put_word(0x08, 64)                      # ancho total
    put_word(0x0A, 64)                      # ancho de datos
    put_word(0x0C, 0x7FFF if extended_mb else size_mb)
    fields[0x0E - 4] = 0x09                 # DIMM
    fields[0x0F - 4] = 0                    # conjunto de dispositivos
    fields[0x10 - 4] = 1                    # cadena 1: ubicación
    fields[0x11 - 4] = 2                    # cadena 2: banco
    fields[0x12 - 4] = 0x1A                 # DDR4
    put_word(0x13, 1 << 14)                 # sin registrar
    put_word(0x15, 3200)                    # velocidad nominal
    fields[0x17 - 4] = 3                    # fabricante
    fields[0x18 - 4] = 4                    # número de serie
    fields[0x19 - 4] = 5                    # etiqueta de inventario
    fields[0x1A - 4] = 6                    # referencia
    fields[0x1B - 4] = 0x02                 # rango 2
    struct.pack_into("<I", fields, 0x1C - 4, extended_mb)
    put_word(0x20, 2666)                    # velocidad configurada
    put_word(0x22, 1200)
    put_word(0x24, 1200)
    put_word(0x26, 1200)

    return _structure(17, bytes(fields), [
        "DIMM 1", "P0 CHANNEL A", "Kingston", "0x12345678",
        "Not Specified", "KF3200C16D4/8GX",
    ])


def _empty_slot() -> bytes:
    fields = bytearray(0x28 - 4)
    struct.pack_into("<H", fields, 0x0C - 4, 0)     # tamaño 0 = zócalo vacío
    fields[0x10 - 4] = 1
    fields[0x12 - 4] = 0x02                        # desconocido
    return _structure(17, bytes(fields), ["DIMM 2", "Unknown"])


def _memory_array(slots: int = 4, capacity_kb: int = 64 * 1024 * 1024) -> bytes:
    fields = bytearray(0x17 - 4)
    fields[0x04 - 4] = 0x03                        # ubicación: placa base
    fields[0x05 - 4] = 0x03                        # uso: memoria del sistema
    fields[0x06 - 4] = 0x03                        # sin corrección de errores
    struct.pack_into("<I", fields, 0x07 - 4, capacity_kb)
    struct.pack_into("<H", fields, 0x0B - 4, 0xFFFE)
    struct.pack_into("<H", fields, 0x0D - 4, slots)
    return _structure(16, bytes(fields), [])


def _end() -> bytes:
    return _structure(127, b"", [])


class TestRecorridoDeLaTabla(unittest.TestCase):
    def test_separa_las_estructuras(self):
        raw = _memory_array() + _memory_device() + _empty_slot() + _end()
        tipos = [s.type for s in smbios.parse_table(raw)]
        self.assertEqual(tipos, [16, 17, 17, 127])

    def test_para_en_el_tipo_127(self):
        raw = _memory_device() + _end() + _memory_device()
        self.assertEqual(len(list(smbios.parse_table(raw))), 2)

    def test_una_tabla_corrupta_no_cuelga(self):
        self.assertEqual(list(smbios.parse_table(b"\x11\x02\x00\x00")), [])
        self.assertEqual(list(smbios.parse_table(b"")), [])

    def test_las_cadenas_se_resuelven_por_numero(self):
        estructura = next(iter(smbios.parse_table(_memory_device())))
        self.assertEqual(estructura.text(0x10), "DIMM 1")
        self.assertEqual(estructura.text(0x1A), "KF3200C16D4/8GX")

    def test_los_rellenos_se_descartan(self):
        estructura = next(iter(smbios.parse_table(_memory_device())))
        self.assertIsNone(estructura.text(0x19))     # "Not Specified"


class TestModulosDeMemoria(unittest.TestCase):
    def _modules(self, raw: bytes) -> list[dict]:
        return smbios.memory_devices(list(smbios.parse_table(raw)))

    def test_campos_de_un_modulo(self):
        modulo = self._modules(_memory_device())[0]
        self.assertEqual(modulo["locator"], "DIMM 1")
        self.assertEqual(modulo["bank"], "P0 CHANNEL A")
        self.assertEqual(modulo["manufacturer"], "Kingston")
        self.assertEqual(modulo["part_number"], "KF3200C16D4/8GX")
        self.assertEqual(modulo["type"], "DDR4")
        self.assertEqual(modulo["form_factor"], "DIMM")
        self.assertEqual(modulo["size_bytes"], 8 * 1024 ** 3)
        self.assertEqual(modulo["speed_mts"], 3200)
        self.assertEqual(modulo["configured_mts"], 2666)
        self.assertEqual(modulo["rank"], 2)
        self.assertEqual(modulo["voltage_configured_mv"], 1200)
        self.assertTrue(modulo["populated"])

    def test_el_bit_de_detalle_correcto(self):
        # El bit 14 es «sin registrar». Confundirlo con el 13 anunciaría un
        # módulo doméstico como memoria registrada de servidor.
        self.assertEqual(self._modules(_memory_device())[0]["details"], ["Sin registrar"])

    def test_modulos_grandes_usan_el_campo_extendido(self):
        # Con 0x7FFF en el campo de 16 bits hay que leer el de 32.
        modulo = self._modules(_memory_device(extended_mb=32768))[0]
        self.assertEqual(modulo["size_bytes"], 32 * 1024 ** 3)

    def test_un_zocalo_vacio_se_reconoce(self):
        modulo = self._modules(_empty_slot())[0]
        self.assertFalse(modulo["populated"])
        self.assertEqual(modulo["size_bytes"], 0)
        self.assertIsNone(modulo["manufacturer"])

    def test_no_se_expone_el_numero_de_serie(self):
        """Identifica el equipo y no aporta nada a lo que enseña el programa."""
        modulo = self._modules(_memory_device())[0]
        self.assertNotIn("serial", " ".join(modulo).lower())
        self.assertNotIn("0x12345678", str(modulo))


class TestConjuntoDeMemoria(unittest.TestCase):
    def test_zocalos_y_capacidad(self):
        arrays = smbios.memory_arrays(list(smbios.parse_table(_memory_array(slots=4))))
        self.assertEqual(arrays[0]["slots"], 4)
        self.assertEqual(arrays[0]["max_capacity_bytes"], 64 * 1024 ** 3)
        self.assertEqual(arrays[0]["error_correction"], "Ninguna")

    def test_muchos_zocalos_caben_en_dos_bytes(self):
        # Leer este campo como un solo byte da 44 en vez de 300.
        arrays = smbios.memory_arrays(list(smbios.parse_table(_memory_array(slots=300))))
        self.assertEqual(arrays[0]["slots"], 300)


if __name__ == "__main__":
    unittest.main()
