"""The data model: typed values, never already formatted text.

Everything here is immutable. A `Snapshot` is a complete photo of the
system at one instant; the interface compares two consecutive snapshots to
know what to repaint, and the JSON exporter serializes one with no extra
work.

Field names carry their unit (`freq_hz`, `size_bytes`, `temp_c`) so there's
no doubt what each holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Optional

from .edid import Edid, VideoMode  # noqa: F401  (re-exported by the model)
from .spd import SpdInfo, Timings  # noqa: F401  (re-exported by the model)


class Need(str, Enum):
    """Why a datum is missing. What the interface shows the user."""

    ROOT = "root"            # privileges must be elevated
    DATABASE = "database"    # the hardware isn't in the database
    HARDWARE = "hardware"    # this machine just doesn't expose it
    DRIVER = "driver"        # a kernel module would have to be loaded
    PLATFORM = "platform"    # doesn't apply to this architecture
    ERROR = "error"          # failed to read; that is our own failure
    KERNEL = "kernel"        # this machine's kernel predates the datum
    PACKAGE = "package"      # a package of the system is not installed (system_deps)


@dataclass(frozen=True, slots=True)
class Note:
    """Explains why one specific datum is missing, with its reason."""

    path: str          # e.g. "cpu.voltage_v"
    need: Need
    message: str
    hint: str = ""     # what the user can do about it
    # What's missing, in three words: «Disk health». The provider sets it on
    # the notes the privileged helper can resolve, and it lets them be listed
    # together without deducing anything from the path.
    what: str = ""
    # It needs permissions and the installed helper is from another version:
    # what fixes it is updating the helper, not giving permissions.
    helper_outdated: bool = False
    # Where it was looked for (a path, a driver's register, a PMU): for the
    # report, never on screen, where a message is said in plain words.
    detail: str = ""
    # The key of its message: what decides on a note looks at this, never at
    # the message, which is in the interface's language.
    key: str = ""


@dataclass(frozen=True, slots=True)
class Failure:
    """A failure of Silux's own code, with its traceback, for the report."""

    where: str         # the provider, or the provider and the step
    error: str         # «KeyError: 'temp1'»
    trace: str
    count: int = 1     # the same failure again only counts


# --------------------------------------------------------------------------
# CPU
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cache:
    level: int
    kind: str                       # "data" | "instruction" | "unified"
    size_bytes: int
    ways: Optional[int] = None
    line_bytes: Optional[int] = None
    sets: Optional[int] = None
    instances: int = 1              # how many there are for this core type
    shared_by: int = 1              # logical CPUs sharing each instance
    # Which logical CPUs share each instance. It lets the hierarchy map be
    # drawn: without it only how many is known, not which.
    instance_cpus: tuple[tuple[int, ...], ...] = ()

    @property
    def total_bytes(self) -> int:
        return self.size_bytes * self.instances


@dataclass(frozen=True, slots=True)
class Clocks:
    current_hz: Optional[int] = None      # mean of this type's cores
    min_hz: Optional[int] = None
    max_hz: Optional[int] = None          # the effective ceiling the kernel applies
    base_hz: Optional[int] = None
    # The base at the TDP the machine is configured to now (intel_pstate's
    # `base_frequency`, HWP's guaranteed performance). A laptop whose maker
    # sets a lower TDP gets a lower base than the specification's.
    base_configured_hz: Optional[int] = None
    max_turbo_hz: Optional[int] = None    # the silicon's ceiling, per CPUID 0x16
    bus_hz: Optional[int] = None          # BCLK / reference clock
    turbo_enabled: Optional[bool] = None
    # Whether the part has a turbo at all («cpb» on AMD, «ida» on Intel). Some
    # parts have none, and «Turbo: —» read as something unread.
    turbo_supported: Optional[bool] = None
    driver: Optional[str] = None
    governor: Optional[str] = None
    energy_preference: Optional[str] = None    # EPP: towards performance or towards saving
    # Where current_hz comes from: "cpufreq", or without a frequency driver
    # "cpuinfo" (/proc/cpuinfo) or "msr" (the processor's P-state).
    current_from: Optional[str] = None

    def _mult(self, hz: Optional[int]) -> Optional[float]:
        if not hz or not self.bus_hz:
            return None
        return round(hz / self.bus_hz, 1)

    @property
    def multiplier(self) -> Optional[float]:
        return self._mult(self.current_hz)

    @property
    def base_multiplier(self) -> Optional[float]:
        return self._mult(self.base_hz)

    @property
    def min_multiplier(self) -> Optional[float]:
        return self._mult(self.min_hz)

    @property
    def max_multiplier(self) -> Optional[float]:
        return self._mult(self.max_hz)

    @property
    def max_turbo_multiplier(self) -> Optional[float]:
        return self._mult(self.max_turbo_hz)

    @property
    def highest_hz(self) -> Optional[int]:
        """The highest it can go: the silicon's ceiling or the kernel's.

        Not `max_hz` alone: that's the ceiling the kernel applies now, and it
        changes on the fly when a power manager turns the turbo off and on.
        Whatever's drawn against it changes scale with each swing and clips
        what was measured before. The silicon's doesn't move; the kernel's is
        looked at too because some machines go past CPUID's.
        """
        return max(filter(None, (self.max_hz, self.max_turbo_hz)), default=None)

    @property
    def turbo_headroom_hz(self) -> Optional[int]:
        """How much frequency the current ceiling leaves unused against the silicon's."""
        if self.max_turbo_hz and self.max_hz and self.max_turbo_hz > self.max_hz:
            return self.max_turbo_hz - self.max_hz
        return None


@dataclass(frozen=True, slots=True)
class Power:
    """The package's power, broken down, with the hardware's limits.

    A single number leaves the user not knowing whether it's fine. The
    breakdown by domain and the limit the processor itself declares turn
    "7 W" into "7 of 65 W, and nearly all of it the cores".
    """

    package_w: Optional[float] = None
    core_w: Optional[float] = None
    uncore_w: Optional[float] = None
    dram_w: Optional[float] = None
    limit_long_w: Optional[float] = None       # PL1: the sustained one, usually the TDP
    limit_short_w: Optional[float] = None      # PL2: the peak for a few seconds
    # The time window each one is averaged over (Intel's tau for PL1): how
    # long the package can stay above PL1 before PL1 holds it back.
    window_long_s: Optional[float] = None
    window_short_s: Optional[float] = None
    # The higher of the two copies of each limit (MSR and MMIO) when they
    # differ: the processor enforces the lower one, the one above.
    limit_long_other_w: Optional[float] = None
    limit_short_other_w: Optional[float] = None

    @property
    def load_percent(self) -> Optional[float]:
        """What fraction of the sustained limit is in use."""
        if self.package_w is None or not self.limit_long_w:
            return None
        return round(100.0 * self.package_w / self.limit_long_w, 1)


@dataclass(frozen=True, slots=True)
class LogicalCpu:
    """A logical CPU: a thread, as the kernel sees it."""

    index: int
    core_id: int
    package_id: int
    type_key: str = "general"
    freq_hz: Optional[int] = None
    temp_c: Optional[float] = None
    usage_percent: Optional[float] = None
    # How well this core came out of the wafer, on ACPI CPPC's performance
    # scale. Not a frequency and can't be turned into one: a relative grade
    # among this part's cores. See `providers/cppc.py`.
    quality: Optional[int] = None


@dataclass(frozen=True, slots=True)
class CpuType:
    """A core type. A homogeneous CPU has one; a hybrid, two.

    Modelling it as a list from the start is deliberate: changing it later
    means rewriting the whole model and the whole interface.
    """

    key: str                    # "general" | "performance" | "efficiency"
    label: str                  # `render` decides it; this is only an identifier
    vendor: str = ""            # "Intel", "AMD"…
    vendor_id: str = ""         # "GenuineIntel"
    brand: str = ""             # CPUID's raw brand string
    codename: Optional[str] = None
    technology: Optional[str] = None
    socket: Optional[str] = None
    architecture: str = ""

    # CPUID splits family and model into a base and an extended field, for
    # historical reasons: when the base field's four bits ran out, the
    # extended ones were added and both must be recombined. The "disp" fields
    # are already the sum, which is what the maker publishes in its
    # datasheet; the others are the raw bits, only useful for debugging.
    # `signature` is leaf 1's whole EAX register.
    family: Optional[int] = None
    model: Optional[int] = None
    stepping: Optional[int] = None
    disp_family: Optional[int] = None
    disp_model: Optional[int] = None
    signature: Optional[int] = None

    virtualization: Optional[str] = None       # "VT-x", "AMD-V" or nothing
    in_virtual_machine: bool = False
    hypervisor: Optional[str] = None           # "VMware", "KVM"…: who's underneath

    cores: int = 0
    threads: int = 0
    cpus: tuple[int, ...] = ()
    smt: bool = False

    caches: tuple[Cache, ...] = ()
    features: tuple[str, ...] = ()
    clocks: Clocks = field(default_factory=Clocks)

    temp_c: Optional[float] = None
    voltage_v: Optional[float] = None
    microcode: Optional[str] = None

    def cache_at(self, level: int, kind: str | None = None) -> Optional[Cache]:
        for c in self.caches:
            if c.level == level and (kind is None or c.kind == kind):
                return c
        return None


@dataclass(frozen=True, slots=True)
class IdleState:
    """How much of the last interval the threads spent in an idle state.

    A datum that comes from subtracting two readings, like usage. `percent`
    is all threads' mean; `low` and `high`, the least and the most. The names
    are the kernel's («C1», «C2», «C6», «C10»): they change between makers
    and aren't translated.
    """

    name: str
    description: Optional[str] = None        # "ACPI FFH MWAIT 0x0"
    percent: float = 0.0
    low: float = 0.0
    high: float = 0.0


@dataclass(frozen=True, slots=True)
class ThermalThrottle:
    """Since boot, how many times and for how long the processor slowed down
    for temperature: the package as a whole, and its cores added up."""

    package_count: int = 0
    package_ms: int = 0
    core_count: int = 0
    core_ms: int = 0


@dataclass(frozen=True, slots=True)
class CpuInfo:
    sockets: int = 1
    hybrid: bool = False
    types: tuple[CpuType, ...] = ()
    logical: tuple[LogicalCpu, ...] = ()
    usage_percent: Optional[float] = None
    package_temp_c: Optional[float] = None
    power: Power = field(default_factory=Power)
    load_average: tuple[float, ...] = ()       # 1, 5 and 15 minutes
    idle_states: tuple[IdleState, ...] = ()
    thermal_throttle: Optional[ThermalThrottle] = None     # Intel only

    @property
    def in_virtual_machine(self) -> bool:
        """Inside a virtual machine: CPUID's «hypervisor» bit."""
        return any(t.in_virtual_machine for t in self.types)

    @property
    def package_power_w(self) -> Optional[float]:
        return self.power.package_w

    @property
    def temperature_c(self) -> Optional[float]:
        """The processor's temperature: the package's if there is one.

        It's the part's hottest point and the one fan control looks at; the
        cores' mean hides the hottest. Without a package sensor, the first
        core type's. Home and the CPU page ask for it here, so they can't
        disagree about the same snapshot.
        """
        if self.package_temp_c is not None:
            return self.package_temp_c
        return self.types[0].temp_c if self.types else None

    @property
    def cores_temp_c(self) -> Optional[float]:
        """The cores' mean, every kind of core weighted by how many it has.

        On a hybrid, the P cores alone read far hotter than the whole
        processor: the E cores run cooler.
        """
        measured = [(t.temp_c, t.cores) for t in self.types if t.temp_c is not None and t.cores]
        if not measured:
            return None
        return sum(temp * n for temp, n in measured) / sum(n for _temp, n in measured)

    @property
    def total_cores(self) -> int:
        return sum(t.cores for t in self.types)

    @property
    def total_threads(self) -> int:
        return sum(t.threads for t in self.types)


# --------------------------------------------------------------------------
# System
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Memory:
    """How memory is split, as /proc/meminfo tells it.

    There are two legitimate ways to count used memory, best kept apart:

    * `used_bytes` = total − available. `free`'s definition and any system
      monitor's: «how much couldn't be recovered even if it wanted». It
      includes the part of the cache that can't be reclaimed, such as tmpfs
      and shared memory.
    * `apps_bytes` = total − free − buffers − reclaimable cache. It lets a
      bar be drawn whose pieces add up exactly to the total.

    The first always comes out somewhat larger than the second, and it's not
    an error: the difference is exactly the cache the kernel can't give back.
    """

    total_bytes: int = 0
    available_bytes: int = 0
    free_bytes: int = 0
    buffers_bytes: int = 0
    cached_bytes: int = 0
    shared_bytes: int = 0
    reclaimable_bytes: int = 0          # SReclaimable: slab that is given back
    swap_total_bytes: int = 0
    swap_free_bytes: int = 0

    @property
    def used_bytes(self) -> int:
        return max(0, self.total_bytes - self.available_bytes)

    @property
    def cache_bytes(self) -> int:
        """The cache the kernel can give back if someone asks for memory."""
        return max(0, self.cached_bytes + self.reclaimable_bytes - self.shared_bytes)

    @property
    def apps_bytes(self) -> int:
        """What's neither free, nor buffers, nor reclaimable cache."""
        return max(0, self.total_bytes - self.free_bytes
                   - self.buffers_bytes - self.cache_bytes)

    @property
    def used_percent(self) -> float:
        return round(100.0 * self.used_bytes / self.total_bytes, 1) if self.total_bytes else 0.0

    @property
    def swap_used_bytes(self) -> int:
        return max(0, self.swap_total_bytes - self.swap_free_bytes)

    @property
    def swap_used_percent(self) -> float:
        if not self.swap_total_bytes:
            return 0.0
        return round(100.0 * self.swap_used_bytes / self.swap_total_bytes, 1)


@dataclass(frozen=True, slots=True)
class PciDevice:
    """Something on the PCI bus worth naming: a graphics card, a disk, a
    network card, a USB, SATA or sound controller.

    `name` is what silux already calls that part on its page (the disk's
    model, the graphics card) when it has one; otherwise `pci.ids`'.
    """

    slot: str                                # "0000:01:00.0"
    kind: str                                # "gpu" | "nvme" | "sata" | "ethernet" | "wifi" | "usb" | "audio"
    name: Optional[str] = None
    vendor: Optional[str] = None
    driver: Optional[str] = None
    # The link with the system, measured as on the Graphics page: the slowest
    # link of the chain up to the root, not what the device's node says.
    # None for what doesn't sit in a slot (USB, SATA, the board's sound).
    link: Optional["PcieLink"] = None
    # What the slot is called on the board, per the firmware's table. Only
    # with permissions, and only if its address matches this device.
    slot_name: Optional[str] = None
    # What the device itself says: with them, what `pci.ids` doesn't have
    # yet gets a name («Intel, audio HD (8086:f0c8)»).
    vendor_id: Optional[int] = None
    device_id: Optional[int] = None
    pci_class: Optional[str] = None          # class and subclass: "0403"


@dataclass(frozen=True, slots=True)
class Platform:
    """What the board and its firmware have enabled."""

    iommu_groups: Optional[int] = None       # None: no active IOMMU
    # "active": in use (/dev/kvm exists). "present": the processor has it and
    # it's not in use; the BIOS or a missing module. None: there's none.
    virtualization: Optional[str] = None
    virtualization_kind: Optional[str] = None      # "AMD-V" | "VT-x"
    # How many devices have memory mapped above 4 GB. One is enough to say
    # the option is on; zero proves nothing.
    above_4g_devices: int = 0
    sensor_chip: Optional[str] = None        # "it8688"
    audio_codec: Optional[str] = None        # "Realtek ALCS1200A"


@dataclass(frozen=True, slots=True)
class UsbDevice:
    """Something plugged in by USB. No serial number: it's never read."""

    port: str                                # "5-4.1.4": bus 5, port 4, and two hubs
    vendor: Optional[str] = None
    product: Optional[str] = None
    usb_id: Optional[str] = None             # "046d:c54d"
    kind: str = "other"                      # see `providers/devices.py`, `_kind`
    speed_mbps: Optional[float] = None       # the negotiated one: 1.5, 12, 480, 5000…
    version: Optional[str] = None            # the one the device declares: "2.00", "3.20"

    @property
    def parent(self) -> Optional[str]:
        """The hub it hangs from, or None if it goes to one of the machine's ports."""
        return self.port.rsplit(".", 1)[0] if "." in self.port else None

    @property
    def is_hub(self) -> bool:
        return self.kind == "hub"

    @property
    def slower_than_capable(self) -> bool:
        """A USB 3 device negotiating at 480 Mb/s or less: usually the cable or
        the port. A USB 2 one at 12 Mb/s is nothing: it does its own thing."""
        try:
            capable = float(self.version or 0) >= 3.0
        except ValueError:
            return False
        return bool(capable and self.speed_mbps and self.speed_mbps < 5000)


@dataclass(frozen=True, slots=True)
class SoundCard:
    name: Optional[str] = None               # the device's, if it's USB
    kind: str = "other"                      # "hdmi" | "board" | "usb" | "other"
    codec: Optional[str] = None              # "Realtek ALCS1200A"
    # The USB card is a camera's microphone: its device also has a video
    # interface. In the USB tree it shows as the camera, not as an audio
    # device, and without this the sound table had one too many.
    camera: bool = False


@dataclass(frozen=True, slots=True)
class Camera:
    name: Optional[str] = None
    nodes: int = 1                           # one device creates several /dev/video*
    virtual: bool = False                    # hangs from no bus


@dataclass(frozen=True, slots=True)
class BluetoothAdapter:
    name: str = "hci0"
    product: Optional[str] = None
    bus: Optional[str] = None                # "usb" | "board"
    powered: Optional[bool] = None


@dataclass(frozen=True, slots=True)
class Vulnerability:
    """A processor vulnerability per the running kernel.

    `status` is the kernel's text, untouched: it's what gets pasted into a
    search engine. `state` is what silux takes from it to count and warn.
    """

    name: str                    # "spectre_v2"
    status: str                  # "Mitigation: Retpolines; IBPB: conditional…"
    state: str                   # "unaffected" | "mitigated" | "vulnerable" | "unknown"


@dataclass(frozen=True, slots=True)
class Swap:
    """A swap space. If it's zram, with how it compresses."""

    device: str                              # "/dev/zram0", "/swapfile"
    kind: str                                # "partition" | "file"
    size_bytes: int = 0
    used_bytes: int = 0
    priority: Optional[int] = None
    zram: bool = False
    algorithm: Optional[str] = None          # "zstd"
    original_bytes: Optional[int] = None     # what was stored, before compressing
    compressed_bytes: Optional[int] = None   # what it takes compressed

    @property
    def ratio(self) -> Optional[float]:
        if not self.original_bytes or not self.compressed_bytes:
            return None
        return round(self.original_bytes / self.compressed_bytes, 1)


@dataclass(frozen=True, slots=True)
class Boot:
    """What the machine booted with and how long each phase took.

    The firmware's and loader's times are published by the boot managers
    that follow systemd's interface (systemd-boot, Limine) and, when the
    manager doesn't, by the firmware's FPDT table; the kernel's, initrd's
    and userspace's by systemd, with any manager.
    """

    loader: Optional[str] = None             # "Limine 12.10.0"
    entry: Optional[str] = None              # "CachyOS.linux-cachyos"
    firmware_s: Optional[float] = None       # from power-on to the loader
    loader_s: Optional[float] = None         # from the loader to the kernel
    kernel_s: Optional[float] = None         # from the kernel to the initrd (or to systemd)
    initrd_s: Optional[float] = None         # None if it booted without an initrd
    userspace_s: Optional[float] = None      # None while it hasn't finished
    # The kernel command line, parameter by parameter, with what identifies
    # the machine already hidden (privacidad.hide_cmdline_identifiers).
    cmdline: tuple[str, ...] = ()

    @property
    def total_s(self) -> Optional[float]:
        """From power-on: without the firmware and the loader there's no total."""
        if self.firmware_s is None or self.loader_s is None:
            return None
        return round(sum(f for f in (self.firmware_s, self.loader_s, self.kernel_s,
                                     self.initrd_s, self.userspace_s) if f is not None), 1)


@dataclass(frozen=True, slots=True)
class System:
    distribution: Optional[str] = None
    distribution_id: Optional[str] = None
    version_id: Optional[str] = None
    variant: Optional[str] = None

    kernel: Optional[str] = None
    kernel_build: Optional[str] = None
    architecture: Optional[str] = None

    hostname: Optional[str] = None
    init: Optional[str] = None
    desktop: Optional[str] = None
    session_type: Optional[str] = None
    shell: Optional[str] = None

    uptime_seconds: float = 0.0
    boot_time: Optional[str] = None

    processes: int = 0
    threads: int = 0
    open_files: int = 0
    # /proc/sys/kernel/tainted, the bit mask; None when it can't be read.
    tainted: Optional[int] = None
    # The modules that tainted it, with their letters from
    # /sys/module/<name>/taint: (("nvidia", "PO"),).
    tainting_modules: tuple[tuple[str, str], ...] = ()

    memory: Memory = field(default_factory=Memory)

    vulnerabilities: tuple[Vulnerability, ...] = ()
    swaps: tuple[Swap, ...] = ()
    boot: Boot = field(default_factory=Boot)


# How far a module's running speed may differ from its declared one without
# being a real underclock. It's the JEDEC grade's rounding and nothing else:
# some firmware writes 2666 and some 2667 for the same memory.
#
# 1 % can't confuse two grades: neighbours are at least 133 MT/s apart in
# DDR4 (2400, 2666, 2933) and 400 in DDR5. And it easily absorbs the
# rounding, at most one MT/s.
ROUNDING_MARGIN = 0.01


# SMBIOS type 17 form factors (DSP0134 table 75) of memory that is part of
# the board: Chip, Row of chips and Die. Codes, as the table gives them.
SOLDERED_FORM_FACTORS = (0x05, 0x0B, 0x10)
FORM_FACTOR_SODIMM = 0x0D
# SMBIOS memory type 1Fh, the only one that is not a technology's name: said
# in the interface's language when painting (`render.memory_type`).
LOGICAL_NON_VOLATILE = "logical-non-volatile"


# The fastest JEDEC speed of each desktop memory type (JESD79-3, JESD79-4 and
# JESD79-5C); anything above is a maker's profile. Soldered LPDDR has no
# profiles and is left out.
JEDEC_TOP_MTS = {"DDR3": 2133, "DDR4": 3200, "DDR5": 8800}


@dataclass(frozen=True, slots=True)
class MemoryModule:
    """A memory slot, occupied or not.

    Empty slots show too: knowing two are free is half the reason someone
    opens this tab.
    """

    locator: Optional[str] = None            # "DIMM A1"
    bank: Optional[str] = None               # "P0 CHANNEL A"
    populated: bool = False
    size_bytes: int = 0
    type: Optional[str] = None               # "DDR4"
    # SMBIOS type 17 form factor code: 09h DIMM, 0Dh SODIMM, 0Bh row of chips.
    form_factor: Optional[int] = None
    # SMBIOS type 17 type detail bits that are set (DSP0134 table 77).
    details: tuple[int, ...] = ()
    speed_mts: Optional[int] = None          # what the module can do
    configured_mts: Optional[int] = None     # what it really runs at
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    rank: Optional[int] = None
    data_width: Optional[int] = None
    total_width: Optional[int] = None
    voltage_min_mv: Optional[int] = None
    voltage_max_mv: Optional[int] = None
    voltage_configured_mv: Optional[int] = None

    @property
    def in_a_slot(self) -> bool:
        """In a slot and not soldered on the board, which has no SPD chip.

        A form factor of memory that is part of the board settles it, even
        where the place is called «ChannelA-DIMM0». No other one does: some
        laptops declare their soldered memory a SODIMM. Then the name SMBIOS
        gives its place: «…DIMM0», «DIMM_A1», HP's «Bottom-Slot 1» are slots;
        «Controller0-ChannelA» is not.
        """
        if self.form_factor in SOLDERED_FORM_FACTORS:
            return False
        place = (self.locator or "").lower()
        return "dimm" in place or "slot" in place

    @property
    def soldered_by(self) -> Optional[str]:
        """How it is known to be soldered: "form" (the firmware's form factor)
        or "place" (its place names no slot); None in a slot."""
        if self.in_a_slot:
            return None
        if self.form_factor in SOLDERED_FORM_FACTORS:
            return "form"
        # Its own SPD chip, or no place at all to judge by: nothing says so.
        if self.spd is not None or not self.locator:
            return None
        return "place"

    @property
    def has_ecc(self) -> Optional[bool]:
        """If the total width is larger than the data width, the extra bits are ECC."""
        if self.total_width is None or self.data_width is None or not self.data_width:
            return None
        return self.total_width > self.data_width

    # Filled from the module's own SPD chip, when it can be read.
    spd: Optional[SpdInfo] = None

    @property
    def rated_mts(self) -> Optional[int]:
        """The speed the module can run at, not the one it was set to.

        The SPD really knows it; the SMBIOS table only repeats what the BIOS
        negotiated, which without XMP are JEDEC's conservative values.
        """
        if self.spd is not None and self.spd.rated_mts:
            return self.spd.rated_mts
        return self.speed_mts

    @property
    def rated_from_firmware(self) -> bool:
        """Whether `rated_mts` is only what the firmware's table says."""
        return not (self.spd is not None and self.spd.rated_mts) and bool(self.speed_mts)

    @property
    def voltage_mv(self) -> Optional[int]:
        """The firmware's configured voltage, else the SPD's JEDEC one."""
        if self.voltage_configured_mv:
            return self.voltage_configured_mv
        if self.spd is not None and self.spd.jedec and self.spd.jedec.voltage_v:
            return round(self.spd.jedec.voltage_v * 1000)
        return None

    @property
    def voltage_from_firmware(self) -> bool:
        """Only the firmware says it: many BIOSes leave the configured voltage
        at its stock value while an XMP or EXPO profile raises the real one.
        The SPD declaring that voltage confirms it."""
        if not self.voltage_configured_mv:
            return False
        declared = ()
        if self.spd is not None:
            declared = self.spd.voltages_v or ((self.spd.jedec.voltage_v,) if self.spd.jedec else ())
        return not any(v and abs(v * 1000 - self.voltage_configured_mv) < 10 for v in declared)

    @property
    def above_jedec(self) -> bool:
        """Running faster than any JEDEC speed of its type: a maker's profile
        (XMP, EXPO), with its own voltage."""
        top = JEDEC_TOP_MTS.get(self.type or "")
        running = self.configured_mts or self.speed_mts
        return bool(top and running and running > top + 1)

    @property
    def underclocked(self) -> bool:
        """The module runs below what it can.

        With a margin, and not out of caution: JEDEC grades come from a clock
        that falls in thirds (DDR4-2666 is 1333.33 MHz, so 2666.67 MT/s) and
        each firmware rounds it its own way. A module the SPD rates at 2667
        and the BIOS sets to 2666 is the same grade, and a bare comparison lit
        the warning and its triangle over one MT/s.
        """
        current = self.configured_mts or self.speed_mts
        rated = self.rated_mts
        if not (current and rated):
            return False
        return current < rated * (1 - ROUNDING_MARGIN)


@dataclass(frozen=True, slots=True)
class MemoryArray:
    slots: Optional[int] = None
    max_capacity_bytes: int = 0
    # SMBIOS type 16 error correction code: 03h none, 05h single-bit ECC…
    error_correction: Optional[int] = None


@dataclass(frozen=True, slots=True)
class MemoryTraffic:
    """What the memory controller is moving right now.

    A sensor and not a benchmark: nobody causes it, it's the traffic there
    is. So it lives apart from the bandwidth `membench` measures, which says
    what memory *can* give and has to occupy the machine to know.

    In bytes per second, like the theoretical and the measured ones, so the
    page's three figures compare without converting anything. The kernel's
    counter counts cache lines and the conversion happens in the provider,
    which has the scale at hand.
    """

    read_bytes_s: int = 0
    write_bytes_s: int = 0
    # Of the total, what the cores ask for. The rest is moved by the
    # integrated graphics and the devices on their own, and those two can't be
    # told apart: their counters read the same idle as at full load.
    cpu_bytes_s: Optional[int] = None

    @property
    def total_bytes_s(self) -> int:
        return self.read_bytes_s + self.write_bytes_s


@dataclass(frozen=True, slots=True)
class PrivilegedState:
    """What's known about the privileged helper, to be able to explain it."""

    supported: bool = False                  # there is pkexec and a helper
    connected: bool = False
    already_root: bool = False
    message: Optional[str] = None            # the last failure, if there was one
    # The helper installed in the system is not this version's: it is not
    # used, and it stays owned by root until it is replaced.
    outdated: bool = False


# --------------------------------------------------------------------------
# Motherboard
# --------------------------------------------------------------------------


# Makers identify themselves in DMI with their full legal name. Nobody calls
# an MSI "Micro-Star International Co., Ltd.".
VENDOR_ALIASES: dict[str, str] = {
    "micro-star international": "MSI",
    "asustek computer": "ASUS",
    "gigabyte technology": "Gigabyte",
    # As written in its monitors' EDID, hyphenated and in capitals.
    "giga-byte technology": "Gigabyte",
    "lg electronics": "LG",
    "american megatrends": "AMI",
    "hewlett-packard": "HP",
    "lenovo": "Lenovo",
    "positivo informatica": "Positivo",
    "dell inc.": "Dell",
    "asrock": "ASRock",
    "biostar": "Biostar",
    "supermicro": "Supermicro",
    "acer": "Acer",
    # Memory makers, as the firmware's table writes them. The SPD gives them
    # by JEDEC code («Crucial», «Micron», «SK Hynix»), and a module can't
    # change name when permissions are given.
    "crucial technology": "Crucial",
    "micron technology": "Micron",
    "kingston": "Kingston",
    "sk hynix": "SK Hynix",
    "hynix semiconductor": "SK Hynix",
    "samsung": "Samsung",
    "g skill": "G.Skill",
    "g.skill": "G.Skill",
    "corsair": "Corsair",
    # As JEP106 writes them (spd._vendor).
    "a-data technology": "ADATA",
    "nanya technology": "Nanya",
    # Network and sound makers, as `pci.ids` writes them: the brand on the
    # box is the first word.
    "realtek semiconductor": "Realtek",
    "mediatek": "MediaTek",
    "qualcomm atheros": "Qualcomm Atheros",
    "broadcom inc": "Broadcom",
    "notebook": "",
}


def short_vendor(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    lowered = name.lower()
    for needle, alias in VENDOR_ALIASES.items():
        if lowered.startswith(needle):
            return alias or name
    return name


_BRAND_NOISE = re.compile(r"\((?:R|TM|tm|r)\)|\bCPU\b|\bProcessor\b|@.*$|\b\d+-Core\b")


def thread_name(index: int) -> str:
    """What a processor thread is called: «CPU 3».

    As the kernel numbers it, and the same on the CPU page's grid as in the
    sensor tree. A core with SMT is two of these.
    """
    return f"CPU {index}"


def short_brand(brand: Optional[str]) -> str:
    """"Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz" -> "Intel Core i5-10400"."""
    if not brand:
        return "Procesador"
    return " ".join(_BRAND_NOISE.sub("", brand).split()) or "Procesador"


# Values makers leave unfilled in the SMBIOS table. Showing "Default string"
# as if it were data is worse than showing nothing.
DMI_PLACEHOLDERS = frozenset({
    "default string", "to be filled by o.e.m.", "to be filled by oem",
    "system manufacturer", "system product name", "system version",
    "not specified", "not applicable", "none", "n/a", "unknown",
    "oem", "o.e.m.", "chassis manufacturer", "chassis version",
    "0123456789", "xxxxxxxx", "empty",
    # Some Gigabyte boards leave the board version as a template.
    "x.x",
})


# «1.0», «Rev 1.0», «01». What a board sold on its own leaves in the system
# version, which isn't any machine's name. The fillers with letters
# («Default string», «System Product Name») are already caught by
# DMI_PLACEHOLDERS.
_ONLY_A_VERSION = re.compile(r"(?:(?:rev|ver(?:sion)?|v)\.?\s*)?[\d.,\s]+", re.I)
# The other two fillers that aren't a name: a lone suffix as the system
# version («-CF») and a family made of the chipset and «MB». With them the
# machine came out as «Gigabyte -CF».
_ONLY_A_SUFFIX = re.compile(r"[^0-9a-z]\S{0,6}", re.I)
_ONLY_THE_BOARD = re.compile(r".*\bMB", re.I)
# A code as the family, no name: Intel's platform as Acer writes it («BDW»,
# «SKL»), or a series letter («X» on an ASUS X550JK).
_ONLY_A_CODE = re.compile(r"[A-Z]{1,4}")
# A product name in words, «Aspire E5-473», not a part code («20W0S14X00»,
# «81HL») or a board's («MS-7D23»).
_IN_WORDS = re.compile(r"(?=.*[A-Za-z]{3}).*\S\s+\S.*")


def _names_a_machine(value: str) -> bool:
    return not (_ONLY_A_VERSION.fullmatch(value) or _ONLY_A_SUFFIX.fullmatch(value)
                or _ONLY_THE_BOARD.fullmatch(value) or _ONLY_A_CODE.fullmatch(value))


def clean_dmi(value: Optional[str]) -> Optional[str]:
    """Drop the fillers unconfigured BIOSes leave."""
    if not value:
        return None
    # «N34ET64W (1.64 )»: spaces the firmware pads its fields with.
    value = re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", " ".join(value.split())))
    return None if value.lower() in DMI_PLACEHOLDERS else value


@dataclass(frozen=True, slots=True)
class Board:
    vendor: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None

    bios_vendor: Optional[str] = None
    bios_version: Optional[str] = None
    bios_date: Optional[str] = None
    bios_release: Optional[str] = None

    firmware_uefi: Optional[bool] = None    # False: a legacy BIOS
    firmware_bits: Optional[int] = None     # UEFI's: 64 or 32
    secure_boot: Optional[bool] = None
    tpm_version: Optional[str] = None

    chipset: Optional[str] = None           # "Intel H510"
    chipset_full: Optional[str] = None      # pci.ids' full name
    # The chipset (the PCH) is a die inside the processor's package, as on
    # most Intel laptops since Tiger Lake: no separate chip on the board.
    chipset_on_package: bool = False
    host_bridge: Optional[str] = None

    system_vendor: Optional[str] = None
    system_name: Optional[str] = None
    system_version: Optional[str] = None
    system_family: Optional[str] = None
    system_sku: Optional[str] = None

    chassis_vendor: Optional[str] = None
    chassis: Optional[str] = None

    @property
    def system_display_name(self) -> Optional[str]:
        """The machine's commercial name, if there is one.

        OEMs write it in the system's version or family; a board sold on its
        own leaves a version number or a factory filler there. The latter
        names nothing, and neither does a value repeating the BIOS's or the
        board's version.

        `system_name` comes last and only in words: on many OEMs it carries
        a product code («11DQS0KM00») and on a loose board the board's own
        («MS-7D23»), but some makers put the commercial name there and a
        version and a platform code in the other two.
        """
        versions = {clean_dmi(self.bios_version), clean_dmi(self.version)} - {None}
        system = clean_dmi(self.system_name)
        for attribute in (self.system_version, self.system_family):
            name = clean_dmi(attribute)
            if not name or name in versions:
                continue
            if _names_a_machine(name):
                return name
            # A series letter as the family («X») and the model in it as the
            # system's name («X550JK»): the machine is that model.
            if _ONLY_A_CODE.fullmatch(name) and system and system.startswith(name) \
                    and system != name:
                return system
        # A loose board repeats its own name there: that's no machine.
        name = system
        board = clean_dmi(self.name)
        if (name and _IN_WORDS.fullmatch(name) and name not in versions
                and not (board and (board in name or name in board))):
            return name
        return None

    @property
    def display_name(self) -> Optional[str]:
        """What this is called in one phrase: «MSI H510M PRO-E».

        The line isn't laptop against desktop, though it might seem so: it's
        a board with a commercial name against an internal code. An X570
        AORUS ELITE was bought by its name; nobody has seen a «316C» or an
        «LNVNB161216», and there the machine's name rules, the one on its
        sticker. The chassis type was an approximation of that and failed
        (a Mini PC came out as «Lenovo 316C»), so what really decides is
        asked: whether the machine has a commercial name. The signal is in
        the datum itself: on a loose board that field carries «1.0» or
        «Default string», and on a branded machine its name.
        """
        if self.system_display_name:
            brand = short_vendor(self.system_vendor) or ""
            name = self.system_display_name
            # Lenovo writes «Lenovo ideapad 330-15ICH» there, brand included;
            # putting it in front again gives «Lenovo Lenovo ideapad».
            machine = (name if name.lower().startswith(brand.lower() or "\0")
                      else " ".join(p for p in (brand, name) if p))
            # Only if it adds something: some makers repeat the board code there.
            if machine and (self.name or "") not in machine:
                return machine
        parts = [short_vendor(self.vendor), self.name]
        joined = " ".join(p for p in parts if p)
        if joined:
            return joined
        # No board at all (a virtual machine: QEMU declares no baseboard):
        # the machine as the firmware calls it, «QEMU Standard PC (i440FX +
        # PIIX, 1996)». And if not even that, `render.board_name` says so.
        machine = " ".join(p for p in (short_vendor(self.system_vendor),
                                      clean_dmi(self.system_name)) if p)
        return machine or None



# --------------------------------------------------------------------------
# Sensores
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GpuMemory:
    """The card's VRAM, and the system RAM it borrows."""

    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None
    # The part of VRAM the CPU can address. With Resizable BAR it's all of it;
    # without, the usual 256 MB, which costs performance.
    visible_bytes: Optional[int] = None
    visible_used_bytes: Optional[int] = None
    # GTT: system memory the driver lends the GPU when VRAM runs short. Not
    # the card's memory, hence apart.
    gtt_total_bytes: Optional[int] = None
    gtt_used_bytes: Optional[int] = None
    vendor: Optional[str] = None
    kind: Optional[str] = None          # GDDR6, HBM2e…
    bus_bits: Optional[int] = None
    # The rate data travels at, which isn't the clock: a GDDR6 at 1258 MHz
    # moves 20 Gbps. The number on spec sheets.
    data_rate_hz: Optional[int] = None
    bandwidth_bytes: Optional[int] = None

    @property
    def used_percent(self) -> Optional[float]:
        if not self.total_bytes or self.used_bytes is None:
            return None
        return round(self.used_bytes / self.total_bytes * 100, 1)

    @property
    def resizable_bar(self) -> Optional[bool]:
        """Whether the CPU sees all of VRAM at once rather than through a window."""
        if not self.total_bytes or not self.visible_bytes:
            return None
        # A small margin: the firmware keeps a few megabytes for itself.
        return self.visible_bytes >= self.total_bytes * 0.95


@dataclass(frozen=True, slots=True)
class PcieLink:
    """A PCIe link: how fast it runs now and how fast it could.

    Used by the graphics card and NVMe disks alike. What counts is the
    slowest link of the chain up to the root port, not what the device at
    the end declares.
    """

    current_speed_gts: Optional[float] = None
    current_width: Optional[int] = None
    max_speed_gts: Optional[float] = None
    max_width: Optional[int] = None
    # What the device's own AER counted since boot; None without AER.
    correctable_errors: Optional[int] = None
    nonfatal_errors: Optional[int] = None
    fatal_errors: Optional[int] = None

    @staticmethod
    def _generation(gts: Optional[float]) -> Optional[int]:
        if not gts:
            return None
        # 2.5 · 5 · 8 · 16 · 32 · 64 GT/s are PCIe's six generations.
        for generation, speed in enumerate((2.5, 5.0, 8.0, 16.0, 32.0, 64.0), start=1):
            if abs(gts - speed) < 0.1:
                return generation
        return None

    @property
    def generation(self) -> Optional[int]:
        return self._generation(self.current_speed_gts)

    @property
    def max_generation(self) -> Optional[int]:
        return self._generation(self.max_speed_gts)

    @property
    def fewer_lanes_at_full_speed(self) -> bool:
        """Running at its top speed with fewer lanes than both ends allow."""
        return bool(self.current_speed_gts and self.max_speed_gts
                    and self.current_speed_gts >= self.max_speed_gts - 0.1
                    and self.current_width and self.max_width
                    and self.current_width < self.max_width)

    @property
    def downgraded(self) -> bool:
        """The card runs below what it can.

        At idle that's normal (drivers lower the link to save power), so it's
        shown as a remark, not a warning.
        """
        if self.current_speed_gts and self.max_speed_gts:
            if self.current_speed_gts < self.max_speed_gts - 0.1:
                return True
        if self.current_width and self.max_width:
            return self.current_width < self.max_width
        return False


@dataclass(frozen=True, slots=True)
class GpuClockLevel:
    """A step of the DPM table: the GPU only runs at these frequencies."""

    index: int
    hz: int
    active: bool = False


@dataclass(frozen=True, slots=True)
class GpuClocks:
    core_hz: Optional[int] = None
    memory_hz: Optional[int] = None
    core_max_hz: Optional[int] = None
    memory_max_hz: Optional[int] = None
    # The clock memory really travels at, the spec sheets' one: a GDDR6 with
    # its command clock at 1258 runs at 2505 effective.
    memory_effective_hz: Optional[int] = None
    soc_hz: Optional[int] = None
    # What the silicon allows, on an Intel: RPn, the minimum; RP1, the most
    # efficient; RP0, the maximum without going over. `core_max_hz` and
    # `core_min_hz` are the limits set now, equal to RP0 and RPn from the
    # factory and changeable by anyone.
    core_min_hz: Optional[int] = None
    silicon_min_hz: Optional[int] = None
    efficient_hz: Optional[int] = None
    silicon_max_hz: Optional[int] = None
    core_levels: tuple[GpuClockLevel, ...] = ()
    memory_levels: tuple[GpuClockLevel, ...] = ()
    performance_level: Optional[str] = None   # auto, low, high, manual…
    # The other DPM tables amdgpu publishes, by its file's name: fclk,
    # socclk, dcefclk, vclk, dclk.
    other_levels: tuple[tuple[str, tuple[GpuClockLevel, ...]], ...] = ()
    # The power profile in force, as amdgpu names it: BOOTUP_DEFAULT, COMPUTE…
    power_profile: Optional[str] = None
    # Whether amdgpu lets clocks and voltages be changed (OverDrive).
    overdrive: Optional[bool] = None


@dataclass(frozen=True, slots=True)
class GpuApi:
    """A graphics API and how far it goes on this machine."""

    name: str                       # OpenGL, Vulkan, OpenCL
    version: Optional[str] = None
    device: Optional[str] = None    # what the card calls itself there
    driver: Optional[str] = None
    implementation: Optional[str] = None  # radv, radeonsi, rusticl…
    extra: Optional[str] = None     # GLSL, compute units…


@dataclass(frozen=True, slots=True)
class Display:
    """One of the card's video outputs, plugged in or not."""

    connector: str                  # DP-1, HDMI-A-1…
    connected: bool = False
    # Careful: this is the kernel's modeset, not the session's. With a
    # Wayland compositor in charge it's False on displays that are on, so it
    # works on the console and X11 but can't say something is in use.
    enabled: bool = False
    # The preferred mode the monitor declares, which is nearly always the one
    # used. The resolution the compositor has set right now isn't in sysfs.
    width: Optional[int] = None
    height: Optional[int] = None
    refresh_hz: Optional[float] = None
    monitor: Optional[Edid] = None

    @property
    def resolution(self) -> Optional[str]:
        if not (self.width and self.height):
            return None
        return f"{self.width} × {self.height}"


@dataclass(frozen=True, slots=True)
class VideoCodec:
    """A codec and what the card can do with it in hardware.

    Among the most useful things to know about a graphics card: it decides
    whether a video is decoded on the chip, spending a couple of watts, or
    on the CPU. And decoding versus encoding matters: nearly all read AV1
    and very few write it.
    """

    name: str                             # H.264, HEVC, AV1…
    decode: bool = False
    encode: bool = False
    max_bit_depth: Optional[int] = None   # 8, 10 or 12
    profiles: tuple[str, ...] = ()        # the driver's, untouched


@dataclass(frozen=True, slots=True)
class GpuEngine:
    """A graphics engine: what it can do and how busy it is.

    A modern card isn't one block «at 40 %»: it's several independent units
    (drawing, copying, video decoding), and knowing which one is loaded is
    the difference between «the card can't give more» and «the decoder is
    saturated and the rest sleeps».
    """

    name: str                       # rcs0, vcs0…, as the kernel names it
    kind: Optional[str] = None      # render, copy, video, video-enhance
    busy_percent: Optional[float] = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Gpu:
    """A graphics card: what the kernel knows and what the APIs say."""

    index: int = 0
    name: Optional[str] = None
    vendor: Optional[str] = None
    codename: Optional[str] = None
    driver: Optional[str] = None
    driver_version: Optional[str] = None
    # «Mesa» when the version above is Mesa's, the userspace driver, and not
    # the kernel module's.
    userspace_driver: Optional[str] = None
    # The shader ISA Mesa and ROCm build for: «gfx1201».
    isa: Optional[str] = None
    # The `gpu_metrics` version when the firmware publishes one this program
    # can't read yet. Kept to be able to say so and to put it in the report,
    # which is where its offset table can come from without the part at hand.
    metrics_version: Optional[str] = None
    drm_node: Optional[str] = None      # card0, card1… not necessarily in order
    pci_slot: Optional[str] = None
    vendor_id: Optional[int] = None
    device_id: Optional[int] = None
    subsystem_vendor_id: Optional[int] = None
    subsystem_device_id: Optional[int] = None
    subsystem_name: Optional[str] = None
    revision: Optional[int] = None
    vbios: Optional[str] = None
    vbios_version: Optional[str] = None
    vbios_date: Optional[str] = None        # ISO, as the driver gives it
    unique_id: Optional[str] = None
    # None when it can't be decided. Not the same as not being one: nouveau
    # doesn't give the VRAM, and a dedicated card would otherwise end up as
    # integrated only because its memory couldn't be counted.
    integrated: Optional[bool] = None
    primary: bool = False
    # Suspended by the kernel's runtime PM (D3): a laptop's dedicated card
    # when nobody uses it. Reading almost anything wakes it, so nothing is
    # asked and what's below stays without data. The last thing known before
    # it slept: when (`time.time()`) and its temperature.
    suspended: bool = False
    last_awake_s: Optional[float] = None
    last_temp_c: Optional[float] = None

    memory: GpuMemory = field(default_factory=GpuMemory)
    link: PcieLink = field(default_factory=PcieLink)
    clocks: GpuClocks = field(default_factory=GpuClocks)

    busy_percent: Optional[float] = None
    memory_busy_percent: Optional[float] = None
    # The whole video engine, encoding and decoding together: on AMD it's one
    # engine (VCN) with one figure (docs/motores-de-graficas.md).
    video_busy_percent: Optional[float] = None
    # Separately, where they're different engines the driver measures apart:
    # NVENC and NVDEC on NVIDIA.
    encode_busy_percent: Optional[float] = None
    decode_busy_percent: Optional[float] = None
    # How much of the interval the card spent fully asleep. Not «100 minus
    # usage»: between busy and deep idle there's a middle ground, on and
    # without work, which isn't the same in power.
    sleep_percent: Optional[float] = None
    # Whether the driver lets the card sleep (RC6 on Intel). Off, idle is
    # always 0 % and it draws power even doing nothing.
    sleep_enabled: Optional[bool] = None
    engines: tuple[GpuEngine, ...] = ()
    codecs: tuple[VideoCodec, ...] = ()
    temp_c: Optional[float] = None
    # The card publishes its temperature by no means: Intel's. Not the same
    # as failing to read it, and painted differently: what doesn't exist is
    # hidden and named at the foot, not left with a dash.
    no_temperature_sensor: bool = False
    # Such a card inside the processor: the temperature of the package it
    # shares with the CPU. Never its own, and never shown as if it were.
    package_temp_c: Optional[float] = None
    # Emulated by a hypervisor (QEMU's VGA, virtio, VMware's SVGA…): no
    # silicon, memory, clocks or sensors of its own.
    virtual: bool = False
    hotspot_c: Optional[float] = None
    memory_temp_c: Optional[float] = None
    power_w: Optional[float] = None
    power_cap_w: Optional[float] = None
    # The limit the card ships with, and the range the driver accepts.
    power_cap_default_w: Optional[float] = None
    power_cap_min_w: Optional[float] = None
    power_cap_max_w: Optional[float] = None
    fan_rpm: Optional[int] = None
    fan_percent: Optional[float] = None
    # A laptop's dedicated card: its fans are the machine's, in its embedded
    # controller, and NVML gives none.
    fan_of_the_machine: bool = False
    voltage_v: Optional[float] = None
    voltage_soc_v: Optional[float] = None
    voltage_memory_v: Optional[float] = None
    # The card's own voltage regulators. Not in hwmon: the firmware's
    # microcontroller counts them.
    vr_gfx_c: Optional[float] = None
    vr_soc_c: Optional[float] = None
    vr_memory_c: Optional[float] = None
    # Whether the card is throttling, and why. The question anyone asks when
    # a game performs worse than it should.
    throttled: Optional[bool] = None
    throttle_reasons: tuple[str, ...] = ()
    compute_units: Optional[int] = None
    rops: Optional[int] = None
    shader_engines: Optional[int] = None
    l2_cache_bytes: Optional[int] = None
    infinity_cache_bytes: Optional[int] = None
    asic: Optional[str] = None

    displays: tuple[Display, ...] = ()
    apis: tuple[GpuApi, ...] = ()
    # (API, the driver's reason as it wrote it) for each graphics API whose
    # driver is installed and rejected this card; the reason may be empty.
    api_rejections: tuple[tuple[str, str], ...] = ()

    @property
    def display_name(self) -> Optional[str]:
        """Its name; `render.gpu_name` says it when there is none."""
        return self.name or self.codename

    @property
    def pci_id(self) -> Optional[str]:
        if self.vendor_id is None or self.device_id is None:
            return None
        return f"{self.vendor_id:04X}:{self.device_id:04X}"

    @property
    def subsystem_id(self) -> Optional[str]:
        if self.subsystem_vendor_id is None or self.subsystem_device_id is None:
            return None
        return f"{self.subsystem_vendor_id:04X}:{self.subsystem_device_id:04X}"

    @property
    def connected_displays(self) -> tuple[Display, ...]:
        return tuple(d for d in self.displays if d.connected)


@dataclass(frozen=True, slots=True)
class NetworkTraffic:
    """What has gone through an interface, and at what rate now."""

    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
    rx_dropped: int = 0
    tx_dropped: int = 0
    # Instant rate, computed between two samples. In bytes per second: the
    # model keeps numbers, and render decides whether to show them in bits.
    rx_rate_bps: Optional[float] = None
    tx_rate_bps: Optional[float] = None

    @property
    def total_bytes(self) -> int:
        return self.rx_bytes + self.tx_bytes

    @property
    def total_rate_bps(self) -> Optional[float]:
        if self.rx_rate_bps is None and self.tx_rate_bps is None:
            return None
        return (self.rx_rate_bps or 0.0) + (self.tx_rate_bps or 0.0)

    @property
    def problems(self) -> int:
        """Packets that didn't reach their destination, for whatever reason."""
        return self.rx_errors + self.tx_errors + self.rx_dropped + self.tx_dropped

    @property
    def dropped(self) -> int:
        """Packets the kernel discarded: mostly not lost on the wire."""
        return self.rx_dropped + self.tx_dropped

    @property
    def errors(self) -> int:
        """Packets that arrived or left damaged."""
        return self.rx_errors + self.tx_errors


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    """A network interface: what it is, how it's connected and how much it moves."""

    name: str
    kind: str = "ethernet"          # ethernet, wifi, loopback, virtual, bridge
    up: bool = False
    carrier: Optional[bool] = None  # whether a cable is plugged in / wifi is associated
    mac: Optional[str] = None
    ipv4: Optional[str] = None
    netmask: Optional[str] = None
    ipv6: tuple[str, ...] = ()
    gateway: Optional[str] = None
    default_route: bool = False
    speed_mbps: Optional[int] = None
    duplex: Optional[str] = None
    mtu: Optional[int] = None
    driver: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None
    pci_slot: Optional[str] = None
    traffic: NetworkTraffic = field(default_factory=NetworkTraffic)

    @property
    def display_name(self) -> str:
        return self.model or self.name

    @property
    def active(self) -> bool:
        """Plugged in and with an address: the one really serving."""
        return self.up and bool(self.ipv4 or self.ipv6)



@dataclass(frozen=True, slots=True)
class Partition:
    """A partition, with what it takes if mounted."""

    name: str                                  # nvme0n1p2
    size_bytes: Optional[int] = None
    filesystem: Optional[str] = None
    mountpoint: Optional[str] = None
    used_bytes: Optional[int] = None
    free_bytes: Optional[int] = None

    @property
    def used_percent(self) -> Optional[float]:
        if not self.size_bytes or self.used_bytes is None:
            return None
        return round(self.used_bytes / self.size_bytes * 100, 1)

    @property
    def mounted(self) -> bool:
        return bool(self.mountpoint)


@dataclass(frozen=True, slots=True)
class Battery:
    """A laptop's battery, the part that degrades most.

    Everything in watt-hours and watts, not milliamp-hours. The kernel uses
    two conventions depending on the firmware (`charge_*` in µAh and
    `energy_*` in µWh), and mAh can't be compared between machines without
    the cell's voltage: 4000 mAh at 7.6 V and 4000 mAh at 11.4 V are very
    different batteries. Normalized on the way in so the card doesn't have
    to choose.
    """

    name: str = ""
    present: bool = True
    # A key, not the kernel's text: «Discharging» is translated, and whoever
    # looks at the card needn't read English.
    status: Optional[str] = None
    percent: Optional[float] = None

    design_wh: Optional[float] = None
    full_wh: Optional[float] = None
    now_wh: Optional[float] = None

    voltage_v: Optional[float] = None
    design_voltage_v: Optional[float] = None
    # Always positive: whether it charges or discharges is `status`'s to say,
    # and a sign whose meaning depends on the firmware tells nothing.
    power_w: Optional[float] = None
    cycles: Optional[int] = None

    manufacturer: Optional[str] = None
    model: Optional[str] = None
    technology: Optional[str] = None
    serial: Optional[str] = None

    # The charge thresholds ASUS, Lenovo and a few others have. Charging to
    # 60 % lengthens the cell's life a good deal and hardly anyone knows their
    # laptop allows it.
    charge_start_percent: Optional[int] = None
    charge_end_percent: Optional[int] = None

    @property
    def health_percent(self) -> Optional[float]:
        """What's left of the capacity it left the factory with.

        The datum this card is looked at for: «87 %» says more than any other
        figure here, being the only one answering «is it dying?».
        """
        if not self.design_wh or self.full_wh is None:
            return None
        return round(self.full_wh / self.design_wh * 100, 1)

    @property
    def without_data(self) -> bool:
        """Declared by the firmware with nothing in it: no capacity, charge or
        voltage, as a battery worn out or badly seated reports itself."""
        return (self.percent is None and not self.full_wh and not self.design_wh
                and not self.now_wh and not self.voltage_v)

    @property
    def on_charger(self) -> bool:
        """Full or held at its charge limit: it does not run on itself."""
        return self.status in ("bat.status.full", "bat.status.held", "bat.status.paused")

    @property
    def power_settling(self) -> bool:
        """Charging or discharging at 0 W can't be: after the charger goes in
        or out, the embedded controller takes a few seconds to update
        `power_now`. Not unread, and not zero: coming."""
        return (self.status in ("bat.status.charging", "bat.status.discharging")
                and not self.power_w)

    @property
    def seconds_left(self) -> Optional[int]:
        """How long it lasts at the current rate, or how long until full.

        At the current rate and not «in general»: idle gives nine hours and
        compiling two, and both are true. So it's shown next to the power
        draw, not alone.
        """
        if not self.power_w or self.now_wh is None:
            return None
        if self.status == "bat.status.charging":
            remaining = (self.full_wh or self.design_wh or 0) - self.now_wh
            return int(remaining / self.power_w * 3600) if remaining > 0 else None
        if self.status == "bat.status.discharging":
            return int(self.now_wh / self.power_w * 3600)
        return None


@dataclass(frozen=True, slots=True)
class DiskIo:
    """What has gone through the disk, and at what rate now."""

    read_bytes: int = 0
    write_bytes: int = 0
    read_ops: int = 0
    write_ops: int = 0
    read_rate_bps: Optional[float] = None
    write_rate_bps: Optional[float] = None

    @property
    def total_rate_bps(self) -> Optional[float]:
        if self.read_rate_bps is None and self.write_rate_bps is None:
            return None
        return (self.read_rate_bps or 0.0) + (self.write_rate_bps or 0.0)


@dataclass(frozen=True, slots=True)
class DiskHealth:
    """The disk's state per its own SMART counters.

    Almost none of it reads without permissions: the kernel keeps the
    diagnostic commands for the administrator because they're the same ones
    that wipe a disk. So it comes apart and may be entirely empty.
    """

    power_on_hours: Optional[int] = None
    power_cycles: Optional[int] = None
    written_bytes: Optional[int] = None        # the well-known TBW
    read_bytes: Optional[int] = None
    # How much life the SSD has left per its own wear counter, from 0 to 100.
    # Spinning disks don't have it.
    percentage_used: Optional[int] = None
    spare_percent: Optional[int] = None
    unsafe_shutdowns: Optional[int] = None
    media_errors: Optional[int] = None
    critical_warning: Optional[int] = None
    # A SATA disk's whole attribute table: (number, normalized, raw). The
    # names depend on the maker; the number doesn't.
    attributes: tuple[tuple[int, int, int], ...] = ()
    # The write counter came out below what the disk holds: it counts in a
    # unit nobody knows, so neither it nor the read one is shown.
    counters_unit_unknown: bool = False

    @property
    def life_left_percent(self) -> Optional[int]:
        if self.percentage_used is None:
            return None
        return max(0, 100 - self.percentage_used)

    @property
    def healthy(self) -> Optional[bool]:
        if self.critical_warning is None:
            return None
        return self.critical_warning == 0


# The kinds of disk, in the order the pages count them.
DISK_KINDS = ("NVMe", "SSD", "HDD", "Flash", "Virtual")


@dataclass(frozen=True, slots=True)
class Disk:
    """A storage drive."""

    name: str                                  # sda, nvme0n1
    model: Optional[str] = None
    vendor: Optional[str] = None
    firmware: Optional[str] = None
    serial: Optional[str] = None
    size_bytes: Optional[int] = None
    # HDD, SSD or NVMe. The first thing one wants to know, and in no field:
    # it's deduced from whether the disk spins and how it's connected.
    kind: Optional[str] = None
    transport: Optional[str] = None            # sata, nvme, usb…
    rotational: Optional[bool] = None
    logical_sector: Optional[int] = None
    physical_sector: Optional[int] = None
    scheduler: Optional[str] = None
    removable: bool = False
    pci_slot: Optional[str] = None
    link: Optional[PcieLink] = None            # NVMe only
    temp_c: Optional[float] = None
    # Whether the drive supports discards (TRIM) and what shows they happen:
    # a partition mounted with `discard`, or the `fstrim.timer` enabled. The
    # latter is a sign, not a guarantee.
    discard: Optional[bool] = None
    discard_mounted: bool = False
    fstrim_timer: bool = False
    partitions: tuple[Partition, ...] = ()
    io: DiskIo = field(default_factory=DiskIo)
    health: DiskHealth = field(default_factory=DiskHealth)

    @property
    def display_name(self) -> str:
        return self.model or self.name

    @property
    def used_bytes(self) -> Optional[int]:
        """What's used, adding up the mounted partitions."""
        used = [p.used_bytes for p in self.partitions if p.used_bytes is not None]
        return sum(used) if used else None

    @property
    def mounted_partitions(self) -> tuple[Partition, ...]:
        return tuple(p for p in self.partitions if p.mounted)


# What a value can be in each unit. Outside it, it is not of its series: a raw
# counter, another quantity. A net behind the providers' own checks, for the
# charts (`Sparkline`) and the sensors' history.
PLAUSIBLE = {
    "%": (0.0, 100.0), "W": (0.0, 5000.0), "GHz": (0.0, 20.0), "MHz": (0.0, 20_000.0),
    "°C": (-60.0, 250.0), "°F": (-76.0, 482.0), "B/s": (0.0, 1e12),
}


def plausible(value: float, unit: str, ceiling: Optional[float] = None) -> bool:
    """Whether a value can be of a series in that unit (and under `ceiling`)."""
    low, high = PLAUSIBLE[unit]
    if ceiling is not None:
        high = min(high, ceiling)
    return low <= value <= high


class SensorKind(str, Enum):
    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"
    FAN = "fan"
    POWER = "power"
    CURRENT = "current"
    ENERGY = "energy"
    CLOCK = "clock"
    USAGE = "usage"
    MEMORY = "memory"
    NETWORK = "network"
    # A transfer rate that isn't network: today, what the memory controller
    # moves. Apart from NETWORK because they share a shape and not a meaning,
    # and together they'd fall into the same branch of the tree.
    BANDWIDTH = "bandwidth"
    # What has crossed a network interface, in decimal like its rates: apart
    # from MEMORY, which is binary.
    DATA = "data"
    OTHER = "other"


# The unit a sensor kind is read in, where that unit has a plausible range.
SENSOR_UNITS = {SensorKind.TEMPERATURE: "°C", SensorKind.POWER: "W",
                SensorKind.USAGE: "%", SensorKind.CLOCK: "MHz"}


UNITS: dict[str, str] = {
    SensorKind.TEMPERATURE: "°C",
    SensorKind.VOLTAGE: "V",
    SensorKind.FAN: "RPM",
    SensorKind.POWER: "W",
    SensorKind.CURRENT: "A",
    SensorKind.ENERGY: "J",
    SensorKind.CLOCK: "MHz",
    SensorKind.USAGE: "%",
    SensorKind.MEMORY: "MiB",
    SensorKind.NETWORK: "kB/s",
    SensorKind.BANDWIDTH: "MB/s",
    SensorKind.DATA: "MB",
    SensorKind.OTHER: "",
}

class DeviceKind(str, Enum):
    """Which kind of device publishes a sensor: processor, board, disk…

    Whoever reads it knows. Deducing it later by comparing the device's name
    with one built elsewhere didn't match («Intel Core i5-10400» against the
    whole CPUID string), and those names are interface text anyway: the
    memory device comes from `_("sensor.mem")`, so in English it says
    «Memory». An order isn't decided with strings that get translated.
    """

    CPU = "cpu"
    BOARD = "board"
    MEMORY = "memory"
    GPU = "gpu"
    DISK = "disk"
    NETWORK = "network"
    POWER = "power"          # battery, adapter, ports that supply power


# The order the tree's devices are drawn in: as they're looked for, not as
# the kernel numbered them, which is hwmon's folder order and changes
# between boots. The processor first, then the board (where fans and
# voltages are looked at), then the rest.
DEVICE_ORDER: dict[str, int] = {
    DeviceKind.CPU: 0,
    DeviceKind.BOARD: 1,
    DeviceKind.MEMORY: 2,
    DeviceKind.GPU: 3,
    DeviceKind.DISK: 4,
    DeviceKind.NETWORK: 5,
    DeviceKind.POWER: 6,
}


# The branch each kind falls into within the sensor tree. Keys, not text:
# the program makes these names up to group (the kernel doesn't give them),
# so they're interface and get translated when the tree is built.
CATEGORIES: dict[str, str] = {
    SensorKind.VOLTAGE: "cat.voltage",
    SensorKind.TEMPERATURE: "cat.temperature",
    SensorKind.FAN: "cat.fan",
    SensorKind.POWER: "cat.power",
    SensorKind.CURRENT: "cat.current",
    SensorKind.ENERGY: "cat.energy",
    SensorKind.CLOCK: "cat.clock",
    SensorKind.USAGE: "cat.usage",
    SensorKind.MEMORY: "cat.memory",
    SensorKind.NETWORK: "cat.network",
    SensorKind.BANDWIDTH: "cat.bandwidth",
    SensorKind.DATA: "cat.network",
    SensorKind.OTHER: "cat.other",
}

# The order branches are shown in, from what people come to look at to what
# they consult: what runs hot, how the fans spin and how much it draws,
# before voltages and a clock per thread. With voltages first, the board's
# branch opened with nine unnamed voltages.
CATEGORY_ORDER: tuple[str, ...] = (
    "cat.temperature", "cat.fan", "cat.power", "cat.usage",
    "cat.voltage", "cat.current", "cat.clock",
    "cat.memory", "cat.network", "cat.bandwidth", "cat.energy", "cat.other",
)


@dataclass(frozen=True, slots=True)
class Sensor:
    """One reading from a sensor chip.

    `key` must be stable between samples: it lets minimums and maximums be
    accumulated per sensor over the session, which is the point of a
    hardware monitor over a plain viewer of current values.
    """

    key: str                        # "coretemp/temp2"
    chip: str                       # the chip's raw name: "coretemp"
    device: str                     # the device: "MSI H510M PRO-E", "Core i5-10400"
    label: str                      # "Core 0", "Vcore", "CPU Fan"
    kind: SensorKind
    value: float
    low: Optional[float] = None     # the low threshold the chip declares
    high: Optional[float] = None    # the high threshold
    critical: Optional[float] = None
    order: int = 0                  # to keep the natural order within the branch
    # True when the sensor doesn't publish the thresholds and silux sets them
    # by which chip it is. Said in the window: an estimated limit and one the
    # maker declares don't deserve the same trust.
    estimated_limits: bool = False
    # True when the driver doesn't say what this channel measures and the
    # name is a number set here: «Voltage 3». On a Super I/O (it87, nct67xx)
    # what reaches each input was decided by the board's designer, and the
    # kernel doesn't know. Said in the window instead of making up a name.
    unnamed: bool = False
    # True when what's read isn't a measurement but the fixed number the
    # firmware returns for a thermal zone wired to no sensor: 16.8 or 27.8 °C
    # stuck in many desktop boards' `acpitz`. The machine publishes it, so
    # it's shown; but it says what it is, carries no thresholds and doesn't
    # count as any part's temperature.
    placeholder: bool = False
    # The chip this reading repeats, or None. A Gigabyte board's WMI
    # interface publishes the same probes as its Super I/O: the same chip
    # read by two drivers. The reading stays in the snapshot (the CSV records
    # it, the JSON has it), but the tree shows it once, the chip's, and says
    # the other driver repeats it.
    mirror_of: Optional[str] = None
    # For what fits no kind with a fixed unit, such as a transfer rate. The
    # exception, not the rule: what recurs deserves its own SensorKind.
    unit_override: Optional[str] = None
    # What kind of device publishes it, to put it in its place in the tree.
    # The board by default, where whatever's unrecognized hangs: a Super I/O
    # on no list is still a board chip.
    device_kind: str = DeviceKind.BOARD
    # What device it is, raw ("cpu", "net:eno1", "gpu:0000:03:00.0"): the
    # tree groups by this and remembers the user's folds by it. `device` is
    # its name, in the interface's language, and is only painted.
    device_key: str = ""
    # The label the chip gives, as the kernel publishes it, or None: what
    # decides on a label («Package id 0», «Vcore») looks at this, never at
    # `label`, which may be one Silux made up in the interface's language.
    chip_label: Optional[str] = None

    @property
    def unit(self) -> str:
        return self.unit_override or UNITS.get(self.kind, "")

    @property
    def plausible(self) -> bool:
        """Whether its value can be one of its kind: a raw counter is not."""
        unit = SENSOR_UNITS.get(self.kind)
        return unit is None or plausible(self.value, unit)

    @property
    def group(self) -> str:
        """The device the tree hangs it from: its key, or its name without one."""
        return self.device_key or self.device

    @property
    def category(self) -> str:
        return CATEGORIES.get(self.kind, "Otros")

    @property
    def alarm(self) -> bool:
        """Whether the reading crossed a threshold the hardware itself declares."""
        return self.alarm_level != "ok"

    @property
    def alarm_level(self) -> str:
        """«ok», «alto» or «crítico», per what the hardware itself says.

        Two levels and not one because they differ: `max` is where the maker
        starts to worry and `crit` where the machine shuts down on its own.
        Painting both the same colour leaves the viewer not knowing whether
        to act now or just keep an eye.
        """
        if self.value is None:
            return "ok"
        if self.critical is not None and self.value >= self.critical:
            return "crítico"
        if self.high is not None and self.value > self.high:
            return "alto"
        if self.low is not None and self.value < self.low:
            return "alto"
        return "ok"

    # From which fraction of the threshold tinting starts. Below three
    # quarters nothing is painted: a processor at 45 of 90 degrees isn't
    # «half hot», it's fine, and an in-between colour would turn colour into
    # decoration that warns of nothing.
    WARM_FROM = 0.75

    @property
    def heat(self) -> Optional[float]:
        """How close it is to its threshold, 0 to 1, or None without one.

        Temperatures only: a voltage at half scale means nothing, and a fan at
        full speed is expected under load.

        It tints a long list. Ninety-nine rows of figures in one colour are
        read one by one; with the one getting close in another colour, you
        know where to look without reading them.
        """
        if self.kind is not SensorKind.TEMPERATURE or self.value is None:
            return None
        ceiling = self.critical if self.critical is not None else self.high
        if not ceiling or ceiling <= 0:
            return None
        fraction = self.value / ceiling
        if fraction <= self.WARM_FROM:
            return 0.0
        return min(1.0, (fraction - self.WARM_FROM) / (1 - self.WARM_FROM))


@dataclass(frozen=True, slots=True)
class DriverHint:
    """A kernel module that would give more sensors and isn't loaded.

    On Linux a hardware monitor isn't limited by what it can read but by the
    drivers that are loaded. Detecting and saying it beats any extra sensor.
    """

    module: str
    provides: str
    command: str
    caution: str = ""


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Snapshot:
    monotonic_ns: int
    cpu: CpuInfo
    board: Board = field(default_factory=Board)
    system: System = field(default_factory=System)
    modules: tuple[MemoryModule, ...] = ()
    spd: tuple[SpdInfo, ...] = ()
    memory_array: Optional[MemoryArray] = None
    memory_traffic: Optional[MemoryTraffic] = None
    gpus: tuple[Gpu, ...] = ()
    network: tuple[NetworkInterface, ...] = ()
    disks: tuple[Disk, ...] = ()
    batteries: tuple[Battery, ...] = ()
    pci_devices: tuple[PciDevice, ...] = ()
    platform: Platform = field(default_factory=Platform)
    usb_devices: tuple[UsbDevice, ...] = ()
    sound_cards: tuple[SoundCard, ...] = ()
    cameras: tuple[Camera, ...] = ()
    bluetooth: tuple[BluetoothAdapter, ...] = ()
    privileged: PrivilegedState = field(default_factory=PrivilegedState)
    sensors: tuple[Sensor, ...] = ()
    driver_hints: tuple[DriverHint, ...] = ()
    capabilities: frozenset[str] = frozenset()
    notes: tuple[Note, ...] = ()
    failures: tuple[Failure, ...] = ()
    # The collector's first snapshot: what comes from two readings (usage,
    # power, transfer rates) has only its baseline, and is still coming.
    first_reading: bool = False

    def sensor_tree(self) -> dict[str, dict[str, tuple[Sensor, ...]]]:
        """Device → category → sensors, in the order they're drawn.

        How HWMonitor and HWiNFO present the data, and not by chance:
        grouping by device and then by quantity lets one look at «what the
        board does» or «what temperatures there are» without reading it all.
        """
        tree: dict[str, dict[str, list[Sensor]]] = {}
        kinds: dict[str, str] = {}
        names: dict[str, str] = {}
        for sensor in self.sensors:
            if sensor.mirror_of:
                continue                # the same reading through another driver: once
            # By its raw key, not its name: names are in the interface's
            # language, and the user's folds are kept by this.
            tree.setdefault(sensor.group, {}).setdefault(sensor.category, []).append(sensor)
            kinds.setdefault(sensor.group, sensor.device_kind)
            names.setdefault(sensor.group, sensor.device)

        ordered: dict[str, dict[str, tuple[Sensor, ...]]] = {}
        # Ordered by name, which is painting: alphabetical in the reader's language.
        for device in sorted(tree, key=lambda d: self._device_order(names[d], kinds[d])):
            categories = tree[device]
            ordered[device] = {
                # By chip and, within it, in its order: a board publishing the
                # same probes two ways (its Super I/O and its WMI interface)
                # showed them interleaved. The filler ones go last.
                name: tuple(sorted(categories[name],
                                   key=lambda s: (s.placeholder, s.chip, s.order, s.label)))
                for name in CATEGORY_ORDER
                if name in categories
            }
        return ordered

    @staticmethod
    def _device_order(device: str, kind: str) -> tuple[int, str]:
        """The order each device of the sensor tree is drawn in.

        Without it they come in the kernel's order, hwmon's folders: an
        arbitrary number that changes between boots. They're sorted as
        they're looked for (processor first, then the board), not as the
        system numbered them. The kind comes with each sensor, since the
        provider already resolved it when reading.
        """
        return (DEVICE_ORDER.get(kind, DEVICE_ORDER[DeviceKind.BOARD]), device)

    @staticmethod
    def device_name(categories: dict) -> str:
        """The name of a `sensor_tree` device, whose key is raw: its sensors'."""
        return next(iter(categories.values()))[0].device

    def notes_for(self, prefix: str) -> tuple[Note, ...]:
        return tuple(n for n in self.notes if n.path.startswith(prefix))

    @property
    def permission_notes(self) -> tuple[Note, ...]:
        """What's missing and is fixed by giving permissions, in the snapshot's
        order.

        Only what the helper can read on this machine: a permission note
        without `what` is a file that won't open, which a password doesn't
        solve; and without a helper there's nobody to ask. Counting too many
        here puts up a button that doesn't fix what it announces.
        """
        if not self.privileged.supported:
            return ()
        return tuple(n for n in self.notes if n.need is Need.ROOT and n.what)

    @property
    def installed_memory_bytes(self) -> Optional[int]:
        """Installed memory: the modules' sum, not what the kernel sees.

        `system.memory.total_bytes` is the usable amount (`MemTotal`): what's
        installed minus what the firmware, the kernel and integrated graphics
        keep. It comes from the firmware's table (with permissions) or else
        the SPD. Without either it isn't known, and it isn't guessed: the
        memory by blocks in `/sys/devices/system/memory` leaves out what
        integrated graphics reserve.
        """
        modules = [m.size_bytes for m in self.modules if m.populated and m.size_bytes]
        if modules:
            return sum(modules)
        spd = [i.capacity_bytes for i in self.spd if i.capacity_bytes]
        if not spd or not self.spd_accounts_for_all_memory:
            return None
        return sum(spd)

    @property
    def spd_accounts_for_all_memory(self) -> bool:
        """Whether the SPD chips add up to the usable memory at least. Memory
        soldered on the board has none, and installed is never less than
        usable."""
        spd = sum(i.capacity_bytes for i in self.spd if i.capacity_bytes)
        util = self.system.memory.total_bytes
        return not util or spd >= util

    @property
    def working_gpu(self) -> Optional[int]:
        """The index of the working graphics card, the one summarized.

        Not the list's first: the order is `cardN`'s, and on a gaming laptop
        the integrated one is often `card0`, so Home said the machine «has»
        integrated graphics. Nor just `boot_vga`, the one the firmware booted
        with, which on a laptop is the integrated one.

        The awake dedicated card, if any: the one that draws on a desktop and
        is used when gaming. If the dedicated card sleeps, the awake one,
        which is the one working. If all sleep or it isn't known, the boot
        one, and failing that the first. A card no driver talks to (on the bus,
        with no driver and no DRM node) does not work, awake or not.
        """
        if not self.gpus:
            return None
        awake = [i for i, g in enumerate(self.gpus)
                 if not g.suspended and (g.driver or g.drm_node)]
        for i in awake:
            if self.gpus[i].integrated is False:
                return i
        for i in awake:
            if self.gpus[i].primary:
                return i
        if awake:
            return awake[0]
        for i, g in enumerate(self.gpus):
            if g.primary:
                return i
        return 0

    def permission_note(self, path: str) -> Optional[Note]:
        """The permission note that field holds, if any.

        To paint a padlock where the datum would go: the page asks for the
        field (`gpus.0.usage`), and the note can be its own or the whole
        part's, `gpus.0`. What's missing for another reason has no padlock.
        """
        for note in self.permission_notes:
            if path == note.path or path.startswith(note.path + "."):
                return note
        return None


def to_jsonable(obj: Any) -> Any:
    """Turn the model into structures `json` can serialize.

    Written by hand instead of using `dataclasses.asdict` because the
    computed properties (multipliers, totals) must be included and the sets
    sorted so the output is stable between runs.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in fields(obj):
            out[f.name] = to_jsonable(getattr(obj, f.name))
        for extra in _COMPUTED.get(type(obj).__name__, ()):
            out[extra] = to_jsonable(getattr(obj, extra))
        return out
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (frozenset, set)):
        return sorted(obj)
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


_COMPUTED: dict[str, tuple[str, ...]] = {
    "Cache": ("total_bytes",),
    "Clocks": ("multiplier", "base_multiplier", "min_multiplier",
               "max_multiplier", "max_turbo_multiplier", "turbo_headroom_hz"),
    "Power": ("load_percent",),
    "GpuMemory": ("used_percent", "resizable_bar"),
    "PcieLink": ("fewer_lanes_at_full_speed", "generation", "max_generation", "downgraded"),
    "Display": ("resolution",),
    "Edid": ("diagonal_inches", "refresh_range",
             "refresh_summary", "best_mode"),
    "VideoMode": ("label",),
    "Gpu": ("display_name", "pci_id", "subsystem_id", "connected_displays"),
    "NetworkTraffic": ("dropped", "errors", "total_bytes", "total_rate_bps", "problems"),
    "NetworkInterface": ("display_name", "active"),
    "Partition": ("used_percent", "mounted"),
    "DiskIo": ("total_rate_bps",),
    "DiskHealth": ("life_left_percent", "healthy"),
    "Disk": ("display_name", "used_bytes", "mounted_partitions"),
    "CpuInfo": ("total_cores", "total_threads", "package_power_w", "temperature_c",
                "cores_temp_c", "in_virtual_machine"),
    "Sensor": ("heat", "unit", "plausible", "group", "category", "alarm", "alarm_level"),
    "Board": ("display_name",),
    "MemoryModule": ("has_ecc", "underclocked", "rated_mts", "in_a_slot", "soldered_by",
                     "rated_from_firmware", "voltage_mv", "voltage_from_firmware",
                     "above_jedec"),
    "SpdInfo": ("rated_mts",),
    "Timings": ("summary",),
    "Memory": ("used_bytes", "used_percent", "cache_bytes", "apps_bytes",
               "swap_used_bytes", "swap_used_percent"),
}
