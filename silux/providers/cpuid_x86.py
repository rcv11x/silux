"""The processor's identity, read straight from CPUID without root.

What sysfs can't give: the real vendor, the brand string, family and model,
the instruction set and, on modern Intel, leaf 0x16's base clock, turbo
ceiling and BCLK, which other tools read from MSRs through a privileged
daemon.

CPUID reports on the core it runs on, so a hybrid CPU is queried once per
core type, with the thread pinned to one of its cores.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .. import db, features
from ..i18n import _
from ..model import Clocks, Need
from ..rawcpuid import CpuidError, CpuidReader, is_supported, pinned
from .base import Draft, Provider

# Leaf 0x1A: the native core type of Intel's hybrid CPUs.
CORE_TYPE_ATOM = 0x20
CORE_TYPE_CORE = 0x40

VENDOR_NAMES = {
    "GenuineIntel": "Intel",
    "AuthenticAMD": "AMD",
    "HygonGenuine": "Hygon",
    "CentaurHauls": "Centaur",
    "GenuineTMx86": "Transmeta",
    "CyrixInstead": "Cyrix",
    "NexGenDriven": "NexGen",
    "UMC UMC UMC ": "UMC",
    "SiS SiS SiS ": "SiS",
    "Geode by NSC": "National Semiconductor",
    "  Shanghai  ": "Zhaoxin",
}

# Leaf 0x40000000's 12-byte signature. Each hypervisor picked one long ago
# and kept it, so the table is short and doesn't age. Matched without the
# padding spaces several use to fill twelve bytes.
HYPERVISOR_NAMES = {
    "VMwareVMware": "VMware",
    "KVMKVMKVM": "KVM",
    "TCGTCGTCGTCG": "QEMU",
    "Microsoft Hv": "Hyper-V",
    "VBoxVBoxVBox": "VirtualBox",
    "XenVMMXenVMM": "Xen",
    "prl hyperv": "Parallels",
    "bhyve bhyve": "bhyve",
    "ACRNACRNACRN": "ACRN",
}


class CpuidIdentity(Provider):
    """Fills each core type's identity from CPUID."""

    name = "cpuid-x86"
    provides = "cpu.identity"
    static = True

    def __init__(self) -> None:
        self._reader: Optional[CpuidReader] = None
        self._error: Optional[str] = None
        if is_supported():
            try:
                self._reader = CpuidReader()
            except CpuidError as exc:
                self._error = str(exc)

    def available(self) -> bool:
        return self._reader is not None

    def unavailable_reason(self):
        if self.available():
            return None
        if not is_supported():
            return ("cpu.identity", Need.PLATFORM,
                    _("prov.cpuid.notx86"), _("prov.cpuid.notx86.hint"))
        return ("cpu.identity", Need.PLATFORM,
                _("prov.cpuid.failed"), _("prov.cpuid.failed.hint"), "",
                _("prov.cpuid.failed.detail").format(error=self._error))

    def collect(self, draft: Draft) -> None:
        reader = self._reader
        if reader is None:
            return
        draft.capabilities.add("cpuid")

        for key, entry in draft.types.items():
            cpus = entry.get("cpus") or [0]
            try:
                with pinned(cpus[0]):
                    self._fill(reader, draft, entry)
            except CpuidError as exc:
                draft.note(f"cpu.types.{key}", Need.PLATFORM,
                           _("prov.cpuid.pin").format(cpu=cpus[0]), detail=str(exc))

    # -- internals ----------------------------------------------------------

    def _fill(self, reader: CpuidReader, draft: Draft, entry: dict) -> None:
        vendor_id = reader.vendor_id
        brand = reader.brand_string()

        eax = reader(1)[0]
        family = (eax >> 8) & 0xF
        model = (eax >> 4) & 0xF
        stepping = eax & 0xF
        ext_family_bits = (eax >> 20) & 0xFF
        ext_model_bits = (eax >> 16) & 0xF

        # Datasheets and identification databases use the composed values,
        # not the raw bits.
        disp_family = family + ext_family_bits if family == 0xF else family
        disp_model = model + (ext_model_bits << 4) if family in (6, 0xF) else model

        feats = features.decode(reader)
        entry.update(
            vendor_id=vendor_id,
            vendor=VENDOR_NAMES.get(vendor_id, vendor_id),
            brand=brand,
            architecture="x86_64" if "lm" in feats else "x86",
            family=family,
            model=model,
            stepping=stepping,
            disp_family=disp_family,
            disp_model=disp_model,
            signature=eax,
            features=feats,
            virtualization=("VT-x" if "vmx" in feats else "AMD-V" if "svm" in feats else None),
            # No real processor sets the hypervisor bit, so it is the most
            # direct sign of running in a virtual machine.
            in_virtual_machine="hypervisor" in feats,
            hypervisor=self._hypervisor(reader) if "hypervisor" in feats else None,
        )

        self._fill_frequencies(reader, entry, hybrid=len(draft.types) > 1)
        # A virtual CPU's identity is whatever the hypervisor declares: QEMU
        # makes up family and model, and with `-cpu host` the chip is the
        # host's but the package isn't the guest's. So it isn't looked up, and
        # no notice asks for a report to fill it in.
        if not entry["in_virtual_machine"]:
            self._fill_identity(draft, entry, vendor_id, disp_family, disp_model,
                                family, model, stepping, brand)

    @staticmethod
    def _hypervisor(reader: CpuidReader) -> Optional[str]:
        """The hypervisor underneath, when the hypervisor bit is set. An
        unknown signature is returned as is: it still identifies it, and the
        report carries it so the table can be extended."""
        signature = reader.hypervisor_id().strip()
        if not signature:
            return None
        return HYPERVISOR_NAMES.get(signature, signature)

    @staticmethod
    def _fill_frequencies(reader: CpuidReader, entry: dict, hybrid: bool) -> None:
        """Leaf 0x16: base clock, turbo ceiling and BCLK (Skylake and later).

        A hybrid answers one base for the whole package, which is neither
        core type's: there each type's own, from intel_pstate, is the base.
        """
        if not reader.supports(0x16):
            return
        base_mhz, max_mhz, bus_mhz, _rest = reader(0x16)
        if not any((base_mhz, max_mhz, bus_mhz)):
            return

        clocks: Clocks = entry.get("clocks") or Clocks()
        entry["clocks"] = dataclasses.replace(
            clocks,
            base_hz=(clocks.base_hz or (clocks.base_configured_hz if hybrid else None)
                     or base_mhz * 1_000_000 or None),
            max_turbo_hz=max_mhz * 1_000_000 or None,
            bus_hz=bus_mhz * 1_000_000 or None,
        )

    @staticmethod
    def _fill_identity(draft: Draft, entry: dict, vendor_id: str, disp_family: int,
                       disp_model: int, family: int, model: int, stepping: int,
                       brand: str) -> None:
        if not db.available():
            draft.note(
                "cpu.codename", Need.DATABASE,
                _("prov.cpuid.nodb"), _("prov.cpuid.nodb.hint"),
            )
            return

        l2 = entry_cache_kb(entry, 2)
        l3 = entry_cache_kb(entry, 3)

        ident = db.identify_x86(
            vendor_id=vendor_id,
            family=family,
            model=model,
            stepping=stepping,
            ext_family=disp_family,
            ext_model=disp_model,
            cores=entry.get("cores", 0),
            brand=brand,
            l2_kb=l2 if l2 is not None else -1,
            l3_kb=l3 if l3 is not None else -1,
        )

        if ident.matched:
            entry["codename"] = ident.codename
            entry["technology"] = ident.technology
            entry["socket"] = db.find_socket(vendor_id, ident.codename, brand)
        else:
            draft.note(
                "cpu.codename", Need.DATABASE,
                _("prov.cpuid.unknown").format(marca=brand),
                _("prov.cpuid.unknown.hint"),
            )

        # A recognised processor can still lack either: some table rows have
        # no process node, and the package comes from a different source.
        if ident.matched and entry.get("technology") is None:
            draft.note(
                "cpu.technology", Need.DATABASE,
                _("prov.cpuid.notech").format(nombre=ident.codename),
                _("prov.cpuid.sendreport"),
            )
        if ident.matched and entry.get("socket") is None:
            draft.note(
                "cpu.socket", Need.DATABASE,
                _("prov.cpuid.nosocket").format(nombre=ident.codename),
                _("prov.cpuid.sendreport"),
            )


def entry_cache_kb(entry: dict, level: int) -> Optional[int]:
    """A cache's size in KB, as libcpuid's database expects it."""
    for cache in entry.get("caches", ()):
        if cache.level == level and cache.kind in ("unified", "data"):
            return cache.size_bytes // 1024
    return None
