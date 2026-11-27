"""The core voltage, read from the processor itself.

No sensor gives it reliably: `k10temp` reports no voltage, and a board's
Super I/O reports several **without labels**, in no promised order, so
picking one would be a guess.

What works the same everywhere is asking the processor, as root through the
helper:

- **AMD**: `0xC0010063` holds the active P-state and `0xC0010064 + n` its
  definition, with the VID in bits 21:14. The voltage is
  `1.55 − 0.00625 × VID`, unchanged since family 15h.
- **Intel**: `MSR_PERF_STATUS` holds the measured voltage in bits 47:32, as
  16-bit fixed point divided by 8192.

Both are read-only with no side effects, which is what earns them a place
on the helper's list.

**It is the voltage the processor requests, not what it gets.** What reaches
the pins is measured by the board's regulator, which hwmon reports when its
chip labels the channels; when both exist, the measured one wins.

**With boost it falls short.** The P-state table describes the base states;
above P0 the part's own controller raises clock and voltage while P0's VID
stays put. The figure isn't wrong, it's another point on the curve.
"""

from __future__ import annotations

from typing import Optional

from .. import rawcpuid
from ..i18n import _
from ..model import DriverHint, Need
from ..privileged.client import HelperError, HelperMissingModule, PrivilegedClient
from .base import Draft, Provider, is_virtual_machine, read_text

# The AMD families whose P-state registers this reads (Zen 1 to Zen 4, from
# AMD's PPRs for families 17h and 19h). Bulldozer and the others before Zen
# keep the voltage in other bits and steps; Zen 5 (1Ah) changed the layout
# again. Both are left out on purpose, and say so (`prov.msr.amdformat`).
# The sheet's Tjmax (`hwmon._sheet_maximum`) is the model's, not a
# register's, and does cover Zen 5.
ZEN_FAMILIES = (0x17, 0x19)


def is_zen(entry: dict) -> bool:
    return entry.get("vendor") == "AMD" and entry.get("disp_family") in ZEN_FAMILIES


# The running P-state (bits 2:0).
AMD_PSTATE_STATUS = 0xC0010063
# Each P-state's definition. There are eight; only the first three are used.
AMD_PSTATE_DEF = 0xC0010064
AMD_PSTATES = 3

# AMD's programmer's guide: CpuVid is PStateDef bits 21:14.
AMD_VID_SHIFT = 14
AMD_VID_MASK = 0xFF
AMD_VID_BASE = 1.55
AMD_VID_STEP = 0.00625

# Intel: IA32_PERF_STATUS. Bits 47:32 are 16-bit fixed point with three
# integer bits, so the divisor is 2^13, not 2^16.
INTEL_PERF_STATUS = 0x198
INTEL_VOLTAGE_SHIFT = 32
INTEL_VOLTAGE_MASK = 0xFFFF
INTEL_VOLTAGE_DIVISOR = 8192.0

# Outside this range it's garbage, not a core voltage: a missing register
# reads as zeros, and a misread one blows up.
MIN_V = 0.2
MAX_V = 2.0


# What loading msr would give, by what is missing.
MSR_GIVES = {
    "base": "prov.hint.msr.base",
    "voltage": "prov.hint.msr.voltage",
    "both": "prov.hint.msr.both",
}


def missing_msr_module(draft: Draft, *, base: bool = False, voltage: bool = False) -> None:
    """The msr module isn't loaded: one notice, with «Load now», naming what
    it would give. AmdPstateClocks (the base clock) runs before MsrVoltage in
    the collector, so an msr notice already there is the base clock's."""
    previous = next((h for h in draft.driver_hints if h.module == "msr"), None)
    if previous is not None:
        draft.driver_hints.remove(previous)
        base = True
    draft.driver_hints.append(DriverHint(
        module="msr",
        provides=_(MSR_GIVES["both" if base and voltage else "base" if base else "voltage"]),
        command="sudo modprobe msr",
        caution=_("prov.hint.msr.caution"),
    ))


def _is_x86() -> bool:
    return rawcpuid.machine() in ("x86_64", "AMD64", "i686", "i386")


# Family 6 before Sandy Bridge (model 0x2A) that come after it in number:
# Westmere-EP, Nehalem-EX and Westmere-EX.
_OLDER_SERVERS = frozenset({0x2C, 0x2E, 0x2F})


def intel_without_voltage() -> bool:
    """An Intel whose MSR_PERF_STATUS carries no voltage.

    Intel documents bits 47:32 from Sandy Bridge on. A Core 2, a Nehalem or
    a Pentium 4 leaves them at zero or holds something else there, so no
    permission brings the figure.
    """
    fields: dict[str, str] = {}
    for line in (read_text("/proc/cpuinfo") or "").splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            if fields:
                break
            continue
        fields.setdefault(key.strip(), value.strip())
    if fields.get("vendor_id") != "GenuineIntel":
        return False
    try:
        family, model = int(fields["cpu family"]), int(fields["model"])
    except (KeyError, ValueError):
        return False
    return family == 0xF or (family == 6 and (model < 0x2A or model in _OLDER_SERVERS))


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
        """Without the helper there is no register to read, and that is fixable.

        `ROOT` on purpose: it carries the button that grants permissions,
        where `DRIVER` would read as «your machine doesn't have it».
        """
        if self.available():
            return None
        if not _is_x86():
            return ("cpu.voltage_v", Need.PLATFORM,
                    _("prov.msr.nox86"), _("prov.msr.nox86.hint"))
        if intel_without_voltage():
            return ("cpu.voltage_v", Need.HARDWARE,
                    _("prov.msr.oldintel"), _("prov.msr.oldintel.hint"))
        return ("cpu.voltage_v", Need.ROOT,
                _("prov.msr.novolt"), "", _("what.cpu.voltage"))

    def collect(self, draft: Draft) -> None:
        # KVM answers the voltage register with a constant: a virtual machine
        # has no voltage to read, with permissions or without.
        if is_virtual_machine(draft):
            return
        # A labelled hwmon sensor wins: it measures what reaches the
        # processor, while this only says what it requests.
        if any(entry.get("voltage_v") is not None
               for entry in draft.types.values()):
            return

        if intel_without_voltage():
            draft.note("cpu.voltage_v", Need.HARDWARE,
                       _("prov.msr.oldintel"), _("prov.msr.oldintel.hint"))
            return
        vendors = {(entry.get("vendor") or "").lower()
                  for entry in draft.types.values()}
        is_amd = any("amd" in m for m in vendors)
        if is_amd and not any(is_zen(entry) for entry in draft.types.values()):
            # Read with Zen's layout, an FX-8150 gave 1.550 V: the VID's bits
            # were others, and zero is the top of the scale.
            draft.note("cpu.voltage_v", Need.DATABASE, _("prov.msr.amdformat"),
                       key="prov.msr.amdformat")
            return
        registers = ([AMD_PSTATE_STATUS]
                     + [AMD_PSTATE_DEF + n for n in range(AMD_PSTATES)]
                     if is_amd else [INTEL_PERF_STATUS])
        try:
            values = self.client.read_msr(0, registers)
        except HelperMissingModule:
            missing_msr_module(draft, voltage=True)
            return
        except HelperError as exc:
            draft.note("cpu.voltage_v", Need.ERROR, _("prov.msr.helperfail"),
                       detail=str(exc), key="prov.msr.helperfail")
            return

        voltage = _amd_voltage(values) if is_amd else _intel_voltage(values)
        if voltage is None or not MIN_V <= voltage <= MAX_V:
            # Read, but not a voltage: said, with what came, for the report.
            draft.note("cpu.voltage_v", Need.HARDWARE, _("prov.msr.novalue"),
                       detail=f"{values!r}", key="prov.msr.novalue")
            return

        for entry in draft.types.values():
            entry["voltage_v"] = round(voltage, 3)
        # The status bar lists the sources that produced something.
        draft.capabilities.add("msr")
