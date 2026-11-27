"""Fills NVIDIA cards with what only NVML knows.

`DrmGpus` has listed them (the PCI node is there for every driver), but with
the proprietary driver that card comes almost empty. This completes it by
asking NVML and matching by PCI address, the only identifier both publish.

It replaces nothing: what came from sysfs (a card with nouveau) stays, and
NVML only fills gaps. The session opens once and stays open; the collector
closes it on exit, the same way it closes the helper. On a card the driver
switches off when idle, an open session keeps it on: there it is closed as
soon as nothing else uses the card (docs/nvml.md, «Que Silux no la mantenga
despierta»).
"""

from __future__ import annotations

import dataclasses
import glob
import os
import time
from typing import Optional

from .. import nvml, sysroot
from ..i18n import _
from ..model import GpuClocks, GpuMemory, Need, PcieLink
from .base import Draft, Provider, read_text
from .dmi import PORTABLE_CHASSIS
from .drm import say_asleep

# Each PCIe generation's speed, to translate the number NVML gives.
SPEEDS_GTS = {1: 2.5, 2: 5.0, 3: 8.0, 4: 16.0, 5: 32.0, 6: 64.0}

# How long NVML stays closed once nothing else uses a card that can sleep.
# The driver switches it off after two of its idle checks in a row, 5 s
# apart, and 200 ms more (GC6_PRECONDITION_CHECK_TIME in dynamic-power.c).
LET_IT_SLEEP_S = 15.0

SUSPENDED = ("suspended", "suspending")


class NvidiaGpus(Provider):
    """Memory, clocks, sensors and throttling of GeForce cards."""

    name = "nvml"
    provides = "gpus.nvidia"

    def __init__(self) -> None:
        # Called `client` on purpose: the collector closes by that name.
        self.client = nvml.Nvml()
        # The cards seen suspended since NVML last read them: the first
        # reading after waking can be impossible (docs/nvml.md).
        self._slept: set[str] = set()
        # Each NVIDIA's runtime PM state at this sample, by slot.
        self._states: dict[str, Optional[str]] = {}
        # Whether the driver switches each card off when idle, once known.
        self._can_sleep: dict[str, bool] = {}
        # When NVML was closed so a card could fall asleep.
        self._let_go_at: Optional[float] = None
        self._clock = time.monotonic

    def available(self) -> bool:
        # With a dump, what was recorded answers: open or not, and which cards
        # it gave (`sysroot.recorded`). Never this machine's NVML.
        if sysroot.active():
            return bool(sysroot.recorded("nvml", "abierta", self.client.open))
        self._states = runtime_states()
        for slot, state in self._states.items():
            if state in SUSPENDED:
                self._slept.add(slot)
                self._can_sleep[slot] = True
            elif slot not in self._can_sleep:
                known = driver_lets_it_sleep(slot)
                if known is not None:
                    self._can_sleep[slot] = known
        if self._leaving_them_alone():
            # NVML talks to every card at once: opening it, or asking with it
            # open, wakes the one that sleeps and keeps it awake. Closed, the
            # cards are still said to rest (`_how_they_rest`).
            self.client.close()
            return bool(self._states)
        return bool(sysroot.recorded("nvml", "abierta", self.client.open))

    def _leaving_them_alone(self) -> bool:
        """Whether NVML stays closed this sample: a card sleeps, or one that
        can was let go of moments ago and has time to fall asleep."""
        if any(state in SUSPENDED for state in self._states.values()):
            return True
        return (self._let_go_at is not None
                and self._clock() - self._let_go_at < LET_IT_SLEEP_S)

    def _how_they_rest(self, draft: Draft) -> None:
        """Asleep or left alone, what each card is, without asking it."""
        leaving = self._leaving_them_alone()
        for index, gpu in enumerate(draft.gpus):
            slot = gpu.get("pci_slot")
            if slot not in self._states:
                continue
            state = self._states[slot]
            gpu["runtime_status"] = state
            if state in SUSPENDED:
                # Without a DRM node no other provider says it sleeps.
                if not gpu.get("suspended"):
                    gpu["suspended"] = True
                    say_asleep(draft, index)
            elif gpu.get("suspended") and not gpu.get("drm_node"):
                # Read asleep at the static pass and awake now: `GpuState`
                # does this for the cards with a DRM node.
                gpu["suspended"] = False
                draft.static_stale = True
            elif leaving and self._can_sleep.get(slot):
                gpu["left_to_sleep"] = True
                _say_left_to_sleep(draft, index)

    def _let_go_if_unused(self, cards: list[nvml.NvidiaGpu]) -> None:
        """Close NVML when a card that can sleep is not working."""
        if any(self._can_sleep.get(card.pci_slot) and not _working(card) for card in cards):
            self.client.close()
            self._let_go_at = self._clock()

    def _cards(self) -> list[nvml.NvidiaGpu]:
        """What NVML answers, recorded for the dumps: as dictionaries and
        without the serial number, which nothing uses."""
        def ask():
            return [dict(dataclasses.asdict(t), serial=None) for t in self.client.devices()]
        raw_cards = sysroot.recorded("nvml", "tarjetas", ask) or ()
        return [nvml.NvidiaGpu(**dict(
                    c, throttle_reasons=tuple(c.get("throttle_reasons") or ()),
                    power_answers=tuple(tuple(a) for a in c.get("power_answers") or ())))
                for c in raw_cards]

    def unavailable_reason(self):
        return None       # without an NVIDIA nothing is missing

    def collect(self, draft: Draft) -> None:
        live = not sysroot.active()
        if live:
            self._how_they_rest(draft)
        cards = self._cards()
        if not cards:
            return
        draft.capabilities.add("nvml")

        by_slot = {gpu.get("pci_slot"): gpu for gpu in draft.gpus if gpu.get("pci_slot")}
        for card in cards:
            target = by_slot.get(card.pci_slot)
            if target is None:
                # NVML sees a card DRM did not list: compute-only Teslas
                # register no graphics node.
                target = draft.gpu(len(draft.gpus))
                target["pci_slot"] = card.pci_slot
                target["vendor"] = "NVIDIA"
            # NVML answers only through NVIDIA's driver.
            target["driver"] = target.get("driver") or "nvidia"
            _fill(target, card)
            if card.fan_percent is None and draft.board.chassis in PORTABLE_CHASSIS:
                target["fan_of_the_machine"] = True

        # The notice that an NVIDIA comes empty is not needed: it does not.
        # Nor that its driver publishes no DRM node: NVML answered for it.
        answered = {f"gpus.{i}" for i, gpu in enumerate(draft.gpus)
                    if gpu.get("pci_slot") in {c.pci_slot for c in cards}}
        draft.notes = [n for n in draft.notes
                       if not (n.need is Need.DRIVER and n.path.startswith("gpus.")
                               and ("NVIDIA" in n.message
                                    or (n.path in answered and n.key == "prov.drm.nodrm")))]

        for card in cards:
            for index, gpu in enumerate(draft.gpus):
                if gpu.get("pci_slot") != card.pci_slot:
                    continue
                gpu["runtime_status"] = read_text(f"{PCI}/{card.pci_slot}/power/runtime_status")
                if gpu.get("power_w") is None:
                    _say_why_no_power(draft, index, card, woke=card.pci_slot in self._slept)
        self._slept -= {card.pci_slot for card in cards}
        if live:
            self._let_go_if_unused(cards)


def _working(card: nvml.NvidiaGpu) -> bool:
    """Whether the card does work that reading it does not stop it sleeping:
    a compute process (the driver keeps the card on while one runs), or an
    engine busy over the last reading. That is what the driver itself
    checks before switching a card off: whether its engines are idle.

    Not the graphics processes: on a hybrid laptop the display server is
    one, with a few MiB, on a card the driver switches off all the same.
    Nor its memory: what counts as used at idle changes with the driver.
    """
    return bool(card.compute_processes) or any(
        (card.busy_percent, card.memory_busy_percent,
         card.encode_busy_percent, card.decode_busy_percent))


def _say_left_to_sleep(draft: Draft, index: int) -> None:
    """Card N is awake and left alone, said instead of a missing driver."""
    path = f"gpus.{index}"
    draft.notes = [n for n in draft.notes
                   if not (n.path == path and n.need is Need.DRIVER)]
    draft.note(path, Need.HARDWARE, _("prov.nvml.lefttosleep"),
               _("prov.nvml.lefttosleep.hint"), key="nvml.lefttosleep",
               title=_("prov.nvml.lefttosleep.title"))


def _say_why_no_power(draft: Draft, index: int, card: nvml.NvidiaGpu, woke: bool) -> None:
    """A dash with no reason breaks rule 5: say the driver did not give it,
    that what it gave was impossible, or that what it gives is its own
    estimate. What NVML answered to each way goes in the report.

    `woke`: the card was seen suspended since it was last read, the probable
    cause of an impossible reading."""
    path = f"gpus.{index}.power_w"
    if card.power_discarded_w is not None:
        ceiling = dict(card.power_answers).get("ceiling", "")
        draft.note(path, Need.HARDWARE, _("prov.nvml.discarded"),
                   _("prov.nvml.discarded.woke") if woke else "",
                   detail=f"{card.power_discarded_w} W from {card.power_discarded_source}, "
                          f"over the ceiling of {ceiling}"
                          + ("; suspended before this reading" if woke else ""),
                   key="nvml.discarded")
    elif card.power_estimate_w is not None:
        draft.note(path, Need.HARDWARE, _("prov.nvml.estimate"),
                   detail=card.power_error or "", key="nvml.estimate")
    elif card.power_sensor is False:
        # «Sin sensor» on the power tile says it; what each way answered goes
        # to the report with the card.
        return
    else:
        draft.note(path, Need.HARDWARE, _("prov.nvml.nopower"), what=_("what.gpu.power"),
                   detail=card.power_error or "", key="nvml.nopower")


PCI = "/sys/bus/pci/devices"
PROC_NVIDIA = "/proc/driver/nvidia/gpus"


def runtime_states() -> dict[str, Optional[str]]:
    """Each NVIDIA graphics card on the bus, by slot, and its runtime PM state.

    Read from the bus, not from what DRM listed: with the proprietary driver
    and no `nvidia-drm.modeset` there is no DRM node, and the card sleeps all
    the same. `power/runtime_status` is the PM core's and wakes nothing.
    """
    states = {}
    for path in sorted(glob.glob(os.path.join(sysroot.path(PCI), "*"))):
        if (read_text(f"{path}/vendor") or "").lower() != "0x10de":
            continue
        if not (read_text(f"{path}/class") or "").startswith("0x03"):
            continue
        states[os.path.basename(path)] = read_text(f"{path}/power/runtime_status")
    return states


def driver_lets_it_sleep(slot: str) -> Optional[bool]:
    """Whether NVIDIA's driver switches this card off when idle (runtime D3).

    Its procfs `power` file says so without a power reference
    (`nv_procfs_read_power`), so reading it wakes nothing; `information`,
    beside it, takes one and wakes the card. None while the driver has not
    set the card up («?»), or without the file.
    """
    for line in (read_text(f"{PROC_NVIDIA}/{slot}/power") or "").splitlines():
        name, _sep, value = line.partition(":")
        if name.strip() == "Runtime D3 status":
            value = value.strip()
            return None if value == "?" else value.startswith("Enabled")
    return None


# CUDA cores per multiprocessor, by generation. The codename's first two
# letters say which (AD107 is Ada, TU116 Turing): an architecture fact, the
# same for the whole family.
CORES_PER_SM = {
    "GP": 128,   # Pascal
    "GV": 64,    # Volta
    "TU": 64,    # Turing
    "GA": 128,   # Ampere
    "AD": 128,   # Ada Lovelace
    "GB": 128,   # Blackwell
}

# Below this they are not cores. The smallest card NVML talks to has about
# 256, and no GPU has more than 200 multiprocessors: the gap leaves no doubt.
MIN_CORES = 200


def _cuda_cores(gpu: dict, raw: Optional[int]) -> Optional[int]:
    """The real CUDA core count, which is not always what NVML answers.

    `nvmlDeviceGetNumGpuCores` returns cores on some cards and
    multiprocessors on others (24 on an RTX 4060, which has 3072 cores). A
    number too low to be cores is multiplied by the cores per multiprocessor
    of its architecture; an unknown architecture gives nothing rather than a
    believable, false figure.
    """
    if raw is None or raw >= MIN_CORES:
        return raw
    key = (gpu.get("codename") or "")[:2].upper()
    factor = CORES_PER_SM.get(key)
    return raw * factor if factor else None


def _fill(gpu: dict, card: nvml.NvidiaGpu) -> None:
    direct = {
        "name": card.name,
        "vbios": card.vbios,
        "driver_version": card.driver_version,
        "unique_id": card.uuid,
        "compute_units": _cuda_cores(gpu, card.cuda_cores),
        "busy_percent": card.busy_percent,
        "memory_busy_percent": card.memory_busy_percent,
        "encode_busy_percent": card.encode_busy_percent,
        "decode_busy_percent": card.decode_busy_percent,
        "temp_c": card.temp_c,
        "power_w": card.power_w,
        "power_source": card.power_source,
        "power_sensor": card.power_sensor,
        "power_estimate_w": card.power_estimate_w,
        "power_estimate_window_s": card.power_estimate_window_s,
        "power_estimate_samples": card.power_estimate_samples,
        "power_cap_w": card.power_cap_w,
        "power_cap_default_w": card.power_cap_default_w,
        "power_cap_min_w": card.power_cap_min_w,
        "power_cap_max_w": card.power_cap_max_w,
        "fan_percent": card.fan_percent,
        "throttled": card.throttled,
    }
    for field, value in direct.items():
        if value is not None and gpu.get(field) is None:
            gpu[field] = value
    if card.throttle_reasons and not gpu.get("throttle_reasons"):
        gpu["throttle_reasons"] = card.throttle_reasons
    if card.power_answers:
        gpu["power_answers"] = card.power_answers

    memory: GpuMemory = gpu.get("memory") or GpuMemory()
    gpu["memory"] = dataclasses.replace(
        memory,
        # NVML's, when it answers: Vulkan, asked earlier, adds NVIDIA's BAR
        # window to the total and an RTX 4060 of 8 GB read «8.2 GB».
        total_bytes=card.memory_total_bytes or memory.total_bytes,
        used_bytes=memory.used_bytes if memory.used_bytes is not None
        else card.memory_used_bytes,
        bus_bits=memory.bus_bits or card.memory_bus_bits,
    )
    # GeForce and Quadro are separate cards. What NVIDIA builds into the
    # processor is Tegra, which does not talk NVML on a PC.
    gpu["integrated"] = False

    clocks: GpuClocks = gpu.get("clocks") or GpuClocks()
    gpu["clocks"] = dataclasses.replace(
        clocks,
        core_hz=clocks.core_hz if clocks.core_hz is not None else card.core_hz,
        core_max_hz=clocks.core_max_hz or card.core_max_hz,
        memory_hz=clocks.memory_hz if clocks.memory_hz is not None else card.memory_hz,
        memory_max_hz=clocks.memory_max_hz or card.memory_max_hz,
    )

    # NVML gives the PCIe generation; the model keeps gigatransfers, which is
    # what sysfs publishes for every other card.
    link: PcieLink = gpu.get("link") or PcieLink()
    gpu["link"] = dataclasses.replace(
        link,
        current_speed_gts=(link.current_speed_gts
                           or SPEEDS_GTS.get(card.link_generation or 0)),
        current_width=link.current_width or card.link_width,
        max_speed_gts=(link.max_speed_gts
                       or SPEEDS_GTS.get(card.max_link_generation or 0)),
        max_width=link.max_width or card.max_link_width,
    )
