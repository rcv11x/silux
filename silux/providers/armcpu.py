"""The processor's identity on ARM, where there is no CPUID.

What an instruction answers on x86, the kernel publishes here already read
from MIDR_EL1: who made the core, which one it is and its revision. That
gives the name («ARM Cortex-A55 r0p0»), which is what an aarch64 has instead
of a brand string: ARM silicon carries none.

The rest has no equivalent and is not faked: no x86-style family or model,
no brand string, no socket. There are instruction-set flags («Features»),
and usually a device tree that says which device it is.
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
    return rawcpuid.maquina().lower().startswith(("aarch64", "arm"))


def _cpuinfo() -> list[dict[str, str]]:
    """The blocks of /proc/cpuinfo, one per logical CPU, in order.

    On aarch64 each block carries the four MIDR fields. On big.LITTLE they
    differ, and that is the point: the blocks say which core each CPU is.
    """
    try:
        raw = pathlib.Path(sysroot.ruta(CPUINFO)).read_text(encoding="utf-8", errors="replace")
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
    """Each logical CPU's (implementer, part).

    It tells big cores from little ones without Intel's PMUs, which ARM does
    not have.
    """
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
    # C strings, and «compatible» chains several separated by zeros.
    clean = raw.split("\x00")[0].strip()
    return clean or None


def machine_model() -> Optional[str]:
    """Which device it is: «Raspberry Pi 4 Model B Rev 1.4».

    On x86 the board's DMI says it. An ARM machine seldom has SMBIOS, but
    almost always a device tree, which plays the same part.
    """
    return _from_tree("model")


class ArmIdentity(Provider):
    """Fills each core type's identity from /proc/cpuinfo."""

    name = "arm-cpuinfo"
    provides = "cpu.identity"
    static = True

    def available(self) -> bool:
        return is_arm() and os.path.exists(sysroot.ruta(CPUINFO))

    def unavailable_reason(self):
        return None          # on x86 nothing is missing: CPUID covers it

    def collect(self, draft: Draft) -> None:
        blocks = _cpuinfo()
        if not blocks:
            return
        draft.capabilities.add("arm-cpuinfo")
        # CPUID already said it does not exist here. The identity does, read
        # elsewhere.
        draft.resolve("cpu.identity")

        by_cpu = midr_by_cpu()
        for key, entry in draft.types.items():
            cpus = entry.get("cpus") or [0]
            implementer, part = by_cpu.get(cpus[0], (None, None))
            block = next((b for b in blocks
                           if _integer(b, "processor") == cpus[0]), blocks[0])
            self._fill(entry, block, implementer, part)

        # On ARM the device tree does what DMI does on x86: say which device
        # this is. Not the processor's, so it goes where the board's would.
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

        # rXpY is how ARM names its silicon revisions, and how its errata do.
        stepping = (f"r{variant}p{revision}"
                if variant is not None and revision is not None else None)

        entry.update(
            vendor=vendor,
            vendor_id=f"0x{implementer:02x}" if implementer is not None else None,
            brand=" ".join(p for p in (vendor, core, stepping) if p) or None,
            codename=identity.get("codename"),
            technology=identity.get("technology"),
            architecture=rawcpuid.maquina(),
            # ARM's equivalent of the CPUID signature: the two numbers that
            # identify the silicon, without a family and model that mean
            # something else here.
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
    # As the kernel names them. Pretty names are render's job.
    return tuple(f for f in re.split(r"\s+", raw) if f)
