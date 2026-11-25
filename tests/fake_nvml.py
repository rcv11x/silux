"""A libnvidia-ml that answers as the driver answered on real cards.

The dumps do not record NVML calls, only what Silux made of them, so the
cases that depend on what each call answers are tested against this. Each
call takes the arguments nvml.h gives it and writes where NVML writes;
a call a card does not answer returns the code the driver returned there.
The figures of each card come from the reports named in its docstring.
"""

from __future__ import annotations

import contextlib
import dataclasses
from typing import Optional
from unittest import mock

from silux import nvml, sysroot

NOT_SUPPORTED = 3
INSUFFICIENT_SIZE = 7

SLOT = "0000:01:00.0"
NVML_SLOT = b"00000000:01:00.0"

# The power monitor's period on the cards seen: 119 samples in 2.44 s.
SAMPLE_PERIOD_US = 20_678
FIRST_SAMPLE_US = 1_764_000_000_000_000


@dataclasses.dataclass
class Card:
    name: str
    # nvmlDeviceGetPowerUsage, or None for NOT_SUPPORTED. A list answers one
    # value per reading, the last one from then on.
    power_mw: object = None
    # Power fields 185 and 186 that answer; the rest are NOT_SUPPORTED.
    fields: dict = dataclasses.field(default_factory=dict)
    # The power samples buffer, in mW, from the oldest.
    samples: list = dataclasses.field(default_factory=list)
    energy_mj: Optional[int] = None
    enforced_mw: Optional[int] = None
    default_mw: Optional[int] = None
    constraints_mw: Optional[tuple] = None
    temp_c: int = 40
    processes: int = 0


def rtx_4060_desktop() -> Card:
    """A desktop RTX 4060 on driver 595 at idle, as `nvidia-smi -q -d POWER`
    showed it: power draw, average and instant N/A, and 119 power samples
    between 52.59 and 55.37 W, 53.11 on average; limits 90 to 115 W."""
    return Card(name="NVIDIA GeForce RTX 4060",
                samples=[52590] + [53095] * 102 + [53096] * 15 + [55370],
                enforced_mw=115000, default_mw=115000, constraints_mw=(90000, 115000),
                temp_c=37)


def rtx_4070() -> Card:
    """A card with a power sensor: nvmlDeviceGetPowerUsage answers."""
    return Card(name="NVIDIA GeForce RTX 4070", power_mw=110500,
                fields={185: 110500, 186: 112000}, samples=[110400] * 49,
                energy_mj=812_345_678, enforced_mw=200000, default_mw=200000,
                constraints_mw=(100000, 220000), temp_c=54)


def rtx_4050_laptop() -> Card:
    """A laptop RTX 4050 on driver 550: its first reading after waking was
    588.21 W, and the next one, a few seconds later, 1.28 W."""
    return Card(name="NVIDIA GeForce RTX 4050 Laptop GPU", power_mw=[588210, 1280],
                samples=[1280] * 49, energy_mj=4_560_000, enforced_mw=80000,
                default_mw=80000, constraints_mw=(5000, 95000), temp_c=44)


class FakeNvml:
    """One card behind libnvidia-ml."""

    def __init__(self, card: Card):
        self.card = card
        self.inits = 0
        self.shutdowns = 0
        self.readings = 0
        self.since: list[int] = []
        self._next_sample_us = FIRST_SAMPLE_US + len(card.samples) * SAMPLE_PERIOD_US
        self._samples = [(FIRST_SAMPLE_US + i * SAMPLE_PERIOD_US, mw)
                         for i, mw in enumerate(card.samples)]

    def advance(self, seconds: float, milliwatts: int) -> None:
        """The driver keeps sampling for `seconds` more."""
        for _i in range(round(seconds * 1_000_000 / SAMPLE_PERIOD_US)):
            self._samples.append((self._next_sample_us, milliwatts))
            self._next_sample_us += SAMPLE_PERIOD_US

    # -- lifecycle and enumeration -------------------------------------------

    def nvmlInit_v2(self):
        self.inits += 1
        return 0

    def nvmlShutdown(self):
        self.shutdowns += 1
        return 0

    def nvmlDeviceGetCount_v2(self, count):
        count._obj.value = 1
        return 0

    def nvmlDeviceGetHandleByIndex_v2(self, index, handle):
        handle._obj.value = 1
        return 0

    def nvmlDeviceGetPciInfo_v3(self, handle, pci):
        pci._obj.busId = NVML_SLOT
        return 0

    def nvmlDeviceGetName(self, handle, buffer, size):
        buffer.value = self.card.name.encode()
        return 0

    def nvmlDeviceGetTemperature(self, handle, sensor, value):
        value._obj.value = self.card.temp_c
        return 0

    # -- power ---------------------------------------------------------------

    def nvmlDeviceGetPowerUsage(self, handle, value):
        self.readings += 1
        answer = self.card.power_mw
        if isinstance(answer, list):
            answer = answer[min(self.readings, len(answer)) - 1]
        if answer is None:
            return NOT_SUPPORTED
        value._obj.value = answer
        return 0

    def nvmlDeviceGetFieldValues(self, handle, count, fields):
        for field in fields[:count.value]:
            if field.fieldId in self.card.fields:
                field.nvmlReturn, field.valueType = 0, 1
                field.value.uiVal = self.card.fields[field.fieldId]
            else:
                field.nvmlReturn = NOT_SUPPORTED
        return 0

    def nvmlDeviceGetSamples(self, handle, kind, last_seen, value_type, count, samples):
        """Only samples newer than `last_seen`; without a buffer, how many."""
        if samples is None:
            self.since.append(last_seen.value)
        newer = [s for s in self._samples if s[0] > last_seen.value]
        value_type._obj.value = 1                      # NVML_VALUE_TYPE_UNSIGNED_INT
        if samples is None:
            count._obj.value = len(newer)
            return 0
        for i, (stamp, mw) in enumerate(newer[:count._obj.value]):
            samples[i].timeStamp = stamp
            samples[i].sampleValue.uiVal = mw
        count._obj.value = min(count._obj.value, len(newer))
        return 0

    def nvmlDeviceGetTotalEnergyConsumption(self, handle, value):
        if self.card.energy_mj is None:
            return NOT_SUPPORTED
        value._obj.value = self.card.energy_mj
        return 0

    def nvmlDeviceGetEnforcedPowerLimit(self, handle, value):
        if self.card.enforced_mw is None:
            return NOT_SUPPORTED
        value._obj.value = self.card.enforced_mw
        return 0

    def nvmlDeviceGetPowerManagementDefaultLimit(self, handle, value):
        if self.card.default_mw is None:
            return NOT_SUPPORTED
        value._obj.value = self.card.default_mw
        return 0

    def nvmlDeviceGetPowerManagementLimitConstraints(self, handle, low, high):
        if self.card.constraints_mw is None:
            return NOT_SUPPORTED
        low._obj.value, high._obj.value = self.card.constraints_mw
        return 0


    # -- who uses it ---------------------------------------------------------

    def nvmlDeviceGetGraphicsRunningProcesses_v3(self, handle, count, infos):
        """With room for none, how many: INSUFFICIENT_SIZE if there are any."""
        count._obj.value = self.card.processes
        return INSUFFICIENT_SIZE if self.card.processes else 0

    def nvmlDeviceGetComputeRunningProcesses_v3(self, handle, count, infos):
        count._obj.value = 0
        return 0


def power_file(status: str) -> str:
    """`/proc/driver/nvidia/gpus/<slot>/power` as nv-procfs.c writes it."""
    return (f"Runtime D3 status:          {status}\n"
            "Video Memory:               Active\n\n"
            "GPU Hardware Support:\n"
            " Video Memory Self Refresh: Supported\n"
            " Video Memory Off:          Supported\n\n"
            "S0ix Power Management:\n"
            " Platform Support:          Not Supported\n"
            " Status:                    Disabled\n\n"
            "Notebook Dynamic Boost:     Supported\n")


def bus(runtime_status: str = "active", d3: Optional[str] = None) -> dict:
    """The card's PCI node and, with `d3`, the driver's power file."""
    base = f"/sys/bus/pci/devices/{SLOT}"
    files = {f"{base}/vendor": "0x10de\n", f"{base}/class": "0x030000\n",
             f"{base}/power/runtime_status": f"{runtime_status}\n"}
    if d3 is not None:
        files[f"/proc/driver/nvidia/gpus/{SLOT}/power"] = power_file(d3)
    return files


@contextlib.contextmanager
def loaded(fake: FakeNvml):
    """The provider talks to `fake` as if it were the machine's NVML, while
    the files it reads come from the tree mounted around it."""
    with mock.patch.object(nvml.ctypes, "CDLL", lambda name: fake), \
            mock.patch.object(sysroot, "active", return_value=False):
        yield
