"""Time in each of the processor's idle states (C-states).

The kernel counts, per thread and per state, the microseconds spent there
since boot (`cpuidle/stateN/time`). Two readings give the share of the last
interval each thread spent in each state: whether the machine really rests
when it does nothing. No permissions needed; the first reading only sets the
base.
"""

from __future__ import annotations

import glob
import os
import re
import time
from typing import Optional

from .. import sysroot
from ..model import IdleState
from .base import Draft, Provider, read_int, read_text
from .counters import increase, window_s

CPUS = "/sys/devices/system/cpu"


class CpuIdle(Provider):
    name = "cpuidle"
    provides = "cpu.idle_states"

    def __init__(self) -> None:
        # Names do not change: read once. cpu → [(folder, name, description)]
        self._states: Optional[dict[int, list[tuple[str, str, Optional[str]]]]] = None
        self._previous: Optional[tuple[float, dict[tuple[int, str], int]]] = None

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(f"{CPUS}/cpu0/cpuidle"))

    def _enumerate(self) -> dict:
        states: dict[int, list] = {}
        for path in glob.glob(os.path.join(sysroot.ruta(CPUS), "cpu[0-9]*", "cpuidle", "state[0-9]*")):
            base = sysroot.fuera(path)
            match = re.search(r"/cpu(\d+)/cpuidle/", base)
            if not match:
                continue
            cpu = int(match.group(1))
            name = read_text(f"{base}/name")
            if name:
                states.setdefault(cpu, []).append((base, name, read_text(f"{base}/desc")))
        for entries in states.values():
            entries.sort(key=lambda e: int(e[0].rsplit("state", 1)[-1]))
        return states

    def collect(self, draft: Draft) -> None:
        # A dump holds one reading of each counter: subtracted from itself it
        # would read «0 % in every state», which looks like a value and is not.
        if sysroot.activo():
            return
        if self._states is None:
            self._states = self._enumerate()
        now = time.monotonic()
        reading: dict[tuple[int, str], int] = {}
        for cpu, states in self._states.items():
            for base, name, _description in states:
                micros = read_int(f"{base}/time")
                if micros is not None:
                    reading[(cpu, name)] = micros
        previous, self._previous = self._previous, (now, reading)
        if previous is None or not reading:
            return
        seconds = window_s(previous[0], now, draft.interval_s)
        if seconds is None:
            return
        draft.cpu_extra["idle_states"] = self.residency(
            previous[1], reading, seconds, self._states)

    @staticmethod
    def residency(before: dict, after: dict, seconds: float, states: dict) -> list[IdleState]:
        """The share of the interval in each state: mean, minimum and maximum
        over the threads, in the kernel's order, from lightest to deepest."""
        if seconds <= 0:
            return []
        order: list[tuple[str, Optional[str]]] = []
        for entries in states.values():
            for _base, name, description in entries:
                if name not in [n for n, _d in order]:
                    order.append((name, description))
        out = []
        for name, description in order:
            shares = []
            for (cpu, state), micros in after.items():
                if state != name or (cpu, state) not in before:
                    continue
                spent = increase(before[(cpu, state)], micros)
                # A counter going back (a thread taken offline and back) gives
                # no share: that thread does not count this time.
                if spent is None:
                    continue
                shares.append(min(100.0, spent / (seconds * 1e6) * 100.0))
            if shares:
                out.append(IdleState(
                    name=name, description=description,
                    percent=round(sum(shares) / len(shares), 1),
                    low=round(min(shares), 1), high=round(max(shares), 1)))
        return out
