"""Memory modules, through the privileged helper.

Without permissions only the total RAM is known, which the kernel counts.
Who made it, its type, speed and free slots are in the SMBIOS table, which
the kernel keeps for root for good reasons: the machine's serial numbers go
with them.

This provider never raises permissions on its own. It waits for the user to
ask from the interface, and until then leaves a note saying what is missing
and why: a diagnostic program that asks for a password at startup gets
uninstalled.
"""

from __future__ import annotations

import subprocess
from typing import Iterator, Optional

from .. import spd, sysroot, system_deps
from ..i18n import _
from ..model import DriverHint, MemoryArray, MemoryModule, Need, PrivilegedState
from ..privileged import smbios
from ..privileged.client import (
    HelperDenied,
    HelperError,
    HelperUnavailable,
    PrivilegedClient,
    already_root,
)
from ..system_env import system_environment
from .base import Draft, Provider, is_virtual_machine


def _module(raw: dict) -> MemoryModule:
    return MemoryModule(
        locator=raw.get("locator"),
        bank=raw.get("bank"),
        populated=bool(raw.get("populated")),
        size_bytes=raw.get("size_bytes") or 0,
        type=raw.get("type"),
        form_factor=raw.get("form_factor"),
        details=tuple(raw.get("details") or ()),
        speed_mts=raw.get("speed_mts"),
        configured_mts=raw.get("configured_mts"),
        manufacturer=raw.get("manufacturer"),
        part_number=raw.get("part_number"),
        rank=raw.get("rank"),
        data_width=raw.get("data_width"),
        total_width=raw.get("total_width"),
        voltage_min_mv=raw.get("voltage_min_mv"),
        voltage_max_mv=raw.get("voltage_max_mv"),
        voltage_configured_mv=raw.get("voltage_configured_mv"),
    )


class PrivilegedMemory(Provider):
    name = "smbios-memory"
    provides = "modules"
    static = True

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client or PrivilegedClient()
        self.requested = False
        self._error: Optional[str] = None

    def collect(self, draft: Draft) -> None:
        draft.driver_hints.extend(self._spd_hint())
        outdated = PrivilegedClient.necesita_reinstalar()
        draft.privileged = PrivilegedState(
            supported=self.client.supported(),
            connected=self.client.connected(),
            already_root=already_root(),
            message=self._error,
            outdated=outdated,
        )

        # QEMU's SMBIOS declares a «DIMM 0» of its own making: a virtual
        # machine has no modules to read, with permissions or without.
        if is_virtual_machine(draft):
            return

        if already_root():
            # No helper in between: the table can be read already.
            self._read_directly(draft)
            return

        if not self.requested:
            self._explain(draft)
            return

        try:
            self.client.connect()
            self._parse(draft, self.client.smbios_table())
            self._error = None
        except HelperDenied as exc:
            self.requested = False
            self._error = str(exc)
            draft.note("modules", Need.ROOT,
                       _("prov.mem.denied"), _("prov.mem.denied.hint"),
                       _("what.memory.modules"))
        except (HelperUnavailable, HelperError) as exc:
            self.requested = False
            self._error = str(exc)
            draft.note("modules", Need.ROOT,
                       _("prov.mem.helperfail").format(error=exc), "",
                       _("what.memory.modules"))

        draft.privileged = PrivilegedState(
            supported=self.client.supported(),
            connected=self.client.connected(),
            already_root=already_root(),
            message=self._error,
            outdated=outdated,
        )

    # -- SPD ----------------------------------------------------------------

    @classmethod
    def _spd_hint(cls) -> Iterator[DriverHint]:
        """SMBIOS says what speed the memory runs at; the SPD says what it
        could run at.

        SMBIOS shows what the firmware negotiated, which without XMP are the
        conservative JEDEC values. The maker's profiles are in each module's
        SPD chip, reached through the SMBus once its driver is loaded.
        """
        # Only chips the kernel registered on a memory bus: a touchpad's
        # buses can have something at 0x50 too.
        chips = spd.spd_chips()
        if not chips or any((chip / "eeprom").exists() for chip in chips):
            return                            # nothing to load, or already read
        # A chip with its driver bound gains nothing from loading one: why it
        # can't be read is spd.unreadable_cause's to say.
        candidates = [chip for chip in chips if not spd.has_driver(chip)]
        if not candidates:
            return

        # The chip's own driver when the kernel named it. Otherwise newest
        # first: one that doesn't apply finds nothing and does no harm.
        named = sorted({m for chip in candidates if (m := spd.driver_for(chip))})
        modinfo = system_deps.program_path("modinfo")
        for module in named or ("spd5118", "ee1004", "at24"):
            if not modinfo:
                return
            result = subprocess.run([modinfo, "-F", "filename", module],
                                    capture_output=True, text=True,
                                    env=system_environment())
            if result.returncode == 0 and result.stdout.strip():
                yield DriverHint(
                    module=module,
                    provides=_("prov.hint.spd.one" if len(candidates) == 1
                               else "prov.hint.spd").format(n=len(candidates)),
                    command=f"sudo modprobe {module}",
                    caution=_("prov.hint.spd.caution"),
                )
                return

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _explain(draft: Draft) -> None:
        draft.note(
            "modules", Need.ROOT,
            _("prov.mem.smbios"), _("prov.mem.smbios.hint"),
            _("what.memory.modules"),
        )

    def _read_directly(self, draft: Draft) -> None:
        try:
            with open(sysroot.path("/sys/firmware/dmi/tables/DMI"), "rb") as handle:
                self._parse(draft, handle.read())
        except OSError as exc:
            self._error = str(exc)
            draft.note("modules", Need.HARDWARE,
                       _("prov.mem.smbiosfail").format(error=exc), "")

    @staticmethod
    def _parse(draft: Draft, table: bytes) -> None:
        if not table:
            return
        structures = list(smbios.parse_table(table))
        draft.modules = [_module(raw) for raw in smbios.memory_devices(structures)]

        arrays = smbios.memory_arrays(structures)
        if arrays:
            first = arrays[0]
            draft.memory_array = MemoryArray(
                slots=first.get("slots"),
                max_capacity_bytes=first.get("max_capacity_bytes") or 0,
                error_correction=first.get("error_correction"),
            )
        # From the same table, each board slot's name.
        draft.pci_slot_names = smbios.system_slots(structures)
        draft.capabilities.add("smbios")
