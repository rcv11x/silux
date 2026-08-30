"""Orquesta a los proveedores y produce snapshots.

La separación entre estático y dinámico es lo que hace que refrescar sea
barato: la identidad del procesador, la topología y las cachés se leen una
vez; las frecuencias, temperaturas, uso y vatios, en cada muestreo.

Si un proveedor revienta, no se lleva por delante la recolección: se anota
como una nota más y el resto sigue. Un sensor raro en una placa rara no debe
dejar la aplicación en blanco.
"""

from __future__ import annotations

import copy
import inspect
import time
from typing import Iterable, Optional, Sequence

from .model import Need, Snapshot
from .privileged.client import PrivilegedClient
from .i18n import _
from .providers import (
    Batteries,
    ArmIdentity,
    CppcClocks,
    CpuidIdentity,
    CpuUsage,
    DerivedSensors,
    Disks,
    DmiBoard,
    Draft,
    DrmGpus,
    GpuApis,
    GpuState,
    NetworkInterfaces,
    NvidiaGpus,
    HwmonSensors,
    PrivilegedMemory,
    Provider,
    SpdModules,
    RaplPower,
    SysfsClocks,
    SysfsTopology,
    SystemIdentity,
    SystemState,
    TurboState,
)

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
    SystemIdentity,
    PrivilegedMemory,   # espera a que el usuario lo pida
    SpdModules,         # después, para pegarse a lo que aquél haya leído
    SysfsClocks,
    TurboState,
    CpuUsage,
    GpuState,
    NetworkInterfaces,  # las interfaces y su ritmo, que se mide entre muestreos
    Disks,              # y los discos, con el suyo
    Batteries,          # la batería, que en un portátil se degrada sola
    NvidiaGpus,
    SystemState,
    RaplPower,
    HwmonSensors,       # nombra los aparatos con lo que ya se sabe
    DerivedSensors,     # el último: solo transforma lo recogido
)


def _ruta_de(exc: OSError) -> str:
    """El fichero que provocó el error, o una descripción si no lo dice."""
    return str(exc.filename) if exc.filename else str(exc)


class Collector:
    """Punto de entrada de la capa de datos. Reutilizable y con estado propio."""

    def __init__(self, providers: Optional[Sequence[Provider]] = None) -> None:
        if providers is not None:
            self.providers: list[Provider] = list(providers)
        else:
            # Un solo ayudante para todos los que lo necesiten. Cada cliente
            # lanza su propio proceso y abre su propio diálogo de polkit, así
            # que dos clientes serían dos veces la contraseña para lo mismo.
            compartido = PrivilegedClient()
            self.providers = [_instanciar(cls, compartido) for cls in DEFAULT_PROVIDERS]
        self._static: Optional[Draft] = None

    # -- API ----------------------------------------------------------------

    def snapshot(self) -> Snapshot:
        if self._static is None:
            self._static = self._collect(p for p in self.providers if p.static)

        draft = self._clone(self._static)
        self._collect((p for p in self.providers if not p.static), into=draft)
        return draft.freeze()

    def sample(self, settle: float = 0.25) -> Snapshot:
        """Una sola foto lista para enseñar.

        El uso de CPU y los vatios son derivadas: la primera lectura solo
        establece la referencia y aún no tiene valor. Por eso se muestrea dos
        veces con una pausa corta en medio.
        """
        self.snapshot()
        time.sleep(settle)
        return self.snapshot()

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
                    _("prov.denied").format(ruta=_ruta_de(exc)),
                    _("prov.denied.hint"),
                )
            except (FileNotFoundError, NotADirectoryError) as exc:
                draft.note(
                    provider.provides or provider.name,
                    Need.HARDWARE,
                    _("prov.missing").format(ruta=_ruta_de(exc)),
                )
            except Exception as exc:                      # noqa: BLE001
                draft.note(
                    provider.provides or provider.name,
                    Need.ERROR,
                    _("prov.crashed").format(nombre=provider.name, error=exc),
                    _("prov.crashed.hint"),
                )
        return draft

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
        draft.privileged = static.privileged
        draft.sensors = list(static.sensors)
        draft.driver_hints = list(static.driver_hints)
        draft.capabilities = set(static.capabilities)
        draft.notes = list(static.notes)
        return draft
