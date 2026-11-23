"""An AMD Zen's P-states, read from the processor: its base clock and, with
no frequency driver, the frequency it runs at.

Families 17h and 19h define each P-state in MSR `0xC0010064 + n`, with
`CpuFid` in bits 7:0 and `CpuDfsId` in bits 13:8; the frequency is
200 MHz × CpuFid / CpuDfsId (AMD's PPR for those families, MSRC001_0064).
`0xC0010063` holds the current P-state, and P0 is the base clock.

These are the registers `msr_voltage` reads through the helper's fixed
list, so they need permissions; without them the base clock's note says so,
with its padlock.

Family 1Ah (Zen 5) encodes the frequency differently and isn't read until
one has been seen.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from ..i18n import _
from ..model import Clocks, Need
from ..privileged.client import HelperError, HelperMissingModule, PrivilegedClient
from .base import Draft, Provider, is_virtual_machine
from .msr_voltage import (
    AMD_PSTATE_DEF,
    AMD_PSTATE_STATUS,
    AMD_PSTATES,
    is_zen,
    missing_msr_module,
)

PSTATE_ENABLED = 1 << 63
FID_MASK = 0xFF
DFS_SHIFT = 8
DFS_MASK = 0x3F
STEP_HZ = 200_000_000
# Anything outside this range is a misread register.
MIN_HZ = 400_000_000
MAX_HZ = 7_000_000_000


def pstate_hz(definition: Optional[int]) -> Optional[int]:
    """The frequency a Zen P-state definition encodes, or None."""
    if not definition or not definition & PSTATE_ENABLED:
        return None
    fid = definition & FID_MASK
    dfs = (definition >> DFS_SHIFT) & DFS_MASK
    if not dfs:
        return None
    hz = STEP_HZ * fid // dfs
    return hz if MIN_HZ <= hz <= MAX_HZ else None


class AmdPstateClocks(Provider):
    """The base clock from P0 and, without cpufreq, the current P-state's."""

    name = "msr-pstate"
    provides = "cpu.clocks.base_hz"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client

    def available(self) -> bool:
        return bool(self.client and self.client.connected())

    def collect(self, draft: Draft) -> None:
        if is_virtual_machine(draft):
            return
        zen = [entry for entry in draft.types.values() if is_zen(entry)]
        clocks = [entry.get("clocks") or Clocks() for entry in zen]
        needs_base = any(c.base_hz is None for c in clocks)
        no_driver = any(c.current_from != "cpufreq" for c in clocks)
        if not zen or not (needs_base or no_driver):
            return
        registers = [AMD_PSTATE_STATUS] + [AMD_PSTATE_DEF + n for n in range(AMD_PSTATES)]
        try:
            values = self.client.read_msr(0, registers)
        except HelperMissingModule:
            # The module's notice says it; a padlock would promise something
            # permissions can't give.
            if needs_base:
                draft.resolve("cpu.clocks.base_hz")
                missing_msr_module(draft, base=True)
            return
        except HelperError as exc:
            if needs_base:
                draft.resolve("cpu.clocks.base_hz")
                draft.note("cpu.clocks.base_hz", Need.ERROR, _("prov.msr.helperfail"),
                           detail=str(exc), key="prov.msr.helperfail")
            return

        base = pstate_hz(values.get(AMD_PSTATE_DEF))
        state = values.get(AMD_PSTATE_STATUS)
        running = (pstate_hz(values.get(AMD_PSTATE_DEF + (state & 0x7)))
                   if state is not None and (state & 0x7) < AMD_PSTATES else None)
        for entry, current in zip(zen, clocks):
            changes = {}
            if current.base_hz is None and base:
                changes["base_hz"] = base
            # Without a driver nothing changes the P-state, so it is the
            # frequency. Not with turbo: the part goes past P0 on its own, and
            # /proc/cpuinfo measures that.
            if current.current_from != "cpufreq" and running and current.turbo_supported is False:
                changes.update(current_hz=running, current_from="msr")
            if changes:
                entry["clocks"] = dataclasses.replace(current, **changes)
        if base:
            draft.resolve("cpu.clocks.base_hz")
            draft.capabilities.add("msr")
