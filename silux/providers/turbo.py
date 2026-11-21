"""Whether the turbo is on.

It explains a gap that otherwise puzzles: CPUID says the part reaches
4.3 GHz and the kernel says the ceiling is 2.9. Almost always the turbo is
off in the firmware or in the driver, and that is worth saying.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Optional

from .. import sysroot
from ..model import Clocks
from .base import Draft, Provider, is_virtual_machine, read_int, read_text

INTEL_PSTATE_NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPUFREQ_BOOST = "/sys/devices/system/cpu/cpufreq/boost"
CPUINFO = "/proc/cpuinfo"
# The kernel's flags for a part that has a turbo: AMD's Core Performance
# Boost (CPUID 0x80000007 EDX bit 9) and Intel's Dynamic Acceleration
# (CPUID 6 EAX bit 1). Read from /proc/cpuinfo and not from CPUID: the dumps
# carry that file, and not those two leaves.
TURBO_FLAGS = ("cpb", "ida")


def _turbo_supported() -> Optional[bool]:
    """Whether the part has a turbo, by the kernel's flags; None without them
    (not x86)."""
    for line in (read_text(CPUINFO) or "").splitlines():
        key, _sep, value = line.partition(":")
        if key.strip() == "flags":
            return any(flag in value.split() for flag in TURBO_FLAGS)
    return None


class TurboState(Provider):
    name = "turbo"
    provides = "cpu.clocks.turbo_enabled"
    # Not static: desktop power profiles turn the turbo on and off at any
    # time, and the frequency ceiling moves with it.
    static = False

    def __init__(self) -> None:
        # The part does not change: read once, not on every sample.
        self._supported: Optional[bool] = None
        self._supported_read = False

    def available(self) -> bool:
        return (os.path.exists(sysroot.ruta(INTEL_PSTATE_NO_TURBO))
                or os.path.exists(sysroot.ruta(CPUFREQ_BOOST))
                or os.path.exists(sysroot.ruta(CPUINFO)))

    def collect(self, draft: Draft) -> None:
        enabled = None
        if (value := read_int(INTEL_PSTATE_NO_TURBO)) is not None:
            enabled = value == 0
        elif (value := read_int(CPUFREQ_BOOST)) is not None:
            enabled = value == 1
        if not self._supported_read:
            self._supported, self._supported_read = _turbo_supported(), True
        # A virtual CPU's flags are the hypervisor's, not the host's part.
        supported = None if is_virtual_machine(draft) else self._supported

        if enabled is None and supported is None:
            return

        for entry in draft.types.values():
            clocks: Clocks = entry.get("clocks") or Clocks()
            entry["clocks"] = dataclasses.replace(clocks, turbo_enabled=enabled,
                                                  turbo_supported=supported)

        # No note: the turbo's state shows next to the clocks, and as it
        # follows the power profile, a notice at the foot came and went.
