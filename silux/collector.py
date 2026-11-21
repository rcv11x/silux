"""Orquesta a los proveedores y produce snapshots.

La separación entre estático y dinámico es lo que hace que refrescar sea
barato: la identidad del procesador, la topología y las cachés se leen una
vez; las frecuencias, temperaturas, uso y vatios, en cada muestreo.

Si un proveedor revienta, no se lleva por delante la recolección: se anota
como una nota más y el resto sigue. Un sensor raro en una placa rara no debe
dejar la aplicación en blanco.
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


def _instanciar(cls: type[Provider], cliente: PrivilegedClient) -> Provider:
    """Crea un proveedor pasándole el ayudante si sabe usarlo."""
    if "client" in inspect.signature(cls).parameters:
        return cls(client=cliente)                     # type: ignore[call-arg]
    return cls()


# El orden importa: la topología define qué tipos de núcleo hay, y CPUID
# necesita saberlo para preguntar una vez por cada uno.
DEFAULT_PROVIDERS: tuple[type[Provider], ...] = (
    SysfsTopology,      # define qué tipos de núcleo hay
    CpuidIdentity,      # necesita saberlo para preguntar una vez por tipo
    ArmIdentity,        # y lo mismo donde no hay CPUID porque no es x86
    CppcClocks,         # rellena los relojes que CPUID 0x16 no supo dar
    DmiBoard,           # da el nombre de la placa, que usa el árbol de sensores
    DrmGpus,            # enumera las gráficas antes de que nadie las consulte
    GpuApis,            # y después les pregunta a OpenGL, Vulkan y OpenCL
    SystemDependencies,  # what the system lacks, saying it for the two above
    SystemIdentity,
    SystemSecurity,     # mitigaciones y arranque: una vez
    PlatformInfo,       # IOMMU, virtualización y los chips de la placa
    PrivilegedMemory,   # espera a que el usuario lo pida
    SpdModules,         # después, para pegarse a lo que aquél haya leído
    SysfsClocks,
    TurboState,
    AmdPstateClocks,    # con permisos, la base de un Zen y, sin cpufreq, su frecuencia
    CpuUsage,
    CpuIdle,            # y cuánto descansa cada hilo, que también se resta
    ThermalThrottleCounts,  # las veces que se frenó por temperatura (Intel)
    GpuState,
    NetworkInterfaces,  # las interfaces y su ritmo, que se mide entre muestreos
    Disks,              # y los discos, con el suyo
    Batteries,          # la batería, que en un portátil se degrada sola
    PciDevices,         # detrás de gráficas, discos y red: usa sus nombres
    ConnectedDevices,   # lo enchufado: USB, sonido, cámaras y Bluetooth
    NvidiaGpus,
    SystemState,
    PowerLimits,        # PL1 y PL2, que se leen sin permisos
    RaplPower,
    ImcTraffic,        # el tráfico de la memoria, que se mide entre muestreos
    HwmonSensors,       # nombra los aparatos con lo que ya se sabe
    MsrVoltage,         # y detrás: el voltaje que ningún sensor etiquetó
    DerivedSensors,     # el último: solo transforma lo recogido
)


# What a virtual machine does not have, whatever the notice that would ask
# for it says: a voltage (KVM answers that register with a constant), memory
# modules (QEMU's SMBIOS makes one up), SPD chips and a memory controller to
# count. Those notices are decided before the sample says it is a guest.
NOT_IN_A_VM = frozenset(("cpu.voltage_v", "modules", "spd", "memory.traffic"))


def _without_what_a_vm_lacks(draft: Draft) -> None:
    if is_virtual_machine(draft):
        draft.notes = [n for n in draft.notes if n.path not in NOT_IN_A_VM]


def _ruta_de(exc: OSError) -> str:
    """El fichero que provocó el error, o una descripción si no lo dice."""
    return str(exc.filename) if exc.filename else str(exc)


# What the system publishes about its hardware. A file missing there is
# something this machine does not have; missing anywhere else (our database,
# a temporary file, a program we launch) it is our failure.
SYSTEM_TREES = ("/sys/", "/proc/", "/dev/", "/etc/", "/run/")


def is_the_systems(exc: OSError) -> bool:
    ruta = str(exc.filename) if exc.filename else ""
    raiz = sysroot.raiz()
    if raiz is not None and ruta.startswith(str(raiz)):
        ruta = ruta[len(str(raiz)):]
    return ruta.startswith(SYSTEM_TREES)


def _with_the_helper_outdated(snapshot: Snapshot) -> Snapshot:
    """What permissions would read, said as what fixes it: the installed
    helper is from another version, so it is not giving permissions but
    updating the helper. Every notice, padlock and the report say it alike."""
    falta = set(snapshot.permission_notes)
    notes = tuple(dataclasses.replace(n, message=_("perm.outdated.body"), hint="",
                                      helper_outdated=True) if n in falta else n
                  for n in snapshot.notes)
    return dataclasses.replace(snapshot, notes=notes)


class Collector:
    """Punto de entrada de la capa de datos. Reutilizable y con estado propio."""

    def __init__(self, providers: Optional[Sequence[Provider]] = None) -> None:
        # How far apart snapshots are meant to be. Whoever takes them says so
        # (the sampler, `sample`, the CLI's --watch): the rates check their
        # window against it.
        self.interval_s = 1.0
        if providers is not None:
            self.providers: list[Provider] = list(providers)
        else:
            # Un solo ayudante para todos los que lo necesiten. Cada cliente
            # lanza su propio proceso y abre su propio diálogo de polkit, así
            # que dos clientes serían dos veces la contraseña para lo mismo.
            compartido = PrivilegedClient()
            self.providers = [_instanciar(cls, compartido) for cls in DEFAULT_PROVIDERS]
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
            # Algo que dormía al leer lo estático ha despertado: la próxima
            # vuelta lo lee entero.
            self.invalidate()
        snapshot = dataclasses.replace(draft.freeze(), failures=self.failures.recent())
        if snapshot.privileged.outdated:
            snapshot = _with_the_helper_outdated(snapshot)
        return snapshot

    def sample(self, settle: float = 0.25) -> Snapshot:
        """Una sola foto lista para enseñar.

        El uso de CPU y los vatios son derivadas: la primera lectura solo
        establece la referencia y aún no tiene valor. Por eso se muestrea dos
        veces con una pausa corta en medio.
        """
        self.interval_s = settle
        self.snapshot()
        time.sleep(settle)
        return self.snapshot()

    def wants_between_samples(self) -> bool:
        """Si algún proveedor quiere leer entre muestras: si no, el hilo de
        muestreo duerme el intervalo entero de una vez."""
        return any(p.wants_between_samples() for p in self.providers if not p.static)

    def between_samples(self) -> None:
        """Las lecturas entre muestras. Un fallo aquí no quita nada de la
        página: la muestra siguiente lee igual y, sin estas lecturas, se queda
        con su instante. Va al informe con su traza."""
        for provider in self.providers:
            if provider.static or not provider.wants_between_samples():
                continue
            try:
                provider.between_samples()
            except Exception as exc:                      # noqa: BLE001
                # The next sample reads anyway; the report says it failed.
                self.failures.record(f"{provider.name}.between_samples", exc)

    def request_elevation(self) -> None:
        """Marca que el usuario quiere los datos que exigen privilegios.

        No eleva nada aquí: se limita a apuntarlo e invalidar lo estático. El
        diálogo de autenticación lo abre el proveedor en el hilo de muestreo,
        que es donde puede bloquear sin congelar la ventana.
        """
        # A todo el que sepa esperar la señal, no solo al de memoria: los
        # discos también piden permisos y comparten el mismo ayudante, así que
        # una autorización sirve para los dos.
        for provider in self.providers:
            if hasattr(provider, "requested"):
                provider.requested = True
                provider.client.allow_asking()
        self.invalidate()

    def close(self) -> None:
        # Los proveedores comparten cliente, así que se cierra cada uno una
        # sola vez aunque lo tengan varios.
        cerrados: set[int] = set()
        for provider in self.providers:
            client = getattr(provider, "client", None)
            if client is not None and id(client) not in cerrados:
                cerrados.add(id(client))
                client.close()

    def invalidate(self) -> None:
        """Fuerza a releer también lo estático (p. ej. tras cargar un módulo)."""
        self._static = None

    # -- interno ------------------------------------------------------------

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
                # No es que el dato no exista: es que no se deja leer. Pasaba
                # con «no aplica a esta plataforma», que es lo contrario de lo
                # que ocurre, y en un entorno enjaulado salía así hasta la red.
                draft.note(
                    provider.provides or provider.name,
                    Need.ROOT,
                    _("prov.denied"),
                    detail=_("prov.denied.detail").format(ruta=_ruta_de(exc)),
                )
            except (FileNotFoundError, NotADirectoryError) as exc:
                if is_the_systems(exc):
                    draft.note(
                        provider.provides or provider.name,
                        Need.HARDWARE,
                        _("prov.missing"),
                        detail=_("prov.missing.detail").format(ruta=_ruta_de(exc)),
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
        """Copia el estado estático para que cada muestreo parta de él intacto.

        Los valores del modelo son inmutables, así que basta con duplicar los
        diccionarios; no hace falta una copia profunda de verdad.
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
