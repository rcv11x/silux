"""Graphics cards, from /sys/class/drm.

There is no CPUID here: each driver publishes its own data where it sees
fit. Common to all are the PCI node (vendor, device, subsystem, link) and
the video connectors. From there:

- **amdgpu** says the most: VRAM, the DPM clock table, usage, VBIOS and a
  full hwmon. Almost everything GPU-Z shows comes from here.
- **i915 and xe** (Intel) give the graphics engine's clocks and little more,
  which is fair: an integrated GPU has no VRAM or VBIOS of its own.
- **nouveau** gives the PCI node and stops; NVIDIA's proprietary driver
  publishes nothing in sysfs and needs NVML. That is said instead of showing
  an empty card.

The marketing name comes from `pci.ids`, ambiguous on recent cards («Radeon
RX 9070/9070 XT/9070 GRE» is three models); the driver settles it through
Vulkan, in another provider. This one keeps the name it knows.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import time
from typing import Optional

from .. import amdgpu, edid, gpumetrics, i915, pciids, sysroot
from ..i18n import _
from ..model import Display, GpuClockLevel, GpuClocks, GpuEngine, GpuMemory, Need, PcieLink
from ..privileged.client import HelperError, PmuUnsupported, PrivilegedClient
from .base import Draft, Provider, is_suspended, read_int, read_text
from .counters import increase, window_s
from .rapl import Discarded, package_ceiling_w

SYS_DRM = "/sys/class/drm"

# Who makes the chip, not always who sells the card.
VENDORS = {
    0x1002: "AMD",
    0x1022: "AMD",
    0x10DE: "NVIDIA",
    0x8086: "Intel",
    0x1AF4: "Red Hat",       # virtio-gpu
    0x15AD: "VMware",
    0x1234: "QEMU",
    0x1A03: "ASPEED",
    0x102B: "Matrox",
}

# The drivers of a graphics device a hypervisor emulates: no silicon below.
VIRTUAL_DRIVERS = frozenset(("bochs-drm", "bochs", "virtio_gpu", "virtio-gpu",
                               "qxl", "vmwgfx", "vboxvideo", "cirrus", "cirrus-qemu",
                               "hyperv_drm"))

# Those that publish almost nothing, and why is worth saying.
BLIND_DRIVERS = {
    "nvidia": ("prov.drm.nvidia", "prov.drm.nvidia.hint"),
    "nouveau": ("prov.drm.nouveau", "prov.drm.nouveau.hint"),
    # i915 and xe are not here on purpose: GpuState sets their notice, as it
    # depends on whether the user gave permissions, which changes mid-session.
    # A static provider reads this table, once.
}

# What an Intel GPU gives by no path: its DRM node has no hwmon and its PMU
# publishes no energy event, so neither temperature nor watts. RAPL's
# «uncore» domain looked like the graphics plane on desktop Intel and is not:
# it stays at 3.2 W while the engine clock goes from 350 to 1050 MHz, a
# believable, false figure.

# Usage and power do exist, but only as kernel counters, read by the
# privileged helper. The user is NOT told to lower
# /proc/sys/kernel/perf_event_paranoid: it is a system-wide lock (at 0 any
# unprivileged process can profile the whole machine), and the middle value,
# 1, does not help either.
#
# The temperature is not here: DerivedSensors says it, with the package's.
# With its counters read ("hardware") nothing is missing to say.
INTEL_NOTICES = {
    "root": ("prov.drm.intelroot", "prov.drm.intelroot.hint", ""),
    "driver": ("prov.drm.inteldriver", "prov.drm.inteldriver.hint",
               "prov.drm.inteldriver.detail"),
    "unopened": ("prov.drm.intelunopened", "prov.drm.intelunopened.hint",
                 "prov.drm.intelunopened.detail"),
}

# Where the kernel publishes each PMU and its events; readable without
# permissions, so it says whether a card has busy counters at all.
EVENT_SOURCE = "/sys/bus/event_source/devices"
BUSY_EVENT = re.compile(r"^[a-z]+\d+-busy$")

# How the kernel names each engine and what it does. The name's prefix is
# enough: rcs0 draws, vcs1 is the second decoder.
INTEL_ENGINES = {
    "rcs": "engine.render",
    "ccs": "engine.compute",
    "bcs": "engine.copy",
    "vcs": "engine.video",
    "vecs": "engine.videoenhance",
}

# The GPU's power plane in RAPL. It is the processor's integrated GPU's, so it
# is not given to a dedicated card even if it is Intel.
ENERGY_PMU = ("power", "energy-gpu")

# «0: 500Mhz », «1: 1150Mhz *»: the asterisk marks the clock in use. On older
# cards this is a real DPM table with eight steps. On RDNA3 and RDNA4 it is
# three lines (minimum, current and maximum), and the first may come with
# «S:» instead of a number: the GPU in deep idle, at 0 MHz. So the index is
# taken as text and dropped if not a number.
_DPM_LEVEL = re.compile(r"^\s*(\w+)\s*:\s*([\d.]+)\s*([MG])hz\s*(\*?)", re.IGNORECASE)
# «32.0 GT/s PCIe»
_SPEED = re.compile(r"([\d.]+)\s*GT/s")
# «Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]»
_NAME_IN_BRACKETS = re.compile(r"^(.*?)\s*\[(.+)\]\s*$")


# AMD writes the integrated GPU's name inside the processor's brand string:
# «AMD Ryzen 7 7445HS w/ Radeon 740M Graphics». Needed because pci.ids does
# not always carry the marketing name (it calls 1002:1901 just «HawkPoint2»,
# without the usual brackets).
_IGPU_IN_BRAND = re.compile(r"\bw/\s+(Radeon\s+[\w\s]*?)\s*Graphics\b",
                               re.IGNORECASE)


def _cpu_igpu(draft) -> Optional[str]:
    """The integrated GPU's marketing name, if the processor declares it."""
    for entry in draft.types.values():
        if match := _IGPU_IN_BRAND.search(entry.get("brand") or ""):
            return " ".join(match.group(1).split())
    return None


# pci.ids' names that say what a device is, not what it's sold as: an Intel
# integrated GPU by its processor's family, «(primary)» for the first PCI
# function of an old chipset's graphics.
_ONLY_A_FAMILY = re.compile(r"Graphics Controller|\((?:primary|secondary)\)")
INTEL = 0x8086


def _intel_commercial_name(name: Optional[str], vendor_id: int, device_id: int) -> Optional[str]:
    """«HD Graphics 4600» where pci.ids says «4th Gen Core Processor
    Integrated Graphics Controller»: Mesa's name for the device ID."""
    if vendor_id != INTEL or not name or not _ONLY_A_FAMILY.search(name):
        return name
    from .. import db

    commercial = db.intel_gpus().get(f"{device_id:04x}")
    if commercial:
        return commercial
    # Older than Mesa names: «Mobile GM965/GL960 Integrated Graphics».
    name = re.sub(r"\s*\((?:primary|secondary)\)", "", name)
    return re.sub(r"\s+Controller$", "", name.strip())


def _split_name(text: str) -> tuple[Optional[str], Optional[str]]:
    """pci.ids writes «codename [marketing name]»; this splits them."""
    if match := _NAME_IN_BRACKETS.match(text):
        return match.group(1) or None, match.group(2)
    return None, text or None


def cards() -> list[pathlib.Path]:
    """The cardN nodes, without their connectors (named cardN-DP-1)."""
    root = pathlib.Path(sysroot.path(SYS_DRM))
    if not root.is_dir():
        return []
    found = [p for p in root.glob("card*") if re.fullmatch(r"card\d+", p.name)]
    return sorted(found, key=lambda p: int(p.name[4:]))


class DrmGpus(Provider):
    """Identity, memory, link and video outputs: everything that does not change."""

    name = "drm-gpus"
    provides = "gpus"
    static = True

    def available(self) -> bool:
        return os.path.isdir(sysroot.path(SYS_DRM))

    def unavailable_reason(self):
        if self.available():
            return None
        return ("gpus", Need.PLATFORM,
                _("prov.drm.nosysfs"), _("prov.drm.nosysfs.hint"), "",
                _("prov.missing.detail").format(ruta=SYS_DRM))

    def collect(self, draft: Draft) -> None:
        nodes = cards()
        if not nodes:
            draft.note(
                "gpus", Need.HARDWARE,
                _("prov.drm.nogpu"), _("prov.drm.nogpu.hint"),
            )
            return

        draft.capabilities.add("drm")
        # Listed once and handed out: with two cards and no driver, the first
        # card takes the first one on the bus.
        no_driver = _gpus_on_bus()
        for index, node in enumerate(nodes):
            device = node / "device"
            gpu = draft.gpu(index)
            gpu["drm_node"] = node.name
            gpu["pci_slot"] = _slot(device)
            gpu["driver"] = _driver(device)
            gpu["primary"] = read_int(f"{device}/boot_vga") == 1
            # First, before touching anything that wakes it. The identity
            # (vendor, device, revision) is stored by the kernel at enumeration
            # and read without waking it; link, memory and driver are not.
            asleep = is_suspended(device)
            gpu["suspended"] = asleep

            self._identity(gpu, device, draft, asleep)
            if gpu["driver"] in GENERIC_FRAMEBUFFER or not gpu.get("vendor_id"):
                self._bus_identity(gpu, draft, index, no_driver)
            if gpu["driver"] in ("i915", "xe"):
                gpu["engines"] = _intel_engines(node)
                # An Intel integrated GPU gives its temperature by no path: i915
                # and xe register hwmon only on dedicated cards
                # (i915_hwmon_register returns if !IS_DGFX; xe_hwmon too). An
                # Arc does, by hwmon. Whether there is something to read is
                # checked, not assumed from the driver: listing a folder wakes
                # nobody.
                hwmon = _hwmon(device)
                gpu["no_temperature_sensor"] = not (
                    hwmon is not None and any(hwmon.glob("temp*_input")))
            gpu["displays"] = _outputs(node.name)
            if asleep:
                draft.note(f"gpus.{index}", Need.HARDWARE,
                           _("prov.drm.asleep"), _("prov.drm.asleep.hint"))
            else:
                gpu["link"] = _link(device)
                gpu["memory"] = _total_memory(device)
                self._ask_the_driver(gpu, device)
            gpu["integrated"] = _is_integrated(gpu)
            if gpu["driver"] in VIRTUAL_DRIVERS:
                gpu["virtual"] = True

            notice = BLIND_DRIVERS.get(gpu["driver"] or "")
            if notice:
                draft.note(f"gpus.{index}", Need.DRIVER,
                           *(_(entry_key) for entry_key in notice), key=notice[0])

        _name_monitors(draft.gpus)

    def _bus_identity(self, gpu: dict, draft: Draft, index: int,
                           candidate_cards: list) -> None:
        """Who the card is when the DRM node does not know.

        The fallback framebuffer hangs from a platform device, not PCI, so
        there is no `vendor` or `device` to read and the card came out all
        dashes, not even its name. The bus lists it, with a driver or without.
        """
        if not candidate_cards:
            return
        device = candidate_cards.pop(0)
        self._identity(gpu, device, draft)
        gpu["pci_slot"] = device.name
        # The DRM node is still the framebuffer's; link and memory are read
        # from the real device, which has them.
        if not is_suspended(device):
            gpu["link"] = _link(device)
        gpu["integrated"] = _is_integrated(gpu)
        draft.note(f"gpus.{index}", Need.DRIVER,
                   _("prov.drm.nodriver").format(
                       tarjeta=gpu.get("name") or _("prov.drm.thiscard")),
                   _("prov.drm.nodriver.hint"))

    @staticmethod
    def _ask_the_driver(gpu: dict, device: pathlib.Path) -> None:
        """What each driver only gives by ioctl.

        From amdgpu, memory, units and ROPs. From i915, the execution units,
        not in sysfs, which only OpenCL answered, counting something else.
        """
        if gpu.get("driver") == "i915":
            DrmGpus._ask_i915(gpu, device)
        if gpu.get("driver") != "amdgpu":
            return
        node = amdgpu.render_node(device)
        if not node:
            return
        info = sysroot.recorded("amdgpu", node, amdgpu.query, node,
                                expected_device_id=gpu.get("device_id"),
                                kind=amdgpu.DeviceInfo)
        if info is None:
            return

        gpu["memory"] = dataclasses.replace(
            gpu.get("memory") or GpuMemory(),
            kind=info.vram_type,
            bus_bits=info.vram_bits,
            data_rate_hz=info.memory_data_rate_hz,
            bandwidth_bytes=info.bandwidth_bytes,
        )
        gpu["compute_units"] = info.compute_units or gpu.get("compute_units")
        gpu["rops"] = info.rops
        gpu["shader_engines"] = info.shader_engines
        gpu["l2_cache_bytes"] = info.l2_cache_bytes
        gpu["infinity_cache_bytes"] = info.infinity_cache_bytes
        firmware = sysroot.recorded("amdgpu_vbios", node, amdgpu.vbios, node,
                                    kind=amdgpu.VbiosInfo)
        if firmware is not None:
            gpu["vbios_version"], gpu["vbios_date"] = firmware.version, firmware.date
        # With an underscore because it is not a model field: only
        # _is_integrated uses it, and freezing drops what it does not know.
        gpu["_is_apu"] = info.is_apu

    @staticmethod
    def _ask_i915(gpu: dict, device: pathlib.Path) -> None:
        """An Intel GPU's execution units.

        The only place with the whole number. OpenCL answers subslices (five
        on an 80 EU Iris Xe G7), sixteen times smaller with the big ones'
        label.
        """
        node = i915.render_node(device)
        if not node:
            return
        info = sysroot.recorded("i915", node, i915.query, node,
                                expected_device_id=gpu.get("device_id"),
                                kind=i915.DeviceInfo)
        if info is None or info.eu_total is None:
            return
        gpu["compute_units"] = info.eu_total

    @staticmethod
    def _identity(gpu: dict, device: pathlib.Path, draft: Draft,
                   asleep: bool = False) -> None:
        # `draft` is needed at the end, to ask the processor's brand how its
        # integrated GPU is called.
        vendor_id = _hex(device / "vendor")
        device_id = _hex(device / "device")
        gpu["vendor_id"] = vendor_id
        gpu["device_id"] = device_id
        gpu["subsystem_vendor_id"] = _hex(device / "subsystem_vendor")
        gpu["subsystem_device_id"] = _hex(device / "subsystem_device")
        gpu["revision"] = _hex(device / "revision")
        # The above is the PCI core's, stored at enumeration
        # (drivers/pci/pci-sysfs.c). This is the driver's, and may wake it:
        # with the card asleep, better no value than waking it.
        if not asleep:
            gpu["vbios"] = read_text(f"{device}/vbios_version")
            gpu["unique_id"] = read_text(f"{device}/unique_id")
        gpu["vendor"] = VENDORS.get(vendor_id or -1)

        if vendor_id is None or device_id is None:
            return
        sub = (gpu["subsystem_vendor_id"], gpu["subsystem_device_id"])
        subsystem = ()
        if all(v is not None for v in sub):
            subsystem = ((vendor_id, device_id, sub[0], sub[1]),)   # type: ignore[assignment]

        names = pciids.lookup([(vendor_id, device_id)], subsystems=subsystem)
        if found_one := names.get((vendor_id, device_id)):
            brand, model = found_one
            gpu["vendor"] = gpu["vendor"] or brand
            gpu["codename"], gpu["name"] = _split_name(model)
            gpu["name"] = _intel_commercial_name(gpu.get("name"), vendor_id, device_id)

        if subsystem and (found_one := names.get(subsystem[0])):
            # Who built the card and what they called it: what turns «Radeon RX
            # 9070/9070 XT/9070 GRE» (three models) into the one it is.
            maker, model = found_one
            gpu["subsystem_name"] = maker or None
            entry_key, marketing_name = _split_name(model)
            gpu["name"] = marketing_name or gpu.get("name")
            gpu["codename"] = gpu.get("codename") or entry_key

        # pci.ids only carries the full subsystem line for combinations someone
        # added, and a recent board seldom is. The vendor alone is: who built
        # the card is worth more than a dash.
        if not gpu.get("subsystem_name") and sub and sub[0] is not None:
            gpu["subsystem_name"] = pciids.vendor_name(sub[0])

        # What pci.ids left without a marketing name. Only what is still called
        # by its codename is touched: one already saying «Radeon» came from
        # the database and is more specific.
        if (gpu.get("vendor") == "AMD"
                and "radeon" not in (gpu.get("name") or "").lower()
                and (integrated := _cpu_igpu(draft))):
            gpu["codename"] = gpu.get("codename") or gpu.get("name")
            gpu["name"] = integrated


def _is_integrated(gpu: dict) -> Optional[bool]:
    """Whether the GPU is built into the processor or a separate card.

    Not reading memory does not mean there is none (nouveau reads none), so
    VRAM does not decide: a GeForce GTX 1050 Mobile, a real dedicated card,
    showed as integrated; and an APU reserves system RAM, so it seemed to
    have its own and showed as dedicated. Each maker says it its own way, and
    what cannot be decided stays undecided instead of answering by
    elimination.
    """
    maker = gpu.get("vendor") or ""
    slot = gpu.get("pci_slot") or ""

    # AMD publishes it in the ioctl: the FUSION bit says the chip is fused
    # with the processor. Nothing is more reliable.
    if (apu := gpu.get("_is_apu")) is not None:
        return apu

    if maker == "Intel":
        # Intel's integrated GPU always lives at function 0 of device 2 on bus 0.
        # A dedicated Arc is on another bus, behind a bridge.
        return slot.endswith(":00:02.0")

    if maker == "NVIDIA":
        # A PC has no NVIDIA integrated GPU; those built into a processor are
        # Tegra, which do not use this driver.
        return False

    return None


class GpuState(Provider):
    """What changes: usage, used VRAM, clocks and its own sensors."""

    name = "gpu-state"
    provides = "gpus.load"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        # The collector shares one client among all who ask for it: two would
        # be two polkit windows for the same password. Without one, there are
        # no counters to read.
        self.client = client
        # (clock, counters) of the previous pass, to subtract. The PMU's are
        # cumulative: a single value says nothing.
        self._pmu_previous: Optional[tuple[int, dict]] = None
        self._pmu_ok = False
        self._pmu_silent = False
        # The PMUs whose counters the helper did return. Any counter is not
        # this card's: a UHD got only the package's energy-gpu, and its notice
        # said its engines' usage was already being read.
        self._pmu_read: set[str] = set()
        self._ceiling: Optional[float] = None
        self._discarded = Discarded("energy-gpu")
        # The idle counter is cumulative like the PMU's, but comes from sysfs
        # and costs no permissions.
        self._rc6: dict[str, tuple[float, int]] = {}
        # The last reading of each awake card: when, and its temperature, to
        # say it while it sleeps.
        self._awake: dict[str, tuple[float, Optional[float]]] = {}
        # What was read between samples of each instant counter, per card
        # (`between_samples`), and which awake cards to read it from.
        self._readings: dict[tuple[pathlib.Path, str], list[float]] = {}
        self._with_instants: list[pathlib.Path] = []
        # The Intel cards whose engine clock is read between samples too,
        # with their DRM node (`_intel_clock`).
        self._with_clock: list[tuple[pathlib.Path, pathlib.Path]] = []

    def available(self) -> bool:
        return os.path.isdir(sysroot.path(SYS_DRM))

    def wants_between_samples(self) -> bool:
        return bool(self._with_instants or self._with_clock)

    def between_samples(self) -> None:
        """Read the usage counters amdgpu gives as an instant.

        `gpu_busy_percent`, `mem_busy_percent` and `vcn_busy_percent` are what
        the firmware measured over its last milliseconds, not the last second:
        a single reading jumps between 59 and 100 with the GPU doing the same.
        MangoHud averages many readings; here, those of the whole interval
        (`_mean`). A sleeping card is not read: that would wake it.
        """
        for device in self._with_instants:
            if is_suspended(device):
                continue
            for field, file_name in INSTANT_USAGE:
                amount = _percent(device / file_name)
                if amount is not None:
                    self._readings.setdefault((device, field), []).append(amount)
        # Reading the actual frequency does not wake an Intel GPU (i915 reads
        # it only if the device is in use), but a suspended one is left alone.
        for device, root in self._with_clock:
            if is_suspended(device):
                continue
            hz = _intel_hz(device, root, "cur")
            if hz is not None:
                self._readings.setdefault((device, "core_hz"), []).append(hz)

    def _mean(self, device: pathlib.Path, field: str, file_name: str) -> Optional[float]:
        """The reading now together with those between samples, in a mean."""
        readings = self._readings.pop((device, field), [])
        now = _percent(device / file_name)
        if now is not None:
            readings.append(now)
        if not readings:
            return None
        return round(sum(readings) / len(readings), 1)

    def collect(self, draft: Draft) -> None:
        busy, watts = self._counters(draft.interval_s)
        self._discarded.note(draft)
        with_instants = []
        with_clock = []
        for index, gpu in enumerate(draft.gpus):
            node = gpu.get("drm_node")
            if not node:
                continue
            root = pathlib.Path(sysroot.path(f"{SYS_DRM}/{node}"))
            device = root / "device"
            if not device.is_dir():
                continue
            if is_suspended(device):
                self._asleep(gpu, node)
                # Read awake at the static pass, its driver's notice said a
                # driver was missing (NVIDIA's, before NVML answers). Asleep,
                # NVML is closed on purpose: what is missing is that it sleeps.
                path = f"gpus.{index}"
                draft.notes = [n for n in draft.notes
                               if not (n.path == path and n.need is Need.DRIVER)]
                if not any(n.path == path and n.need is Need.HARDWARE for n in draft.notes):
                    draft.note(path, Need.HARDWARE,
                               _("prov.drm.asleep"), _("prov.drm.asleep.hint"))
                continue
            if gpu.get("suspended"):
                # The static data was read with it asleep and half the card is missing.
                gpu["suspended"] = False
                draft.static_stale = True

            for field, file_name in INSTANT_USAGE:
                gpu[field] = self._mean(device, field, file_name)
            if (device / "gpu_busy_percent").exists():
                with_instants.append(device)
            gpu["memory"] = _used_memory(device, gpu.get("memory") or GpuMemory())
            gpu["link"] = _link(device, gpu.get("link") or PcieLink())
            gpu["clocks"] = _clocks(device, root)
            _sensors(gpu, device)
            _telemetry(gpu, device, draft, index)
            if gpu.get("vendor") == "AMD" and gpu.get("integrated"):
                # On an APU, hwmon's `power1` is the package's PPT: processor
                # and GPU together (amdgpu_pm.c labels it «PPT» and reads it from
                # AMDGPU_PP_SENSOR_GPU_INPUT_POWER, the SMU's SocketPower on
                # APUs). Its cap too. Not the GPU's power, and not shown as such.
                gpu["power_w"] = None
                gpu["power_cap_w"] = None
            self._awake[node] = (time.time(), gpu.get("temp_c"))

            if gpu.get("driver") in ("i915", "xe"):
                gpu["sleep_percent"] = self._idle(node, root, draft.interval_s)
                gpu["clocks"] = self._intel_clock(device, root, gpu["clocks"],
                                                  gpu["sleep_percent"])
                with_clock.append((device, root))
                rc6 = _first(read_int(f"{root}/gt/gt0/rc6_enable"),
                               read_int(f"{root}/power/rc6_enable"))
                gpu["sleep_enabled"] = None if rc6 is None else rc6 != 0
                gpu["throttled"], gpu["throttle_reasons"] = _intel_throttle(root)
                _intel_usage(gpu, busy)
                # Only to the integrated GPU: the power plane is the one the
                # processor keeps for its GPU, and giving it to a dedicated card
                # would credit it with another's power.
                if watts is not None and gpu.get("integrated"):
                    gpu["power_w"] = watts
                if gpu.get("integrated") is False:
                    # An Arc: the helper only opens the integrated GPU's
                    # counter, and Intel's notices speak of that one. What
                    # really happens with this one is said.
                    draft.note(f"gpus.{index}.usage", Need.HARDWARE,
                               _("prov.drm.arcusage"), _("prov.drm.arcusage.hint"))
                else:
                    self._intel_notices(draft, index, gpu)
        self._with_instants = with_instants
        self._with_clock = with_clock
        # Those of a card that went to sleep or vanished do not wait for it
        # to come back: they would be from another time.
        current_ones = set(with_instants) | {pair[0] for pair in with_clock}
        self._readings = {k: v for k, v in self._readings.items() if k[0] in current_ones}

    def _asleep(self, gpu: dict, node: str) -> None:
        """A suspended card: nothing is asked of it.

        Not usage, clocks, hwmon or link: any of them wakes it, and every
        sample would keep it awake. The link read at startup is no longer the
        current one, so the current part goes and what the card supports stays.
        """
        gpu["suspended"] = True
        link = gpu.get("link") or PcieLink()
        gpu["link"] = dataclasses.replace(link, current_speed_gts=None,
                                          current_width=None)
        if (last := self._awake.get(node)) is not None:
            gpu["last_awake_s"], gpu["last_temp_c"] = last

    # -- the kernel's busy counter ------------------------------------------

    def _counters(self, interval_s: float) -> tuple[Optional[dict[str, dict[str, float]]],
                                                      Optional[float]]:
        """Each engine's busy share in percent, and the watts.

        The helper returns counters accumulated since it opened them; what
        matters comes from subtracting the previous pass and dividing by the
        window. The first reading only sets the base, like CPU usage.
        """
        helper_client = self.client
        if self._pmu_silent or helper_client is None or not helper_client.connected():
            return None, None

        try:
            clock, raw, scales = helper_client.gpu_pmu()
        except PmuUnsupported:
            # This machine has no GPU counters: not asked again every sample
            # for something that will not appear.
            self._pmu_silent = True
            return None, None
        except HelperError:
            # A single failure loses nothing: the pipe may have broken and the
            # user may authorize again.
            return None, None

        self._pmu_ok = True
        self._pmu_read = {pmu for pmu, events in raw.items()
                            if any(BUSY_EVENT.match(e) for e in events)}
        previous, self._pmu_previous = self._pmu_previous, (clock, raw)
        if previous is None:
            return None, None
        previous_clock, previous_raw = previous
        seconds = window_s(previous_clock / 1e9, clock / 1e9, interval_s)
        if seconds is None:
            return None, None
        window = seconds * 1e9

        out: dict[str, dict[str, float]] = {}
        watts = None
        for pmu, events in raw.items():
            before_counts = previous_raw.get(pmu, {})
            for event, amount in events.items():
                before = before_counts.get(event)
                grown = None if before is None else increase(before, amount)
                if grown is None:
                    continue                  # a new or restarted counter
                if (pmu, event) == ENERGY_PMU:
                    scale = scales.get(pmu, {}).get(event)
                    if scale:
                        # The counter is in joules once scaled, and a watt is
                        # a joule per second.
                        watts = grown * scale * 1e9 / window
                        # The integrated GPU is part of the package: it cannot
                        # draw more than the package can.
                        if self._ceiling is None:
                            self._ceiling = package_ceiling_w()
                        if not self._discarded.check(watts, self._ceiling, before, amount,
                                                     window / 1e9):
                            watts = None
                    continue
                # Capped at 100: in very short windows the counter and the clock
                # do not start aligned and a bit more comes out.
                percent = grown * 100.0 / window
                out.setdefault(pmu, {})[event] = min(100.0, max(0.0, percent))
        return out, watts

    def _intel_clock(self, device: pathlib.Path, root: pathlib.Path,
                     clocks: GpuClocks, asleep: Optional[float]) -> GpuClocks:
        """The engine's clock over the interval, not one reading.

        `act_freq` reads 0 whenever the GPU is in RC6, which during a video is
        most of the time: one reading a second went 0/1050/0/450/1100 MHz
        with a 4K60 video. RC6 is sleep, not a 0 MHz clock, so the figure is
        the mean of the readings that found it awake (one every 250 ms and
        this one). With none awake it is asleep (0), unless RC6 says it worked
        part of the interval unseen: then the frequency the driver asked for,
        the one it wakes up at.
        """
        readings = self._readings.pop((device, "core_hz"), [])
        if clocks.core_hz is not None:
            readings.append(clocks.core_hz)
        if not readings:
            return clocks
        awake = [hz for hz in readings if hz]
        if awake:
            hz = round(sum(awake) / len(awake) / 1e6) * 1_000_000
        elif asleep is not None and asleep < ASLEEP_ALL_THE_INTERVAL:
            hz = _intel_hz(device, root, "req") or 0
        else:
            hz = 0
        return dataclasses.replace(clocks, core_hz=hz)

    def _idle(self, node: str, root: pathlib.Path, interval_s: float) -> Optional[float]:
        """How much of the interval the GPU slept entirely.

        Intel's RC6, from sysfs without permissions: a counter of accumulated
        milliseconds, subtracted from the previous pass. It is not «100 minus
        usage»: between working and sleeping there is a middle state (on and
        waiting) that costs power and does not count here.
        """
        accumulated = _first(read_int(f"{root}/gt/gt0/rc6_residency_ms"),
                             read_int(f"{root}/power/rc6_residency_ms"),
                             read_int(f"{root}/device/tile0/gt0/gtidle/idle_residency_ms"))
        if accumulated is None:
            return None
        now = time.monotonic()
        previous, self._rc6[node] = self._rc6.get(node), (now, accumulated)
        if previous is None:
            return None
        before, asleep_time = previous
        seconds = window_s(before, now, interval_s)
        grown = increase(asleep_time, accumulated)
        if seconds is None or grown is None:
            return None
        return min(100.0, max(0.0, grown * 100.0 / (seconds * 1000.0)))

    def _intel_notices(self, draft: Draft, index: int, gpu: dict) -> None:
        """Why that card has gaps, by what can be read today.

        With the helper running, what is said depends on this card: its
        counters came, the kernel does not publish them, or it does and they
        could not be opened (why is not known from here).
        """
        pmu = _pmu_of(gpu) or ""
        helper_client = self.client
        if helper_client is None or not helper_client.connected():
            # What was read before the helper went is not being read now:
            # the permissions are missing again.
            entry_key = "root"
        elif self._pmu_ok and pmu in self._pmu_read:
            return
        elif self._pmu_ok or self._pmu_silent:
            entry_key = "unopened" if _pmu_published(pmu) else "driver"
        else:
            entry_key = "root"
        message, hint, detail = (_(k) if k else "" for k in INTEL_NOTICES[entry_key])
        draft.note(f"gpus.{index}", NEED_INTEL[entry_key], message, hint,
                   what=_("what.gpu.usage") if entry_key == "root" else "",
                   detail=detail.format(pmu=pmu or "?"))


# The kernel not publishing a card's counters is not a module to load.
NEED_INTEL = {"root": Need.ROOT, "driver": Need.HARDWARE, "unopened": Need.ERROR}


def _pmu_published(item_name: str) -> bool:
    """Whether the kernel publishes busy counters for that PMU."""
    if not item_name:
        return False
    try:
        events = os.listdir(sysroot.path(f"{EVENT_SOURCE}/{item_name}/events"))
    except OSError:
        return False
    return any(BUSY_EVENT.match(e) for e in events)


def _intel_engines(root: pathlib.Path) -> tuple[GpuEngine, ...]:
    """Which engines the card has and what each can do.

    From `engine/` in the DRM node, without permissions: identity, not
    telemetry. The capabilities matter (`hevc` says it decodes H.265 in
    hardware, `sfc` that it has a scaler) and come out nowhere else.
    """
    folder = root / "engine"
    if not folder.is_dir():
        return ()
    engines = []
    for node in sorted(folder.iterdir()):
        item_name = node.name
        family = re.match(r"^([a-z]+)\d+$", item_name)
        capabilities = (read_text(f"{node}/capabilities") or "").split()
        engines.append(GpuEngine(
            name=item_name,
            kind=INTEL_ENGINES.get(family.group(1)) if family else None,
            capabilities=tuple(capabilities),
        ))
    return tuple(engines)


def _pmu_of(gpu: dict) -> Optional[str]:
    """The name the kernel publishes this GPU's PMU under.

    i915 registers the integrated GPU with a fixed name. xe appends the PCI
    slot, with the colons turned into underscores.
    """
    driver = gpu.get("driver")
    slot = gpu.get("pci_slot")
    if driver == "i915":
        # The short name is the integrated GPU's only; any other carries its
        # slot (i915_pmu.c: `is_igp` is 0000:00:02.0, otherwise «i915_» and
        # dev_name with colons as underscores). With «i915» for all, an Arc
        # showed the integrated GPU's usage.
        if slot in (None, "0000:00:02.0"):
            return "i915"
        return f"i915_{slot.replace(':', '_')}"
    if driver == "xe":
        return f"xe_{slot.replace(':', '_')}" if slot else None
    return None


def _intel_usage(gpu: dict, busy: Optional[dict]) -> None:
    """Spread the PMU's engines over the model's percentages.

    The summary takes the maximum, not the sum: with several engines of one
    kind, the sum would pass 100 % without the card being maxed out. The
    per-engine detail is kept apart, where «the GPU gives no more» and «only
    video is loaded» can be told apart.
    """
    engines = (busy or {}).get(_pmu_of(gpu) or "")
    if not engines:
        return
    render = [v for e, v in engines.items() if e.startswith(("rcs", "ccs"))]
    video = [v for e, v in engines.items() if e.startswith(("vcs", "vecs"))]
    if render:
        gpu["busy_percent"] = max(render)
    if video:
        gpu["video_busy_percent"] = max(video)

    gpu["engines"] = tuple(
        dataclasses.replace(engine, busy_percent=engines.get(f"{engine.name}-busy"))
        for engine in gpu.get("engines") or ()
    )


# -- reading fields ---------------------------------------------------------

def _hex(path: pathlib.Path) -> Optional[int]:
    raw = read_text(str(path))
    if not raw:
        return None
    try:
        return int(raw, 16)
    except ValueError:
        return None


# amdgpu's usage counters, which give an instant and not a mean: the model's
# field and its file in the PCI node.
INSTANT_USAGE = (("busy_percent", "gpu_busy_percent"),
                   ("memory_busy_percent", "mem_busy_percent"),
                   ("video_busy_percent", "vcn_busy_percent"))


def _percent(path: pathlib.Path) -> Optional[float]:
    amount = read_int(str(path))
    return float(amount) if amount is not None else None


def _slot(device: pathlib.Path) -> Optional[str]:
    try:
        return device.resolve().name          # 0000:0c:00.0
    except OSError:
        return None


# The drivers that belong to no card: the fallback the kernel sets up to have
# a picture when the real driver is not there. They read no sensors, give no
# clocks and do not know the chip below, so their card would be all dashes.
# They show when booting with `nomodeset`, with the driver not installed
# (typical with a new NVIDIA) or with a card newer than the kernel.
GENERIC_FRAMEBUFFER = frozenset({
    "simple-framebuffer", "simpledrm", "vesafb", "efifb", "offb", "vga16fb",
})

# A graphics card's PCI classes: VGA controller and 3D controller. The second
# is laptops' dedicated GPUs, which have no video output.
GRAPHICS_CLASSES = (0x030000, 0x030200)


def _gpus_on_bus() -> list[pathlib.Path]:
    """The cards on the PCI bus, with a driver loaded or not.

    It lets one say «you have a GeForce RTX 3050» on a machine where the
    kernel stayed on the fallback framebuffer: the bus lists the hardware even
    with nobody able to talk to it.
    """
    root = pathlib.Path(sysroot.path("/sys/bus/pci/devices"))
    found = []
    for device in sorted(root.glob("*")) if root.is_dir() else ():
        pci_class = _hex(device / "class")
        if pci_class is not None and (pci_class & 0xFFFF00) in (
                c & 0xFFFF00 for c in GRAPHICS_CLASSES):
            found.append(device)
    return found


def _driver(device: pathlib.Path) -> Optional[str]:
    link = device / "driver"
    try:
        return link.resolve().name if link.exists() else None
    except OSError:
        return None


def _pcie_chain(device: pathlib.Path) -> list[pathlib.Path]:
    """The device and every bridge it goes through up to the root.

    The whole chain is needed because the link that counts is the slowest
    hop's. Modern cards carry a PCIe switch inside, whose inner side
    negotiates at the chip's speed even if the board's port cannot: an RX
    9070 XT says 32 GT/s inside while it talks to the system at 16. Showing
    the inside number tells the user they have PCIe 5.0 on a board without
    it.
    """
    # The device itself always goes in, address or not: a SoC's GPU hangs
    # from the platform tree, not a PCI bus, and only what it publishes is
    # there.
    current = device.resolve()
    hops = [current]
    current = current.parent
    while re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", current.name):
        hops.append(current)
        current = current.parent
    return hops


# The only link widths PCIe has. Any other figure in sysfs is a sentinel,
# not a value.
PCIE_WIDTHS = frozenset({1, 2, 4, 8, 12, 16, 32})


def _arc_behind_its_switch(device: pathlib.Path) -> bool:
    """An Intel GPU with bridges above it: a dedicated Arc.

    Arc A and B carry a PCIe switch inside, and the GPU and the switch's
    inner downstream port always publish 2.5 GT/s × 1 (Intel documents it in
    article 000094587, from the A380 to the B580); the real link is the
    switch's outer side, with the board. Which bridge that side is cannot be
    told for sure without a dump: with the port on the chipset there is
    another Intel bridge between, and a Core's root port is Intel's too.
    Better no link than «PCIe 1.0 × 1».

    The integrated GPU lives at 00:02.0, under the root with no bridges above.
    """
    node = device.resolve()
    if (read_text(f"{node}/vendor") or "").lower() != "0x8086":
        return False
    if not (read_text(f"{node}/class") or "").startswith("0x03"):
        return False
    return len(_pcie_chain(device)) > 1


_AER_FILES = (("correctable_errors", "aer_dev_correctable", "TOTAL_ERR_COR"),
              ("nonfatal_errors", "aer_dev_nonfatal", "TOTAL_ERR_NONFATAL"),
              ("fatal_errors", "aer_dev_fatal", "TOTAL_ERR_FATAL"))


def _aer(device: pathlib.Path) -> dict[str, Optional[int]]:
    """The device's AER totals. Counters, so they are read on every sample:
    an error in the middle of a session has to show up then."""
    errors: dict[str, Optional[int]] = {}
    for key, name, total in _AER_FILES:
        errors[key] = None
        for line in (read_text(f"{device}/{name}") or "").splitlines():
            label, _space, value = line.partition(" ")
            if label == total and value.strip().isdigit():
                errors[key] = int(value)
    return errors


def _link(device: pathlib.Path, previous: Optional[PcieLink] = None) -> PcieLink:
    if _arc_behind_its_switch(device):
        return PcieLink(**_aer(device))
    # Once per call and not once per figure: resolving sysfs links up to the
    # root is the costliest part of reading a link.
    chain = _pcie_chain(device)
    def speed(node: pathlib.Path, item_name: str) -> Optional[float]:
        raw = read_text(f"{node}/{item_name}")
        if not raw:
            return None
        match = _SPEED.search(raw)
        return float(match.group(1)) if match else None

    def minimum(item_name: str, read_one) -> Optional[float]:
        amounts = [v for node in chain if (v := read_one(node, item_name)) is not None]
        return min(amounts) if amounts else None

    def width(node: pathlib.Path, item_name: str) -> Optional[int]:
        """The lane count, dropping what is not a lane count.

        A device not on a real PCIe bus (an integrated GPU) publishes the
        files anyway, with sentinels: 0 without a link and 255 (0xFF) when not
        known. Unfiltered, an integrated GPU declared a 255-lane link.
        """
        amount = read_int(f"{node}/{item_name}")
        return amount if amount in PCIE_WIDTHS else None
    max_seen = (previous.max_speed_gts if previous else None) or minimum("max_link_speed", speed)
    max_width = (previous.max_width if previous else None) or minimum("max_link_width", width)
    return PcieLink(
        current_speed_gts=minimum("current_link_speed", speed),
        current_width=(lambda v: int(v) if v is not None else None)(minimum("current_link_width", width)),
        # The ceiling does not change; on resampling the one read stays.
        max_speed_gts=max_seen,
        max_width=int(max_width) if max_width is not None else None,
        **_aer(device),
    )


def _total_memory(device: pathlib.Path) -> GpuMemory:
    return GpuMemory(
        total_bytes=read_int(f"{device}/mem_info_vram_total"),
        visible_bytes=read_int(f"{device}/mem_info_vis_vram_total"),
        gtt_total_bytes=read_int(f"{device}/mem_info_gtt_total"),
        vendor=read_text(f"{device}/mem_info_vram_vendor"),
    )


def _used_memory(device: pathlib.Path, previous_value: GpuMemory) -> GpuMemory:
    return dataclasses.replace(
        previous_value,
        used_bytes=read_int(f"{device}/mem_info_vram_used"),
        visible_used_bytes=read_int(f"{device}/mem_info_vis_vram_used"),
        gtt_used_bytes=read_int(f"{device}/mem_info_gtt_used"),
    )


def _levels(path: pathlib.Path) -> tuple[GpuClockLevel, ...]:
    """The DPM table: the GPU does not run at any clock, only at these."""
    raw = read_text(str(path))
    if not raw:
        return ()
    levels = []
    for text_line in raw.splitlines():
        match = _DPM_LEVEL.match(text_line)
        if not match or not match.group(1).isdigit():
            continue
        scale = 1_000_000_000 if match.group(3).upper() == "G" else 1_000_000
        levels.append(GpuClockLevel(
            index=int(match.group(1)),
            hz=int(float(match.group(2)) * scale),
            active=bool(match.group(4)),
        ))
    return tuple(levels)


def _first(*candidate_list: Optional[int]) -> Optional[int]:
    """The first that exists, even if zero.

    With `or` the most interesting reading was lost: a GPU really stopped
    reads 0 MHz, and that is not a missing value, it is the answer.
    """
    return next((c for c in candidate_list if c is not None), None)


def _clocks(device: pathlib.Path,
             node: Optional[pathlib.Path] = None) -> GpuClocks:
    core = _levels(device / "pp_dpm_sclk")
    memory = _levels(device / "pp_dpm_mclk")
    hwmon = _hwmon(device)
    frequencies = _labelled(hwmon, "freq")

    # hwmon gives the instant clock; the asterisked line is coarser but is
    # there without hwmon, as on Intel.
    active = lambda levels_list: next((n.hz for n in levels_list if n.active), None)
    return GpuClocks(
        core_hz=_first(frequencies.get("sclk"), active(core),
                         _intel_hz(device, node, "cur")),
        memory_hz=_first(frequencies.get("mclk"), active(memory)),
        core_max_hz=_first(max((n.hz for n in core), default=None),
                             _intel_hz(device, node, "max")),
        core_min_hz=_intel_hz(device, node, "min"),
        silicon_min_hz=_intel_hz(device, node, "RPn"),
        efficient_hz=_intel_hz(device, node, "RP1"),
        silicon_max_hz=_intel_hz(device, node, "RP0"),
        memory_max_hz=max((n.hz for n in memory), default=None),
        core_levels=core,
        memory_levels=memory,
        performance_level=read_text(f"{device}/power_dpm_force_performance_level"),
        other_levels=tuple((name, levels) for name in OTHER_DPM
                           if (levels := _levels(device / f"pp_dpm_{name}"))),
        power_profile=_power_profile(device),
        overdrive=_overdrive(device) if core else None,
    )


# The DPM tables beyond the core's and memory's, in the order shown.
OTHER_DPM = ("fclk", "socclk", "dcefclk", "vclk", "dclk")
# amdgpu.ppfeaturemask's PP_OVERDRIVE_MASK (amd_shared.h).
OVERDRIVE_BIT = 0x4000


def _power_profile(device: pathlib.Path) -> Optional[str]:
    """The profile marked with «*» in `pp_power_profile_mode`."""
    for line in (read_text(str(device / "pp_power_profile_mode")) or "").splitlines():
        match = re.match(r"\s*\d+\s+([A-Z0-9_]+)\s*\*", line)
        if match:
            return match.group(1)
    return None


def _overdrive(device: pathlib.Path) -> Optional[bool]:
    """On when the driver publishes its OverDrive table; off when its feature
    mask leaves it out. Unknown otherwise."""
    if os.path.exists(sysroot.path(f"{device}/pp_od_clk_voltage")):
        return True
    mask = read_text("/sys/module/amdgpu/parameters/ppfeaturemask")
    try:
        return bool(int(mask, 0) & OVERDRIVE_BIT) if mask else None
    except ValueError:
        return None


# Why an Intel GPU throttles, as i915 publishes it in `gt/gt0/`: one file per
# reason, 0 or 1. Only on recent generations; a Comet Lake has none. Silux
# names them, so they are translated.
INTEL_REASONS = (
    ("pl1", "gpu.throttle.intel.pl1"),
    ("pl2", "gpu.throttle.intel.pl2"),
    ("pl4", "gpu.throttle.intel.pl4"),
    ("thermal", "gpu.throttle.intel.thermal"),
    ("prochot", "gpu.throttle.intel.prochot"),
    ("ratl", "gpu.throttle.intel.ratl"),
    ("vr_thermalert", "gpu.throttle.intel.vrthermal"),
    ("vr_tdc", "gpu.throttle.intel.vrtdc"),
)


def _intel_throttle(node: pathlib.Path) -> tuple[Optional[bool], tuple[str, ...]]:
    """Whether the GPU is throttling and why, or (None, ()) if it does not say.

    `throttle_reason_status` is the summary; the others, each reason. Written
    from the kernel's documentation: a UHD 630 has none of them.
    """
    base = f"{node}/gt/gt0/throttle_reason"
    state = read_int(f"{base}_status")
    if state is None:
        return None, ()
    reasons = []
    for reason, entry_key in INTEL_REASONS:
        if read_int(f"{base}_{reason}"):
            reasons.append(entry_key)
    return bool(state) or bool(reasons), tuple(reasons)


# How xe names the silicon's clocks, which i915 calls RP0, RP1 and RPn.
# xe's `cur_freq` is the requested one, as i915's `cur`; the actual is `act_freq`.
_XE = {"RP0": "rp0", "RP1": "rpe", "RPn": "rpn", "cur": "act", "req": "cur"}
# RC6 above this share of the interval is having slept all of it.
ASLEEP_ALL_THE_INTERVAL = 99.0


def _intel_hz(device: pathlib.Path, node: Optional[pathlib.Path],
              which: str) -> Optional[int]:
    """An Intel graphics engine's clocks, whatever they are called.

    They moved twice and neither old path is fully gone, so all four are
    looked at:

    - classic i915 puts them loose in the DRM node, not the PCI node; looking
      in `device/`, the link to the PCI device, missed them.
    - i915 since kernel 5.19 puts them in `gt/gt0/` with the `rps_` prefix,
      to allow more than one graphics engine per card.
    - xe, the new driver, uses another hierarchy.

    A zero is returned as is when it is the current clock: an integrated GPU
    in deep idle turns its engine off and reads 0, which is the answer, not
    a missing one. In a maximum or minimum it is an unfilled field: nobody
    has a 0 MHz ceiling.
    """
    current = which in ("cur", "act")

    def scale_value(mhz: Optional[int]) -> Optional[int]:
        if mhz is None or (mhz == 0 and not current):
            return None
        return mhz * 1_000_000

    if node is not None:
        # `act` is the one it really runs at; `cur` is the requested one. The
        # maximum has no such distinction. `req` is the requested one by name.
        measure = {"cur": "act", "req": "cur"}.get(which, which)
        for path in (f"{node}/gt/gt0/rps_{measure}_freq_mhz",
                     f"{node}/gt/gt0/rps_{which}_freq_mhz",
                     f"{node}/gt_{measure}_freq_mhz",
                     f"{node}/gt_{which}_freq_mhz"):
            if (mhz := read_int(path)) is not None:
                return scale_value(mhz)

    mhz = read_int(f"{device}/gt_{which}_freq_mhz")
    if mhz is None:
        # xe, Intel's new driver, moves them inside the gt hierarchy.
        mhz = read_int(f"{device}/tile0/gt0/freq0/{_XE.get(which, which)}_freq")
    return scale_value(mhz)


# -- the card's own hwmon ---------------------------------------------------

def _hwmon(device: pathlib.Path) -> Optional[pathlib.Path]:
    folder_path = device / "hwmon"
    if not folder_path.is_dir():
        return None
    return next(iter(sorted(folder_path.glob("hwmon*"))), None)


def _labelled(hwmon: Optional[pathlib.Path], prefix: str) -> dict[str, int]:
    """The hwmon channels that carry a label, indexed by it.

    Cards do not order their temperatures the same, so looking them up by
    number (`temp1`, `temp2`) is a lottery; by label (`edge`, `junction`,
    `mem`) it always lands right.
    """
    if hwmon is None:
        return {}
    amounts = {}
    for label_text in sorted(hwmon.glob(f"{prefix}*_label")):
        item_name = read_text(str(label_text))
        item = read_int(str(label_text).replace("_label", "_input"))
        if item_name and item is not None:
            amounts[item_name.lower()] = item
    return amounts


def _sensors(gpu: dict, device: pathlib.Path) -> None:
    hwmon = _hwmon(device)
    if hwmon is None:
        return

    temperatures = _labelled(hwmon, "temp")
    milli = lambda v: round(v / 1000, 1) if v is not None else None
    # «edge» on amdgpu; «pkg» on xe, the GPU package's (xe_hwmon.c labels the
    # package channel so, and «vram» the memory's).
    gpu["temp_c"] = milli(_first(temperatures.get("edge"), temperatures.get("pkg")))
    gpu["hotspot_c"] = milli(_first(temperatures.get("junction"),
                                     temperatures.get("hotspot")))
    gpu["memory_temp_c"] = milli(_first(temperatures.get("mem"),
                                         temperatures.get("vram")))

    if gpu["temp_c"] is None:
        # Intel and virtual GPUs do not label: there the first channel is right.
        gpu["temp_c"] = milli(read_int(f"{hwmon}/temp1_input"))

    micro = _first(read_int(f"{hwmon}/power1_average"),
                     read_int(f"{hwmon}/power1_input"))
    gpu["power_w"] = round(micro / 1_000_000, 1) if micro is not None else None
    cap = read_int(f"{hwmon}/power1_cap")
    gpu["power_cap_w"] = round(cap / 1_000_000, 1) if cap is not None else None
    for key, name in (("power_cap_default_w", "power1_cap_default"),
                      ("power_cap_min_w", "power1_cap_min"), ("power_cap_max_w", "power1_cap_max")):
        micro = read_int(f"{hwmon}/{name}")
        gpu[key] = round(micro / 1_000_000, 1) if micro is not None else None

    gpu["fan_rpm"] = read_int(f"{hwmon}/fan1_input")
    pwm = read_int(f"{hwmon}/pwm1")
    maximum = read_int(f"{hwmon}/pwm1_max") or 255
    gpu["fan_percent"] = round(pwm / maximum * 100, 1) if pwm is not None else None

    voltages = _labelled(hwmon, "in")
    millivolts = _first(voltages.get("vddgfx"), voltages.get("vddnb"))
    gpu["voltage_v"] = round(millivolts / 1000, 3) if millivolts is not None else None


def _telemetry(gpu: dict, device: pathlib.Path,
                draft: Draft, index: int) -> None:
    """What only the firmware tells: why it throttles and how fast it really runs.

    Applied on top of what hwmon read, not instead: hwmon is on every card
    and this only on recent AMD ones, so it fills gaps and adds its own.
    """
    measures = gpumetrics.read(device)
    if measures is None:
        # A version that cannot be read is not the same as having no table,
        # and both ended in the same silence: the user saw empty throttle
        # reasons and voltages with nothing to explain them.
        if (new_value := gpumetrics.uninterpreted(device)) is not None:
            version, _size = new_value
            draft.note(f"gpus.{index}.metrics", Need.DATABASE,
                       _("prov.drm.metricsnew").format(version=version),
                       _("prov.drm.metricsnew.hint"))
            gpu["metrics_version"] = version
        return

    gpu["throttled"] = measures.throttled
    gpu["throttle_reasons"] = measures.throttle_reasons
    gpu["vr_gfx_c"] = measures.temp_vr_gfx_c
    gpu["vr_soc_c"] = measures.temp_vr_soc_c
    gpu["vr_memory_c"] = measures.temp_vr_mem_c
    gpu["voltage_soc_v"] = measures.voltage_soc_v
    gpu["voltage_memory_v"] = measures.voltage_memory_v

    clocks: GpuClocks = gpu.get("clocks") or GpuClocks()
    gpu["clocks"] = dataclasses.replace(
        clocks,
        memory_effective_hz=measures.memory_clock_effective_hz,
        soc_hz=measures.soc_clock_hz,
        core_hz=_first(clocks.core_hz, measures.gfx_clock_hz),
        memory_hz=_first(clocks.memory_hz, measures.memory_clock_hz),
    )
    for field, amount in (("busy_percent", measures.gfx_activity_percent),
                         ("memory_busy_percent", measures.memory_activity_percent),
                         ("video_busy_percent", measures.video_activity_percent),
                         ("temp_c", measures.temp_edge_c),
                         ("hotspot_c", measures.temp_hotspot_c),
                         ("memory_temp_c", measures.temp_memory_c),
                         ("power_w", measures.socket_power_w),
                         ("voltage_v", measures.voltage_gfx_v)):
        if gpu.get(field) is None and amount is not None:
            gpu[field] = amount


def _outputs(card: str) -> tuple[Display, ...]:
    """This card's video connectors, plugged in or not."""
    root = pathlib.Path(sysroot.path(SYS_DRM))
    outputs = []
    for connector in sorted(root.glob(f"{card}-*")):
        item_name = connector.name[len(card) + 1:]
        if item_name.startswith("Writeback"):
            continue                   # not an output, an internal target
        state = (read_text(f"{connector}/status") or "").lower()
        plate = edid.read(connector)
        width = high = None
        if plate and plate.native_width:
            # The EDID beats `modes`: it says the real native resolution.
            width, high = plate.native_width, plate.native_height
        elif modes := read_text(f"{connector}/modes"):
            # The first line is the monitor's preferred mode.
            first_one = modes.splitlines()[0].strip()
            if match := re.fullmatch(r"(\d+)x(\d+)\D*", first_one):
                width, high = int(match.group(1)), int(match.group(2))
        outputs.append(Display(
            connector=item_name,
            connected=state == "connected",
            enabled=(read_text(f"{connector}/enabled") or "").lower() == "enabled",
            width=width,
            height=high,
            refresh_hz=plate.native_refresh_hz if plate else None,
            monitor=plate,
        ))
    return tuple(outputs)


def _name_monitors(gpus: list[dict]) -> None:
    """Turn the EDID's three letters into names, for every screen.

    Done at the end and at once: `pnp.ids` is 63 kB, not worth walking once
    per monitor.
    """
    plates = [d.monitor for gpu in gpus for d in gpu.get("displays", ()) if d.monitor]
    if not plates:
        return
    names = edid.resolve_vendors(plates)
    if not names:
        return
    for gpu in gpus:
        gpu["displays"] = tuple(
            dataclasses.replace(out, monitor=dataclasses.replace(
                out.monitor,
                manufacturer=names.get(out.monitor.manufacturer_id)))
            if out.monitor else out
            for out in gpu.get("displays", ())
        )
