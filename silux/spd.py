"""Lectura del SPD de los módulos de memoria.

El SPD es un pequeño chip de identificación que lleva cada módulo pegado al
mismo circuito. Cuenta cosas que la tabla SMBIOS no sabe: **a qué velocidad
puede ir el módulo**, no solo a cuál lo ha puesto la BIOS. Esa diferencia es
justo lo que explica una memoria de 3200 corriendo a 2667.

Se llega a él por el bus SMBus, y en la mayoría de distribuciones el fichero
queda legible por cualquiera (no hay nada sensible salvo el número de serie,
que este módulo ni mira). Hace falta que el kernel haya cargado el driver del
chip: `ee1004` para DDR4, `spd5118` para DDR5.

Lo que sigue decodifica el formato de DDR4 (JEDEC 21-C, anexo K, 4.1.2.12).
Está contrastado contra módulos reales, y hay un fixture en los tests con el
volcado de uno para que siga estándolo.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Iterator, Optional

from .i18n import _
from . import sysroot

I2C_DEVICES = pathlib.Path("/sys/bus/i2c/devices")
# Un chip SPD por zócalo, en las direcciones 0x50 a 0x57 del bus.
SPD_ADDRESS = re.compile(r"^\d+-00(5[0-7])$")

DRAM_TYPES = {0x0B: "DDR3", 0x0C: "DDR4", 0x0E: "LPDDR3", 0x0F: "LPDDR4",
              0x10: "LPDDR4X", 0x12: "DDR5", 0x13: "LPDDR5"}

MODULE_TYPES = {0x01: "RDIMM", 0x02: "UDIMM", 0x03: "SODIMM", 0x04: "LRDIMM",
                0x05: "Mini-RDIMM", 0x06: "Mini-UDIMM", 0x08: "72b-SO-RDIMM",
                0x09: "72b-SO-UDIMM", 0x0C: "16b-SO-DIMM", 0x0D: "32b-SO-DIMM"}

# The makers by their JEDEC code, the whole JEP106 list (tools/gen_jep106.py,
# from OpenOCD): bank from 1 and code without its parity bit. A hand table
# of 15 had Kingston, Infineon, Elpida and Transcend in the wrong place and
# left every other maker out.
JEP106 = pathlib.Path(__file__).parent / "db" / "jep106.json"

# Rangos de cordura. Un valor fuera de aquí significa que se ha decodificado
# mal, y es preferible no enseñar nada a enseñar una cifra inventada.
PLAUSIBLE_MTS = (800, 12800)
PLAUSIBLE_CL = (5, 80)
# DDR3 runs at 1.35-1.5 V, DDR4 at 1.2-1.5 and DDR5 at 1.1-1.45: a profile
# outside this was decoded wrong (a tester's DDR4 XMP read 0.81 V).
PLAUSIBLE_V = (1.0, 1.65)


@dataclass(frozen=True, slots=True)
class Timings:
    """Un juego de temporizaciones: el JEDEC de fábrica o un perfil XMP."""

    name: str
    speed_mts: int
    cl: Optional[int] = None
    trcd: Optional[int] = None
    trp: Optional[int] = None
    tras: Optional[int] = None
    trc: Optional[int] = None
    voltage_v: Optional[float] = None

    @property
    def summary(self) -> str:
        partes = [str(v) for v in (self.cl, self.trcd, self.trp, self.tras) if v]
        return "-".join(partes) if partes else "—"

    @property
    def plausible(self) -> bool:
        if not PLAUSIBLE_MTS[0] <= self.speed_mts <= PLAUSIBLE_MTS[1]:
            return False
        if self.cl is not None and not PLAUSIBLE_CL[0] <= self.cl <= PLAUSIBLE_CL[1]:
            return False
        if self.voltage_v is not None and not PLAUSIBLE_V[0] <= self.voltage_v <= PLAUSIBLE_V[1]:
            return False
        return True


@dataclass(frozen=True, slots=True)
class SpdInfo:
    address: str                              # "10-0050"
    slot: int                                 # 0 a 7, según la dirección
    dram_type: Optional[str] = None
    module_type: Optional[str] = None
    manufacturer: Optional[str] = None
    # Quién fabricó los chips, que a menudo no es quien vende el módulo: los
    # Crucial llevan silicio de Micron, y eso la tabla SMBIOS no lo dice.
    dram_manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    # When it was made, as the SPD dates it: a week of a year. Numbers: it
    # is said in the reader's language when painting (`render.made`).
    manufactured_year: Optional[int] = None
    manufactured_week: Optional[int] = None
    ranks: Optional[int] = None
    device_width: Optional[int] = None
    bus_width: Optional[int] = None
    ecc_bits: int = 0
    # DDR5 parte el módulo en dos subcanales de 32 bits. Explica por qué un
    # DIMM de 64 bits declara dos canales y no es un error de lectura.
    channels: int = 1
    # Sale de multiplicar la densidad de los chips por cuántos hay. Es el mismo
    # número que da SMBIOS, pero sin pedir permisos de administrador.
    capacity_bytes: Optional[int] = None
    jedec: Optional[Timings] = None
    profiles: tuple[Timings, ...] = ()
    xmp_revision: Optional[str] = None
    # Perfiles cuya presencia se reconoce pero cuyas cifras no se interpretan:
    # hoy, los de DDR5. Ver `_ddr5_perfiles`.
    overclock_profiles: tuple[str, ...] = ()
    # The speed an XMP profile declares, kept even when the rest of the
    # profile cannot be trusted (F-A2): its cycle is read right, its timings
    # and voltage are not. Dropping it, a tester's DDR4-3200 read «catalogado
    # a 2400» and lost «al máximo del procesador».
    xmp_speeds_mts: tuple[int, ...] = ()
    decoded: bool = False                     # False = formato no soportado

    @property
    def rated_mts(self) -> Optional[int]:
        """La velocidad más alta que el módulo declara saber dar."""
        candidatos = [t.speed_mts for t in (self.jedec, *self.profiles) if t]
        candidatos += list(self.xmp_speeds_mts)
        return max(candidatos) if candidatos else None


# El paso de la rejilla de velocidades de memoria, en MT/s: 200/3, o sea
# 66,666… Todas las que existen son múltiplos suyos, y en las tres
# generaciones: DDR3-1066 son 1066,67; DDR4-2666, 2666,67; DDR5-6400, 6400
# exactos. Los perfiles XMP tampoco se salen —3600, 3733,33, 4133,33, 6600—
# porque el reloj de referencia va en tercios.
PASO_JEDEC = (200, 3)


# Las velocidades con nombre de cada generación, como las nombra JEDEC. La
# rejilla de 200/3 de arriba no basta para todas: DDR2-667 son 666,67 y JEDEC
# la nombra redondeando, no truncando, y la LPDDR5/5X no cae en la rejilla
# (5500 y 7500 están a media casilla). Fuentes: JESD79F (DDR), JESD79-2F
# (DDR2), JESD79-3F (DDR3), JESD79-4D (DDR4), JESD79-5C (DDR5), JESD209-3C
# (LPDDR3), JESD209-4D (LPDDR4/4X), JESD209-5C (LPDDR5/5X); 7467 es el grado
# de LPDDR5X que usan Intel y Micron.
VELOCIDADES_JEDEC = (
    200, 266, 333, 400,                                   # DDR
    533, 667, 800, 1066,                                  # DDR2
    1333, 1600, 1866, 2133,                               # DDR3, LPDDR3
    2400, 2666, 2933, 3200,                               # DDR4
    3733, 4266,                                           # LPDDR4X
    3600, 4000, 4400, 4800, 5200, 5600, 6000, 6400,       # DDR5
    6800, 7200, 7600, 8000, 8400, 8800,
    5500, 7467, 7500, 8533, 9600,                         # LPDDR5, LPDDR5X
)

# Cuánto se puede separar lo medido de su grado y seguir siendo ese grado: el
# tCK del SPD va cuantizado a un picosegundo (un 0,1 % a 8800 MT/s), y el
# firmware redondea los tercios a un lado o al otro (2666 o 2667). Con un
# 0,5 % la casilla 7533 de la rejilla, que no es un grado, caía en 7500.
TOLERANCIA_JEDEC = 0.003


def grado_jedec(mts: float) -> int:
    """El nombre del grado al que corresponde una velocidad calculada.

    Hace falta porque el tCK del SPD viene cuantizado a un picosegundo y la
    división no cae redonda: un DDR4-2133 guarda 938 ps y `2000000/938` da
    2132,2, no 2133,33. Antes esto se redondeaba a la centena más cercana, que
    va bien con los grados redondos y mal con los que llevan tercio: DDR4-2666
    salía «2700 MT/s», que no es una velocidad que exista, y con ella el módulo
    parecía ir por debajo de lo suyo. Fallaban once de los veintiocho grados
    conocidos de DDR3, DDR4, DDR5 y XMP.

    Primero se busca el grado con nombre más cercano (`VELOCIDADES_JEDEC`), de
    cualquier generación: 2666,67 es «DDR4-2666», 666,67 es «DDR2-667» y la
    LPDDR5-5500 sigue siendo 5500. Lo que no es un grado de JEDEC —un perfil
    XMP— va al múltiplo de 200/3 más cercano, truncado. La cuenta va
    en enteros —`n * 200 // 3`— para que el truncado no dependa de cómo caiga
    un flotante.

    Si el valor no se parece a ninguna velocidad de las que existen, se
    devuelve lo medido: un SPD ilegible no tiene por qué salir con un número
    bonito y falso. Y por debajo de la primera posición de la rejilla no hay
    grado que dar, así que sale un cero, que es lo que el resto del módulo
    entiende como «no hay dato».
    """
    if mts > 0:
        cercana = min(VELOCIDADES_JEDEC, key=lambda v: abs(v - mts))
        if abs(cercana - mts) <= mts * TOLERANCIA_JEDEC:
            return cercana
    # Lo que no es un grado de JEDEC (un perfil XMP: 3600, 3733, 4133) sigue
    # en la rejilla, porque el reloj de referencia va en tercios igual.
    paso, divisor = PASO_JEDEC
    n = round(mts * divisor / paso)
    if n <= 0:
        return 0
    grado = n * paso // divisor
    if abs(grado - mts) > mts * 0.02:
        return round(mts)
    return grado


# Densidad de cada chip, en gigabits. El índice es el valor del SPD, y cada
# generación numera los suyos.
DDR5_DENSIDADES = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 64}
DDR5_ANCHOS = {0: 4, 1: 8, 2: 16, 3: 32}
DDR4_DENSIDADES = {2: 1, 3: 2, 4: 4, 5: 8, 6: 16, 7: 32}


# --------------------------------------------------------------------------
# decodificación DDR4
# --------------------------------------------------------------------------


def _signed(value: int) -> int:
    return value - 256 if value > 127 else value


class _Ddr4:
    """Los desplazamientos del formato DDR4, con nombre."""

    TCK_MIN, TCK_MAX = 18, 19
    TAA, TRCD, TRP = 24, 25, 26
    TRAS_TRC_UPPER, TRAS_LSB, TRC_LSB = 27, 28, 29
    FINE_TRC, FINE_TRP, FINE_TRCD, FINE_TAA = 120, 121, 122, 123
    FINE_TCK_MAX, FINE_TCK_MIN = 124, 125
    ORGANIZATION, BUS_WIDTH = 12, 13
    VENDOR_BANK, VENDOR_ID = 320, 321
    DRAM_BANK, DRAM_ID = 350, 351
    DENSITY = 4
    DATE_YEAR, DATE_WEEK = 323, 324
    PART_NUMBER = slice(329, 349)
    XMP_MAGIC = slice(384, 386)
    XMP_REVISION = 387


def _ciclos_jedec(picosegundos: float, tck_ps: float) -> Optional[int]:
    """Un tiempo pasado a ciclos de reloj, con el redondeo de JEDEC.

    Hacia arriba, porque la memoria no puede responder antes de tiempo: 22,2
    ciclos son un CL23, y al más cercano saldría un CL22 que no aguanta. Pero
    con un margen del 2,6 %, que es el del algoritmo de JEDEC: el SPD guarda
    el ciclo truncado a picosegundos —833 en DDR4-2400, que son 833,33—, y un
    tiempo de justo 17 ciclos sale 17,006, que con el techo a secas subiría a
    18. En enteros, para que no dependa de cómo caiga un flotante.
    """
    if not (tck_ps and picosegundos):
        return None
    return (int(picosegundos) * 1000 // int(tck_ps) + 974) // 1000 or None


def _ddr4_timing(spd: bytes, medium: int, fine: int, tck_ps: float) -> Optional[int]:
    """Convierte un tiempo del SPD a ciclos de reloj.

    El valor va en dos partes: una gruesa en unidades de 125 ps y un ajuste
    fino con signo en picosegundos. Ignorar el ajuste fino desplaza los
    resultados justo lo suficiente para que un CL22 salga como CL21.
    """
    if not tck_ps:
        return None
    picoseconds = spd[medium] * 125 + _signed(spd[fine])
    return _ciclos_jedec(picoseconds, tck_ps)


def _decode_ddr4(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr4
    tck_ps = spd[d.TCK_MIN] * 125 + _signed(spd[d.FINE_TCK_MIN])
    # DDR4 transfiere dos veces por ciclo: de ahí el 2 000 000.
    speed = grado_jedec(2_000_000 / tck_ps) if tck_ps else 0

    tras = (((spd[d.TRAS_TRC_UPPER] & 0x0F) << 8) | spd[d.TRAS_LSB]) * 125
    trc = ((((spd[d.TRAS_TRC_UPPER] & 0xF0) >> 4) << 8) | spd[d.TRC_LSB]) * 125
    trc += _signed(spd[d.FINE_TRC])

    jedec = Timings(
        name="JEDEC",
        speed_mts=speed,
        cl=_ddr4_timing(spd, d.TAA, d.FINE_TAA, tck_ps),
        trcd=_ddr4_timing(spd, d.TRCD, d.FINE_TRCD, tck_ps),
        trp=_ddr4_timing(spd, d.TRP, d.FINE_TRP, tck_ps),
        tras=_ciclos_jedec(tras, tck_ps),
        trc=_ciclos_jedec(trc, tck_ps),
        voltage_v=1.2,
    )

    organization = spd[d.ORGANIZATION]
    bus = spd[d.BUS_WIDTH]
    ranks = ((organization >> 3) & 0x07) + 1
    ancho_chip = 4 << (organization & 0x07)
    ancho_bus = 8 << (bus & 0x07)

    return SpdInfo(
        address=address,
        slot=slot,
        dram_type=DRAM_TYPES.get(spd[2]),
        module_type=MODULE_TYPES.get(spd[3] & 0x0F),
        manufacturer=_vendor(spd[d.VENDOR_BANK], spd[d.VENDOR_ID]),
        dram_manufacturer=_vendor(spd[d.DRAM_BANK], spd[d.DRAM_ID]),
        part_number=_text(spd[d.PART_NUMBER]),
        **_date(spd[d.DATE_YEAR], spd[d.DATE_WEEK]),
        ranks=ranks,
        device_width=ancho_chip,
        bus_width=ancho_bus,
        ecc_bits=8 if (bus >> 3) & 0x03 else 0,
        capacity_bytes=_capacidad(
            DDR4_DENSIDADES.get(spd[d.DENSITY] & 0x0F), ancho_chip, ancho_bus, ranks),
        jedec=jedec if jedec.plausible else None,
        profiles=tuple(_xmp_profiles(spd)),
        xmp_speeds_mts=_xmp_speed(spd, jedec if jedec.plausible else None),
        xmp_revision=_xmp_revision(spd),
        decoded=True,
    )


# --------------------------------------------------------------------------
# decodificación DDR5
# --------------------------------------------------------------------------


class _Ddr5:
    """Los desplazamientos del formato DDR5 (JEDEC JESD400-5).

    No se parece al de DDR4 más que en el byte que dice qué tipo de memoria es.
    El chip pasa de 512 bytes a 1024, los tiempos dejan de ir en dos partes
    (una gruesa y un ajuste fino) y se guardan en picosegundos de dieciséis
    bits, y todo lo que identifica al módulo se muda a un bloque propio que
    empieza en el byte 512.
    """

    TCK_MIN, TCK_MAX = 20, 22
    TAA, TRCD, TRP, TRAS, TRC = 24, 26, 28, 30, 32
    DENSITY, ADDRESSING, IO_WIDTH = 4, 5, 6
    ORGANIZATION, BUS_WIDTH = 234, 235
    VENDOR_BANK, VENDOR_ID = 512, 513
    DATE_YEAR, DATE_WEEK = 515, 516
    PART_NUMBER = slice(521, 551)
    DRAM_BANK, DRAM_ID = 552, 553
    # Los bloques de perfiles de fábrica, cada uno con su firma al principio.
    XMP_MAGIC = slice(640, 642)
    EXPO_MAGIC = slice(832, 836)


def _u16(spd: bytes, offset: int) -> int:
    """Los tiempos van en dos bytes, el bajo primero."""
    if offset + 1 >= len(spd):
        return 0
    return spd[offset] | (spd[offset + 1] << 8)


def _ddr5_ciclos(picosegundos: int, tck_ps: int) -> Optional[int]:
    """Un tiempo del SPD pasado a ciclos de reloj.

    Se redondea hacia arriba: un CL que sale en 39,2 ciclos es un CL40, porque
    la memoria no puede responder antes de tiempo. Redondear al más cercano
    convierte un CL40 en CL39, que no existe.
    """
    if not (tck_ps and picosegundos):
        return None
    return -(-picosegundos // tck_ps) or None


def _decode_ddr5(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr5
    tck_ps = _u16(spd, d.TCK_MIN)
    # Como DDR4, dos transferencias por ciclo. Un tCK de 357 ps son 5600 MT/s.
    speed = grado_jedec(2_000_000 / tck_ps) if tck_ps else 0

    jedec = Timings(
        name="JEDEC",
        speed_mts=speed,
        cl=_ddr5_ciclos(_u16(spd, d.TAA), tck_ps),
        trcd=_ddr5_ciclos(_u16(spd, d.TRCD), tck_ps),
        trp=_ddr5_ciclos(_u16(spd, d.TRP), tck_ps),
        tras=_ddr5_ciclos(_u16(spd, d.TRAS), tck_ps),
        trc=_ddr5_ciclos(_u16(spd, d.TRC), tck_ps),
        # DDR5 bajó de 1,2 V a 1,1 V, que es de donde sale buena parte de su
        # eficiencia.
        voltage_v=1.1,
    )

    organizacion = spd[d.ORGANIZATION] if len(spd) > d.ORGANIZATION else 0
    bus = spd[d.BUS_WIDTH] if len(spd) > d.BUS_WIDTH else 0
    ranks = ((organizacion >> 3) & 0x07) + 1
    canales = ((bus >> 5) & 0x03) + 1
    ancho_canal = 8 << (bus & 0x07)
    extension = ((bus >> 3) & 0x03) * 4        # los bits de ECC, si los hay

    densidad = spd[d.DENSITY] if len(spd) > d.DENSITY else 0
    ancho_chip = DDR5_ANCHOS.get((spd[d.IO_WIDTH] >> 5) & 0x07
                                 if len(spd) > d.IO_WIDTH else -1)

    return SpdInfo(
        address=address,
        slot=slot,
        dram_type=DRAM_TYPES.get(spd[2]),
        module_type=MODULE_TYPES.get(spd[3] & 0x0F),
        manufacturer=_vendor(spd[d.VENDOR_BANK], spd[d.VENDOR_ID])
        if len(spd) > d.VENDOR_ID else None,
        dram_manufacturer=_vendor(spd[d.DRAM_BANK], spd[d.DRAM_ID])
        if len(spd) > d.DRAM_ID else None,
        part_number=_text(spd[d.PART_NUMBER]) if len(spd) > d.PART_NUMBER.stop else None,
        **(_date(spd[d.DATE_YEAR], spd[d.DATE_WEEK]) if len(spd) > d.DATE_WEEK else {}),
        ranks=ranks,
        device_width=ancho_chip,
        bus_width=ancho_canal * canales,
        ecc_bits=extension * canales,
        channels=canales,
        capacity_bytes=_capacidad(
            DDR5_DENSIDADES.get(densidad & 0x1F), ancho_chip,
            ancho_canal * canales, ranks, dies=1 << ((densidad >> 5) & 0x07)),
        jedec=jedec if jedec.plausible else None,
        overclock_profiles=_ddr5_perfiles(spd),
        decoded=True,
    )


def _ddr5_perfiles(spd: bytes) -> tuple[str, ...]:
    """Qué perfiles de fábrica trae el módulo, sin interpretarlos.

    XMP 3.0 y EXPO guardan aquí las temporizaciones que el fabricante garantiza
    por encima de las de JEDEC. Sus formatos no son públicos como el de JEDEC, y
    leerlos a ojo daría cifras creíbles y equivocadas, que es peor que no
    darlas. Reconocer su firma sí es seguro, y decir que están es mejor que
    callarlo: quien mire sabrá que su memoria puede ir más rápido de lo que
    marca la tabla.
    """
    d = _Ddr5
    encontrados = []
    if len(spd) > d.XMP_MAGIC.stop and spd[d.XMP_MAGIC] == b"\x0c\x4a":
        encontrados.append("XMP 3.0")
    if len(spd) > d.EXPO_MAGIC.stop and spd[d.EXPO_MAGIC] == b"EXPO":
        encontrados.append("EXPO")
    return tuple(encontrados)


def _capacidad(gigabits: Optional[int], ancho_chip: Optional[int],
               ancho_bus: int, ranks: int, dies: int = 1) -> Optional[int]:
    """Cuánta memoria hay: los chips que caben por lo que guarda cada uno.

    Es el mismo número que da la tabla SMBIOS, pero aquella pide permisos de
    administrador y el chip SPD del módulo se lee sin pedir nada. En un equipo
    donde el usuario no eleve permisos, esta es la única forma de saber cuánta
    memoria tiene cada zócalo.
    """
    if not (gigabits and ancho_chip and ancho_bus):
        return None
    chips_por_rank = ancho_bus // ancho_chip
    return gigabits * chips_por_rank * ranks * dies * 1024**3 // 8


def _vendor(bank: int, code: int) -> Optional[str]:
    """Traduce un código JEDEC de fabricante.

    El primer byte no es el número de banco sino cuántos códigos de
    continuación lo preceden, y ambos llevan bit de paridad impar en el bit 7.
    Leerlo como un número suelto da bancos equivocados.
    """
    return _jep106().get(((bank & 0x7F) + 1, code & 0x7F))


@functools.lru_cache(maxsize=1)
def _jep106() -> dict[tuple[int, int], str]:
    try:
        datos = json.loads(JEP106.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {(int(banco), int(codigo, 16)): nombre
            for banco, codigos in datos.get("makers", {}).items()
            for codigo, nombre in codigos.items()}


def _text(raw: bytes) -> Optional[str]:
    value = raw.decode("ascii", "replace").strip().strip("\x00").strip()
    return value or None


def _date(year: int, week: int) -> dict:
    """Van en BCD: 0x21 es 2021, no 33. The fields of `SpdInfo`."""
    def bcd(value: int) -> Optional[int]:
        high, low = value >> 4, value & 0x0F
        return high * 10 + low if high <= 9 and low <= 9 else None

    y, w = bcd(year), bcd(week)
    if not y or not w or not 1 <= w <= 53:
        return {}
    return {"manufactured_year": 2000 + y, "manufactured_week": w}


def _xmp_revision(spd: bytes) -> Optional[str]:
    if len(spd) < 388 or spd[_Ddr4.XMP_MAGIC] != b"\x0c\x4a":
        return None
    revision = spd[_Ddr4.XMP_REVISION]
    return f"{revision >> 4}.{revision & 0x0F}"


# DDR4 XMP 2.0, profile 1, as memtest86+ reads it (system/spd.c,
# parse_spd_ddr4): each time is its byte in 125 ps plus a signed fine
# offset in ps; tRAS and tRC carry their high bits in 404's nibbles, in
# 32 ns steps. Checked with a tester's TEAMGROUP-UD4-3200 (T-Force Vulcan
# Z): 3200 16-18-18-38, as the module is sold. Before, every time was read
# a byte off («CL 18, tRP 4»). Profile 2's place has no source to read it
# from, and no module here carries one: it is not read.
XMP1_VOLTAGE = 393
XMP1_TCK, XMP1_TCK_FINE = 396, 431
XMP1_TAA, XMP1_TAA_FINE = 401, 430
XMP1_TRCD, XMP1_TRCD_FINE = 402, 429
XMP1_TRP, XMP1_TRP_FINE = 403, 428
XMP1_UPPER, XMP1_TRAS, XMP1_TRAS_FINE, XMP1_TRC = 404, 405, 427, 406


def _signed(byte: int) -> int:
    return byte - 256 if byte > 127 else byte


def _xmp1_tck_ps(spd: bytes) -> Optional[int]:
    """Profile 1's cycle in ps, or None without the XMP header."""
    if len(spd) <= XMP1_TCK_FINE or spd[_Ddr4.XMP_MAGIC] != b"\x0c\x4a":
        return None
    return spd[XMP1_TCK] * 125 + _signed(spd[XMP1_TCK_FINE]) or None


def _xmp_voltage(byte: int) -> Optional[float]:
    """Bit 7 is one volt and the rest hundredths: 0xA3 is 1.35 V, the
    voltage that module is sold at. Read as (b >> 1) · 0.01 it was 0.81 V.
    Not from a source: memtest86+ does not read it."""
    return round((byte >> 7) + (byte & 0x7F) * 0.01, 2) or None


def _xmp_speed(spd: bytes, jedec: Optional[Timings]) -> tuple[int, ...]:
    """Profile 1's speed alone, for a profile whose timings make no sense:
    its cycle is still a rated speed. Only above JEDEC."""
    tck = _xmp1_tck_ps(spd)
    if not tck:
        return ()
    speed = grado_jedec(2_000_000 / tck)
    if not PLAUSIBLE_MTS[0] <= speed <= PLAUSIBLE_MTS[1]:
        return ()
    if jedec is not None and speed <= jedec.speed_mts:
        return ()
    return (speed,)


def _xmp_profiles(spd: bytes) -> Iterator[Timings]:
    """XMP profile 1 of a DDR4, if it makes sense.

    XMP is Intel's and not published by JEDEC: what does not pass the
    plausibility filter is dropped, and the page says the module has a
    profile it cannot read.
    """
    tck = _xmp1_tck_ps(spd)
    if not tck:
        return

    def tiempo(mtb: int, fine: int) -> int:
        return spd[mtb] * 125 + _signed(spd[fine])

    alto = spd[XMP1_UPPER]
    tras = (alto & 0x0F) * 32_000 + tiempo(XMP1_TRAS, XMP1_TRAS_FINE)
    trc = (alto >> 4) * 32_000 + spd[XMP1_TRC] * 125
    profile = Timings(
        name="XMP 1",
        speed_mts=grado_jedec(2_000_000 / tck),
        cl=_ciclos_jedec(tiempo(XMP1_TAA, XMP1_TAA_FINE), tck),
        trcd=_ciclos_jedec(tiempo(XMP1_TRCD, XMP1_TRCD_FINE), tck),
        trp=_ciclos_jedec(tiempo(XMP1_TRP, XMP1_TRP_FINE), tck),
        tras=_ciclos_jedec(tras, tck),
        trc=_ciclos_jedec(trc, tck),
        voltage_v=_xmp_voltage(spd[XMP1_VOLTAGE]),
    )
    if profile.plausible:
        yield profile


# --------------------------------------------------------------------------
# lectura
# --------------------------------------------------------------------------


def decode(spd: bytes, address: str = "", slot: int = 0) -> SpdInfo:
    if len(spd) < 128:
        return SpdInfo(address=address, slot=slot)

    dram = DRAM_TYPES.get(spd[2])
    if spd[2] == 0x0C:
        return _decode_ddr4(spd, address, slot)
    if spd[2] == 0x12:
        return _decode_ddr5(spd, address, slot)

    # DDR3 y anteriores tienen otro formato. Se identifica el tipo, que ya es
    # algo, y se deja claro que el detalle no está implementado.
    return SpdInfo(address=address, slot=slot, dram_type=dram, decoded=False)


def available() -> bool:
    return any(True for _chip in _eeproms())


# Clase PCI de un controlador SMBus, que es como se le reconoce sin depender
# del fabricante.
CLASE_SMBUS = 0x0C0500
SYS_PCI = pathlib.Path("/sys/bus/pci/devices")
SYS_I2C = pathlib.Path("/sys/bus/i2c/devices")


# Why the SPD cannot be read, by its code, and how it is said.
CAUSE_NO_SMBUS, CAUSE_NO_BUS, CAUSE_NO_DRIVER = "nosmbus", "nobus", "nodriver"
CAUSES = {
    CAUSE_NO_SMBUS: ("spd.nosmbus", "spd.nosmbus.hint"),
    CAUSE_NO_BUS: ("spd.nobus", "spd.nobus.hint"),
    CAUSE_NO_DRIVER: ("spd.nodriver", "spd.nodriver.hint"),
}


def unreadable_cause() -> str:
    """Por qué no se puede leer el SPD en este equipo, como código.

    Hay tres motivos distintos y la solución de cada uno no se parece a la de
    los otros. Antes se contestaba siempre lo mismo —«carga ee1004»— y en la
    mayoría de las placas AMD ese consejo no sirve de nada: el módulo ya está
    disponible y el problema es que no hay ningún bus donde buscar.
    """
    if not _hay_controlador_smbus():
        return CAUSE_NO_SMBUS
    if not _hay_bus_de_memoria():
        # El caso más común en placas AMD: el firmware declara la región de
        # entrada/salida del SMBus como suya y el kernel no la toca por si
        # los dos escriben a la vez.
        return CAUSE_NO_BUS
    # Cada generación de memoria lleva un chip distinto y hace falta el driver
    # que le corresponde. Faltaba el de DDR3, y a una placa X79 con Xeon E5 v2
    # se le proponían los dos que no le sirven de nada.
    return CAUSE_NO_DRIVER


def diagnostico(causa: Optional[str] = None) -> tuple[str, str]:
    """Por qué no se puede leer el SPD, y qué hacer, dicho para la persona."""
    mensaje, ayuda = CAUSES[causa or unreadable_cause()]
    return _(mensaje), _(ayuda)


def _hay_controlador_smbus() -> bool:
    """Si la placa trae el bus por el que viven los chips SPD."""
    try:
        for dispositivo in sysroot.ruta(SYS_PCI).iterdir():
            crudo = (dispositivo / "class").read_text().strip()
            if int(crudo, 16) == CLASE_SMBUS:
                return True
    except (OSError, ValueError):
        pass
    return False


def _hay_bus_de_memoria() -> bool:
    """Si hay algún bus i2c que no sea el de la gráfica.

    Las tarjetas gráficas registran los suyos para hablar con los monitores y
    con sus propios sensores, y no llevan a ninguna memoria.
    """
    try:
        for bus in sysroot.ruta(SYS_I2C).glob("i2c-*"):
            nombre = (bus / "name").read_text().strip().lower()
            if "amdgpu" not in nombre and "nvidia" not in nombre and "i915" not in nombre:
                return True
    except OSError:
        pass
    return False


def _eeproms() -> Iterator[tuple[pathlib.Path, int]]:
    if not sysroot.ruta(I2C_DEVICES).is_dir():
        return
    for entry in sorted(sysroot.ruta(I2C_DEVICES).iterdir()):
        match = SPD_ADDRESS.match(entry.name)
        if match and (entry / "eeprom").exists():
            yield entry, int(match.group(1), 16) - 0x50


def read_all() -> list[SpdInfo]:
    """Lee el SPD de todos los zócalos que el kernel esté exponiendo."""
    found = []
    for entry, slot in _eeproms():
        try:
            raw = (entry / "eeprom").read_bytes()
        except OSError:
            continue
        found.append(decode(raw, address=entry.name, slot=slot))
    return found
