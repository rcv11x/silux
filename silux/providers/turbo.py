"""Whether turbo is enabled.

It explains a puzzling gap: CPUID says the part reaches 4.3 GHz while the
kernel's ceiling is 2.9. Nearly always turbo is off in the firmware or the
driver, and that is worth saying.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Optional

from .. import db, render, sysroot
from ..i18n import _
from ..model import Clocks, Need
from .base import Draft, Provider, is_virtual_machine, read_int, read_text

INTEL_PSTATE_NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPUFREQ_BOOST = "/sys/devices/system/cpu/cpufreq/boost"
CPUINFO = "/proc/cpuinfo"
# The kernel's flags for a part with turbo: AMD's Core Performance Boost
# (CPUID 0x80000007 EDX bit 9) and Intel's Dynamic Acceleration (CPUID 6 EAX
# bit 1). Read from /proc/cpuinfo rather than CPUID because dumps carry that
# file but not those two leaves.
TURBO_FLAGS = ("cpb", "ida")


def _turbo_supported() -> Optional[bool]:
    """Whether the part has turbo, from the kernel's flags; None without them
    (not x86)."""
    for line in (read_text(CPUINFO) or "").splitlines():
        key, _sep, value = line.partition(":")
        if key.strip() == "flags":
            return any(flag in value.split() for flag in TURBO_FLAGS)
    return None


class TurboState(Provider):
    name = "turbo"
    provides = "cpu.clocks.turbo_enabled"
    # Not static: desktop power profiles toggle turbo at any time, and the
    # frequency ceiling moves with it.
    static = False

    def __init__(self) -> None:
        # The part doesn't change; read once.
        self._supported: Optional[bool] = None
        self._supported_read = False

    def available(self) -> bool:
        return (os.path.exists(sysroot.path(INTEL_PSTATE_NO_TURBO))
                or os.path.exists(sysroot.path(CPUFREQ_BOOST))
                or os.path.exists(sysroot.path(CPUINFO)))

    def collect(self, draft: Draft) -> None:
        enabled = None
        if (value := read_int(INTEL_PSTATE_NO_TURBO)) is not None:
            enabled = value == 0
        elif (value := read_int(CPUFREQ_BOOST)) is not None:
            enabled = value == 1
        if not self._supported_read:
            self._supported, self._supported_read = _turbo_supported(), True
        # A virtual CPU's flags come from the hypervisor, not the host's part.
        supported = None if is_virtual_machine(draft) else self._supported
        brands = {entry.get("brand") for entry in draft.types.values() if entry.get("brand")}
        if supported is False and brands and all(db.amd_turbo(b) is True for b in brands):
            # AMD lists a boost clock for this model: the firmware takes the
            # flag away when it switches Core Performance Boost off. Off, not
            # missing.
            supported = True
            enabled = False
        if enabled is None and supported:
            # Some parts without turbo set the flag anyway. With no boost
            # control from the kernel to say otherwise, the maker's
            # specifications decide.
            if brands and all(db.amd_turbo(brand) is False for brand in brands):
                supported = False

        if supported is False:
            # intel_pstate writes no_turbo=1 on a part without turbo: there is
            # nothing to have switched off.
            enabled = None
        if enabled is not None or supported is not None:
            for entry in draft.types.values():
                clocks: Clocks = entry.get("clocks") or Clocks()
                entry["clocks"] = dataclasses.replace(clocks, turbo_enabled=enabled,
                                                      turbo_supported=supported)
        # No note of turbo's state: it shows next to the clocks, and since it
        # follows the power profile, a footnote would keep coming and going.
        _base_set_by_hand(draft)


# Between the firmware's base and the maker's, more than CPPC's own rounding
# (3401 for 3400): a base set by hand in the BIOS.
CHANGED_BASE_HZ = 50_000_000


def _factory_clocks(entry: dict) -> Optional[tuple[int, Optional[int]]]:
    """An AMD model's base and boost as AMD lists them, in hertz."""
    if entry.get("vendor") != "AMD":
        return None
    row = db.amd_model(entry.get("brand") or "")
    if not row or not row.get("base_mhz"):
        return None
    boost = row.get("boost_mhz")
    return row["base_mhz"] * 1_000_000, boost * 1_000_000 if boost else None


def _base_set_by_hand(draft: Draft) -> None:
    """An AMD whose firmware base isn't AMD's: the kernel works its maximum
    out from that base (amd-pstate scales it by a fixed figure), so neither
    its maximum nor the part's ceiling are the processor's. They go, and the
    note says the base, AMD's and AMD's boost."""
    if is_virtual_machine(draft):
        return
    for entry in draft.types.values():
        clocks: Clocks = entry.get("clocks") or Clocks()
        factory = _factory_clocks(entry)
        if not factory or not clocks.base_hz or abs(clocks.base_hz - factory[0]) < CHANGED_BASE_HZ:
            continue
        kernel_max = clocks.max_hz or clocks.max_turbo_hz
        entry["clocks"] = dataclasses.replace(clocks, max_hz=None, max_turbo_hz=None,
                                              factory_base_hz=factory[0],
                                              factory_boost_hz=factory[1])
        hint = _("prov.cppc.basechanged.hint").format(
            kernel=render.hz(kernel_max) if kernel_max else render.DASH,
            boost=render.hz(factory[1]) if factory[1] else render.DASH)
        if clocks.turbo_enabled is False:
            hint = f"{hint} {_('prov.cppc.basechanged.noturbo')}"
        draft.note("cpu.clocks.max_hz", Need.HARDWARE,
                   _("prov.cppc.basechanged").format(base=render.hz(clocks.base_hz),
                                                     factory=render.hz(factory[0])),
                   hint, key="prov.cppc.basechanged")
        return
