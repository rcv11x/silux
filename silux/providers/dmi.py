"""Motherboard, firmware and chipset.

Three sources answering one question (what this is built on):

* `/sys/class/dmi/id` gives the board, the firmware and the system, as the
  SMBIOS table declares them. The serial numbers and UUID sit next to them,
  readable by root only; this provider does not look at them.
* `/sys/firmware/efi` and `/sys/class/tpm` say how the machine boots.
* The PCI bus identifies the chipset: the LPC/eSPI bridge on bus 0 *is* the
  chipset, and `pci.ids` names it.

Makers leave SMBIOS fields with fillers like «Default string». They are
dropped: showing them as data is worse than an empty field.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Optional

from .. import pciids, sysroot
from ..i18n import _
from ..model import Board, Need, clean_dmi
from .base import Draft, Provider, is_virtual_machine, read_text

SYS_DMI = "/sys/class/dmi/id"
PCI_DEVICES = pathlib.Path("/sys/bus/pci/devices")
EFI = pathlib.Path("/sys/firmware/efi")
SECURE_BOOT = EFI / "efivars" / "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"

# SMBIOS gives the number; this program gives the name, so it goes by keys
# and is translated when painted.
CHASSIS_TYPES = {
    "1": "chassis.other", "2": "chassis.unknown", "3": "chassis.desktop",
    "4": "chassis.lowdesktop", "5": "chassis.pizzabox", "6": "chassis.minitower",
    "7": "chassis.tower", "8": "chassis.laptop", "9": "chassis.laptop",
    "10": "chassis.notebook", "11": "chassis.handheld", "12": "chassis.dock",
    "13": "chassis.aio", "14": "chassis.subnotebook", "15": "chassis.compact",
    "16": "chassis.lunchbox", "17": "chassis.rack", "18": "chassis.expansion",
    "23": "chassis.rack", "24": "chassis.smalldesktop", "30": "chassis.tablet",
    "31": "chassis.convertible", "32": "chassis.detachable",
    "35": "chassis.minipc",
}

# The chassis that carry their fans in the embedded controller and not in a
# Super I/O on a board: a laptop must not be sent to `sensors-detect`.
PORTABLE_CHASSIS = frozenset(("chassis.laptop", "chassis.notebook", "chassis.subnotebook",
                              "chassis.handheld", "chassis.tablet", "chassis.convertible",
                              "chassis.detachable"))

CLASS_HOST_BRIDGE = 0x060000
CLASS_ISA_BRIDGE = 0x060100
# Modern Intel chipsets present themselves as an eSPI controller, which the
# kernel classifies like the old ISA bridge.
CHIPSET_CLASSES = (CLASS_ISA_BRIDGE,)

# "H510 Chipset eSPI Controller" -> "H510"; "B550 LPC Bridge" -> "B550".
_CHIPSET_MODEL = re.compile(
    r"\b([A-Z]{1,3}\d{2,4}[A-Z]*)\b(?=.*(chipset|lpc|espi|isa))", re.IGNORECASE
)


# On AM4 and AM5 the LPC bridge on bus 0 is the FCH inside the processor,
# named the same on every board. There the board's name says the chipset
# («B550M» is a microATX B550; «B650E-F», a B650E). The list is closed on
# purpose: a letter and three digits is also a laptop («Aspire A515-45»), and
# a missing chipset is better explained than made up.
_AMD_CHIPSETS = ("A320", "B350", "X370", "B450", "X470", "A520", "B550", "X570",
                 "A620", "B650", "X670", "B840", "B850", "X870",
                 "X399", "TRX40", "TRX50", "WRX80", "WRX90")
_CHIPSET_IN_BOARD_NAME = re.compile(rf"\b({'|'.join(_AMD_CHIPSETS)})(E\b)?")
AMD = "Advanced Micro Devices"


def chipset_from_board_name(board: Optional[str]) -> Optional[str]:
    """The AMD chipset written in a board's name, if it is."""
    match = _CHIPSET_IN_BOARD_NAME.search(board or "")
    return match.group(1) + (match.group(2) or "") if match else None


def chipset(bridge: Optional[tuple[str, str]], board: Optional[str]) -> Optional[str]:
    """«Intel H510», «AMD X570», or nothing if nobody says.

    `bridge` is what `pci.ids` says of the LPC/eSPI bridge: maker and name.
    An AMD one without a model looks at the board, and failing that, a PCI
    device's name is not taken for a chipset.
    """
    if bridge is None:
        return None
    vendor, name = bridge
    match = _CHIPSET_MODEL.search(name)
    model = match.group(1) if match else None
    if model is None and vendor.startswith(AMD):
        model = chipset_from_board_name(board)
    brand = "AMD" if vendor.startswith(AMD) else vendor.split()[0]
    return f"{brand} {model}" if model else None


def _dmi(field: str) -> Optional[str]:
    return clean_dmi(read_text(f"{SYS_DMI}/{field}"))


class DmiBoard(Provider):
    name = "dmi"
    provides = "board"
    static = True

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(SYS_DMI))

    def unavailable_reason(self):
        if self.available():
            return None
        return ("board", Need.PLATFORM,
                _("prov.dmi.none"), _("prov.dmi.none.hint"))

    def collect(self, draft: Draft) -> None:
        draft.capabilities.add("dmi")
        model, chipset_full, host_bridge = self._chipset(_dmi("board_name"))

        draft.board = Board(
            vendor=_dmi("board_vendor"),
            name=_dmi("board_name"),
            version=_dmi("board_version"),

            bios_vendor=_dmi("bios_vendor"),
            bios_version=_dmi("bios_version"),
            bios_date=_dmi("bios_date"),
            bios_release=_dmi("bios_release"),

            firmware=self._firmware(),
            secure_boot=self._secure_boot(),
            tpm_version=self._tpm(),

            chipset=model,
            chipset_full=chipset_full,
            host_bridge=host_bridge,

            system_vendor=_dmi("sys_vendor"),
            system_name=_dmi("product_name"),
            system_version=_dmi("product_version"),
            system_family=_dmi("product_family"),
            system_sku=_dmi("product_sku"),

            chassis_vendor=_dmi("chassis_vendor"),
            chassis=CHASSIS_TYPES.get(read_text(f"{SYS_DMI}/chassis_type") or ""),
        )

        # A virtual machine has no board to blame (QEMU declares none): the
        # board page says what it is instead.
        if not draft.board.name and not is_virtual_machine(draft):
            draft.note(
                "board.name", Need.HARDWARE,
                _("prov.dmi.noboard"), _("prov.dmi.noboard.hint"),
            )

    # -- firmware -----------------------------------------------------------

    @staticmethod
    def _firmware() -> str:
        if not sysroot.ruta(EFI).is_dir():
            return "BIOS heredada"
        bits = read_text(str(sysroot.ruta(EFI) / "fw_platform_size"))
        return f"UEFI ({bits} bits)" if bits else "UEFI"

    @staticmethod
    def _secure_boot() -> Optional[bool]:
        """The EFI variable holds 4 bytes of attributes, then the value."""
        try:
            data = sysroot.ruta(SECURE_BOOT).read_bytes()
        except OSError:
            return None
        return bool(data[4]) if len(data) >= 5 else None

    @staticmethod
    def _tpm() -> Optional[str]:
        for entry in sorted(pathlib.Path(sysroot.ruta("/sys/class/tpm")).glob("tpm*")):
            major = read_text(str(entry / "tpm_version_major"))
            if major:
                return f"TPM {major}.0"
            # Old TPM 1.2 chips do not publish that file.
            if (entry / "caps").exists():
                return "TPM 1.2"
        return None

    # -- chipset ------------------------------------------------------------

    @staticmethod
    def _chipset(board: Optional[str] = None) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """The LPC/eSPI bridge on bus 0 identifies the chipset; the host
        bridge, the memory controller inside the CPU."""
        if not sysroot.ruta(PCI_DEVICES).is_dir():
            return None, None, None

        candidates: dict[int, tuple[int, int]] = {}
        for entry in sorted(sysroot.ruta(PCI_DEVICES).iterdir()):
            if not entry.name.startswith("0000:00:"):
                continue                      # the chipset is always on bus 0
            try:
                device_class = int(read_text(str(entry / "class")) or "0", 16)
                vendor = int(read_text(str(entry / "vendor")) or "0", 16)
                device = int(read_text(str(entry / "device")) or "0", 16)
            except ValueError:
                continue
            if device_class in CHIPSET_CLASSES and CLASS_ISA_BRIDGE not in candidates:
                candidates[CLASS_ISA_BRIDGE] = (vendor, device)
            elif device_class == CLASS_HOST_BRIDGE and CLASS_HOST_BRIDGE not in candidates:
                candidates[CLASS_HOST_BRIDGE] = (vendor, device)

        names = pciids.lookup(candidates.values())

        model = chipset_full = host = None
        if (pair := candidates.get(CLASS_ISA_BRIDGE)) and pair in names:
            chipset_full = names[pair][1]
            model = chipset(names[pair], board)
        if (pair := candidates.get(CLASS_HOST_BRIDGE)) and pair in names:
            host = names[pair][1]

        return model, chipset_full, host
