"""Base clock, the part's ceiling and BCLK when CPUID 0x16 doesn't give them.

Leaf 0x16 only exists on Intel from Skylake; on AMD, older Intel and any
old x86, three rows of the Clocks card would stay empty. This fills them
from what there is, most reliable first:

- **ACPI CPPC** (`/sys/devices/system/cpu/cpuN/acpi_cppc/`), published for
  `amd-pstate` and for `intel_pstate` with HWP: the nominal clock in MHz and
  a performance scale that gives the part's ceiling. Not AMD-specific: it is
  ACPI 5.0, on any platform that declares it.
- **The brand string**, which on two decades of Intel parts and some AMD
  ones ends in «@ 3.30GHz»: the only source on a Core 2 or a Phenom, which
  have neither 0x16 nor CPPC.

It never overwrites another source: on modern Intel, CPUID 0x16 comes first
and this touches nothing.

CPPC also gives something no other Linux tool shows: **how good each core
came out of the wafer**. The cores of one part aren't equal; the firmware
knows, and the scheduler sends a lone thread to the best one.
"""

from __future__ import annotations

import dataclasses
import os
import re
from typing import Optional

from .. import kernel, sysroot
from ..i18n import _
from ..model import Clocks, Need
from .base import Draft, Provider, is_virtual_machine, read_int
from .msr_pstate import is_zen

SYS_CPU = "/sys/devices/system/cpu"

# The reference clock of every CPPC platform: Nehalem and Zen onwards fix it
# at 100 MHz. Core 2 and older used a 133, 200, 266 or 333 MHz FSB, so BCLK is
# only derived with CPPC; assuming 100 MHz on a Core 2 would be making it up.
REFERENCE_HZ = 100_000_000

# The multiplier moves in 0.25 steps. If base / multiplier strays further
# than this from 100 MHz, the assumption fails and the value stays empty
# rather than lie.
TOLERANCE = 0.02

# «Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz»
_BRAND_FREQUENCY = re.compile(r"@\s*([\d.]+)\s*([GM])Hz", re.IGNORECASE)


class CppcClocks(Provider):
    """Fills the clocks CPUID couldn't give, never overwriting those it did."""

    name = "cppc-clocks"
    provides = "cpu.clocks.base_hz"
    # CPPC's nominal clock and scale come from firmware tables and don't
    # change while the machine is on.
    static = True

    def available(self) -> bool:
        return os.path.isdir(sysroot.path(SYS_CPU))

    def collect(self, draft: Draft) -> None:
        no_base = False
        no_bus = False
        no_ceiling = False
        no_ceiling_source = False
        # Only an AMD can owe its ceiling to amd-pstate: an Intel without
        # CPUID 0x16 can lack it too, for other reasons.
        ceiling_is_amds = False

        for entry in draft.types.values():
            clocks: Clocks = entry.get("clocks") or Clocks()
            leader = (entry.get("cpus") or [0])[0]
            cppc = _read_cppc(leader)
            if cppc:
                # Only when the firmware really has it: the brand string isn't a
                # new source, it comes from the CPUID already reported.
                draft.capabilities.add("cppc")

            nominal = _nominal_hz(cppc)
            base = (clocks.base_hz or nominal or clocks.base_configured_hz
                    or _base_from_brand(entry.get("brand")))

            # BCLK is only derived when the base comes from CPPC (see
            # REFERENCE_HZ), and only on x86: server ARM publishes ACPI CPPC too,
            # with no 100 MHz reference to hang a multiplier from.
            is_x86 = (entry.get("architecture") or "").startswith("x86")
            bus = clocks.bus_hz
            if bus is None and nominal and is_x86:
                bus = _reference_clock(nominal)

            ceiling = clocks.max_turbo_hz
            if ceiling is None:
                if _has_ranking(entry.get("cpus") or [leader]) \
                        and not _amd_pstate_ceiling(leader):
                    no_ceiling = True
                    ceiling_is_amds = ceiling_is_amds or entry.get("vendor") == "AMD"
                else:
                    ceiling = _silicon_ceiling(leader, cppc, nominal)
            # A ceiling below the base means the calculation went wrong.
            if ceiling and base and ceiling < base:
                ceiling = None

            if (base, bus, ceiling) != (clocks.base_hz, clocks.bus_hz, clocks.max_turbo_hz):
                entry["clocks"] = dataclasses.replace(
                    clocks, base_hz=base, bus_hz=bus, max_turbo_hz=ceiling
                )

            no_base = no_base or base is None
            no_bus = no_bus or (bus is None and is_x86)
            # Said only with a frequency driver: without one, the foot of the
            # clocks card already says what's missing, and turbo may be absent.
            no_ceiling_source = no_ceiling_source or (
                ceiling is None and is_x86 and clocks.turbo_supported is not False
                and os.path.isdir(sysroot.path(f"{SYS_CPU}/cpu{leader}/cpufreq")))

        _note_quality(draft)

        # A virtual machine's hypervisor exposes no clock at all, and sysfs_cpu
        # says so once.
        if is_virtual_machine(draft):
            no_base = no_bus = no_ceiling_source = False

        if no_base and any(is_zen(e) for e in draft.types.values()):
            # A Zen reports it in its P0 (msr_pstate), and permissions fix that.
            draft.note(
                "cpu.clocks.base_hz", Need.ROOT,
                _("prov.cppc.nobase.zen"), _("prov.cppc.nobase.zen.hint"),
                _("what.cpu.base"),
            )
        elif no_base:
            draft.note(
                "cpu.clocks.base_hz", Need.HARDWARE,
                _("prov.cppc.nobase"), _("prov.cppc.nobase.hint"),
            )
        if no_bus:
            draft.note(
                "cpu.clocks.bus_hz", Need.HARDWARE,
                _("prov.cppc.nobclk"), _("prov.cppc.nobclk.hint"),
            )
        if no_ceiling_source and not no_ceiling:
            draft.note(
                "cpu.clocks.max_turbo_hz", Need.HARDWARE,
                _("prov.cppc.noceiling.source"), _("prov.cppc.noceiling.source.hint"),
            )
        if no_ceiling:
            # Without amd-pstate the ceiling isn't published; if that's because
            # the kernel predates the driver, say so.
            too_old = kernel.too_old("amd_pstate") if ceiling_is_amds else None
            draft.note(
                "cpu.clocks.max_turbo_hz", Need.KERNEL if too_old else Need.HARDWARE,
                _("prov.cppc.noceiling"),
                f"{too_old} {_('prov.cppc.noceiling.hint')}" if too_old
                else _("prov.cppc.noceiling.hint"),
            )


# -- reading ----------------------------------------------------------------

def _read_cppc(cpu_index: int) -> dict[str, int]:
    """One CPU's acpi_cppc integers. Empty without firmware support."""
    folder = f"{SYS_CPU}/cpu{cpu_index}/acpi_cppc"
    if not os.path.isdir(sysroot.path(folder)):
        return {}
    fields = ("nominal_freq", "lowest_freq", "nominal_perf", "highest_perf")
    values = {}
    for field in fields:
        value = read_int(f"{folder}/{field}")
        if value:                      # 0 means the firmware left it empty
            values[field] = value
    return values


def _note_quality(draft: Draft) -> None:
    """Spread the firmware's per-core silicon rating over the logical CPUs.

    It is the same `highest_perf` rejected above as a ceiling, for the same
    reason: when the platform ranks its cores, the field stops meaning «how
    far the part goes» and means «how much better this core is than its
    siblings». As a frequency it's a trap; as a comparison it's exact.

    Only recorded where cores really differ, and **within each core type**:
    a firmware giving the same number sixteen times measures nothing, and on
    a hybrid Intel the P/E difference isn't quality, it's a different core.
    """
    ratings: dict[int, int] = {}
    for index in draft.logical:
        base = f"{SYS_CPU}/cpu{index}"
        # amd-pstate publishes the ranking already normalised; elsewhere it's
        # the CPPC field behind it. On an Intel with HWP that is each core's
        # `highest_perf`, the same idea under another name.
        rating = (read_int(f"{base}/cpufreq/amd_pstate_prefcore_ranking")
                or read_int(f"{base}/acpi_cppc/highest_perf"))
        if rating:
            ratings[index] = rating

    noted = False
    for entry in draft.types.values():
        own = {i: ratings[i] for i in (entry.get("cpus") or ()) if i in ratings}
        if len(set(own.values())) < 2:
            continue
        for index, rating in own.items():
            draft.cpu(index)["quality"] = rating
        noted = True
    if noted:
        draft.capabilities.add("cppc-prefcore")


def _nominal_hz(cppc: dict[str, int]) -> Optional[int]:
    """`nominal_freq` is in MHz and is the processor's base clock."""
    mhz = cppc.get("nominal_freq")
    return mhz * 1_000_000 if mhz else None


def _amd_pstate_ceiling(cpu_index: int) -> Optional[int]:
    """The ceiling amd-pstate publishes, already worked out, in hertz."""
    khz = read_int(f"{SYS_CPU}/cpu{cpu_index}/cpufreq/amd_pstate_max_freq")
    return khz * 1000 if khz else None


def _has_ranking(cpus) -> bool:
    """Whether these cores' `highest_perf` is a ranking rather than a scale.

    With preferred cores each has its own (181, 196, 186…) and none is the
    part's top performance. ACPI publishes `acpi_cppc/` with any driver, so
    this also happens without amd-pstate, when nothing gives the ceiling.
    """
    ratings = {read_int(f"{SYS_CPU}/cpu{index}/acpi_cppc/highest_perf") for index in cpus}
    return len(ratings - {None, 0}) > 1


def _silicon_ceiling(cpu_index: int, cppc: dict[str, int],
                       nominal_hz: Optional[int]) -> Optional[int]:
    """The part's maximum boost, as opposed to the ceiling the kernel applies."""
    # amd-pstate publishes the result, and with boost off it keeps showing the
    # real ceiling while `cpuinfo_max_freq` drops: the gap the Clocks card
    # exists to explain.
    if hz := _amd_pstate_ceiling(cpu_index):
        return hz

    nominal_perf = cppc.get("nominal_perf")
    highest_perf = cppc.get("highest_perf")
    if not (nominal_hz and nominal_perf and highest_perf):
        return None
    # Only valid where every core has the same figure; the caller has already
    # ruled out a ranking (`_has_ranking`).
    return int(nominal_hz * highest_perf / nominal_perf)


def _base_from_brand(brand: Optional[str]) -> Optional[int]:
    """A last resort: the frequency many Intel parts carry in their name."""
    if not brand:
        return None
    match = _BRAND_FREQUENCY.search(brand)
    if not match:
        return None
    scale = 1_000_000_000 if match.group(2).upper() == "G" else 1_000_000
    return int(float(match.group(1)) * scale)


def _reference_clock(base_hz: int) -> Optional[int]:
    """The BCLK the multiplier hangs from, derived from the base clock.

    A 3401 MHz base gives 34.00 × 100.03 MHz, which is what the firmware
    shows. Dividing rather than assuming 100 MHz keeps the stored number
    grounded in the data.
    """
    multiplier = round(base_hz / REFERENCE_HZ * 4) / 4
    if multiplier < 1:
        return None
    clock = int(round(base_hz / multiplier))
    if abs(clock - REFERENCE_HZ) > REFERENCE_HZ * TOLERANCE:
        return None
    return clock
