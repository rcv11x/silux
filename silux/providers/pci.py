"""What hangs from the PCI bus, and what the board has enabled.

Two providers. `PlatformInfo` is read once: IOMMU, virtualization, the
sensor chip, the sound codec. `PciDevices` on every sample, since a device's
link changes on its own: an idle graphics card lowers it to save power.

Names are not taken raw from `pci.ids` when Silux already calls that part
something else: the disk as in Storage, the graphics card as in Graphics,
the network card as in Network (rule 1). So `PciDevices` runs after those
three in `collector.py`.
"""

from __future__ import annotations

import glob
import os
import pathlib
import re
from typing import Optional

from .. import pciids, sysroot
from ..model import PciDevice, PcieLink, Platform
from .base import Draft, Provider, en_reposo, read_text
from .drm import VENDORS, _cadena_pcie, _enlace

DEVICES = "/sys/bus/pci/devices"

# The PCI class (first four digits) of what is shown. Bridges and the rest
# are not devices anyone looks for by name.
CLASSES = {
    "0300": "gpu", "0302": "gpu", "0380": "gpu",
    "0108": "nvme", "0106": "sata", "0104": "sata",
    "0200": "ethernet", "0280": "wifi",
    "0c03": "usb", "0403": "audio", "0401": "audio",
}
# In what order: what goes in a slot first, the board's controllers after.
IN_A_SLOT = ("gpu", "nvme", "ethernet", "wifi")
ORDER = ("gpu", "nvme", "ethernet", "wifi", "sata", "usb", "audio")

_ADDRESS = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]")


def _hex(path: str) -> Optional[int]:
    raw = read_text(path)
    try:
        return int(raw, 16) if raw else None
    except ValueError:
        return None


class PciDevices(Provider):
    """The PCI devices with their name, driver and link."""

    name = "pci"
    provides = "pci_devices"

    def __init__(self) -> None:
        # What is there does not change while the program runs; the link does.
        self._fixed: Optional[list[dict]] = None
        # Each slot's last link: its maximum does not change and is not reread.
        self._links: dict[str, PcieLink] = {}

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(DEVICES))

    def collect(self, draft: Draft) -> None:
        if self._fixed is None:
            self._fixed = self._enumerate()
        own = self._own_names(draft)
        out = []
        for fixed in self._fixed:
            node = pathlib.Path(sysroot.ruta(f"{DEVICES}/{fixed['slot']}"))
            # The link only means something for what goes in a slot. A USB,
            # SATA or sound controller lives inside the chipset or processor:
            # its node publishes the chipset's internal link, which would read
            # as a slot running at half. A suspended card is not asked:
            # reading its link wakes it since Linux 6.18 (`en_reposo`).
            link = (_enlace(node, self._links.get(fixed["slot"]))
                      if fixed["kind"] in IN_A_SLOT and not en_reposo(node) else None)
            if link is not None:
                self._links[fixed["slot"]] = link
            # An Intel integrated card publishes no link: it hangs from none,
            # being inside the processor. A link without a single figure is not
            # an unknown link, it is none.
            if link is not None and not any((link.current_speed_gts, link.max_speed_gts,
                                               link.current_width, link.max_width)):
                link = None
            out.append(PciDevice(
                slot=fixed["slot"], kind=fixed["kind"],
                name=own.get(fixed["slot"]) or fixed["name"],
                vendor=fixed["vendor"], driver=fixed["driver"],
                link=link,
                slot_name=self._slot_name(node, draft.pci_slot_names),
                vendor_id=fixed["ids"][0], device_id=fixed["ids"][1], pci_class=fixed["class_code"]))
        out.sort(key=lambda d: (ORDER.index(d.kind), d.slot))
        draft.pci_devices = out

    @staticmethod
    def _enumerate() -> list[dict]:
        raws = []
        for path in sorted(glob.glob(os.path.join(sysroot.ruta(DEVICES), "*"))):
            slot = os.path.basename(path)
            if not _ADDRESS.fullmatch(slot):
                continue
            base = sysroot.fuera(path)
            code = (read_text(f"{base}/class") or "")[2:6]
            kind = CLASSES.get(code)
            if kind is None:
                continue
            driver = None
            try:
                link = pathlib.Path(path, "driver")
                driver = link.resolve().name if link.exists() else None
            except OSError:
                pass
            raws.append({"slot": slot, "kind": kind, "driver": driver, "class_code": code,
                           "ids": (_hex(f"{base}/vendor"), _hex(f"{base}/device"))})
        pairs = [c["ids"] for c in raws if None not in c["ids"]]
        names = pciids.lookup(pairs) if pairs else {}
        for raw in raws:
            vendor, model = names.get(raw["ids"], (None, None))
            # A device pci.ids does not know yet still belongs to someone:
            # the vendor by its id.
            raw["vendor"] = vendor or VENDORS.get(raw["ids"][0])
            raw["name"] = model
        return raws

    @staticmethod
    def _own_names(draft: Draft) -> dict[str, str]:
        """The name each part already has on its page, by address."""
        own: dict[str, str] = {}
        for gpu in draft.gpus:
            if gpu.get("pci_slot") and gpu.get("name"):
                own[gpu["pci_slot"]] = gpu["name"]
        for disk in draft.disks:
            if getattr(disk, "pci_slot", None) and disk.model:
                own[disk.pci_slot] = disk.model
        for interface in draft.network:
            slot = getattr(interface, "pci_slot", None)
            name = getattr(interface, "display_name", None)
            if slot and name and name != interface.name:
                own[slot] = name
        return own

    @staticmethod
    def _slot_name(node: pathlib.Path, names: dict) -> Optional[str]:
        """The slot's name, if the firmware's table points to this device or
        to a bridge on its chain (a graphics card carries its own)."""
        if not names:
            return None
        for hop in _cadena_pcie(node):
            if (name := names.get(hop.name)):
                return name
        return None


class PlatformInfo(Provider):
    """IOMMU, virtualization, decoding above 4 GB and the board's chips.
    Once."""

    name = "platform"
    provides = "platform"
    static = True

    def collect(self, draft: Draft) -> None:
        kind, state = self._virtualization()
        draft.platform = Platform(
            iommu_groups=self._iommu(),
            virtualization=state, virtualization_kind=kind,
            above_4g_devices=self._above_4g(),
            sensor_chip=self._sensor_chip(),
            audio_codec=self._codec(),
        )

    @staticmethod
    def _iommu() -> Optional[int]:
        groups = glob.glob(os.path.join(sysroot.ruta("/sys/kernel/iommu_groups"), "*"))
        return len(groups) or None

    @staticmethod
    def _virtualization() -> tuple[Optional[str], Optional[str]]:
        flags = ""
        for line in (read_text("/proc/cpuinfo") or "").splitlines():
            if line.startswith("flags"):
                flags = line.partition(":")[2]
                break
        words = flags.split()
        kind = "AMD-V" if "svm" in words else "VT-x" if "vmx" in words else None
        if kind is None:
            return None, None
        # `/dev/kvm` is not in /sys or /proc: asked through `a_traves` so a
        # dump keeps what its machine answered.
        in_use = sysroot.a_traves("plataforma", "kvm", lambda: os.path.exists("/dev/kvm"))
        return kind, "active" if in_use else "present"

    @staticmethod
    def _above_4g() -> int:
        count = 0
        for path in glob.glob(os.path.join(sysroot.ruta(DEVICES), "*", "resource")):
            for line in (read_text(sysroot.fuera(path)) or "").splitlines():
                fields = line.split()
                try:
                    if len(fields) >= 2 and int(fields[1], 16) and int(fields[0], 16) >= 1 << 32:
                        count += 1
                        break
                except ValueError:
                    continue
        return count

    @staticmethod
    def _sensor_chip() -> Optional[str]:
        from .hwmon import BOARD_CHIP

        for path in sorted(glob.glob(os.path.join(sysroot.ruta("/sys/class/hwmon"), "*", "name"))):
            name = read_text(sysroot.fuera(path)) or ""
            if BOARD_CHIP.match(name) and not name.startswith(("acpitz", "thermal")) \
                    and not name.endswith("_wmi"):
                return name
        return None

    @staticmethod
    def _codec() -> Optional[str]:
        """The board's sound codec. HDMI ones belong to the graphics card."""
        for path in sorted(glob.glob(os.path.join(sysroot.ruta("/proc/asound"), "card*", "codec#*"))):
            first = (read_text(sysroot.fuera(path)) or "").split("\n", 1)[0]
            name = first.partition(":")[2].strip()
            if name and "HDMI" not in name:
                return name
        return None
