"""The traffic the memory controller moves, read from its PMU.

A sensor, not a benchmark: nobody causes this traffic, it is what there is.
`membench` says what the memory *can* give and has to load the machine to
know; this says what it moves right now. It counts the whole controller,
with the processor's traffic inside, so `ia_requests` (what the cores ask
for) is read as well.

**Intel only.** AMD publishes no named counters: from Zen 4 the kernel
registers an `amd_umc_N` PMU without an `events/` group, so the event number
would be written by hand with no part to check it on; before Zen 3 nothing
is documented. Rather than make up a figure, it says this machine does not
publish it.

It needs the privileged helper: uncore counters need CAP_PERFMON, and
lowering `perf_event_paranoid` would open profiling of the whole machine to
any process.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from .. import sysroot
from ..i18n import _
from ..model import DeviceKind, MemoryTraffic, Need, Sensor, SensorKind
from ..privileged.client import HelperError, PmuUnsupported, PrivilegedClient
from ..privileged.protocol import PMU_IMC, PMU_IMC_EVENT, PMU_ROOT
from .base import Draft, Provider
from .counters import increase, window_s

_PMU_IMC = re.compile(PMU_IMC)
_PMU_IMC_EVENT = re.compile(PMU_IMC_EVENT)

# How each generation names the same thing. The first two rows are the
# traffic's direction; the third is that same traffic by origin.
READ_EVENTS = frozenset({"data_reads", "data_read", "cas_count_read"})
WRITE_EVENTS = frozenset({"data_writes", "data_write", "cas_count_write"})
CORE_EVENTS = frozenset({"ia_requests"})

# The unit the kernel publishes these counters in. Checked, not assumed: the
# scale alone does not say what it multiplies, and a mebibyte factor on
# something else would give a believable, false figure.
UNIT = "MiB"
BYTES_PER_UNIT = 1 << 20

# The device these sensors hang from: the same as RAM usage, with its key,
# so they are one and not two. Which goes first in the tree is decided by
# each sensor's kind, not by this name.
DEVICE = "sensor.mem"


def has_controller() -> bool:
    """Whether this machine publishes any memory controller PMU.

    Checked without privileges (listing the folder is allowed, opening the
    counter is not): it tells «needs permission» from «this machine does not
    have it», so a Ryzen is not asked for a password to show nothing.
    """
    try:
        return any(_PMU_IMC.match(name) for name in os.listdir(sysroot.ruta(PMU_ROOT)))
    except OSError:
        return False


def has_counters() -> bool:
    """Whether a memory controller PMU publishes an event the helper opens.

    Then the helper not opening it is an error to tell, not hardware that
    lacks it. Listing the events needs no privileges either.
    """
    try:
        root = sysroot.ruta(PMU_ROOT)
        names = os.listdir(root)
    except OSError:
        return False
    for name in names:
        if not _PMU_IMC.match(name):
            continue
        try:
            events = os.listdir(os.path.join(root, name, "events"))
        except OSError:
            continue
        if any(_PMU_IMC_EVENT.match(event) for event in events):
            return True
    return False


class ImcTraffic(Provider):
    """Bytes per second to and from RAM, by the uncore's PMU."""

    name = "imc"
    provides = "memory.traffic"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client
        self._previous: Optional[tuple[int, dict[str, dict[str, int]]]] = None
        self._silent = False          # this machine has none: stop asking
        # What the helper said when it could not open them, for the report.
        self._reason = ""

    def available(self) -> bool:
        if self._silent or not has_controller():
            return False
        return bool(self.client and self.client.connected())

    def unavailable_reason(self):
        if self.available():
            return None
        if has_controller() and not self._silent:
            return ("memory.traffic", Need.ROOT,
                    _("prov.imc.denied"), _("prov.imc.denied.hint"),
                    _("what.memory.traffic"))
        if has_counters():
            # The kernel publishes them and the helper could not open them:
            # not «this machine does not have it».
            return ("memory.traffic", Need.ERROR,
                    _("prov.imc.unopened"), _("prov.imc.unopened.hint"), "", self._reason)
        return ("memory.traffic", Need.HARDWARE,
                _("prov.imc.none"), _("prov.imc.none.hint"))

    def collect(self, draft: Draft) -> None:
        if not self.available():
            return
        try:
            reading = self.client.imc()       # type: ignore[union-attr]
        except PmuUnsupported as exc:
            # It has none. Stop asking; the notice becomes «this machine does
            # not publish it».
            self._silent = True
            self._reason = str(exc)
            self._previous = None
            return
        except HelperError:
            # A single failure loses nothing: the pipe may have broken and the
            # user may authorize again.
            return

        if reading.truncated:
            # Channels missing, so the sum would fall short. A low, believable
            # figure is worse than none.
            draft.note("memory.traffic", Need.ERROR,
                       _("prov.imc.truncated"), _("prov.imc.truncated.hint"))
            return

        previous, self._previous = self._previous, (reading.monotonic_ns, reading.counters)
        draft.capabilities.add("imc")
        if previous is None:
            return                            # the first one only sets the base

        previous_clock, previous_counters = previous
        seconds = window_s(previous_clock / 1e9, reading.monotonic_ns / 1e9, draft.interval_s)
        if seconds is None:
            return

        totals = {"read": 0, "write": 0, "cpu": 0}
        seen = {"read": False, "write": False, "cpu": False}
        for pmu, events in reading.counters.items():
            before_counts = previous_counters.get(pmu, {})
            for event, value in events.items():
                if event in READ_EVENTS:
                    field = "read"
                elif event in WRITE_EVENTS:
                    field = "write"
                elif event in CORE_EVENTS:
                    field = "cpu"
                else:
                    continue
                before = before_counts.get(event)
                grown = None if before is None else increase(before, value)
                if grown is None:
                    return          # a new or restarted counter: not this time
                if reading.units.get(pmu, {}).get(event) != UNIT:
                    continue        # unknown unit: not converted
                scale = reading.scales.get(pmu, {}).get(event)
                if not scale:
                    continue
                moved = grown * scale * BYTES_PER_UNIT
                totals[field] += int(moved / seconds)
                seen[field] = True

        if not (seen["read"] and seen["write"]):
            return
        draft.memory_traffic = MemoryTraffic(
            read_bytes_s=totals["read"],
            write_bytes_s=totals["write"],
            cpu_bytes_s=totals["cpu"] if seen["cpu"] else None,
        )
        draft.resolve("memory.traffic")

        # And to the sensor tree, where it adds the session's maximum: the
        # most this machine has moved. Unlike the core voltage (a P-state's
        # step), this is a continuous measure, so its history means something.
        # «From the processor» does not go up: next to read and write it would
        # read as a third direction of the traffic.
        for key, label, bytes_s, order in (
                ("read", "sensor.imc.read", totals["read"], 0),
                ("write", "sensor.imc.write", totals["write"], 1)):
            draft.sensors.append(Sensor(
                key=f"imc/{key}",
                chip="uncore_imc",
                device=_(DEVICE),
                device_key="memory",
                device_kind=DeviceKind.MEMORY,
                label=_(label),
                kind=SensorKind.BANDWIDTH,
                value=bytes_s / 1e6,
                order=order,
            ))
