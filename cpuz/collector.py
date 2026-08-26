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
import time
from typing import Iterable, Optional, Sequence

from .model import Need, Snapshot
from .providers import (
    CpuidIdentity,
    CpuUsage,
    DerivedSensors,
    DmiBoard,
    Draft,
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

# El orden importa: la topología define qué tipos de núcleo hay, y CPUID
# necesita saberlo para preguntar una vez por cada uno.
DEFAULT_PROVIDERS: tuple[type[Provider], ...] = (
    SysfsTopology,      # define qué tipos de núcleo hay
    CpuidIdentity,      # necesita saberlo para preguntar una vez por tipo
    DmiBoard,           # da el nombre de la placa, que usa el árbol de sensores
    SystemIdentity,
    PrivilegedMemory,   # espera a que el usuario lo pida
    SpdModules,         # después, para pegarse a lo que aquél haya leído
    SysfsClocks,
    TurboState,
    CpuUsage,
    SystemState,
    RaplPower,
    HwmonSensors,       # nombra los aparatos con lo que ya se sabe
    DerivedSensors,     # el último: solo transforma lo recogido
)


class Collector:
    """Punto de entrada de la capa de datos. Reutilizable y con estado propio."""

    def __init__(self, providers: Optional[Sequence[Provider]] = None) -> None:
        self.providers: list[Provider] = list(providers) if providers is not None else [
            cls() for cls in DEFAULT_PROVIDERS
        ]
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
        for provider in self.providers:
            if isinstance(provider, PrivilegedMemory):
                provider.requested = True
        self.invalidate()

    def close(self) -> None:
        for provider in self.providers:
            client = getattr(provider, "client", None)
            if client is not None:
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
            except Exception as exc:                      # noqa: BLE001
                draft.note(
                    provider.provides or provider.name,
                    Need.PLATFORM,
                    f"El proveedor «{provider.name}» falló: {exc}",
                    "Es un fallo de cpuz, no de tu equipo. Merece un informe.",
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
        draft.privileged = static.privileged
        draft.sensors = list(static.sensors)
        draft.driver_hints = list(static.driver_hints)
        draft.capabilities = set(static.capabilities)
        draft.notes = list(static.notes)
        return draft
