"""Processor usage from /proc/stat.

Usage is a rate: the file only has accumulated jiffies, so the previous
reading is kept and the difference divided.
"""

from __future__ import annotations

import time
from typing import Optional

from .. import sysroot
from ..i18n import _
from ..model import Need
from .base import Draft, Provider
from .counters import increase, window_s

# user nice system idle iowait irq softirq steal …
_IDLE_FIELDS = (3, 4)          # idle, iowait


class CpuUsage(Provider):
    name = "procfs-usage"
    provides = "cpu.usage_percent"

    def __init__(self) -> None:
        self._previous: dict[str, tuple[int, int]] = {}
        self._previous_at = 0.0

    def available(self) -> bool:
        try:
            with open(sysroot.path("/proc/stat")):
                return True
        except OSError:
            return False

    def unavailable_reason(self):
        if self.available():
            return None
        return ("cpu.usage_percent", Need.PLATFORM,
                _("prov.procfs.nostat"), "", "",
                _("prov.missing.detail").format(ruta="/proc/stat"))

    def collect(self, draft: Draft) -> None:
        current = self._read()
        if not current:
            return
        now = time.monotonic()
        if window_s(self._previous_at, now, draft.interval_s) is None:
            # A window this short holds only two or three jiffies, which would
            # make usage 0, 50 or 100 %.
            self._previous, self._previous_at = current, now
            return

        total = self._delta("cpu", current)
        if total is not None:
            draft.cpu_extra["usage_percent"] = total

        for index, cpu in draft.logical.items():
            value = self._delta(f"cpu{index}", current)
            if value is not None:
                cpu["usage_percent"] = value

        if load := self._load_average():
            draft.cpu_extra["load_average"] = load

        self._previous, self._previous_at = current, now

    @staticmethod
    def _load_average() -> tuple[float, ...]:
        """The 1, 5 and 15 minute load averages.

        Usage says how busy the CPU is now; load says how many processes were
        waiting on average. With 12 threads, a load of 12 is full saturation.
        """
        try:
            with open(sysroot.path("/proc/loadavg"), encoding="ascii") as fh:
                return tuple(float(v) for v in fh.read().split()[:3])
        except (OSError, ValueError):
            return ()

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _read() -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        try:
            with open(sysroot.path("/proc/stat"), encoding="ascii") as fh:
                for line in fh:
                    if not line.startswith("cpu"):
                        break
                    parts = line.split()
                    values = [int(v) for v in parts[1:]]
                    idle = sum(values[i] for i in _IDLE_FIELDS if i < len(values))
                    out[parts[0]] = (sum(values), idle)
        except (OSError, ValueError):
            return {}
        return out

    def _delta(self, key: str, current: dict[str, tuple[int, int]]) -> Optional[float]:
        before = self._previous.get(key)
        if before is None or key not in current:
            return None
        total_delta = increase(before[0], current[key][0])
        idle_delta = increase(before[1], current[key][1])
        if not total_delta or idle_delta is None:
            return None
        return round(100.0 * max(0.0, total_delta - idle_delta) / total_delta, 1)
