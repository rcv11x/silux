"""Runs the providers and produces snapshots.

Splitting static from dynamic is what makes refreshing cheap: the
processor's identity, topology and caches are read once; frequencies,
temperatures, usage and watts, every sample.

A provider that crashes doesn't take the collection down with it: it is
noted and the rest go on. An odd sensor on an odd board must not leave the
application blank.
"""

from __future__ import annotations

import dataclasses
import inspect
import time
from typing import Iterable, Optional, Sequence

from . import sysroot
from .failures import Failures
from .i18n import _
from .model import Need, Snapshot
from .privileged.client import PrivilegedClient
from .providers import (
    AmdPstateClocks,
    ArmIdentity,
    Batteries,
    ConnectedDevices,
    CppcClocks,
    CpuidIdentity,
    CpuIdle,
    CpuUsage,
    DerivedSensors,
    Disks,
    DmiBoard,
    Draft,
    DrmGpus,
    GpuApis,
    GpuState,
    HwmonSensors,
    ImcTraffic,
    MsrVoltage,
    NetworkInterfaces,
    NvidiaGpus,
    PciDevices,
    PlatformInfo,
    PowerLimits,
    PrivilegedMemory,
    Provider,
    RaplPower,
    SpdModules,
    SysfsClocks,
    SysfsTopology,
    SystemDependencies,
    SystemIdentity,
    SystemSecurity,
    SystemState,
    ThermalThrottleCounts,
    TurboState,
)
from .providers.base import is_virtual_machine


def _instantiate(cls: type[Provider], client: PrivilegedClient) -> Provider:
    """Build a provider, handing it the helper if it knows how to use it."""
    if "client" in inspect.signature(cls).parameters:
        return cls(client=client)                     # type: ignore[call-arg]
    return cls()

# The order matters: the topology says which core types there are, and
# CPUID needs that to ask once per type.
DEFAULT_PROVIDERS: tuple[type[Provider], ...] = (
    SysfsTopology,
    CpuidIdentity,
    ArmIdentity,
    CppcClocks,         # fills in the clocks CPUID 0x16 couldn't give
    DmiBoard,           # the board's name, which the sensor tree uses
    DrmGpus,            # lists the cards before anything asks them
    GpuApis,            # then asks OpenGL, Vulkan and OpenCL about them
    SystemDependencies,  # what the system lacks, saying it for the two above
    SystemIdentity,
    SystemSecurity,
    PlatformInfo,
    PrivilegedMemory,
    SpdModules,         # after it, to match up with what it read
    SysfsClocks,
    TurboState,
    AmdPstateClocks,
    CpuUsage,
    CpuIdle,            # how long each thread rests, also taken from usage
    ThermalThrottleCounts,
    GpuState,
    NetworkInterfaces,
    Disks,
    Batteries,
    PciDevices,         # after the cards, disks and network: it uses their names
    ConnectedDevices,
    NvidiaGpus,
    SystemState,
    PowerLimits,        # before RaplPower, which adds its watts to this card
    RaplPower,
    ImcTraffic,
    HwmonSensors,       # names the devices with what is already known
    MsrVoltage,         # after it: the voltage no sensor labelled
    DerivedSensors,     # last: it only transforms what was collected
)


# What a virtual machine does not have, whatever the notice that would ask
# for it says: a voltage (KVM answers that register with a constant), memory
# modules (QEMU's SMBIOS makes one up), SPD chips and a memory controller to
# count. Those notices are decided before the sample says it is a guest.
NOT_IN_A_VM = frozenset(("cpu.voltage_v", "modules", "spd", "memory.traffic"))


def _without_what_a_vm_lacks(draft: Draft) -> None:
    if is_virtual_machine(draft):
        draft.notes = [n for n in draft.notes if n.path not in NOT_IN_A_VM]


def _path_of(exc: OSError) -> str:
    """The file that caused the error, or a description if it doesn't say."""
    return str(exc.filename) if exc.filename else str(exc)


# What the system publishes about its hardware. A file missing there is
# something this machine does not have; missing anywhere else (our database,
# a temporary file, a program we launch) it is our failure.
SYSTEM_TREES = ("/sys/", "/proc/", "/dev/", "/etc/", "/run/")


def is_the_systems(exc: OSError) -> bool:
    path = str(exc.filename) if exc.filename else ""
    root = sysroot.root()
    if root is not None and path.startswith(str(root)):
        path = path[len(str(root)):]
    return path.startswith(SYSTEM_TREES)


def _with_the_helper_outdated(snapshot: Snapshot) -> Snapshot:
    """What permissions would read, said as what fixes it: the installed
    helper is from another version, so it is not giving permissions but
    updating the helper. Every notice, padlock and the report say it alike."""
    missing = set(snapshot.permission_notes)
    notes = tuple(dataclasses.replace(n, message=_("perm.outdated.body"), hint="",
                                      helper_outdated=True) if n in missing else n
                  for n in snapshot.notes)
    return dataclasses.replace(snapshot, notes=notes)


class Collector:
    """The data layer's entry point. Reusable, with its own state."""

    def __init__(self, providers: Optional[Sequence[Provider]] = None) -> None:
        # How far apart snapshots are meant to be. Whoever takes them says so
        # (the sampler, `sample`, the CLI's --watch): the rates check their
        # window against it.
        self.interval_s = 1.0
        if providers is not None:
            self.providers: list[Provider] = list(providers)
        else:
            # One helper for every provider that needs it. Each client starts
            # its own process and opens its own polkit dialog, so two clients
            # would be the password twice for the same thing.
            shared = PrivilegedClient()
            self.providers = [_instantiate(cls, shared) for cls in DEFAULT_PROVIDERS]
        self._static: Optional[Draft] = None
        self.failures = Failures()

    # -- API ----------------------------------------------------------------

    def snapshot(self) -> Snapshot:
        if self._static is None:
            self._static = self._collect(p for p in self.providers if p.static)

        draft = self._clone(self._static)
        draft.interval_s = self.interval_s
        self._collect((p for p in self.providers if not p.static), into=draft)
        _without_what_a_vm_lacks(draft)
        if draft.static_stale:
            # Something asleep when the static data was read has woken up:
            # the next pass reads it all.
            self.invalidate()
        snapshot = dataclasses.replace(draft.freeze(), failures=self.failures.recent())
        if snapshot.privileged.outdated:
            snapshot = _with_the_helper_outdated(snapshot)
        return snapshot

    def sample(self, settle: float = 0.25) -> Snapshot:
        """One snapshot ready to show.

        CPU usage and watts are rates: the first reading only sets the
        baseline. So it samples twice with a short pause between.
        """
        self.interval_s = settle
        self.snapshot()
        time.sleep(settle)
        return self.snapshot()

    def wants_between_samples(self) -> bool:
        """Whether any provider wants to read between samples; if not, the
        sampling thread sleeps the whole interval at once."""
        return any(p.wants_between_samples() for p in self.providers if not p.static)

    def between_samples(self) -> None:
        """The readings between samples. A failure here takes nothing off the
        page: the next sample reads anyway and, without them, keeps its own
        instant. It goes to the report with its traceback."""
        for provider in self.providers:
            if provider.static or not provider.wants_between_samples():
                continue
            try:
                provider.between_samples()
            except Exception as exc:                      # noqa: BLE001
                # The next sample reads anyway; the report says it failed.
                self.failures.record(f"{provider.name}.between_samples", exc)

    def request_elevation(self) -> None:
        """Mark that the user wants the data that needs privileges.

        Nothing is elevated here: it is only noted, and the static data
        invalidated. The provider opens the authentication dialog on the
        sampling thread, where it can block without freezing the window.
        """
        # Everyone who can wait for the signal, not only memory: the disks
        # ask for permissions too and share the same helper, so one
        # authorization serves both.
        for provider in self.providers:
            if hasattr(provider, "requested"):
                provider.requested = True
                provider.client.allow_asking()
        self.invalidate()

    def close(self) -> None:
        # Providers share a client, so each is closed once even when several
        # hold it.
        closed: set[int] = set()
        for provider in self.providers:
            client = getattr(provider, "client", None)
            if client is not None and id(client) not in closed:
                closed.add(id(client))
                client.close()

    def invalidate(self) -> None:
        """Force the static data to be read again (after loading a module, say)."""
        self._static = None

    # -- internals ----------------------------------------------------------

    def _collect(self, providers: Iterable[Provider], into: Optional[Draft] = None) -> Draft:
        draft = into if into is not None else Draft()
        for provider in providers:
            try:
                if not provider.available():
                    if reason := provider.unavailable_reason():
                        draft.note(*reason)
                    continue
                provider.collect(draft)
            except PermissionError as exc:
                # Not that the data doesn't exist: it can't be read. It used
                # to say «doesn't apply to this platform», the opposite of
                # what happens, and in a sandbox even the network said so.
                draft.note(
                    provider.provides or provider.name,
                    Need.ROOT,
                    _("prov.denied"),
                    detail=_("prov.denied.detail").format(ruta=_path_of(exc)),
                )
            except (FileNotFoundError, NotADirectoryError) as exc:
                if is_the_systems(exc):
                    draft.note(
                        provider.provides or provider.name,
                        Need.HARDWARE,
                        _("prov.missing"),
                        detail=_("prov.missing.detail").format(ruta=_path_of(exc)),
                    )
                else:
                    self._our_failure(draft, provider, exc)
            except Exception as exc:                      # noqa: BLE001
                self._our_failure(draft, provider, exc)
        return draft

    def _our_failure(self, draft: Draft, provider: Provider, exc: Exception) -> None:
        """Silux's own failure: an error on its page, and in the report with
        its traceback. Never «this machine does not have it» (rule 5). It
        replaces what another provider said of the same datum: a padlock
        would promise what permissions may not give."""
        self.failures.record(provider.name, exc)
        draft.resolve(provider.provides or provider.name)
        draft.note(
            provider.provides or provider.name,
            Need.ERROR,
            _("prov.crashed").format(nombre=provider.name, error=exc),
            _("prov.crashed.hint"),
            key="prov.crashed",
        )

    @staticmethod
    def _clone(static: Draft) -> Draft:
        """Copy the static state so each sample starts from it untouched.

        The model's values are immutable, so duplicating the dictionaries is
        enough; no real deep copy is needed.
        """
        draft = Draft()
        draft.sockets = static.sockets
        draft.hybrid = static.hybrid
        draft.types = {k: dict(v) for k, v in static.types.items()}
        for entry in draft.types.values():
            entry["cpus"] = list(entry.get("cpus", ()))
        draft.logical = {k: dict(v) for k, v in static.logical.items()}
        draft.board = static.board
        draft.system = static.system
        draft.modules = list(static.modules)
        draft.spd = list(static.spd)
        draft.memory_array = static.memory_array
        draft.gpus = [dict(g) for g in static.gpus]
        draft.network = list(static.network)
        draft.disks = list(static.disks)
        draft.platform = static.platform
        draft.pci_slot_names = dict(static.pci_slot_names)
        draft.privileged = static.privileged
        draft.sensors = list(static.sensors)
        draft.driver_hints = list(static.driver_hints)
        draft.capabilities = set(static.capabilities)
        draft.notes = list(static.notes)
        return draft
