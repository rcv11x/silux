"""Lectura del SPD de los módulos de memoria.

El SPD es un pequeño chip de identificación que lleva cada módulo pegado al
mismo circuito. Cuenta cosas que la tabla SMBIOS no sabe: **a qué velocidad
puede ir el módulo**, no solo a cuál lo ha puesto la BIOS. Esa diferencia es
justo lo que explica una memoria de 3200 corriendo a 2667.

Se llega a él por el bus SMBus, y en la mayoría de distribuciones el fichero
queda legible por cualquiera —no hay nada sensible salvo el número de serie,
que este módulo ni mira—. Hace falta que el kernel haya cargado el driver del
chip: `ee1004` para DDR4, `spd5118` para DDR5.

Lo que sigue decodifica el formato de DDR4 (JEDEC 21-C, anexo K, 4.1.2.12).
Está contrastado contra módulos reales, y hay un fixture en los tests con el
volcado de uno para que siga estándolo.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Iterator, Optional

I2C_DEVICES = pathlib.Path("/sys/bus/i2c/devices")
# Un chip SPD por zócalo, en las direcciones 0x50 a 0x57 del bus.
SPD_ADDRESS = re.compile(r"^\d+-00(5[0-7])$")

DRAM_TYPES = {0x0B: "DDR3", 0x0C: "DDR4", 0x0E: "LPDDR3", 0x0F: "LPDDR4",
              0x10: "LPDDR4X", 0x12: "DDR5", 0x13: "LPDDR5"}

MODULE_TYPES = {0x01: "RDIMM", 0x02: "UDIMM", 0x03: "SODIMM", 0x04: "LRDIMM",
                0x05: "Mini-RDIMM", 0x06: "Mini-UDIMM", 0x08: "72b-SO-RDIMM",
                0x09: "72b-SO-UDIMM", 0x0C: "16b-SO-DIMM", 0x0D: "32b-SO-DIMM"}

# Fabricantes por su código JEDEC (banco, identificador). La lista oficial
# son cientos de entradas; aquí solo van las que se pueden justificar, porque
# una tabla con códigos inventados es peor que no tener tabla: cuando falla,
# el nombre que da la tabla SMBIOS sirve igual de bien.
JEDEC_VENDORS = {
    (1, 0x2C): "Micron",
    (1, 0x4F): "Transcend",
    (1, 0x98): "Kingston",
    (1, 0xAD): "SK Hynix",
    (1, 0xCE): "Samsung",
    (1, 0xDA): "Winbond",
    (2, 0xC1): "Infineon",
    (2, 0xFE): "Elpida",
    (3, 0x0B): "Nanya",
    (5, 0x1F): "Apacer",
    (5, 0x51): "Qimonda",
    (5, 0xCB): "ADATA",
    (6, 0x1B): "Crucial",          # comprobado contra un módulo real
    (6, 0x04): "Netlist",
}

# Rangos de cordura. Un valor fuera de aquí significa que se ha decodificado
# mal, y es preferible no enseñar nada a enseñar una cifra inventada.
PLAUSIBLE_MTS = (800, 12800)
PLAUSIBLE_CL = (5, 80)


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
    manufactured: Optional[str] = None        # "semana 32 de 2021"
    ranks: Optional[int] = None
    device_width: Optional[int] = None
    bus_width: Optional[int] = None
    ecc_bits: int = 0
    jedec: Optional[Timings] = None
    profiles: tuple[Timings, ...] = ()
    xmp_revision: Optional[str] = None
    decoded: bool = False                     # False = formato no soportado

    @property
    def rated_mts(self) -> Optional[int]:
        """La velocidad más alta que el módulo declara saber dar."""
        candidatos = [t.speed_mts for t in (self.jedec, *self.profiles) if t]
        return max(candidatos) if candidatos else None


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
    DATE_YEAR, DATE_WEEK = 323, 324
    PART_NUMBER = slice(329, 349)
    XMP_MAGIC = slice(384, 386)
    XMP_REVISION = 387


def _ddr4_timing(spd: bytes, medium: int, fine: int, tck_ps: float) -> Optional[int]:
    """Convierte un tiempo del SPD a ciclos de reloj.

    El valor va en dos partes: una gruesa en unidades de 125 ps y un ajuste
    fino con signo en picosegundos. Ignorar el ajuste fino desplaza los
    resultados justo lo suficiente para que un CL22 salga como CL21.
    """
    if not tck_ps:
        return None
    picoseconds = spd[medium] * 125 + _signed(spd[fine])
    return round(picoseconds / tck_ps) or None


def _decode_ddr4(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr4
    tck_ps = spd[d.TCK_MIN] * 125 + _signed(spd[d.FINE_TCK_MIN])
    # DDR4 transfiere dos veces por ciclo: de ahí el 2 000 000.
    speed = round(2_000_000 / tck_ps / 100) * 100 if tck_ps else 0

    tras = (((spd[d.TRAS_TRC_UPPER] & 0x0F) << 8) | spd[d.TRAS_LSB]) * 125
    trc = ((((spd[d.TRAS_TRC_UPPER] & 0xF0) >> 4) << 8) | spd[d.TRC_LSB]) * 125
    trc += _signed(spd[d.FINE_TRC])

    jedec = Timings(
        name="JEDEC",
        speed_mts=speed,
        cl=_ddr4_timing(spd, d.TAA, d.FINE_TAA, tck_ps),
        trcd=_ddr4_timing(spd, d.TRCD, d.FINE_TRCD, tck_ps),
        trp=_ddr4_timing(spd, d.TRP, d.FINE_TRP, tck_ps),
        tras=round(tras / tck_ps) if tck_ps else None,
        trc=round(trc / tck_ps) if tck_ps else None,
        voltage_v=1.2,
    )

    organization = spd[d.ORGANIZATION]
    bus = spd[d.BUS_WIDTH]

    return SpdInfo(
        address=address,
        slot=slot,
        dram_type=DRAM_TYPES.get(spd[2]),
        module_type=MODULE_TYPES.get(spd[3] & 0x0F),
        manufacturer=_vendor(spd[d.VENDOR_BANK], spd[d.VENDOR_ID]),
        dram_manufacturer=_vendor(spd[d.DRAM_BANK], spd[d.DRAM_ID]),
        part_number=_text(spd[d.PART_NUMBER]),
        manufactured=_date(spd[d.DATE_YEAR], spd[d.DATE_WEEK]),
        ranks=((organization >> 3) & 0x07) + 1,
        device_width=4 << (organization & 0x07),
        bus_width=8 << (bus & 0x07),
        ecc_bits=8 if (bus >> 3) & 0x03 else 0,
        jedec=jedec if jedec.plausible else None,
        profiles=tuple(_xmp_profiles(spd)),
        xmp_revision=_xmp_revision(spd),
        decoded=True,
    )


def _vendor(bank: int, code: int) -> Optional[str]:
    """Traduce un código JEDEC de fabricante.

    El primer byte no es el número de banco sino cuántos códigos de
    continuación lo preceden, y ambos llevan bit de paridad impar en el bit 7.
    Leerlo como un número suelto da bancos equivocados.
    """
    return JEDEC_VENDORS.get(((bank & 0x7F) + 1, code & 0x7F))


def _text(raw: bytes) -> Optional[str]:
    value = raw.decode("ascii", "replace").strip().strip("\x00").strip()
    return value or None


def _date(year: int, week: int) -> Optional[str]:
    """Van en BCD: 0x21 es 2021, no 33."""
    def bcd(value: int) -> Optional[int]:
        high, low = value >> 4, value & 0x0F
        return high * 10 + low if high <= 9 and low <= 9 else None

    y, w = bcd(year), bcd(week)
    if not y or not w or not 1 <= w <= 53:
        return None
    return f"semana {w} de {2000 + y}"


def _xmp_revision(spd: bytes) -> Optional[str]:
    if len(spd) < 388 or spd[_Ddr4.XMP_MAGIC] != b"\x0c\x4a":
        return None
    revision = spd[_Ddr4.XMP_REVISION]
    return f"{revision >> 4}.{revision & 0x0F}"


def _xmp_profiles(spd: bytes) -> Iterator[Timings]:
    """Perfiles XMP 2.0, con red de seguridad.

    La estructura de XMP no está publicada por JEDEC y su descripción circula
    por ingeniería inversa, así que no hay forma de garantizar que un módulo
    concreto encaje. En vez de fiarse, cada perfil decodificado pasa por un
    filtro de plausibilidad: si la velocidad o la latencia salen absurdas, se
    descarta en silencio. Es preferible no enseñar un perfil a enseñar uno
    inventado.
    """
    if len(spd) < 464 or spd[_Ddr4.XMP_MAGIC] != b"\x0c\x4a":
        return

    for number, base in enumerate((185, 220), start=1):
        offset = 384 + base - 176          # los perfiles empiezan tras la cabecera
        if offset + 12 >= len(spd):
            continue
        tck = spd[offset + 3] * 125
        if not tck:
            continue
        speed = round(2_000_000 / tck / 100) * 100
        profile = Timings(
            name=f"XMP {number}",
            speed_mts=speed,
            cl=round(spd[offset + 9] * 125 / tck) or None,
            trcd=round(spd[offset + 10] * 125 / tck) or None,
            trp=round(spd[offset + 11] * 125 / tck) or None,
            voltage_v=round(((spd[offset] >> 1) & 0x7F) * 0.01 + 
                            (0.005 if spd[offset] & 1 else 0), 3) or None,
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

    # DDR5 y anteriores tienen otro formato. Se identifica el tipo, que ya es
    # algo, y se deja claro que el detalle no está implementado.
    return SpdInfo(address=address, slot=slot, dram_type=dram, decoded=False)


def available() -> bool:
    return any(True for _ in _eeproms())


def _eeproms() -> Iterator[tuple[pathlib.Path, int]]:
    if not I2C_DEVICES.is_dir():
        return
    for entry in sorted(I2C_DEVICES.iterdir()):
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
