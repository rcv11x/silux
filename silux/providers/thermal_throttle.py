"""How often the processor throttled for temperature since boot (Intel).

The kernel counts, under each CPU's `thermal_throttle/`, every time a core
or the package hit its thermal limit and for how long. The count starts at
boot, so zero is an answer: it hasn't happened.
"""

from __future__ import annotations

import glob
import os
from typing import Optional

from .. import sysroot
from ..model import ThermalThrottle
from .base import Draft, Provider, read_int, read_text

CPUS = "/sys/devices/system/cpu"


class ThermalThrottleCounts(Provider):
    name = "thermal-throttle"
    provides = "cpu.thermal_throttle"

    def __init__(self) -> None:
        # One directory per physical core and one per package; a core's
        # threads share its counters.
        self._cores: Optional[list[str]] = None
        self._packages: list[str] = []

    def available(self) -> bool:
        return os.path.isdir(sysroot.path(f"{CPUS}/cpu0/thermal_throttle"))

    def _directories(self) -> None:
        cores: dict[tuple, str] = {}
        packages: dict[Optional[str], str] = {}
        for path in sorted(glob.glob(os.path.join(sysroot.path(CPUS), "cpu[0-9]*", "thermal_throttle")),
                           key=lambda p: int(os.path.basename(os.path.dirname(p))[3:])):
            cpu = sysroot.unrooted(os.path.dirname(path))
            package = read_text(f"{cpu}/topology/physical_package_id")
            core = read_text(f"{cpu}/topology/core_id")
            cores.setdefault((package, core), sysroot.unrooted(path))
            packages.setdefault(package, sysroot.unrooted(path))
        self._cores, self._packages = list(cores.values()), list(packages.values())

    def collect(self, draft: Draft) -> None:
        if self._cores is None:
            self._directories()

        def total(directories: list[str], counter: str) -> int:
            return sum(read_int(f"{d}/{counter}") or 0 for d in directories)

        draft.cpu_extra["thermal_throttle"] = ThermalThrottle(
            package_count=total(self._packages, "package_throttle_count"),
            package_ms=total(self._packages, "package_throttle_total_time_ms"),
            core_count=total(self._cores, "core_throttle_count"),
            core_ms=total(self._cores, "core_throttle_total_time_ms"),
        )
