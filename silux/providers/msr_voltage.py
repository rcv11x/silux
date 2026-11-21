"""The core voltage, asked to the processor itself.

No sensor gives it reliably: `k10temp` publishes no voltage, and a board's
Super I/O chip publishes several **without labels**, so picking one would be
guessing, and the driver does not promise their order.

What is the same on every machine is asking the processor, as root through
the helper:

- **AMD**: register `0xC0010063` says which P-state is active and
  `0xC0010064 + n` holds its definition, with the VID in bits 21:14. The
  voltage is `1.55 − 0.00625 × VID`, the same since family 15h.
- **Intel**: `MSR_PERF_STATUS` holds the measured voltage in bits 47:32, in
  16-bit fixed point: divided by 8192.

Both are read-only and have no side effects when read, the condition to be
on the helper's list.

**It is the voltage the processor asks for, not the one it gets.** What
reaches the pins is measured by the board's regulator, which hwmon gives when
its chip labels its channels; when both are there, the measured one wins.

**And with boost it falls short.** The P-state table describes the base
states; above P0 the part's own controller raises clock and voltage, and P0's
VID keeps its value. The figure is not false, it is another point of the
curve.
"""

from __future__ import annotations

from typing import Optional

from .. import rawcpuid
from ..i18n import _
from ..model import Need
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider, is_virtual_machine

# Which P-state is running now (bits 2:0).
AMD_PSTATE_STATUS = 0xC0010063
# Each one's definition. There are eight, but only the first three are used.
AMD_PSTATE_DEF = 0xC0010064
AMD_PSTATES = 3

# From AMD's programmer's guide: in PStateDef, CpuVid is bits 21:14.
AMD_VID_SHIFT = 14
AMD_VID_MASK = 0xFF
AMD_VID_BASE = 1.55
AMD_VID_STEP = 0.00625

# Intel: IA32_PERF_STATUS. The voltage is in bits 47:32 in 16-bit fixed point,
# so the divisor is 2^13 and not 2^16: the three high bits are the integer part.
INTEL_PERF_STATUS = 0x198
INTEL_VOLTAGE_SHIFT = 32
INTEL_VOLTAGE_MASK = 0xFFFF
INTEL_VOLTAGE_DIVISOR = 8192.0

# Below or above this it is not a core voltage but garbage: a register that
# does not exist reads as zeros, and a misread one blows up.
MIN_V = 0.2
MAX_V = 2.0


def _is_x86() -> bool:
    return rawcpuid.maquina() in ("x86_64", "AMD64", "i686", "i386")


def _amd_voltage(values: dict) -> Optional[float]:
    """The VID of the active P-state."""
    state = values.get(AMD_PSTATE_STATUS)
    if state is None:
        return None
    definition = values.get(AMD_PSTATE_DEF + (state & 0x7))
    if not definition:
        return None
    vid = (definition >> AMD_VID_SHIFT) & AMD_VID_MASK
    return AMD_VID_BASE - AMD_VID_STEP * vid


def _intel_voltage(values: dict) -> Optional[float]:
    raw = values.get(INTEL_PERF_STATUS)
    if not raw:
        return None
    field = (raw >> INTEL_VOLTAGE_SHIFT) & INTEL_VOLTAGE_MASK
    return field / INTEL_VOLTAGE_DIVISOR if field else None


class MsrVoltage(Provider):
    """The core voltage by MSR, when no sensor gives it."""

    name = "msr-voltage"
    provides = "cpu.voltage_v"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client

    def available(self) -> bool:
        return bool(self.client and self.client.connected())

    def unavailable_reason(self):
        """Without the helper there is no register to read, and that has a fix.

        `ROOT` on purpose: it carries the button that gives permissions, where
        `DRIVER` reads as «your machine does not have it».
        """
        if self.available():
            return None
        if not _is_x86():
            return ("cpu.voltage_v", Need.PLATFORM,
                    _("prov.msr.nox86"), _("prov.msr.nox86.hint"))
        return ("cpu.voltage_v", Need.ROOT,
                _("prov.msr.novolt"), _("prov.msr.novolt.hint"), _("what.cpu.voltage"))

    def collect(self, draft: Draft) -> None:
        # KVM answers the voltage register with a constant: inside a virtual
        # machine there is no voltage to read, with permissions or without.
        if is_virtual_machine(draft):
            return
        # A labelled hwmon sensor wins: it measures what reaches the
        # processor, and this only says what it asks for.
        if any(entry.get("voltage_v") is not None
               for entry in draft.types.values()):
            return

        vendors = {(entry.get("vendor") or "").lower()
                  for entry in draft.types.values()}
        is_amd = any("amd" in m for m in vendors)
        registers = ([AMD_PSTATE_STATUS]
                     + [AMD_PSTATE_DEF + n for n in range(AMD_PSTATES)]
                     if is_amd else [INTEL_PERF_STATUS])
        try:
            values = self.client.read_msr(0, registers)
        except HelperError:
            # Most often the «msr» module is not loaded, and one command
            # fixes that: say which.
            draft.note("cpu.voltage_v", Need.DRIVER,
                       _("prov.msr.nomodule"), _("prov.msr.nomodule.hint"))
            return

        voltage = _amd_voltage(values) if is_amd else _intel_voltage(values)
        if voltage is None or not MIN_V <= voltage <= MAX_V:
            return

        for entry in draft.types.values():
            entry["voltage_v"] = round(voltage, 3)
        # The status bar lists the sources that gave something.
        draft.capabilities.add("msr")
