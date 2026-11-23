"""Every sensor of the machine, from /sys/class/hwmon.

The whole tree is walked once and gives two things: the full sensor list
the Monitor page uses, and the specific values (per-core temperature,
voltage) the CPU page needs. Two passes would read the same files twice per
sample.

Here also lives what most sets a Linux hardware monitor apart: **finding
which driver is missing**. The machine is limited not by what the program can
read but by the modules the kernel has loaded. A board without its Super I/O
module shows no fan and no voltage, and saying so is worth more than any
extra sensor.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import subprocess
from typing import Iterator, Optional

from .. import sysroot, system_deps, thermal
from ..i18n import _
from ..model import DeviceKind, DriverHint, Need, Sensor, SensorKind, short_brand
from ..system_env import system_environment
from .base import Draft, Provider, is_virtual_machine, mean, read_int, read_text
from .dmi import PORTABLE_CHASSIS

HWMON = pathlib.Path("/sys/class/hwmon")
POWER_SUPPLY = pathlib.Path("/sys/class/power_supply")

# File prefix -> (kind, divisor to the model's unit)
MEASUREMENTS: dict[str, tuple[SensorKind, float]] = {
    "temp": (SensorKind.TEMPERATURE, 1000.0),      # millidegrees
    "in": (SensorKind.VOLTAGE, 1000.0),            # millivolts
    "fan": (SensorKind.FAN, 1.0),                  # already RPM
    "power": (SensorKind.POWER, 1_000_000.0),      # microwatts
    "curr": (SensorKind.CURRENT, 1000.0),          # milliamps
    "energy": (SensorKind.ENERGY, 1_000_000.0),    # microjoules
    # GPUs publish their clocks here, in hertz. They go to megahertz, the unit
    # the tree keeps every clock in, the processor's included.
    "freq": (SensorKind.CLOCK, 1_000_000.0),
}

# Channels not named `_input`. amdgpu publishes power as `power1_average` (a
# mean over the last window, not an instant reading).
ALTERNATIVES = ("_average",)

# Which device each chip belongs to. Order matters: the first rule wins.
CPU_CHIP = re.compile(r"^(coretemp|k10temp|k8temp|zenpower|cpu_thermal)$")
# The `*_wmi` ones are the sensors the board maker exposes through its own
# interface, next to the same board named by its Super I/O.
BOARD_CHIP = re.compile(
    r"^(nct\d+|it\d+|w836\d+|f71\d+|smsc|lm\d+|nzxt|asus|acpitz|thermal"
    r"|\w+_wmi)")
# Drivers that read not their own chip but another driver's, another way:
# `gigabyte_wmi` asks the board's firmware for its Super I/O's temperatures,
# which `it87` reads directly. Only what is known goes here, and even so the
# readings confirm it before they are taken as repeated.
MIRRORS = {"gigabyte_wmi": re.compile(r"^it8\d+")}
# How far apart two readings of the same sensor, one after the other, can be:
# the chip rounds to degrees and milliseconds pass between them.
MIRROR_MARGIN = 2.0

DISK_CHIP = re.compile(r"^(drivetemp|nvme)")
NET_CHIP = re.compile(r"^(r8\d+|e1000|igb|ixgbe|iwlwifi|mt79|ath\d+k?)")
# The hint for a board's Super I/O chip, which is no module's name.
SUPERIO = "(Super I/O)"
# The memory modules' own sensors (the SPD hub of DDR5, the JC-42 of DDR4).
MEMORY_CHIP = re.compile(r"^(spd5118|jc42)")
# Wi-Fi cards, whose sensor does not always hang from their interface.
WIFI_CHIP = re.compile(r"^(iwlwifi|mt79|ath\d+k?)")
GPU_CHIP = re.compile(r"^(amdgpu|radeon|i915|xe|nouveau)")

# Super I/O chips: without any, the board is giving no fans.
SUPERIO_CHIPS = re.compile(r"^(nct\d+|it\d+|w836\d+|f71\d+|smsc|nzxt|asus)")

_CORE_LABEL = re.compile(r"^Core\s+(\d+)$", re.IGNORECASE)
_PACKAGE_LABEL = re.compile(r"^(Package id \d+|Tdie|Tctl|CPU Temperature)$", re.IGNORECASE)
_VCORE_LABEL = re.compile(r"(vcore|cpu\s*v(core|oltage)|vid)", re.IGNORECASE)

# What an ACPI thermal zone the firmware declares and connects to nothing
# returns: always the same number, measured by nobody. Tenths of kelvin
# written in the table (2900, 3010 and 3030; and 2832, 10.0 °C, an HP's
# second zone beside its 27.8 with the processor at 49).
ACPI_ZONES_CHIP = "acpitz"
FILLER_VALUES = frozenset((10.0, 16.8, 27.8, 29.8))

# The CPU's chips, by preference: the first ones measure the die.
CPU_CHIPS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "k8temp", "acpitz")


def device_for(chip: str, entry: pathlib.Path, cpu_name: str, board_name: str,
               gpu_names: Optional[dict[str, str]] = None) -> tuple[str, str, str]:
    """Which tree device this chip hangs from, and its kind.

    The name matters: a tree saying "coretemp" and "nct6683" makes one know
    what each thing is; one saying the processor's and the board's names
    reads by itself, as HWMonitor and HWiNFO do.

    The kind comes from here too: it is the same decision. With only the name
    returned, the tree had to work the kind out again by comparing strings.

    And its key, built from the same raw things as its name and never from
    the name, which is in the interface's language: the tree groups by it.
    """
    if CPU_CHIP.match(chip):
        return cpu_name, DeviceKind.CPU, "cpu"
    if BOARD_CHIP.match(chip):
        return board_name, DeviceKind.BOARD, "board"
    if DISK_CHIP.match(chip):
        disk = _disk_name(entry)
        return disk or _("sensor.dev.storage"), DeviceKind.DISK, f"disk:{disk or ''}"
    if GPU_CHIP.match(chip):
        # The real name when known: «amdgpu» says nothing on a machine with
        # two GPUs, and with one it still makes one know the driver.
        slot = _pci_slot(entry) or ""
        if entry_name := (gpu_names or {}).get(slot):
            return entry_name, DeviceKind.GPU, f"gpu:{slot}"
        return _("sensor.dev.gpuchip").format(chip=chip), DeviceKind.GPU, f"gpu-chip:{chip}"
    if NET_CHIP.match(chip):
        if interface := _net_iface(entry):
            return _("sensor.dev.net").format(chip=interface), DeviceKind.NETWORK, f"net:{interface}"
        # An iwlwifi sensor read «Network (iwlwifi_1)»: without its
        # interface, what it is and not the driver's name.
        wifi = bool(WIFI_CHIP.match(chip))
        backup = _("sensor.dev.wifi") if wifi else render_chip(chip)
        return (_("sensor.dev.net").format(chip=backup), DeviceKind.NETWORK,
                f"net-chip:{'wifi' if wifi else chip}")
    if MEMORY_CHIP.match(chip):
        return _("sensor.mem"), DeviceKind.MEMORY, "memory"
    if (supply := _power_supply_kind(chip)):
        return _power_supply_name(chip), DeviceKind.POWER, _power_supply_key(*supply)
    return chip, DeviceKind.BOARD, f"chip:{chip}"


# What a laptop publishes as a sensor chip, raw unless translated.
# `ucsi_source_psy_USBC000:001` is the kernel's name for the USB-C port that
# negotiates charging, which nobody would recognize in the tree.
_POWER_SUPPLIES = (
    (re.compile(r"^(?:BAT|CMB)(\d*)$", re.I), "sensor.dev.battery"),
    (re.compile(r"^(?:AC|ADP)(\d*)$", re.I), "sensor.dev.adapter"),
    # No number: what follows `USBC` is an ACPI id, not the port's number.
    (re.compile(r"^(ucsi)[-_].*$", re.I), "sensor.dev.usbc"),
)
_IS_USBC = _POWER_SUPPLIES[-1][0]
_IS_BATTERY = _POWER_SUPPLIES[0][0]


def _by_number(path: pathlib.Path) -> tuple:
    """«temp2» before «temp10»: as text, coretemp's cores came out of order
    («Core 8, 12, Package, 20…, 0, 4»)."""
    hit = re.match(r"^([a-z]+)(\d+)_", path.name)
    return (hit.group(1), int(hit.group(2))) if hit else (path.name, 0)


def render_chip(chip: str) -> str:
    from ..render import chip_name
    return chip_name(chip)


def render_bus_address(device: str) -> str:
    from ..render import bus_address
    return bus_address(device)


def _i2c_device(entry: pathlib.Path) -> Optional[str]:
    """The I2C device a hwmon chip hangs from, «0-0050»; None off the bus."""
    try:
        name = (entry / "device").resolve().name
    except OSError:
        return None
    return name if re.fullmatch(r"\d+-[0-9a-f]{4}", name) else None


def _also_in_power_supply(chip: str) -> bool:
    """Whether this hwmon chip is the same device as a power supply entry.

    On a laptop, the battery and USB-C ports hang from both places with the
    same name. The folder must exist and publish something to be read: if
    `power_supply` gave none of those three values, skipping the hwmon chip
    would lose the value instead of deduplicating it.
    """
    # hwmon writes underscores where power_supply has dashes:
    # «ucsi_source_psy_USBC000:001» is «ucsi-source-psy-USBC000:001».
    for entry_name in dict.fromkeys((chip, chip.replace("_", "-"))):
        folder = sysroot.path(POWER_SUPPLY) / entry_name
        if folder.is_dir() and any((folder / field).exists()
                                    for field in ("voltage_now", "current_now", "power_now")):
            return True
    return False


def _power_supply_kind(chip: str) -> Optional[tuple[str, int]]:
    """Which power supply it is: its name's key, and its number (0 for none)."""
    for pattern, key in _POWER_SUPPLIES:
        if (hit := pattern.match(chip)):
            return key, _power_supply_number(hit)
    return None


def _power_supply_number(hit: re.Match) -> int:
    suffix = hit.group(1)
    return int(suffix) + 1 if suffix.isdigit() and int(suffix) else 0


def _power_supply_key(key: str, number: int) -> str:
    return f"power:{key}:{number}"


def _power_supply_name(chip: str) -> Optional[str]:
    """«Battery» instead of «BAT0», «USB-C port» instead of the kernel's name.

    The number stays when there is one: a laptop with two batteries must tell
    them apart, and with one the number is not needed.
    """
    for pattern, key in _POWER_SUPPLIES:
        if (hit := pattern.match(chip)):
            number = _power_supply_number(hit)
            return f"{_(key)} {number}" if number else _(key)
    return None


def _pci_slot(entry: pathlib.Path) -> Optional[str]:
    """The PCI address of the device a sensor chip hangs from."""
    try:
        target = (entry / "device").resolve()
    except OSError:
        return None
    while target.name and target.name != "/":
        if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", target.name):
            return target.name
        target = target.parent
    return None


def _net_name(entry: pathlib.Path) -> Optional[str]:
    """The network interface a sensor belongs to.

    A Realtek's temperature sensor hangs not from the card but from the MDIO
    bus that talks to the physical chip, a couple of levels down, so it climbs
    to the interface's `net/`.

    Virtual interfaces do not count. Climbing blindly reached
    `/sys/devices/virtual`, which has a `net/` too (loopback and bridges), and
    any virtual sensor's temperature ended under «Network (lo)». Stopping
    where devices end does not work either: the MDIO bus is a container
    without `uevent`, right in the middle of the good path.
    """
    interface = _net_iface(entry)
    return _("sensor.dev.net").format(chip=interface) if interface else None


def _net_iface(entry: pathlib.Path) -> Optional[str]:
    """The network interface a sensor belongs to, raw (`_net_name`)."""
    try:
        current = (entry / "device").resolve()
    except OSError:
        return None
    for _level in range(6):
        net = current / "net"
        if net.is_dir() and "/virtual/" not in f"{net}/":
            interfaces = sorted(p.name for p in net.iterdir())
            if interfaces:
                return interfaces[0]
        if current.parent == current:
            break
        current = current.parent
    return None


def _disk_name(entry: pathlib.Path) -> Optional[str]:
    """The model of the disk a temperature chip belongs to."""
    for candidate in (entry / "device" / "model", entry / "device" / "device" / "model"):
        if (model := read_text(str(candidate))):
            vendor = read_text(str(candidate.parent / "vendor")) or ""
            return " ".join(f"{vendor} {model}".split())
    return None


# amdgpu's labels are the firmware's. They say something to whoever knows
# what an «sclk» is, and nothing otherwise.
GPU_LABELS = {
    "sclk": "sensor.gpucore", "mclk": "sensor.mem", "fclk": "Fabric",
    "socclk": "SoC", "vddgfx": "sensor.gpucore", "vddnb": "Northbridge",
    "vddc": "sensor.gpucore", "edge": "sensor.edge",
    "junction": "sensor.hotspot", "mem": "sensor.mem",
    "PPT": "sensor.package",
}


def _friendly(chip: str, prefix: str, index: str, label: Optional[str]) -> str:
    if label:
        if GPU_CHIP.match(chip):
            return _(GPU_LABELS.get(label, label))
        # NVMe's overall temperature is labelled in English by the kernel.
        if DISK_CHIP.match(chip) and label == "Composite":
            return _("sensor.nvme.composite")
        return label
    fallback = {
        "temp": "sensor.temp", "in": "sensor.voltage", "fan": "sensor.fan",
        "power": "sensor.power", "curr": "sensor.current",
        "energy": "sensor.energy",
    }
    return f"{_(fallback.get(prefix, prefix))} {index}"


# How far a threshold of each kind can reasonably go. Chips leave unused
# fields as they come and the kernel returns them: an NVMe published «high =
# 65261.85 °C», 0xFFFF in kelvin, a factory value nobody filled. Unfiltered,
# half the sensors would have a limit no board reaches, and an alarm that
# never fires is as useless as none.
CAPS = {
    SensorKind.TEMPERATURE: 200.0,      # °C
    SensorKind.VOLTAGE: 30.0,           # V
    SensorKind.FAN: 30_000.0,           # RPM
    SensorKind.POWER: 2_000.0,          # W
    SensorKind.CURRENT: 200.0,          # A
    SensorKind.USAGE: 100.0,            # %
}


def _device_name(entry: pathlib.Path) -> str:
    """The name of the device a hwmon hangs from («nvme1», «2:0:0:0»), or
    its own if it hangs from none."""
    try:
        return (entry / "device").resolve(strict=True).name
    except OSError:
        return entry.name


def _plausible(reading, kind):
    """Drop a threshold outside what that kind of sensor can give."""
    if reading is None:
        return None
    cap = CAPS.get(kind)
    if cap is not None and not -cap <= reading <= cap:
        return None
    return reading


def _thresholds(kind, low, high, critical, chip=None) -> dict:
    """A sensor's three limits, cleaned of those that are not valid.

    Chips carry factory values in fields nobody set, and the kernel returns
    them. An nct6798 publishes `temp_min = 127` and `temp_max = 127` for its
    six temperatures: a board at 34 °C is then «below the minimum» and six
    alarms fire at once. A false alarm costs more trust than a right one wins.

    Fans raise no alarm: one at full speed is what load expects, and one
    stopped is too, as almost every modern card stops them at idle.

    Nor what is plugged in from outside: a USB-C port with nothing connected
    reads 0 V, below any minimum the chip declares. Zero there is not a fault,
    it is that nothing is plugged in.
    """
    if kind is SensorKind.FAN:
        return {"low": None, "high": None, "critical": None}
    if _power_supply_kind(chip or ""):
        return {"low": None, "high": None, "critical": None}

    low = _plausible(low, kind)
    high = _plausible(high, kind)
    critical = _plausible(critical, kind)

    # A minimum above the maximum is a pair nobody filled.
    if low is not None and high is not None and low >= high:
        low = high = None

    if kind is SensorKind.TEMPERATURE:
        # Only what the part declares: without it, no limit and no colour.
        high, critical = thermal.limits(high, critical)
    return {"low": low, "high": high, "critical": critical}


class HwmonSensors(Provider):
    """Lists every chip and hands the CPU page what is its."""

    name = "hwmon"
    provides = "sensors"

    def __init__(self) -> None:
        super().__init__()
        # The ACPI zones seen reading something other than the filler.
        self._live_zones: set[str] = set()
        # The (mirror driver, chip) pairs confirmed as the same reading.
        self._mirrors: set[tuple[str, str]] = set()

    def available(self) -> bool:
        return sysroot.path(HWMON).is_dir()

    def unavailable_reason(self):
        if self.available():
            return None
        return ("sensors", Need.DRIVER,
                _("prov.hwmon.nochips"), _("prov.hwmon.nochips.hint"), "",
                _("prov.hwmon.nochips.detail"))

    def collect(self, draft: Draft) -> None:
        cpu_name = short_brand(draft.types[next(iter(draft.types), "")].get("brand")
                               if draft.types else None)
        board_name = draft.board.display_name or _("board.unnamed")
        # The GPUs are already listed when this runs: the order of the
        # providers in `collector.py` guarantees it.
        gpu_names = {gpu["pci_slot"]: (gpu.get("name")
                                       or _("sensor.dev.gpu").format(
                                           n=gpu["index"]))
                     for gpu in draft.gpus if gpu.get("pci_slot")}

        sensors = self._without_fillers(self._read_hwmon(cpu_name, board_name, gpu_names))
        sensors = self._without_repeats(sensors)
        sensors = self._with_core_types(draft, sensors)
        sensors = self._with_their_modules(draft, sensors)
        sensors = self._with_the_sheet_maximum(draft, sensors)
        sensors += list(self._read_power_supplies())
        if not sensors:
            return

        draft.capabilities.add("hwmon")
        draft.sensors.extend(sensors)
        self._fill_cpu(draft, sensors)
        draft.driver_hints.extend(self._missing_drivers(
            sensors, laptop=draft.board.chassis in PORTABLE_CHASSIS))

    @staticmethod
    def _sheet_maximum(draft: Draft) -> Optional[float]:
        """AMD's Tjmax for this exact model, from Zen 2 on.

        Before Zen 2, k10temp's Tctl can carry an offset for fan control and
        older parts' sheets give a case temperature: neither compares with
        what is read. A hypervisor's model is not looked up.
        """
        from .. import db

        if not draft.types or is_virtual_machine(draft):
            return None
        cpu = next(iter(draft.types.values()))
        family, model = cpu.get("disp_family"), cpu.get("disp_model")
        if cpu.get("vendor_id") != "AuthenticAMD" or family is None or model is None:
            return None
        if not (family >= 0x19 or (family == 0x17 and model >= 0x30)):
            return None
        row = db.amd_model(cpu.get("brand") or "")
        return thermal.limit(row.get("tjmax_c")) if row else None

    @classmethod
    def _with_the_sheet_maximum(cls, draft: Draft, sensors: list[Sensor]) -> list[Sensor]:
        """k10temp declares no limit: its temperatures warn from the sheet's."""
        if not any(s.chip == "k10temp" for s in sensors):
            return sensors
        maximum = cls._sheet_maximum(draft)
        if maximum is None:
            return sensors
        return [dataclasses.replace(s, sheet_high=maximum)
                if (s.chip == "k10temp" and s.kind is SensorKind.TEMPERATURE
                    and s.high is None and s.critical is None) else s
                for s in sensors]

    @staticmethod
    def _with_their_modules(draft: Draft, sensors: list[Sensor]) -> list[Sensor]:
        """A memory sensor named by its module: «Temperatura 1» said nothing
        of which. By the module's number where the modules are known, and by
        its chip's address always."""
        from ..model import MemoryModule, module_numbers
        addresses = {s.bus_address for s in sensors if s.bus_address}
        if not addresses:
            return sensors
        modules = draft.modules or [MemoryModule(populated=True, spd=info) for info in draft.spd]
        numbers = module_numbers(modules, addresses)
        out = []
        for sensor in sensors:
            if sensor.bus_address and sensor.kind is SensorKind.TEMPERATURE:
                where = render_bus_address(sensor.bus_address)
                number = numbers.get(sensor.bus_address)
                label = (_("sensor.mem.module").format(n=number, direccion=where)
                         if number else _("sensor.mem.address").format(direccion=where))
                sensor = dataclasses.replace(sensor, label=label)
            out.append(sensor)
        return out

    @staticmethod
    def _with_core_types(draft: Draft, sensors: list[Sensor]) -> list[Sensor]:
        """On a hybrid processor, which type of core each core sensor reads:
        coretemp numbers them by core id («Core 20»), which doesn't say."""
        types = {cpu.get("core_id"): cpu.get("type_key") for cpu in draft.logical.values()}
        if len({t for t in types.values() if t}) < 2:
            return sensors
        out = []
        for sensor in sensors:
            if (sensor.chip in CPU_CHIPS
                    and (match := _CORE_LABEL.match(sensor.chip_label or ""))
                    and types.get(int(match.group(1))) in ("performance", "efficiency")):
                sensor = dataclasses.replace(sensor, core_type=types[int(match.group(1))])
            out.append(sensor)
        return out

    # -- reading ------------------------------------------------------------

    def _without_fillers(self, found_sensors: Iterator[Sensor]) -> list[Sensor]:
        """Mark the ACPI zones giving the firmware's fixed number.

        On a laptop those zones really measure and can pass through 27.8 °C
        like any other value: one seen at another number is not marked again,
        so it is remembered between samples.
        """
        out = []
        for sensor in found_sensors:
            if (sensor.chip == ACPI_ZONES_CHIP
                    and sensor.kind is SensorKind.TEMPERATURE):
                if sensor.value not in FILLER_VALUES:
                    self._live_zones.add(sensor.key)
                elif sensor.key not in self._live_zones:
                    sensor = dataclasses.replace(sensor, placeholder=True, low=None,
                                                 high=None, critical=None)
            out.append(sensor)
        return out

    def _without_repeats(self, found_sensors: list[Sensor]) -> list[Sensor]:
        """Mark the temperatures a driver repeats from another (`MIRRORS`).

        A board can show twelve temperatures that are six: the IT8688's and
        the same again through `gigabyte_wmi`. They are taken as repeated when
        both drivers publish the same number of probes reading the same as
        their pair, within two readings' margin and forgiving one. Once
        confirmed it is remembered: under load a probe can move more than the
        margin between reading one driver and the other, and the tree cannot
        gain and lose six rows every sample.
        """
        def temperatures(chip: str) -> list[Sensor]:
            return sorted((s for s in found_sensors if s.chip == chip
                           and s.kind is SensorKind.TEMPERATURE), key=lambda s: s.order)

        chips = list(dict.fromkeys(s.chip for s in found_sensors))
        repeated: dict[str, str] = {}
        for mirror, pattern in MIRRORS.items():
            own = temperatures(mirror)
            if not own:
                continue
            for chip in chips:
                if not pattern.match(chip):
                    continue
                others = temperatures(chip)
                if len(others) != len(own):
                    continue
                if (mirror, chip) not in self._mirrors:
                    # All but one: the socket's probe moves several degrees a
                    # second, and between reading one driver and the other it
                    # may not match even being the same one.
                    far = sum(1 for a, b in zip(own, others)
                                if abs(a.value - b.value) > MIRROR_MARGIN)
                    if far > (1 if len(own) >= 3 else 0):
                        continue
                    self._mirrors.add((mirror, chip))
                repeated.update({s.key: chip for s in own})
                break
        if not repeated:
            return found_sensors
        return [dataclasses.replace(s, mirror_of=repeated[s.key])
                if s.key in repeated else s for s in found_sensors]

    def _read_hwmon(self, cpu_name: str, board_name: str,
                    gpu_names: Optional[dict[str, str]] = None) -> Iterator[Sensor]:
        if not sysroot.path(HWMON).is_dir():
            return
        entries = sorted(sysroot.path(HWMON).iterdir())
        names = [read_text(str(entry / "name")) for entry in entries]
        for entry, chip in zip(entries, names):
            if not chip:
                continue
            # A laptop's battery and USB-C ports show in two places: here and
            # in `/sys/class/power_supply`, with the same chip name and values.
            # power_supply's reading stays, as it carries named labels
            # («Voltage» and not «Voltage 0»): there the kernel says what each
            # file is.
            if _also_in_power_supply(chip):
                continue
            device, device_kind, key = device_for(chip, entry, cpu_name, board_name, gpu_names)
            channels = sorted(entry.glob("*_input"), key=_by_number)
            seen = {path.name.replace("_input", "") for path in channels}
            for suffix in ALTERNATIVES:
                channels += [path for path in sorted(entry.glob(f"*{suffix}"), key=_by_number)
                            if path.name.replace(suffix, "") not in seen]
            address = _i2c_device(entry) if device_kind == DeviceKind.MEMORY else None
            for order, path in enumerate(channels):
                sensor = self._parse(chip, device, path, order, device_kind, key)
                if sensor is not None and address:
                    # Each module's chip on its own: two had the same key.
                    sensor = dataclasses.replace(
                        sensor, key=f"{chip}-{address}/{sensor.key.split('/', 1)[1]}",
                        bus_address=address)
                elif sensor is not None and names.count(chip) > 1:
                    # Two drives of one driver (two NVMe) shared their keys,
                    # and with them one row, its peak and its average. By the
                    # device each hangs from, which a reboot keeps.
                    sensor = dataclasses.replace(
                        sensor, key=f"{chip}-{_device_name(entry)}/{sensor.key.split('/', 1)[1]}")
                if sensor is not None:
                    yield sensor

    @staticmethod
    def _parse(chip: str, device: str, path: pathlib.Path, order: int = 0,
               device_kind: str = DeviceKind.BOARD, device_key: str = "") -> Optional[Sensor]:
        match = re.match(r"^([a-z]+)(\d+)_(?:input|average)$", path.name)
        if match is None:
            return None
        prefix, index = match.groups()
        suffix = "_average" if path.name.endswith("_average") else "_input"
        if prefix not in MEASUREMENTS:
            return None

        raw = read_int(str(path))
        if raw is None:
            return None
        kind, divisor = MEASUREMENTS[prefix]

        def threshold(entry_name: str) -> Optional[float]:
            value = read_int(str(path).replace(suffix, f"_{entry_name}"))
            return None if value is None else value / divisor

        label_text = read_text(str(path).replace(suffix, "_label"))
        return Sensor(
            key=f"{chip}/{prefix}{index}",
            chip=chip,
            device=device,
            device_kind=device_kind,
            device_key=device_key,
            label=_friendly(chip, prefix, index, label_text),
            chip_label=label_text,
            unnamed=not label_text,
            kind=kind,
            value=round(raw / divisor, 3),
            **_thresholds(kind, threshold("min"), threshold("max"),
                        threshold("crit"), chip),
            order=order,
        )

    @staticmethod
    def _read_power_supplies() -> Iterator[Sensor]:
        """Batteries and adapters. A desktop has none; on a laptop they are
        half of what matters."""
        if not sysroot.path(POWER_SUPPLY).is_dir():
            return
        fields = (
            ("voltage_now", SensorKind.VOLTAGE, 1_000_000.0, "sensor.voltage"),
            ("current_now", SensorKind.CURRENT, 1_000_000.0, "sensor.current"),
            ("power_now", SensorKind.POWER, 1_000_000.0, "sensor.power"),
        )
        entries = sorted(sysroot.path(POWER_SUPPLY).iterdir())
        # A laptop's USB-C ports, numbered in order when there are several,
        # instead of being told apart by the kernel's name.
        ports = [e.name for e in entries if _IS_USBC.match(e.name)]
        # The kernel may call the only battery BAT1: numbered only when there
        # are several.
        batteries = [e.name for e in entries if _IS_BATTERY.match(e.name)]
        for entry in entries:
            name = entry.name
            device = _power_supply_name(name) or _("sensor.dev.power").format(n=name)
            if batteries == [name]:
                device = _("sensor.dev.battery")
            supply = _power_supply_kind(name)
            key = (_power_supply_key(*supply) if supply
                     else f"power-supply:{name}")
            if name in ports:
                # Nothing plugged in: it reads 0 V and 0 A, which says nothing.
                if read_int(str(entry / "online")) == 0:
                    continue
                if len(ports) > 1:
                    device = f"{device} {ports.index(name) + 1}"
                    key = f"{key}#{ports.index(name) + 1}"
            for filename, kind, divisor, label in fields:
                raw = read_int(str(entry / filename))
                if raw is None:
                    continue
                yield Sensor(
                    key=f"power_supply/{name}/{filename}",
                    chip=name,
                    device=device,
                    device_kind=DeviceKind.POWER,
                    device_key=key,
                    label=_(label), kind=kind,
                    value=round(abs(raw) / divisor, 3),
                )

    # -- handing out to the CPU page ----------------------------------------

    def _fill_cpu(self, draft: Draft, sensors: list[Sensor]) -> None:
        by_chip: dict[str, list[Sensor]] = {}
        for sensor in sensors:
            by_chip.setdefault(sensor.chip, []).append(sensor)

        # A zone giving the filler number is nobody's temperature.
        chip = next((name for name in CPU_CHIPS
                     if any(not s.placeholder for s in by_chip.get(name, ()))), None)
        if chip is None:
            draft.note("cpu.temp_c", Need.DRIVER,
                       _("prov.hwmon.nocpu"),
                       _("prov.hwmon.nocpu.hint").format(
                           chips=", ".join(sorted(by_chip))))
        else:
            self._spread_temperatures(
                draft, [s for s in by_chip[chip] if not s.placeholder])

        self._pick_voltage(draft, sensors)

    @staticmethod
    def _spread_temperatures(draft: Draft, sensors: list[Sensor]) -> None:
        per_core: dict[int, float] = {}
        package: list[float] = []
        # `k10temp` only publishes Tdie where Tctl carries an offset for fan
        # control (20 °C on an 1800X, 27 on a Threadripper 1950X). With both,
        # the temperature is Tdie; with Tctl alone, they are the same.
        die: list[float] = []
        unlabelled: list[float] = []
        # The sensors each figure comes from, for their declared limits.
        by_role: dict[str, list[Sensor]] = {"core": [], "die": [], "package": [],
                                            "unlabelled": []}

        for sensor in sensors:
            if sensor.kind is not SensorKind.TEMPERATURE:
                continue
            label_text = sensor.chip_label or ""
            if match := _CORE_LABEL.match(label_text):
                per_core[int(match.group(1))] = sensor.value
                by_role["core"].append(sensor)
            elif label_text.lower() == "tdie":
                die.append(sensor.value)
                by_role["die"].append(sensor)
            elif _PACKAGE_LABEL.match(label_text):
                package.append(sensor.value)
                by_role["package"].append(sensor)
            else:
                unlabelled.append(sensor.value)
                by_role["unlabelled"].append(sensor)

        source = "die" if die else "package"
        package = die or package
        if package:
            # The package's own sensor, which a GPU inside it shares.
            draft.cpu_extra["package_sensor_temp_c"] = round(max(package), 1)
        if not package and not per_core:
            package = unlabelled            # single-sensor chips, like acpitz
            source = "unlabelled"
        # `CpuInfo.temperature_c` is the package's, or else the cores': the
        # limits are those its sensors declare.
        declared = [s for s in by_role[source if package else "core"]
                    if s.high is not None or s.critical is not None]
        if declared:
            draft.cpu_extra["temp_high_c"] = declared[0].high
            draft.cpu_extra["temp_critical_c"] = declared[0].critical
        elif sheet := [s.sheet_high for s in by_role[source if package else "core"]
                       if s.sheet_high is not None]:
            draft.cpu_extra["temp_sheet_high_c"] = sheet[0]

        for cpu in draft.logical.values():
            if (value := per_core.get(cpu.get("core_id", -1))) is not None:
                cpu["temp_c"] = value

        if package:
            draft.cpu_extra["package_temp_c"] = round(max(package), 1)

        for entry in draft.types.values():
            average = mean([draft.logical[i].get("temp_c") for i in entry.get("cpus", ())])
            if average is not None:
                entry["temp_c"] = round(average, 1)
            elif package:
                entry["temp_c"] = round(max(package), 1)

    @staticmethod
    def _pick_voltage(draft: Draft, sensors: list[Sensor]) -> None:
        for sensor in sensors:
            if sensor.kind is SensorKind.VOLTAGE and _VCORE_LABEL.search(sensor.chip_label or ""):
                for entry in draft.types.values():
                    entry["voltage_v"] = sensor.value
                return
        # With none labelled, no notice here: `msr_voltage` runs after and
        # knows whether the processor itself can give it. A notice here too
        # said two things of the same, and this one said nothing could be done.

    # -- missing drivers ----------------------------------------------------

    @staticmethod
    def _module_exists(module: str) -> bool:
        def ask() -> bool:
            modinfo = system_deps.program_path("modinfo")
            if not modinfo:
                return False
            result = subprocess.run([modinfo, "-F", "filename", module],
                                    capture_output=True, text=True,
                                    env=system_environment())
            return result.returncode == 0 and bool(result.stdout.strip())
        return bool(sysroot.recorded("modinfo", module, ask))

    def _missing_drivers(self, sensors: list[Sensor],
                         laptop: bool = False) -> Iterator[DriverHint]:
        chips = {sensor.chip for sensor in sensors}

        if not laptop and not any(SUPERIO_CHIPS.match(chip) for chip in chips):
            yield DriverHint(
                module=SUPERIO,
                provides=_("prov.hint.superio"),
                command="sudo sensors-detect",
                caution=_("prov.hint.superio.caution"),
            )

        if "drivetemp" not in chips and self._has_ata_disks() and self._module_exists("drivetemp"):
            yield DriverHint(
                module="drivetemp",
                provides=_("prov.hint.drivetemp"),
                command="sudo modprobe drivetemp",
                caution="",
            )

    @staticmethod
    def _has_ata_disks() -> bool:
        block = pathlib.Path(sysroot.path("/sys/class/block"))
        if not block.is_dir():
            return False
        return any("/ata" in str(entry.resolve()) for entry in block.glob("sd?"))
