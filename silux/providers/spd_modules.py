"""The SPD of each memory module, matched to SMBIOS's modules.

Two views of the same modules: SMBIOS says where each one is and at what
speed the firmware set it; the SPD says what it can do. Together they say
«runs at 2667 of the 3200 it supports».

No permissions needed: on most distributions the SPD chip is readable by
anyone once the kernel loads its driver.
"""

from __future__ import annotations

import dataclasses

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
        # The bus may be missing, reserved by the firmware, or only lack its
        # driver: each has its own fix, and «load ee1004» helps none of the
        # first two.
        cause = spd_module.unreadable_cause()
        reason, fix = spd_module.diagnostico(cause)
        # Without the bus, or with it reserved, it is the board's. With the bus
        # and no driver, loading one reads it.
        need = Need.DRIVER if cause == spd_module.CAUSE_NO_DRIVER else Need.HARDWARE
        return ("spd", need, reason, fix)

    def collect(self, draft: Draft) -> None:
        readings = spd_module.read_all()
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

        Nothing maps a chip's bus address to the firmware's slot name: match
        by part number where both have one, then in order, as every tool does.
        """
        populated = [i for i, m in enumerate(draft.modules) if m.populated]
        if not populated:
            return

        pending = list(readings)
        matches: dict[int, object] = {}
        # Every module by part number first: matched one by one, soldered
        # memory could take the slot's only reading before the slot did.
        for index in populated:
            part = (draft.modules[index].part_number or "").strip()
            match = next((r for r in pending
                          if part and r.part_number and r.part_number.strip() == part), None)
            if match is not None:
                pending.remove(match)
                matches[index] = match
        # Then the rest in order, a slot before memory soldered on the board:
        # that has no SPD chip of its own on the bus.
        rest = sorted((i for i in populated if i not in matches),
                      key=lambda i: not draft.modules[i].in_a_slot)
        for index in rest:
            if not pending:
                break
            matches[index] = pending.pop(0)
        for index, match in matches.items():
            draft.modules[index] = dataclasses.replace(draft.modules[index], spd=match)
