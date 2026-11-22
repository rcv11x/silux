"""Each memory module's SPD, matched to the SMBIOS modules.

Two views of the same modules: SMBIOS says where each one sits and the
speed the firmware set, the SPD says what it is rated for. Together they
give «runs at 2667 of its 3200».

No permissions needed: on most distributions the SPD is readable by anyone
once the kernel loads its driver.
"""

from __future__ import annotations

import dataclasses
import errno

from .. import render
from .. import spd as spd_module
from ..i18n import _
from ..model import Need
from .base import Draft, Provider


class SpdModules(Provider):
    name = "spd"
    provides = "spd"
    static = True

    def available(self) -> bool:
        return spd_module.available()

    def unavailable_reason(self):
        if self.available():
            return None
        # The bus may be missing, reserved by the firmware, or just lack its
        # driver; each has a different fix, and «load ee1004» only helps the
        # last.
        cause = spd_module.unreadable_cause()
        reason, fix = spd_module.diagnosis(cause)
        # Without the bus, or with it reserved, it's down to the board. With
        # the bus and no driver, loading one fixes it.
        need = Need.DRIVER if cause == spd_module.CAUSE_NO_DRIVER else Need.HARDWARE
        return ("spd", need, reason, fix)

    def collect(self, draft: Draft) -> None:
        failures: list = []
        readings = spd_module.read_all(failures)
        partial = {r.address for r in readings if r.partial}
        if partial:
            # Page 0 read and the rest didn't: the page switch is a write,
            # and the machine blocks writes to the SPD.
            draft.note("spd", Need.HARDWARE, _("prov.spd.partial"),
                       _("prov.spd.partial.hint"),
                       detail="; ".join(f"{device}: {errno.errorcode.get(exc.errno, exc.errno)}"
                                        for device, exc in failures if device in partial),
                       key="prov.spd.partial")
            failures = [(device, exc) for device, exc in failures if device not in partial]
        if failures:
            # The chip is there and reading it failed. On DDR5 that happens
            # when the machine blocks SPD writes (the driver needs them to
            # switch pages) or the driver didn't survive a suspend; which one
            # can't be told from here, so the errno goes to the report.
            draft.note("spd", Need.HARDWARE, _("prov.spd.readfailed"),
                       _("prov.spd.readfailed.hint"),
                       # The error's name and not its text, which is in
                       # the system's language and not the report's.
                       detail="; ".join(f"{device}: {errno.errorcode.get(exc.errno, exc.errno)}"
                                        for device, exc in failures),
                       key="prov.spd.readfailed")
        if not readings:
            return

        draft.capabilities.add("spd")
        draft.spd = readings
        self._merge(draft, readings)

        if any(not r.decoded for r in readings):
            kinds = {r.dram_type for r in readings if not r.decoded and r.dram_type}
            draft.note(
                "spd", Need.PLATFORM,
                _("prov.spd.unsupported").format(
                    tipos=render.enumeration(sorted(kinds))
                          or _("prov.spd.thesemodules")),
                _("prov.spd.unsupported.hint"),
            )

    @staticmethod
    def _merge(draft: Draft, readings: list) -> None:
        """Attach each SPD reading to its SMBIOS module.

        Nothing maps a chip's bus address to the firmware's slot name, so
        match by part number where both have one, then in order, like every
        other tool.
        """
        populated = [i for i, m in enumerate(draft.modules) if m.populated]
        if not populated:
            return

        pending = list(readings)
        matches: dict[int, object] = {}
        # Part numbers first, for every module: matching one at a time, a
        # soldered module could take the reading that belongs to a slot.
        for index in populated:
            part = (draft.modules[index].part_number or "").strip()
            match = next((r for r in pending
                          if part and r.part_number and r.part_number.strip() == part), None)
            if match is not None:
                pending.remove(match)
                matches[index] = match
        # Then the rest in order, slots before soldered memory, which has no
        # SPD chip of its own on the bus.
        rest = sorted((i for i in populated if i not in matches),
                      key=lambda i: not draft.modules[i].in_a_slot)
        for index in rest:
            if not pending:
                break
            matches[index] = pending.pop(0)
        for index, match in matches.items():
            module = draft.modules[index]
            # The chip is the module's own word on its type: some firmware of
            # the DDR2 years declares it DDR (0x12 for 0x13).
            draft.modules[index] = dataclasses.replace(
                module, spd=match, type=match.dram_type or module.type)
