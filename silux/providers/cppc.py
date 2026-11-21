"""Base clock, the part's ceiling and BCLK when CPUID 0x16 does not give them.

Leaf 0x16 only exists on Intel from Skylake. On AMD, older Intel or any old
x86, three rows of the Clocks card stayed empty. This fills them with what
there is, most reliable first:

- **ACPI CPPC** (`/sys/devices/system/cpu/cpuN/acpi_cppc/`), published for
  `amd-pstate` and for `intel_pstate` with HWP: the nominal clock in MHz and
  a performance scale that gives the part's ceiling. Not an AMD source: it is
  ACPI 5.0, used by any platform that declares it.
- **The brand string**, which on Intel parts of almost twenty years and some
  AMD ones ends in «@ 3.30GHz»: the only place to look on a Core 2 or a
  Phenom, which have neither 0x16 nor CPPC.

It never overwrites what another source set: on modern Intel, CPUID 0x16 goes
first and this touches nothing.

From CPPC it also takes something that is not a clock and that no other
Linux tool shows: **how good each core came out of the wafer**. The cores of
one part are not equal; the firmware knows and says so, and the scheduler
sends a lone thread's work to the best one.
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

# The reference clock of every platform with CPPC: Nehalem and Zen onwards
# fixed it at 100 MHz. Core 2 and older used an FSB of 133, 200, 266 or
# 333 MHz, so BCLK is only derived with CPPC: assuming 100 MHz on a Core 2
# would be making it up.
REFERENCE_HZ = 100_000_000

# The multiplier moves in steps of 0.25. If the base divided by its
# multiplier strays from 100 MHz by more than this, the assumption fails and
# the value stays empty rather than lie.
TOLERANCE = 0.02

# «Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz»
_BRAND_FREQUENCY = re.compile(r"@\s*([\d.]+)\s*([GM])Hz", re.IGNORECASE)


class CppcClocks(Provider):
    """Completes the clocks CPUID could not give, without overwriting those it did."""

    name = "cppc-clocks"
    provides = "cpu.clocks.base_hz"
    # CPPC's nominal clock and scale come from firmware tables: they do not
    # change while the machine is on.
    static = True

    def available(self) -> bool:
        return os.path.isdir(sysroot.path(SYS_CPU))

    def collect(self, draft: Draft) -> None:
        no_base = False
        no_bus = False
        no_ceiling = False
        # Only an AMD can owe its ceiling to amd-pstate: on an Intel without
        # CPUID 0x16 it can be missing too, and not because of that driver.
        ceiling_is_amds = False

        for entry in draft.types.values():
            clocks: Clocks = entry.get("clocks") or Clocks()
            leader = (entry.get("cpus") or [0])[0]
            cppc = _read_cppc(leader)
            if cppc:
                # Only when the firmware really has it: the brand string is not
                # a new source, it comes from the CPUID already announced.
                draft.capabilities.add("cppc")

            nominal = _nominal_hz(cppc)
            base = (clocks.base_hz or nominal or clocks.base_configured_hz
                    or _base_from_brand(entry.get("brand")))

            # BCLK is only derived when the base comes from CPPC (see
            # REFERENCE_HZ), and only on x86: a server ARM publishes ACPI CPPC
            # too, with no 100 MHz reference clock to hang a multiplier from.
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
            # A ceiling below the base is a calculation gone wrong.
            if ceiling and base and ceiling < base:
                ceiling = None

            if (base, bus, ceiling) != (clocks.base_hz, clocks.bus_hz, clocks.max_turbo_hz):
                entry["clocks"] = dataclasses.replace(
                    clocks, base_hz=base, bus_hz=bus, max_turbo_hz=ceiling
                )

            no_base = no_base or base is None
            no_bus = no_bus or (bus is None and is_x86)

        _note_quality(draft)

        # In a virtual machine the hypervisor exposes no clock at all, and
        # sysfs_cpu says that once.
        if is_virtual_machine(draft):
            no_base = no_bus = False

        if no_base and any(is_zen(e) for e in draft.types.values()):
            # A Zen says it itself, in its P0 (msr_pstate): permissions fix it.
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
        if no_ceiling:
            # Without amd-pstate the ceiling is not published; if that is
            # because the kernel predates the driver, that is what to say.
            too_old = kernel.too_old("amd_pstate") if ceiling_is_amds else None
            draft.note(
                "cpu.clocks.max_turbo_hz", Need.KERNEL if too_old else Need.HARDWARE,
                _("prov.cppc.noceiling"),
                f"{too_old} {_('prov.cppc.noceiling.hint')}" if too_old
                else _("prov.cppc.noceiling.hint"),
            )


# -- reading ----------------------------------------------------------------

def _read_cppc(cpu_index: int) -> dict[str, int]:
    """The integers of acpi_cppc for one CPU. Empty without firmware support."""
    folder = f"{SYS_CPU}/cpu{cpu_index}/acpi_cppc"
    if not os.path.isdir(sysroot.path(folder)):
        return {}
    fields = ("nominal_freq", "lowest_freq", "nominal_perf", "highest_perf")
    values = {}
    for field in fields:
        value = read_int(f"{folder}/{field}")
        if value:                      # a 0 is «the firmware did not fill it»
            values[field] = value
    return values


def _note_quality(draft: Draft) -> None:
    """Spread over the logical CPUs the silicon rating the firmware publishes.

    The same `highest_perf` discarded above for the ceiling, for the same
    reason: when the platform ranks its cores, that field stops meaning «how
    far the part goes» and means «how much better this core is than its
    siblings». As a frequency it is a trap; as a comparison it says exactly
    that.

    Only noted where cores really differ, and **within each core type**. A
    firmware giving the same number sixteen times measures nothing. And a
    hybrid Intel always differs between a P-core and an E-core, which is not
    the point: an E-core did not come out worse, it is another core.
    """
    ratings: dict[int, int] = {}
    for index in draft.logical:
        base = f"{SYS_CPU}/cpu{index}"
        # amd-pstate publishes the ranking already normalized; elsewhere, the
        # CPPC field it comes from. On an Intel with HWP this is each core's
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
    """`nominal_freq` is in MHz; it is the processor's base clock."""
    mhz = cppc.get("nominal_freq")
    return mhz * 1_000_000 if mhz else None


def _amd_pstate_ceiling(cpu_index: int) -> Optional[int]:
    """The ceiling amd-pstate publishes already worked out, in hertz."""
    khz = read_int(f"{SYS_CPU}/cpu{cpu_index}/cpufreq/amd_pstate_max_freq")
    return khz * 1000 if khz else None


def _has_ranking(cpus) -> bool:
    """Whether these cores' `highest_perf` is a ranking and not a scale.

    With preferred cores each carries its own (181, 196, 186…) and none is
    the part's top performance. ACPI publishes `acpi_cppc/` with any driver,
    so this also happens without amd-pstate, when nobody gives the ceiling.
    """
    ratings = {read_int(f"{SYS_CPU}/cpu{index}/acpi_cppc/highest_perf") for index in cpus}
    return len(ratings - {None, 0}) > 1


def _silicon_ceiling(cpu_index: int, cppc: dict[str, int],
                       nominal_hz: Optional[int]) -> Optional[int]:
    """The part's maximum boost, distinct from the ceiling the kernel applies."""
    # amd-pstate publishes the calculation done, and with boost off it keeps
    # showing the real ceiling while `cpuinfo_max_freq` drops: the gap the
    # Clocks card is there to explain.
    if hz := _amd_pstate_ceiling(cpu_index):
        return hz

    nominal_perf = cppc.get("nominal_perf")
    highest_perf = cppc.get("highest_perf")
    if not (nominal_hz and nominal_perf and highest_perf):
        return None
    # Only valid where every core carries the same figure: the caller has
    # already ruled out a ranking (`_has_ranking`).
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
    """The BCLK the multiplier hangs from, worked out from the base clock.

    A 3401 MHz base gives a 34.00 multiplier over 100.03 MHz, which is what
    the firmware shows. The division is done rather than assuming 100 MHz,
    so the stored number still comes from the data.
    """
    multiplier = round(base_hz / REFERENCE_HZ * 4) / 4
    if multiplier < 1:
        return None
    clock = int(round(base_hz / multiplier))
    if abs(clock - REFERENCE_HZ) > REFERENCE_HZ * TOLERANCE:
        return None
    return clock
