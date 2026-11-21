"""The battery, the part of a laptop that wears out the most.

What people want to know is not its voltage: it is how much capacity it has
left against what it had new.

**Two conventions, both in use.** Depending on the firmware, the kernel
publishes capacity as `charge_*` (µAh) or `energy_*` (µWh), and some publish
both. Milliamp-hours cannot be compared across machines without the cell
voltage (4000 mAh at 7.6 V and at 11.4 V are very different batteries), so
everything here is in watt-hours: a charge is multiplied by the design
voltage, which is the one that goes with the nominal capacity and does not
move with how full it is.

No permissions needed: plain sysfs.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from .. import sysroot
from ..i18n import _
from ..model import Battery, Need
from .base import Draft, Provider, read_int, read_text

POWER_SUPPLY = pathlib.Path("/sys/class/power_supply")

# The kernel's status -> its translation key. The kernel writes it in English
# and capitalized, which is not shown.
STATUSES = {
    "charging": "bat.status.charging",
    "discharging": "bat.status.discharging",
    "full": "bat.status.full",
    "not charging": "bat.status.held",
    "unknown": "bat.status.unknown",
}


def _is_battery(entry: pathlib.Path) -> bool:
    """The machine's battery, not the charger or a wireless mouse.

    `/sys/class/power_supply` holds everything: the power adapter, USB-C
    ports and any device with a cell. `type` is not enough: a wireless mouse
    publishes `type=Battery` too, and a desktop would get a battery page.
    `scope` tells them apart: devices say «Device»; the machine's battery
    says «System», or nothing on older laptops.
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
    """What goes in or out right now, always positive.

    The sign of `current_now` means different things in different firmware,
    so the absolute value is taken and `status` says which way it goes.
    """
    if (microwatts := read_int(str(entry / "power_now"))) is not None:
        return round(abs(microwatts) / 1e6, 2)
    microamps = read_int(str(entry / "current_now"))
    if microamps is None or not voltage:
        return None
    return round(abs(microamps) / 1e6 * voltage, 2)


def _read(entry: pathlib.Path) -> Battery:
    voltage = read_int(str(entry / "voltage_now"))
    volts = round(voltage / 1e6, 3) if voltage else None
    design = read_int(str(entry / "voltage_min_design"))
    design_volts = round(design / 1e6, 3) if design else None

    # The design voltage converts mAh to Wh: it goes with the nominal
    # capacity. The current one moves with the charge and would give another
    # capacity on every sample.
    nominal = design_volts or volts

    raw = (read_text(str(entry / "status")) or "").strip().lower()
    percent = read_int(str(entry / "capacity"))

    return Battery(
        name=entry.name,
        present=read_int(str(entry / "present")) != 0,
        status=STATUSES.get(raw, "bat.status.unknown"),
        percent=float(percent) if percent is not None else None,
        design_wh=_watt_hours(entry, "full_design", nominal),
        full_wh=_watt_hours(entry, "full", nominal),
        now_wh=_watt_hours(entry, "now", nominal),
        voltage_v=volts,
        design_voltage_v=design_volts,
        power_w=_watts(entry, volts),
        cycles=read_int(str(entry / "cycle_count")) or None,
        manufacturer=read_text(str(entry / "manufacturer")),
        model=read_text(str(entry / "model_name")),
        technology=read_text(str(entry / "technology")),
        serial=read_text(str(entry / "serial_number")),
        charge_start_percent=read_int(
            str(entry / "charge_control_start_threshold")),
        charge_end_percent=read_int(
            str(entry / "charge_control_end_threshold")),
    )


class Batteries(Provider):
    """The machine's batteries. A desktop has none, and that is said."""

    name = "battery"
    provides = "batteries"

    def available(self) -> bool:
        return sysroot.ruta(POWER_SUPPLY).is_dir()

    def unavailable_reason(self):
        if self.available():
            return None
        return ("batteries", Need.PLATFORM,
                _("prov.bat.nosysfs"), _("prov.bat.nosysfs.hint"), "",
                _("prov.missing.detail").format(ruta="/sys/class/power_supply"))

    def collect(self, draft: Draft) -> None:
        if not sysroot.ruta(POWER_SUPPLY).is_dir():
            return
        found = [_read(entry)
                       for entry in sorted(sysroot.ruta(POWER_SUPPLY).iterdir())
                       if _is_battery(entry)]
        if not found:
            # No note: a desktop has no battery, and saying so every time
            # would be warning that a machine is what it is. The page hides.
            return
        draft.capabilities.add("battery")
        draft.batteries = found
