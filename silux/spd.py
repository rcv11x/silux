"""Reading the memory modules' SPD.

The SPD is a small identification chip each module carries on its own
board. It tells what the SMBIOS table doesn't know: **the speed the module
can run at**, not only the one the BIOS set. That difference is exactly
what explains a 3200 memory running at 2667.

It is reached over the SMBus, and on most distributions the file is
readable by anyone (nothing in it is sensitive but the serial number, which
this module doesn't even look at). The kernel needs the chip's driver
loaded: `ee1004` for DDR4, `spd5118` for DDR5.

What follows decodes the DDR4 format (JEDEC 21-C, annex K, 4.1.2.12) and
DDR5's. Checked against real modules, with a test fixture holding one's dump
so it stays that way.
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Iterator, Optional

from . import sysroot
from .i18n import _

I2C_DEVICES = pathlib.Path("/sys/bus/i2c/devices")
# One SPD chip per slot, at addresses 0x50 to 0x57 on the bus.
SPD_ADDRESS = re.compile(r"^\d+-00(5[0-7])$")

DRAM_TYPES = {0x07: "DDR", 0x08: "DDR2", 0x0B: "DDR3", 0x0C: "DDR4", 0x0E: "LPDDR3", 0x0F: "LPDDR4",
              0x10: "LPDDR4X", 0x12: "DDR5", 0x13: "LPDDR5"}

# DDR3 numbers its module types its own way (JEDEC 21-C annex K, byte 3).
DDR3_MODULE_TYPES = {0x01: "RDIMM", 0x02: "UDIMM", 0x03: "SODIMM", 0x04: "Micro-DIMM",
                     0x05: "Mini-RDIMM", 0x06: "Mini-UDIMM", 0x08: "72b-SO-UDIMM",
                     0x09: "72b-SO-RDIMM", 0x0B: "LRDIMM", 0x0C: "16b-SO-DIMM",
                     0x0D: "32b-SO-DIMM"}

MODULE_TYPES = {0x01: "RDIMM", 0x02: "UDIMM", 0x03: "SODIMM", 0x04: "LRDIMM",
                0x05: "Mini-RDIMM", 0x06: "Mini-UDIMM", 0x08: "72b-SO-RDIMM",
                0x09: "72b-SO-UDIMM", 0x0C: "16b-SO-DIMM", 0x0D: "32b-SO-DIMM"}

# The makers by their JEDEC code, the whole JEP106 list (tools/gen_jep106.py,
# from OpenOCD): bank from 1 and code without its parity bit.
JEP106 = pathlib.Path(__file__).parent / "db" / "jep106.json"

# Sanity ranges. A value outside them means it was decoded wrong, and
# showing nothing beats showing a made-up figure.
# DDR2 starts at 400 MT/s and CL 3.
PLAUSIBLE_MTS = (400, 12800)
PLAUSIBLE_CL = (3, 80)
# DDR2 runs at 1.8 V, DDR3 at 1.35-1.5, DDR4 at 1.2-1.5 and DDR5 at
# 1.1-1.45: a profile outside this was decoded wrong (one DDR4 XMP profile
# read as 0.81 V).
PLAUSIBLE_V = (1.0, 1.9)


@dataclass(frozen=True, slots=True)
class Timings:
    """A set of timings: the factory JEDEC one or an XMP profile."""

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
        parts = [str(v) for v in (self.cl, self.trcd, self.trp, self.tras) if v]
        return "-".join(parts) if parts else "—"

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
    slot: int                                 # 0 to 7, by the address
    dram_type: Optional[str] = None
    module_type: Optional[str] = None
    manufacturer: Optional[str] = None
    # Who made the chips, often not who sells the module: Crucial modules
    # carry Micron silicon, which the SMBIOS table doesn't say.
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
    # DDR5 splits the module into two 32-bit subchannels. It explains why a
    # 64-bit DIMM declares two channels and isn't a misreading.
    channels: int = 1
    # The chips' density times how many there are. The same number SMBIOS
    # gives, without asking for administrator permissions.
    capacity_bytes: Optional[int] = None
    jedec: Optional[Timings] = None
    profiles: tuple[Timings, ...] = ()
    xmp_revision: Optional[str] = None
    # Profiles whose presence is recognized but whose figures aren't
    # interpreted: today, DDR5's. See `_ddr5_profiles`.
    overclock_profiles: tuple[str, ...] = ()
    # Only the first page could be read (a DDR5 chip whose page switch the
    # machine blocks): what lies beyond it is unknown, not absent.
    partial: bool = False
    # The speed an XMP profile declares, kept even when the rest of the
    # profile can't be trusted (F-A2): its cycle reads right, its timings and
    # voltage don't. Dropping it, a DDR4-3200 module read as rated for 2400
    # and lost «at the processor's maximum».
    xmp_speeds_mts: tuple[int, ...] = ()
    # The voltages the module declares it can run at. DDR3 can declare 1.5,
    # 1.35 (DDR3L) and 1.25 V; the board picks one.
    voltages_v: tuple[float, ...] = ()
    decoded: bool = False                     # False = unsupported format

    @property
    def rated_mts(self) -> Optional[int]:
        """The highest speed the module declares it can do."""
        candidates = [t.speed_mts for t in (self.jedec, *self.profiles) if t]
        candidates += list(self.xmp_speeds_mts)
        return max(candidates) if candidates else None


# The step of the memory speed grid, in MT/s: 200/3, or 66.666… Every speed
# there is is a multiple of it, in all three generations: DDR3-1066 is
# 1066.67, DDR4-2666 is 2666.67, DDR5-6400 is exactly 6400. XMP profiles
# don't leave it either (3600, 3733.33, 4133.33, 6600), because the
# reference clock goes in thirds.
JEDEC_STEP = (200, 3)


# Each generation's named speeds, as JEDEC names them. The 200/3 grid above
# isn't enough for all: DDR2-667 is 666.67 and JEDEC names it by rounding,
# not truncating, and LPDDR5/5X don't fall on the grid (5500 and 7500 are
# half a step off). Sources: JESD79F (DDR), JESD79-2F (DDR2), JESD79-3F
# (DDR3), JESD79-4D (DDR4), JESD79-5C (DDR5), JESD209-3C (LPDDR3),
# JESD209-4D (LPDDR4/4X), JESD209-5C (LPDDR5/5X); 7467 is the LPDDR5X grade
# Intel and Micron use.
JEDEC_SPEEDS = (
    200, 266, 333, 400,                                   # DDR
    533, 667, 800, 1066,                                  # DDR2
    1333, 1600, 1866, 2133,                               # DDR3, LPDDR3
    2400, 2666, 2933, 3200,                               # DDR4
    3733, 4266,                                           # LPDDR4X
    3600, 4000, 4400, 4800, 5200, 5600, 6000, 6400,       # DDR5
    6800, 7200, 7600, 8000, 8400, 8800,
    5500, 7467, 7500, 8533, 9600,                         # LPDDR5, LPDDR5X
)

# How far a measured speed may stray from its grade and still be it: the
# SPD's tCK is quantized to a picosecond (0.1 % at 8800 MT/s), and firmware
# rounds the thirds one way or the other (2666 or 2667). With 0.5 % the
# grid's 7533 step, which isn't a grade, fell into 7500.
JEDEC_TOLERANCE = 0.003


def jedec_grade(mts: float) -> int:
    """The name of the grade a computed speed belongs to.

    Needed because the SPD's tCK is quantized to a picosecond and the
    division doesn't come out round: a DDR4-2133 stores 938 ps and
    `2000000/938` gives 2132.2, not 2133.33. Rounding to the nearest hundred
    works for round grades and fails for those with a third: DDR4-2666 came
    out as «2700 MT/s», a speed that doesn't exist.

    The nearest named grade (`JEDEC_SPEEDS`) of any generation is looked for
    first: 2666.67 is «DDR4-2666», 666.67 is «DDR2-667», and LPDDR5-5500
    stays 5500. What isn't a JEDEC grade (an XMP profile) goes to the nearest
    multiple of 200/3, truncated, computed in integers (`n * 200 // 3`) so
    the truncation doesn't depend on how a float falls.

    If the value looks like no speed that exists, the measured one is
    returned: an unreadable SPD needn't come out with a pretty false number.
    Below the grid's first step there's no grade to give, so it returns zero,
    which the rest of the module reads as «no datum».
    """
    if mts > 0:
        nearest = min(JEDEC_SPEEDS, key=lambda v: abs(v - mts))
        if abs(nearest - mts) <= mts * JEDEC_TOLERANCE:
            return nearest
    # What isn't a JEDEC grade (an XMP profile: 3600, 3733, 4133) stays on
    # the grid, since the reference clock goes in thirds all the same.
    step, divisor = JEDEC_STEP
    n = round(mts * divisor / step)
    if n <= 0:
        return 0
    grade = n * step // divisor
    if abs(grade - mts) > mts * 0.02:
        return round(mts)
    return grade


# Each chip's density, in gigabits. The index is the SPD's value, and each
# generation numbers its own.
DDR5_DENSITIES = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 64}
DDR5_WIDTHS = {0: 4, 1: 8, 2: 16, 3: 32}
DDR3_DENSITIES = {0: 0.25, 1: 0.5, 2: 1, 3: 2, 4: 4, 5: 8, 6: 16}
DDR4_DENSITIES = {2: 1, 3: 2, 4: 4, 5: 8, 6: 16, 7: 32}


# --------------------------------------------------------------------------
# DDR3 decoding
# --------------------------------------------------------------------------

class _Ddr3:
    """The DDR3 format's offsets (JEDEC 21-C, annex K), by name."""

    DENSITY, VOLTAGE, ORGANIZATION, BUS_WIDTH = 4, 6, 7, 8
    FTB, MTB_DIVIDEND, MTB_DIVISOR = 9, 10, 11
    TCK_MIN, TAA, TRCD, TRP = 12, 16, 18, 20
    TRAS_TRC_UPPER, TRAS_LSB, TRC_LSB = 21, 22, 23
    FINE_TCK_MIN, FINE_TAA, FINE_TRCD, FINE_TRP, FINE_TRC = 34, 35, 36, 37, 38
    VENDOR_BANK, VENDOR_ID = 117, 118
    DATE_YEAR, DATE_WEEK = 120, 121
    PART_NUMBER = slice(128, 146)
    DRAM_BANK, DRAM_ID = 148, 149
    XMP_MAGIC = slice(176, 178)
    XMP_REVISION = 178


def _ddr3_voltages(byte: int) -> tuple[float, ...]:
    """Byte 6: bit 0 set means *not* 1.5 V operable; bits 1 and 2 add 1.35 V
    (DDR3L) and 1.25 V (DDR3U)."""
    voltages = [] if byte & 0x01 else [1.5]
    if byte & 0x02:
        voltages.append(1.35)
    if byte & 0x04:
        voltages.append(1.25)
    return tuple(voltages)


def _decode_ddr3(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr3
    # The medium timebase is a fraction of a nanosecond (1/8 on every module
    # seen) and the fine one of a picosecond, both declared by the module.
    mtb_ps = 1000 * spd[d.MTB_DIVIDEND] / spd[d.MTB_DIVISOR] if spd[d.MTB_DIVISOR] else 125
    ftb_ps = (spd[d.FTB] >> 4) / (spd[d.FTB] & 0x0F) if spd[d.FTB] & 0x0F else 1

    def time_ps(medium: int, fine: Optional[int] = None) -> float:
        return spd[medium] * mtb_ps + (_signed(spd[fine]) * ftb_ps if fine is not None else 0)

    tck_ps = time_ps(d.TCK_MIN, d.FINE_TCK_MIN)
    # Two transfers per cycle, like DDR4: a 1.5 ns cycle is 1333 MT/s.
    speed = jedec_grade(2_000_000 / tck_ps) if tck_ps else 0
    upper = spd[d.TRAS_TRC_UPPER]
    tras_ps = (((upper & 0x0F) << 8) | spd[d.TRAS_LSB]) * mtb_ps
    trc_ps = ((((upper >> 4) & 0x0F) << 8) | spd[d.TRC_LSB]) * mtb_ps + _signed(spd[d.FINE_TRC]) * ftb_ps
    voltages = _ddr3_voltages(spd[d.VOLTAGE])
    jedec = Timings(
        name="JEDEC",
        speed_mts=speed,
        cl=_jedec_cycles(time_ps(d.TAA, d.FINE_TAA), tck_ps),
        trcd=_jedec_cycles(time_ps(d.TRCD, d.FINE_TRCD), tck_ps),
        trp=_jedec_cycles(time_ps(d.TRP, d.FINE_TRP), tck_ps),
        tras=_jedec_cycles(tras_ps, tck_ps),
        trc=_jedec_cycles(trc_ps, tck_ps),
        voltage_v=voltages[0] if voltages else None,
    )

    organization = spd[d.ORGANIZATION]
    bus = spd[d.BUS_WIDTH]
    ranks = ((organization >> 3) & 0x07) + 1
    chip_width = 4 << (organization & 0x07)
    bus_width = 8 << (bus & 0x07)
    capacity = _capacity(DDR3_DENSITIES.get(spd[d.DENSITY] & 0x0F), chip_width, bus_width, ranks)
    xmp = None
    if spd[d.XMP_MAGIC] == b"\x0c\x4a":
        xmp = f"{spd[d.XMP_REVISION] >> 4}.{spd[d.XMP_REVISION] & 0x0F}"

    return SpdInfo(
        address=address,
        slot=slot,
        dram_type=DRAM_TYPES.get(spd[2]),
        module_type=DDR3_MODULE_TYPES.get(spd[3] & 0x0F),
        manufacturer=_vendor(spd[d.VENDOR_BANK], spd[d.VENDOR_ID]),
        dram_manufacturer=_vendor(spd[d.DRAM_BANK], spd[d.DRAM_ID]),
        part_number=_text(spd[d.PART_NUMBER]),
        **_date(spd[d.DATE_YEAR], spd[d.DATE_WEEK]),
        ranks=ranks,
        device_width=chip_width,
        bus_width=bus_width,
        ecc_bits=8 if (bus >> 3) & 0x03 else 0,
        capacity_bytes=int(capacity) if capacity else None,
        jedec=jedec if jedec.plausible else None,
        # XMP 1.x on DDR3 is recognized, not interpreted: its layout has no
        # source to check against here.
        overclock_profiles=(f"XMP {xmp}",) if xmp else (),
        voltages_v=voltages,
        decoded=True,
    )


# --------------------------------------------------------------------------
# DDR2 decoding (JEDEC 21-C, its SPD annex): times in nanoseconds, no
# timebases, and the capacity per rank as a bit field.
# --------------------------------------------------------------------------

DDR2_MODULE_TYPES = {0x01: "RDIMM", 0x02: "UDIMM", 0x04: "SODIMM", 0x08: "Micro-DIMM",
                     0x10: "Mini-RDIMM", 0x20: "Mini-UDIMM"}
# Byte 31, the capacity of each rank: one bit per size, in MiB.
DDR2_RANK_DENSITIES = {0: 1024, 1: 2048, 2: 4096, 3: 8192, 4: 16384, 5: 128, 6: 256, 7: 512}
# The tenths of a cycle time, where four codes mean quarters and thirds.
DDR2_TENTHS = {0xA: 0.25, 0xB: 1 / 3, 0xC: 2 / 3, 0xD: 0.75}


class _Ddr2:
    """The DDR2 format's offsets, by name."""

    RANKS, BUS_WIDTH, BUS_WIDTH_HIGH, ECC = 5, 6, 7, 11
    CHIP_WIDTH, TCK, CAS_LATENCIES, MODULE_TYPE = 13, 9, 18, 20
    TRP, TRCD, TRAS, DENSITY, TRC = 27, 29, 30, 31, 41
    VENDOR, PART_NUMBER, DATE_YEAR, DATE_WEEK = slice(64, 72), slice(73, 91), 93, 94


def _ddr2_cycle_ns(byte: int) -> float:
    """«0x30» is 3.0 ns, «0x3D» 3.75: whole nanoseconds and their tenths."""
    tenths = byte & 0x0F
    return (byte >> 4) + DDR2_TENTHS.get(tenths, tenths / 10)


def _ddr2_vendor(codes: bytes) -> Optional[str]:
    """The maker's code after as many 0x7F continuation codes as its bank."""
    for bank, code in enumerate(codes):
        if code != 0x7F:
            return _vendor(bank, code) if code else None
    return None


def _decode_ddr2(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr2
    tck_ns = _ddr2_cycle_ns(spd[d.TCK])
    latencies = [bit for bit in range(8) if spd[d.CAS_LATENCIES] >> bit & 1]
    tck_ps = tck_ns * 1000
    jedec = Timings(
        name="JEDEC",
        # Two transfers per cycle: a 3 ns cycle is 667 MT/s.
        speed_mts=jedec_grade(2000 / tck_ns) if tck_ns else 0,
        # The cycle time in byte 9 is the one at the highest latency.
        cl=max(latencies) if latencies else None,
        trcd=_jedec_cycles((spd[d.TRCD] >> 2) * 1000 + (spd[d.TRCD] & 3) * 250, tck_ps),
        trp=_jedec_cycles((spd[d.TRP] >> 2) * 1000 + (spd[d.TRP] & 3) * 250, tck_ps),
        tras=_jedec_cycles(spd[d.TRAS] * 1000, tck_ps),
        trc=_jedec_cycles(spd[d.TRC] * 1000, tck_ps),
        # Every DDR2 module runs at 1.8 V: SSTL 1.8 (byte 8) is the standard.
        voltage_v=1.8,
    )
    ranks = (spd[d.RANKS] & 0x07) + 1
    per_rank_mib = sum(size for bit, size in DDR2_RANK_DENSITIES.items()
                       if spd[d.DENSITY] >> bit & 1)
    return SpdInfo(
        address=address,
        slot=slot,
        dram_type=DRAM_TYPES.get(spd[2]),
        module_type=DDR2_MODULE_TYPES.get(spd[d.MODULE_TYPE] & 0x3F),
        manufacturer=_ddr2_vendor(spd[d.VENDOR]),
        part_number=_text(spd[d.PART_NUMBER]),
        **_date(spd[d.DATE_YEAR], spd[d.DATE_WEEK]),
        ranks=ranks,
        device_width=spd[d.CHIP_WIDTH] or None,
        bus_width=spd[d.BUS_WIDTH] | spd[d.BUS_WIDTH_HIGH] << 8 or None,
        ecc_bits=8 if spd[d.ECC] & 0x02 else 0,
        capacity_bytes=per_rank_mib * ranks * 1024**2 or None,
        jedec=jedec if jedec.plausible else None,
        voltages_v=(1.8,),
        decoded=True,
    )


# --------------------------------------------------------------------------
# DDR4 decoding
# --------------------------------------------------------------------------


def _signed(value: int) -> int:
    return value - 256 if value > 127 else value


class _Ddr4:
    """The DDR4 format's offsets, by name."""

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


def _jedec_cycles(picoseconds: float, tck_ps: float) -> Optional[int]:
    """A time turned into clock cycles, with JEDEC's rounding.

    Up, because memory can't answer early: 22.2 cycles are a CL23, and to
    the nearest it would be a CL22 that doesn't hold. But with a 2.6 %
    margin, JEDEC's algorithm's: the SPD stores the cycle truncated to
    picoseconds (833 for DDR4-2400, really 833.33), and a time of exactly 17
    cycles comes out as 17.006, which a bare ceiling would take to 18. In
    integers, so it doesn't depend on how a float falls.
    """
    if not (tck_ps and picoseconds):
        return None
    return (int(picoseconds) * 1000 // int(tck_ps) + 974) // 1000 or None


def _ddr4_timing(spd: bytes, medium: int, fine: int, tck_ps: float) -> Optional[int]:
    """Turn an SPD time into clock cycles.

    The value comes in two parts: a coarse one in 125 ps units and a signed
    fine adjustment in picoseconds. Ignoring the fine adjustment shifts the
    results just enough for a CL22 to come out as CL21.
    """
    if not tck_ps:
        return None
    picoseconds = spd[medium] * 125 + _signed(spd[fine])
    return _jedec_cycles(picoseconds, tck_ps)


def _decode_ddr4(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr4
    tck_ps = spd[d.TCK_MIN] * 125 + _signed(spd[d.FINE_TCK_MIN])
    # DDR4 transfers twice per cycle: hence the 2 000 000.
    speed = jedec_grade(2_000_000 / tck_ps) if tck_ps else 0

    after = (((spd[d.TRAS_TRC_UPPER] & 0x0F) << 8) | spd[d.TRAS_LSB]) * 125
    trc = ((((spd[d.TRAS_TRC_UPPER] & 0xF0) >> 4) << 8) | spd[d.TRC_LSB]) * 125
    trc += _signed(spd[d.FINE_TRC])

    jedec = Timings(
        name="JEDEC",
        speed_mts=speed,
        cl=_ddr4_timing(spd, d.TAA, d.FINE_TAA, tck_ps),
        trcd=_ddr4_timing(spd, d.TRCD, d.FINE_TRCD, tck_ps),
        trp=_ddr4_timing(spd, d.TRP, d.FINE_TRP, tck_ps),
        tras=_jedec_cycles(after, tck_ps),
        trc=_jedec_cycles(trc, tck_ps),
        voltage_v=1.2,
    )

    organization = spd[d.ORGANIZATION]
    bus = spd[d.BUS_WIDTH]
    ranks = ((organization >> 3) & 0x07) + 1
    chip_width = 4 << (organization & 0x07)
    bus_width = 8 << (bus & 0x07)

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
        device_width=chip_width,
        bus_width=bus_width,
        ecc_bits=8 if (bus >> 3) & 0x03 else 0,
        capacity_bytes=_capacity(
            DDR4_DENSITIES.get(spd[d.DENSITY] & 0x0F), chip_width, bus_width, ranks),
        jedec=jedec if jedec.plausible else None,
        profiles=tuple(_xmp_profiles(spd)),
        xmp_speeds_mts=_xmp_speed(spd, jedec if jedec.plausible else None),
        xmp_revision=_xmp_revision(spd),
        decoded=True,
    )


# --------------------------------------------------------------------------
# DDR5 decoding
# --------------------------------------------------------------------------


class _Ddr5:
    """The DDR5 format's offsets (JEDEC JESD400-5).

    It shares nothing with DDR4's but the byte saying which memory type it
    is. The chip goes from 512 bytes to 1024, times stop coming in two parts
    and are stored in sixteen-bit picoseconds, and everything identifying the
    module moves to its own block starting at byte 512.
    """

    TCK_MIN, TCK_MAX = 20, 22
    TAA, TRCD, TRP, TRAS, TRC = 24, 26, 28, 30, 32
    DENSITY, ADDRESSING, IO_WIDTH = 4, 5, 6
    ORGANIZATION, BUS_WIDTH = 234, 235
    VENDOR_BANK, VENDOR_ID = 512, 513
    DATE_YEAR, DATE_WEEK = 515, 516
    PART_NUMBER = slice(521, 551)
    DRAM_BANK, DRAM_ID = 552, 553
    # The factory profile blocks, each with its signature at the start.
    XMP_MAGIC = slice(640, 642)
    EXPO_MAGIC = slice(832, 836)


def _u16(spd: bytes, offset: int) -> int:
    """Times take two bytes, low first."""
    if offset + 1 >= len(spd):
        return 0
    return spd[offset] | (spd[offset + 1] << 8)


def _ddr5_cycles(picoseconds: int, tck_ps: int) -> Optional[int]:
    """An SPD time turned into clock cycles.

    Rounded up: a CL coming out at 39.2 cycles is a CL40, because memory
    can't answer early. Rounding to the nearest turns a CL40 into a CL39,
    which doesn't exist.
    """
    if not (tck_ps and picoseconds):
        return None
    return -(-picoseconds // tck_ps) or None


def _decode_ddr5(spd: bytes, address: str, slot: int) -> SpdInfo:
    d = _Ddr5
    tck_ps = _u16(spd, d.TCK_MIN)
    # Like DDR4, two transfers per cycle. A 357 ps tCK is 5600 MT/s.
    speed = jedec_grade(2_000_000 / tck_ps) if tck_ps else 0

    jedec = Timings(
        name="JEDEC",
        speed_mts=speed,
        cl=_ddr5_cycles(_u16(spd, d.TAA), tck_ps),
        trcd=_ddr5_cycles(_u16(spd, d.TRCD), tck_ps),
        trp=_ddr5_cycles(_u16(spd, d.TRP), tck_ps),
        tras=_ddr5_cycles(_u16(spd, d.TRAS), tck_ps),
        trc=_ddr5_cycles(_u16(spd, d.TRC), tck_ps),
        # DDR5 went from 1.2 V to 1.1 V, where much of its efficiency comes
        # from.
        voltage_v=1.1,
    )

    # The module's organization is on page 1: with page 0 alone, unknown.
    full = len(spd) > d.BUS_WIDTH
    organization = spd[d.ORGANIZATION] if full else 0
    bus = spd[d.BUS_WIDTH] if full else 0
    ranks = ((organization >> 3) & 0x07) + 1 if full else None
    channels = ((bus >> 5) & 0x03) + 1
    channel_width = 8 << (bus & 0x07)
    extension = ((bus >> 3) & 0x03) * 4        # the ECC bits, if any

    density = spd[d.DENSITY] if len(spd) > d.DENSITY else 0
    chip_width = DDR5_WIDTHS.get((spd[d.IO_WIDTH] >> 5) & 0x07
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
        device_width=chip_width,
        bus_width=channel_width * channels if full else None,
        ecc_bits=extension * channels,
        channels=channels,
        capacity_bytes=_capacity(
            DDR5_DENSITIES.get(density & 0x1F), chip_width,
            channel_width * channels, ranks, dies=1 << ((density >> 5) & 0x07))
        if full else None,
        jedec=jedec if jedec.plausible else None,
        overclock_profiles=_ddr5_profiles(spd),
        decoded=True,
        partial=len(spd) < DDR5_SIZE,
    )


def _ddr5_profiles(spd: bytes) -> tuple[str, ...]:
    """Which factory profiles the module carries, without interpreting them.

    XMP 3.0 and EXPO keep here the timings the maker guarantees beyond
    JEDEC's. Their formats aren't public like JEDEC's, and reading them by
    eye would give believable wrong figures, worse than none. Recognizing
    their signature is safe, and saying they're there beats silence: whoever
    looks learns their memory can go faster than the table says.
    """
    d = _Ddr5
    found = []
    if len(spd) > d.XMP_MAGIC.stop and spd[d.XMP_MAGIC] == b"\x0c\x4a":
        found.append("XMP 3.0")
    if len(spd) > d.EXPO_MAGIC.stop and spd[d.EXPO_MAGIC] == b"EXPO":
        found.append("EXPO")
    return tuple(found)


def _capacity(gigabits: Optional[int], chip_width: Optional[int],
               bus_width: int, ranks: int, dies: int = 1) -> Optional[int]:
    """How much memory there is: the chips that fit times what each holds.

    The same number the SMBIOS table gives, but that one needs
    administrator permissions and the module's SPD chip reads without asking
    anything. Where the user doesn't elevate, it is the only way to know how
    much memory each slot has.
    """
    if not (gigabits and chip_width and bus_width):
        return None
    chips_per_rank = bus_width // chip_width
    return gigabits * chips_per_rank * ranks * dies * 1024**3 // 8


def _vendor(bank: int, code: int) -> Optional[str]:
    """Translate a JEDEC maker code.

    The first byte isn't the bank number but how many continuation codes
    precede it, and both carry an odd parity bit in bit 7. Read as a plain
    number it gives the wrong bank.
    """
    return _jep106().get(((bank & 0x7F) + 1, code & 0x7F))


@functools.lru_cache(maxsize=1)
def _jep106() -> dict[tuple[int, int], str]:
    try:
        data = json.loads(JEP106.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {(int(bank), int(code, 16)): name
            for bank, codes in data.get("makers", {}).items()
            for code, name in codes.items()}


def _text(raw: bytes) -> Optional[str]:
    value = raw.decode("ascii", "replace").strip().strip("\x00").strip()
    return value or None


def _date(year: int, week: int) -> dict:
    """In BCD: 0x21 is 2021, not 33. The fields of `SpdInfo`."""
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
# 32 ns steps. Checked against a module sold as 3200 16-18-18-38. Profile
# 2's place has no source to read it from, and no module here carries one:
# it isn't read.
XMP1_VOLTAGE = 393
XMP1_TCK, XMP1_TCK_FINE = 396, 431
XMP1_TAA, XMP1_TAA_FINE = 401, 430
XMP1_TRCD, XMP1_TRCD_FINE = 402, 429
XMP1_TRP, XMP1_TRP_FINE = 403, 428
XMP1_UPPER, XMP1_TRAS, XMP1_TRAS_FINE, XMP1_TRC = 404, 405, 427, 406


def _xmp1_tck_ps(spd: bytes) -> Optional[int]:
    """Profile 1's cycle in ps, or None without the XMP header."""
    if len(spd) <= XMP1_TCK_FINE or spd[_Ddr4.XMP_MAGIC] != b"\x0c\x4a":
        return None
    return spd[XMP1_TCK] * 125 + _signed(spd[XMP1_TCK_FINE]) or None


def _xmp_voltage(byte: int) -> Optional[float]:
    """Bit 7 is one volt and the rest hundredths: 0xA3 is 1.35 V. Read as
    (b >> 1) · 0.01 it was 0.81 V. Not from a source: memtest86+ doesn't
    read it."""
    return round((byte >> 7) + (byte & 0x7F) * 0.01, 2) or None


def _xmp_speed(spd: bytes, jedec: Optional[Timings]) -> tuple[int, ...]:
    """Profile 1's speed alone, for a profile whose timings make no sense:
    its cycle is still a rated speed. Only above JEDEC."""
    tck = _xmp1_tck_ps(spd)
    if not tck:
        return ()
    speed = jedec_grade(2_000_000 / tck)
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

    def timing(mtb: int, fine: int) -> int:
        return spd[mtb] * 125 + _signed(spd[fine])

    high = spd[XMP1_UPPER]
    after = (high & 0x0F) * 32_000 + timing(XMP1_TRAS, XMP1_TRAS_FINE)
    trc = (high >> 4) * 32_000 + spd[XMP1_TRC] * 125
    profile = Timings(
        name="XMP 1",
        speed_mts=jedec_grade(2_000_000 / tck),
        cl=_jedec_cycles(timing(XMP1_TAA, XMP1_TAA_FINE), tck),
        trcd=_jedec_cycles(timing(XMP1_TRCD, XMP1_TRCD_FINE), tck),
        trp=_jedec_cycles(timing(XMP1_TRP, XMP1_TRP_FINE), tck),
        tras=_jedec_cycles(after, tck),
        trc=_jedec_cycles(trc, tck),
        voltage_v=_xmp_voltage(spd[XMP1_VOLTAGE]),
    )
    if profile.plausible:
        yield profile


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def decode(spd: bytes, address: str = "", slot: int = 0) -> SpdInfo:
    if len(spd) < 128:
        return SpdInfo(address=address, slot=slot)

    dram = DRAM_TYPES.get(spd[2])
    if spd[2] == 0x08:
        return _decode_ddr2(spd, address, slot)
    if spd[2] == 0x0B and len(spd) >= 176:
        return _decode_ddr3(spd, address, slot)
    if spd[2] == 0x0C:
        return _decode_ddr4(spd, address, slot)
    if spd[2] == 0x12:
        return _decode_ddr5(spd, address, slot)

    # DDR and older have another format. The type is identified, which is
    # something, and it's made clear the detail isn't implemented.
    return SpdInfo(address=address, slot=slot, dram_type=dram, decoded=False)


def available() -> bool:
    return any(True for _chip in _eeproms())


# The PCI class of an SMBus controller, how it's recognized without
# depending on the maker.
SMBUS_CLASS = 0x0C0500
SYS_PCI = pathlib.Path("/sys/bus/pci/devices")
SYS_I2C = pathlib.Path("/sys/bus/i2c/devices")


# Why the SPD cannot be read, by its code, and how it is said.
CAUSE_NO_SMBUS, CAUSE_NO_BUS, CAUSE_NO_DRIVER = "nosmbus", "nobus", "nodriver"
CAUSE_NO_CHIP, CAUSE_NO_CONTENT = "nochip", "nocontent"
CAUSES = {
    CAUSE_NO_SMBUS: ("spd.nosmbus", "spd.nosmbus.hint"),
    CAUSE_NO_BUS: ("spd.nobus", "spd.nobus.hint"),
    CAUSE_NO_DRIVER: ("spd.nodriver", "spd.nodriver.hint"),
    CAUSE_NO_CHIP: ("spd.nochip", "spd.nochip.hint"),
    CAUSE_NO_CONTENT: ("spd.nocontent", "spd.nocontent.hint"),
}
# The driver for each SPD chip, by the name the kernel registers it under
# (`i2c_register_spd`: «spd» is DDR3 and older, read by at24).
SPD_DRIVERS = {"spd5118": "spd5118", "ee1004": "ee1004", "spd": "at24", "at24": "at24"}
PCI_ADDRESS = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def memory_buses() -> list[str]:
    """The numbers of the i2c buses that hang straight from an SMBus controller.

    The modules' SPD chips live there. A touchpad's DesignWare buses and a
    graphics card's hang from other devices and never lead to memory.
    """
    found = []
    try:
        entries = sorted(sysroot.path(SYS_I2C).iterdir())
    except OSError:
        return found
    for bus in entries:
        if not bus.name.startswith("i2c-"):
            continue
        try:
            parent = pathlib.PurePosixPath(os.readlink(bus)).parent.name
            pci_class = int((sysroot.path(SYS_PCI) / parent / "class").read_text().strip(), 16)
        except (OSError, ValueError):
            continue
        if PCI_ADDRESS.match(parent) and pci_class >> 8 == SMBUS_CLASS >> 8:
            found.append(bus.name[len("i2c-"):])
    return found


def spd_chips(buses: Optional[list[str]] = None) -> list[pathlib.Path]:
    """The devices the kernel registered at 0x50-0x57 of the memory buses."""
    buses = memory_buses() if buses is None else buses
    try:
        entries = sorted(sysroot.path(SYS_I2C).iterdir())
    except OSError:
        return []
    return [entry for entry in entries
            if SPD_ADDRESS.match(entry.name)
            and entry.name.split("-", 1)[0] in buses]


def has_driver(chip: pathlib.Path) -> bool:
    """Whether a driver is bound: its link, or what only a driver creates."""
    return ((chip / "driver").exists() or (chip / "eeprom").exists()
            or (chip / "hwmon").is_dir())


def driver_for(chip: pathlib.Path) -> Optional[str]:
    """The module that reads this chip, from the name the kernel gave it."""
    try:
        return SPD_DRIVERS.get((chip / "name").read_text().strip())
    except OSError:
        return None


def unreadable_cause() -> str:
    """Why the SPD can't be read on this machine, as a code.

    There are three different reasons, and each one's fix is unlike the
    others'. Answering «load ee1004» every time is useless on most AMD
    boards: the module is already there and the problem is that there's no
    bus to look on.
    """
    if not _has_smbus_controller():
        return CAUSE_NO_SMBUS
    buses = memory_buses()
    if not buses:
        # The most common case on AMD boards: the firmware claims the SMBus
        # I/O region as its own and the kernel leaves it alone in case both
        # write at once.
        return CAUSE_NO_BUS
    chips = spd_chips(buses)
    if any(not has_driver(chip) for chip in chips):
        return CAUSE_NO_DRIVER
    # With no chip registered there is no driver to load; with all of them
    # bound, the driver doesn't publish what they hold.
    return CAUSE_NO_CONTENT if chips else CAUSE_NO_CHIP


def diagnosis(cause: Optional[str] = None) -> tuple[str, str]:
    """Why the SPD can't be read, and what to do, said for the person."""
    cause = cause or unreadable_cause()
    message, hint = CAUSES[cause]
    if cause == CAUSE_NO_DRIVER:
        # The chip's own driver when the kernel named it; the three
        # generations' otherwise.
        modules = sorted({m for chip in spd_chips() if not has_driver(chip)
                          if (m := driver_for(chip))})
        if modules:
            return _(message), _("spd.nodriver.load").format(
                orden="  ".join(f"sudo modprobe {m}" for m in modules))
    return _(message), _(hint)


def _has_smbus_controller() -> bool:
    """Whether the board has the bus the SPD chips live on."""
    try:
        for device in sysroot.path(SYS_PCI).iterdir():
            raw = (device / "class").read_text().strip()
            if int(raw, 16) == SMBUS_CLASS:
                return True
    except (OSError, ValueError):
        pass
    return False


def _eeproms() -> Iterator[tuple[pathlib.Path, int]]:
    if not sysroot.path(I2C_DEVICES).is_dir():
        return
    for entry in sorted(sysroot.path(I2C_DEVICES).iterdir()):
        match = SPD_ADDRESS.match(entry.name)
        if match and (entry / "eeprom").exists():
            yield entry, int(match.group(1), 16) - 0x50


# A DDR5 SPD is 1024 bytes in eight pages of 128. The driver switches pages by
# writing to the chip; where the machine blocks SPD writes only page 0 reads.
DDR5_SIZE, DDR5_PAGE = 1024, 128
# DDR5's JEDEC speeds start at 3200 MT/s (a 625 ps cycle).
DDR5_MIN_MTS = 3200


def first_page(raw: bytes, address: str, slot: int) -> Optional[SpdInfo]:
    """A DDR5 chip's page 0 alone, if it holds up.

    Its CRC is on page 3, so it can't be checked: the type byte, a DDR5
    cycle, plausible timings and known module type and chip width have to
    vouch for it instead. Nothing that fails is shown.
    """
    if len(raw) < DDR5_PAGE or raw[2] != 0x12:
        return None
    info = _decode_ddr5(raw[:DDR5_PAGE], address, slot)
    if (info.jedec is None or info.jedec.cl is None or info.jedec.speed_mts < DDR5_MIN_MTS
            or info.module_type is None or info.device_width is None):
        return None
    return info


def read_pages(path) -> tuple[list[Optional[bytes]], Optional[OSError]]:
    """A chip's pages of 128 bytes, each in a read of its own, and the first
    error; a page that failed is None.

    Unbuffered: asked for 128 bytes, a buffered file asks the kernel for a
    whole block (4096), which crosses into page 1; where the machine blocks
    the page switch that read fails, and page 0 with it.
    """
    pages: list[Optional[bytes]] = []
    error: Optional[OSError] = None
    with open(path, "rb", buffering=0) as eeprom:
        for offset in range(0, DDR5_SIZE, DDR5_PAGE):
            try:
                eeprom.seek(offset)
                chunk = eeprom.read(DDR5_PAGE)
            except OSError as exc:
                error = error or exc
                pages.append(None)
                continue
            if not chunk:
                break                          # a smaller chip ends here
            pages.append(chunk)
    return pages, error


def read_all(failures: Optional[list] = None) -> list[SpdInfo]:
    """Read the SPD of every slot the kernel exposes.

    `failures` collects (device, OSError) for each `eeprom` that is there and
    could not be read whole: that is not the same as having none. A DDR5 one
    whose page 0 read gives what that page holds.
    """
    found = []
    for entry, slot in _eeproms():
        try:
            pages, error = read_pages(entry / "eeprom")
        except OSError as exc:
            if failures is not None:
                failures.append((entry.name, exc))
            continue
        if error is None:
            found.append(decode(b"".join(p for p in pages if p), address=entry.name, slot=slot))
            continue
        if failures is not None:
            failures.append((entry.name, error))
        if pages and pages[0] and (partial := first_page(pages[0], entry.name, slot)) is not None:
            found.append(partial)
    return found
