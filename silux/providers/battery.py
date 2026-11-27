"""The battery, the part of a laptop that wears out most.

What people want to know isn't its voltage but how much capacity it has
left compared with new.

The kernel reports capacity as `charge_*` (µAh) or `energy_*` (µWh),
depending on the firmware, and some report both. Milliamp-hours can't be
compared across machines without the cell voltage (4000 mAh at 7.6 V and at
11.4 V are very different batteries), so everything here is in watt-hours:
a charge is multiplied by the design voltage, which goes with the nominal
capacity and doesn't move with the charge level.

No permissions needed: plain sysfs.
"""

from __future__ import annotations

import dataclasses
import pathlib
import time
from typing import Optional

from .. import sysroot
from ..i18n import _
from ..model import Battery, Need
from . import counters
from .base import Draft, Provider, read_int, read_text

POWER_SUPPLY = pathlib.Path("/sys/class/power_supply")
# Lenovo IdeaPad and LOQ: the charge kept around 60–80 % to spare the cell.
# Readable by anyone; the driver publishes it on its ACPI device.
IDEAPAD = pathlib.Path("/sys/bus/platform/drivers/ideapad_acpi")

# The kernel's status → its translation key. The kernel writes it
# capitalised, in English, which is never shown.
STATUSES = {
    "charging": "bat.status.charging",
    "discharging": "bat.status.discharging",
    "full": "bat.status.full",
    "not charging": "bat.status.held",
    "unknown": "bat.status.unknown",
}


# A lithium cell lives between about 2.5 V, where the protection cuts it,
# and 4.45 V, a high-voltage cell full; its nominal is 3.6 to 3.85 V. A pack
# can't read outside these fractions of its nominal voltage.
VOLTAGE_RANGE = (0.6, 1.25)


def _technology(raw: Optional[str]) -> Optional[str]:
    return None if not raw or raw.strip().lower() == "unknown" else raw.strip()


def _firmware_text(raw: Optional[str]) -> Optional[str]:
    """The text as the firmware wrote it, or None if it's only control
    characters: an empty field some firmwares fill with a byte."""
    if not raw:
        return None
    text = "".join(c for c in raw if c.isprintable()).strip()
    return text or None


def _plausible(volts: Optional[float], nominal: Optional[float]) -> bool:
    if not volts or not nominal:
        return True
    low, high = VOLTAGE_RANGE
    return low * nominal <= volts <= high * nominal


def _is_battery(entry: pathlib.Path) -> bool:
    """The machine's battery, not the charger or a wireless mouse.

    `/sys/class/power_supply` holds the adapter, USB-C ports and any device
    with a cell, and `type=Battery` alone would give a desktop a battery page
    for its mouse. `scope` tells them apart: devices say «Device», the
    machine's battery says «System», or nothing on older laptops.
    """
    if (read_text(str(entry / "type")) or "").strip().lower() != "battery":
        return False
    scope = (read_text(str(entry / "scope")) or "").strip().lower()
    return scope in ("", "system", "unknown")


def _watt_hours(entry: pathlib.Path, which: str,
                 nominal_voltage: Optional[float]) -> Optional[float]:
    """`energy_*` if present; else `charge_*` times the design voltage."""
    if (microwatt_hours := read_int(str(entry / f"energy_{which}"))) is not None:
        return round(microwatt_hours / 1e6, 2)
    microamp_hours = read_int(str(entry / f"charge_{which}"))
    if microamp_hours is None or not nominal_voltage:
        return None
    return round(microamp_hours / 1e6 * nominal_voltage, 2)


def _watts(entry: pathlib.Path, voltage: Optional[float]) -> Optional[float]:
    """What flows in or out right now, always positive.

    The sign of `current_now` differs between firmwares, so the absolute
    value is taken and `status` gives the direction.
    """
    if (microwatts := read_int(str(entry / "power_now"))) is not None:
        return round(abs(microwatts) / 1e6, 2)
    microamps = read_int(str(entry / "current_now"))
    if microamps is None or not voltage:
        return None
    return round(abs(microamps) / 1e6 * voltage, 2)


def _conservation_mode(entry: pathlib.Path) -> Optional[bool]:
    """Whether the laptop holds the charge low to spare the cell, if it says.

    The kernel's generic `charge_types` calls it Long_Life; before that,
    Lenovo's driver published it as `conservation_mode`.
    """
    types = read_text(str(entry / "charge_types"))
    if types and "[" in types:
        return "[Long_Life]" in types
    for path in sorted(sysroot.path(IDEAPAD).glob("*/conservation_mode")):
        value = read_int(str(path))
        if value in (0, 1):
            return value == 1
    return None


def readable_voltage(entry: pathlib.Path) -> Optional[float]:
    """The pack's voltage, or None when it reads none or one no pack of its
    nominal has (Sensors leaves out what Batería says it can't read)."""
    voltage = read_int(str(entry / "voltage_now"))
    volts = round(voltage / 1e6, 3) if voltage else None
    design = read_int(str(entry / "voltage_min_design"))
    design_volts = round(design / 1e6, 3) if design else None
    return volts if _plausible(volts, design_volts) else None


def _read(entry: pathlib.Path) -> Battery:
    voltage = read_int(str(entry / "voltage_now"))
    volts = round(voltage / 1e6, 3) if voltage else None
    design = read_int(str(entry / "voltage_min_design"))
    design_volts = round(design / 1e6, 3) if design else None
    impossible = None
    if not _plausible(volts, design_volts):
        impossible, volts = volts, None

    # The design voltage converts mAh to Wh because it goes with the nominal
    # capacity; the current voltage moves with the charge and would give a
    # different capacity every sample.
    nominal = design_volts or volts

    raw = (read_text(str(entry / "status")) or "").strip().lower()
    percent = read_int(str(entry / "capacity"))
    end = read_int(str(entry / "charge_control_end_threshold"))
    status = STATUSES.get(raw, "bat.status.unknown")
    conservation = _conservation_mode(entry)
    # «Not charging» is held at the top only when it is at the top: below its
    # stop threshold it waits to drop under the start one, and below full it
    # is a conservation mode, or a charger that doesn't charge.
    if status == "bat.status.held":
        if conservation:
            status = "bat.status.conservation"
        elif end and percent is not None and percent < end - 1:
            status = "bat.status.paused"
        elif not end and percent is not None and percent < 99:
            status = "bat.status.notcharging"

    full_wh = _watt_hours(entry, "full", nominal)
    design_wh = _watt_hours(entry, "full_design", nominal)
    now_wh = _watt_hours(entry, "now", nominal)
    # A charge of zero with no capacity or percentage to set it against is
    # the firmware filling the field, not an empty battery.
    if now_wh == 0 and not full_wh and not design_wh and percent is None:
        now_wh = None

    return Battery(
        name=entry.name,
        present=read_int(str(entry / "present")) != 0,
        status=status,
        percent=float(percent) if percent is not None else None,
        design_wh=design_wh,
        full_wh=full_wh,
        now_wh=now_wh,
        voltage_v=volts,
        design_voltage_v=design_volts,
        impossible_voltage_v=impossible,
        power_w=_watts(entry, volts),
        cycles=read_int(str(entry / "cycle_count")) or None,
        manufacturer=_firmware_text(read_text(str(entry / "manufacturer"))),
        model=_firmware_text(read_text(str(entry / "model_name"))),
        # «Unknown» is the kernel's word for none (POWER_SUPPLY_TECHNOLOGY_UNKNOWN).
        technology=_technology(_firmware_text(read_text(str(entry / "technology")))),
        serial=_firmware_text(read_text(str(entry / "serial_number"))),
        charge_start_percent=read_int(
            str(entry / "charge_control_start_threshold")),
        charge_end_percent=end,
        conservation_mode=conservation,
    )


# Which way `energy_now` moves in each state: what it does the other way is
# no rate (the charger went in or out between readings).
DIRECTION = {"bat.status.charging": 1, "bat.status.discharging": -1}


@dataclasses.dataclass
class _EnergySeen:
    """The last `energy_now` value and when it was first read."""
    wh: float
    since_s: float
    status: str
    # Whether `since_s` is when the firmware changed it. The first value's
    # isn't: it was there already, and a window from it would be too short.
    at_a_change: bool
    power_w: Optional[float] = None


class Batteries(Provider):
    """The machine's batteries. A desktop has none."""

    name = "battery"
    provides = "batteries"

    def __init__(self) -> None:
        super().__init__()
        self._energy: dict[str, _EnergySeen] = {}

    def _from_energy(self, battery: Battery, now_s: float, interval_s: float) -> Optional[float]:
        """Watts from how much `energy_now` moved between two of the
        firmware's updates, which come every few seconds: between two
        readings of ours it mostly stays put."""
        seen = self._energy.get(battery.name)
        if seen is None or seen.status != battery.status:
            self._energy[battery.name] = _EnergySeen(battery.now_wh, now_s, battery.status, False)
            return None
        if battery.now_wh == seen.wh:
            return seen.power_w
        moved = (battery.now_wh - seen.wh) * DIRECTION[battery.status]
        seconds = counters.window_s(seen.since_s, now_s, interval_s)
        power = (round(moved * 3600 / seconds, 2)
                 if seen.at_a_change and seconds is not None and moved > 0 else None)
        self._energy[battery.name] = _EnergySeen(battery.now_wh, now_s, battery.status, True, power)
        return power

    def available(self) -> bool:
        return sysroot.path(POWER_SUPPLY).is_dir()

    def unavailable_reason(self):
        if self.available():
            return None
        return ("batteries", Need.PLATFORM,
                _("prov.bat.nosysfs"), _("prov.bat.nosysfs.hint"), "",
                _("prov.missing.detail").format(ruta="/sys/class/power_supply"))

    def collect(self, draft: Draft) -> None:
        if not sysroot.path(POWER_SUPPLY).is_dir():
            return
        found = [_read(entry)
                       for entry in sorted(sysroot.path(POWER_SUPPLY).iterdir())
                       if _is_battery(entry)]
        if not found:
            # No note: a desktop has no battery, and saying so would be
            # warning that a machine is what it is. The page just hides.
            return
        now_s = time.monotonic()
        for index, battery in enumerate(found):
            if (battery.power_w is None and battery.now_wh is not None
                    and battery.status in DIRECTION):
                watts = self._from_energy(battery, now_s, draft.interval_s)
                found[index] = dataclasses.replace(battery, power_w=watts,
                                                   power_from_energy=watts is not None)
            else:
                self._energy.pop(battery.name, None)
        draft.capabilities.add("battery")
        draft.batteries = found
