"""What every provider shares.

A provider reads one source (CPUID, sysfs, hwmon…) and writes into a
`Draft`. The draft is mutable because collecting is; at the end it freezes
into an immutable `Snapshot`, the only thing that leaves the data layer.

Each provider says what it needs to work. When it cannot, it does not vanish
in silence: it leaves a `Note` saying why, and the interface shows it
instead of an unexplained gap.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .. import sysroot
from ..model import (
    Board,
    Clocks,
    CpuInfo,
    CpuType,
    DriverHint,
    Gpu,
    LogicalCpu,
    MemoryArray,
    MemoryModule,
    MemoryTraffic,
    Need,
    Note,
    Platform,
    Power,
    PrivilegedState,
    Sensor,
    Snapshot,
    System,
)


@dataclass
class Draft:
    """Mutable state during a collection. It never leaves the collector."""

    monotonic_ns: int = field(default_factory=time.monotonic_ns)
    # The sampling interval: a rate from a window shorter than half of it is
    # no rate (`counters.window_s`).
    interval_s: float = 1.0
    sockets: int = 1
    hybrid: bool = False
    types: dict[str, dict[str, Any]] = field(default_factory=dict)
    logical: dict[int, dict[str, Any]] = field(default_factory=dict)
    cpu_extra: dict[str, Any] = field(default_factory=dict)
    board: Board = field(default_factory=Board)
    system: System = field(default_factory=System)
    modules: list[MemoryModule] = field(default_factory=list)
    spd: list = field(default_factory=list)
    memory_array: Optional[MemoryArray] = None
    memory_traffic: Optional[MemoryTraffic] = None
    gpus: list[dict[str, Any]] = field(default_factory=list)
    network: list = field(default_factory=list)
    disks: list = field(default_factory=list)
    batteries: list = field(default_factory=list)
    pci_devices: list = field(default_factory=list)
    platform: Platform = field(default_factory=Platform)
    usb_devices: list = field(default_factory=list)
    sound_cards: list = field(default_factory=list)
    cameras: list = field(default_factory=list)
    bluetooth: list = field(default_factory=list)
    # PCI address → slot name, from the firmware's table (permissions).
    pci_slot_names: dict = field(default_factory=dict)
    privileged: PrivilegedState = field(default_factory=PrivilegedState)
    sensors: list[Sensor] = field(default_factory=list)
    driver_hints: list[DriverHint] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    notes: list[Note] = field(default_factory=list)
    # The static data was read with something asleep that is not any more: a
    # suspended card is not read whole so as not to wake it, and when it
    # wakes the rest is fetched. The collector looks at this after the pass.
    static_stale: bool = False

    # -- writing helpers ----------------------------------------------------

    def type_for(self, key: str) -> dict[str, Any]:
        return self.types.setdefault(key, {"key": key, "label": key, "cpus": []})

    def cpu(self, index: int) -> dict[str, Any]:
        return self.logical.setdefault(index, {"index": index, "core_id": -1, "package_id": 0})

    def gpu(self, index: int) -> dict[str, Any]:
        """Card number N, created the first time it is named.

        Dictionaries and not `Gpu`: several providers fill them in turn (the
        kernel first, the graphics APIs after), and rebuilding a frozen
        dataclass at each step loses fields another one just set.
        """
        while len(self.gpus) <= index:
            self.gpus.append({"index": len(self.gpus)})
        return self.gpus[index]

    def note(self, path: str, need: Need, message: str, hint: str = "",
             what: str = "", detail: str = "", key: str = "") -> None:
        self.notes.append(Note(path=path, need=need, message=message, hint=hint,
                               what=what, detail=detail, key=key))

    def resolve(self, path: str) -> None:
        """Drop the notes on a value another provider did get.

        Providers do not know each other, but several can reach the same value
        by different paths, and the first one says it could not: on ARM the
        processor's identity showed as missing («CPUID is an x86
        instruction») with the core's name written right above.
        """
        self.notes = [n for n in self.notes if n.path != path]

    # -- freezing -----------------------------------------------------------

    def freeze(self) -> Snapshot:
        types: list[CpuType] = []
        for raw in self.types.values():
            data = dict(raw)
            data["cpus"] = tuple(sorted(data.get("cpus", ())))
            data["caches"] = tuple(data.get("caches", ()))
            data["features"] = tuple(data.get("features", ()))
            data.setdefault("clocks", Clocks())
            # Drop any key that is not a model field: a provider writing too
            # much must not break the freeze.
            valid = {f for f in CpuType.__dataclass_fields__}
            types.append(CpuType(**{k: v for k, v in data.items() if k in valid}))

        logical = tuple(
            LogicalCpu(**{k: v for k, v in raw.items() if k in LogicalCpu.__dataclass_fields__})
            for _index, raw in sorted(self.logical.items())
        )

        cpu = CpuInfo(
            sockets=self.sockets,
            hybrid=self.hybrid,
            types=tuple(types),
            logical=logical,
            usage_percent=self.cpu_extra.get("usage_percent"),
            package_temp_c=self.cpu_extra.get("package_temp_c"),
            power=self.cpu_extra.get("power") or Power(),
            load_average=tuple(self.cpu_extra.get("load_average") or ()),
            idle_states=tuple(self.cpu_extra.get("idle_states") or ()),
            thermal_throttle=self.cpu_extra.get("thermal_throttle"),
        )

        return Snapshot(
            monotonic_ns=self.monotonic_ns,
            cpu=cpu,
            board=self.board,
            system=self.system,
            modules=tuple(self.modules),
            spd=tuple(self.spd),
            memory_array=self.memory_array,
            memory_traffic=self.memory_traffic,
            network=tuple(self.network),
            disks=tuple(self.disks),
            batteries=tuple(self.batteries),
            pci_devices=tuple(self.pci_devices),
            platform=self.platform,
            usb_devices=tuple(self.usb_devices),
            sound_cards=tuple(self.sound_cards),
            cameras=tuple(self.cameras),
            bluetooth=tuple(self.bluetooth),
            gpus=tuple(
                Gpu(**{k: v for k, v in raw.items() if k in Gpu.__dataclass_fields__})
                for raw in self.gpus
            ),
            privileged=self.privileged,
            sensors=tuple(self.sensors),
            driver_hints=tuple(self.driver_hints),
            capabilities=frozenset(self.capabilities),
            notes=tuple(self.notes),
        )


class Provider:
    """The base of every provider.

    `static` tells what is read once (identity, topology, caches) from what
    is refreshed on every sample (clocks, temperatures, usage).
    """

    name: str = "unnamed"
    provides: str = ""
    static: bool = False

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> Optional[tuple]:
        """(path, need, message, hint) if it cannot be used; None if it can.

        With a fifth item, what is missing in a few words, when it is about
        permissions and the helper can read it (`Note.what`).
        """
        return None

    def collect(self, draft: Draft) -> None:
        raise NotImplementedError

    def wants_between_samples(self) -> bool:
        """Whether it reads something between one sample and the next
        (`between_samples`). Almost none: each reading wakes the thread."""
        return False

    def between_samples(self) -> None:
        """A reading between samples, for what the hardware gives as an
        instant and is shown as the interval's mean."""


# --------------------------------------------------------------------------
# reading sysfs and procfs, tolerating files that do not exist
# --------------------------------------------------------------------------


def read_text(path: str) -> Optional[str]:
    try:
        with open(sysroot.ruta(path), encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except (OSError, ValueError):
        return None


def is_suspended(device) -> bool:
    """Whether the kernel has the device suspended by runtime PM (D3).

    The power management core publishes `power/runtime_status`, not the
    driver: `runtime_status_show` (drivers/base/power/sysfs.c) returns the
    stored state without waking the device. Almost everything else wakes it:
    the PCIe link since Linux 6.18, hwmon and amdgpu's ioctls, opening the
    render node, NVML. Whoever asks wakes the card and then measures it awake,
    which is not how it was.
    """
    return read_text(f"{device}/power/runtime_status") in ("suspended", "suspending")


def on_its_own(draft: "Draft", path: str, function, *args):
    """One value read on its own: if it fails, it is that value's notice and
    not the provider's, which would lose everything else it reads."""
    try:
        return function(*args)
    except Exception as exc:                                  # noqa: BLE001
        from ..i18n import _
        draft.note(path, Need.ERROR, _("prov.crashed").format(nombre=path, error=exc),
                   _("prov.crashed.hint"))
        return None


def is_virtual_machine(draft: "Draft") -> bool:
    """Whether CPUID, read earlier in the sample, says this is a guest."""
    return any(t.get("in_virtual_machine") for t in draft.types.values())


def read_int(path: str) -> Optional[int]:
    raw = read_text(path)
    if raw is None:
        return None
    try:
        return int(raw, 0)
    except ValueError:
        return None


def parse_cpu_list(raw: Optional[str]) -> tuple[int, ...]:
    """Turns "0-3,8,10-11" into (0, 1, 2, 3, 8, 10, 11)."""
    if not raw:
        return ()
    out: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, _sep, end = chunk.partition("-")
            try:
                out.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                out.append(int(chunk))
            except ValueError:
                continue
    return tuple(out)


def parse_size(raw: Optional[str]) -> Optional[int]:
    """Turns "32K" / "12288K" / "8M" into bytes."""
    if not raw:
        return None
    raw = raw.strip()
    multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3}
    if raw[-1].upper() in multipliers:
        try:
            return int(raw[:-1]) * multipliers[raw[-1].upper()]
        except ValueError:
            return None
    try:
        return int(raw)
    except ValueError:
        return None


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    real = [v for v in values if v is not None]
    return sum(real) / len(real) if real else None
