"""The processor's identity on ARM, which has no CPUID.

The kernel publishes what MIDR_EL1 says: who designed the core, which core
it is and its revision. That gives the name («ARM Cortex-A55 r0p0»), the
aarch64 stand-in for a brand string, which ARM silicon doesn't carry.

The rest has no equivalent and isn't faked: no x86-style family or model,
no brand string, no socket. There are instruction-set flags («Features»),
and usually a device tree naming the device.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
from typing import Optional

from .. import db, rawcpuid, sysroot
from ..i18n import _
from .base import Draft, Provider, read_text

CPUINFO = "/proc/cpuinfo"
DEVICE_TREE = "/sys/firmware/devicetree/base"

def is_arm() -> bool:
    return rawcpuid.machine().lower().startswith(("aarch64", "arm"))


def _cpuinfo() -> list[dict[str, str]]:
    """/proc/cpuinfo's blocks, one per logical CPU, in order.

    On aarch64 each carries the four MIDR fields. On big.LITTLE they differ,
    which is how each CPU's core is told apart.
    """
    try:
        raw = pathlib.Path(sysroot.path(CPUINFO)).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    blocks, current = [], {}
    for line in raw.splitlines():
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        key, _sep, value = line.partition(":")
        current[key.strip()] = value.strip()
    if current:
        blocks.append(current)
    return blocks


def _integer(block: dict[str, str], key: str) -> Optional[int]:
    raw = block.get(key)
    if not raw:
        return None
    try:
        return int(raw, 16) if raw.startswith("0x") else int(raw)
    except ValueError:
        return None


def midr_by_cpu() -> dict[int, tuple[Optional[int], Optional[int]]]:
    """Each logical CPU's (implementer, part), which tells big cores from
    little ones without Intel's hybrid PMUs."""
    out: dict[int, tuple[Optional[int], Optional[int]]] = {}
    for block in _cpuinfo():
        index = _integer(block, "processor")
        if index is None:
            continue
        out[index] = (_integer(block, "CPU implementer"),
                          _integer(block, "CPU part"))
    return out


def _from_tree(name: str) -> Optional[str]:
    """A device tree string, without its trailing zero."""
    raw = read_text(f"{DEVICE_TREE}/{name}")
    if not raw:
        return None
    # C strings; «compatible» chains several, separated by NULs.
    clean = raw.split("\x00")[0].strip()
    return clean or None


def machine_model() -> Optional[str]:
    """Which device this is: «Raspberry Pi 4 Model B Rev 1.4».

    On x86 the board's DMI says it. ARM machines rarely have SMBIOS but
    nearly always a device tree, which plays the same role.
    """
    return _from_tree("model")


class ArmIdentity(Provider):
    """Fills each core type's identity from /proc/cpuinfo."""

    name = "arm-cpuinfo"
    provides = "cpu.identity"
    static = True

    def available(self) -> bool:
        return is_arm() and os.path.exists(sysroot.path(CPUINFO))

    def unavailable_reason(self):
        return None          # on x86 nothing is missing: CPUID covers it

    def collect(self, draft: Draft) -> None:
        blocks = _cpuinfo()
        if not blocks:
            return
        draft.capabilities.add("arm-cpuinfo")
        # CPUID already noted it doesn't exist here; the identity does, read
        # another way.
        draft.resolve("cpu.identity")

        by_cpu = midr_by_cpu()
        for key, entry in draft.types.items():
            cpus = entry.get("cpus") or [0]
            implementer, part = by_cpu.get(cpus[0], (None, None))
            block = next((b for b in blocks
                           if _integer(b, "processor") == cpus[0]), blocks[0])
            self._fill(entry, block, implementer, part)

        # The device tree names the device, not the processor, so it goes
        # where the board's name would.
        model = machine_model()
        if model and not draft.board.name:
            draft.board = dataclasses.replace(
                draft.board, name=model,
                vendor=draft.board.vendor or _from_tree("compatible"))

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _fill(entry: dict, block: dict[str, str],
                  implementer: Optional[int], part: Optional[int]) -> None:
        # The generated database carries libcpuid's MIDR table, with each
        # core's codename and process node.
        identity = (db.identify_arm(implementer, part)
                     if None not in (implementer, part) else {})
        vendor = identity.get("vendor")
        core = identity.get("part_name")
        variant = _integer(block, "CPU variant")
        revision = _integer(block, "CPU revision")

        # rXpY is how ARM names silicon revisions, and how its errata refer
        # to them.
        stepping = (f"r{variant}p{revision}"
                if variant is not None and revision is not None else None)

        entry.update(
            vendor=vendor,
            vendor_id=f"0x{implementer:02x}" if implementer is not None else None,
            brand=" ".join(p for p in (vendor, core, stepping) if p) or None,
            codename=identity.get("codename"),
            technology=identity.get("technology"),
            architecture=rawcpuid.machine(),
            # ARM's counterpart of the CPUID signature: the two numbers that
            # identify the silicon, without x86's family and model, which
            # mean something else here.
            signature=(implementer << 24 | part << 4) if None not in (implementer, part) else None,
            features=_flags(block),
        )
        if core is None and part is not None:
            entry["brand"] = " ".join(
                p for p in (vendor,
                            _("cpu.arm.core").format(id=f"0x{part:03x}"),
                            stepping) if p)


def _flags(block: dict[str, str]) -> tuple[str, ...]:
    raw = block.get("Features") or block.get("flags") or ""
    # As the kernel names them; display names are render's job.
    return tuple(f for f in re.split(r"\s+", raw) if f)
