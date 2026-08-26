"""Infraestructura común de los proveedores.

Un proveedor lee una fuente concreta (CPUID, sysfs, hwmon…) y escribe en un
`Draft`. El borrador es mutable porque la recolección lo es; al final se
congela en un `Snapshot` inmutable, que es lo único que sale de la capa de
datos.

Cada proveedor declara qué necesita para funcionar. Cuando no puede,
no desaparece en silencio: deja una `Note` explicando por qué, y la interfaz
la enseña en vez de mostrar un hueco sin explicación.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..model import (
    Board, Cache, Clocks, CpuInfo, CpuType, DriverHint, Gpu, LogicalCpu,
    NetworkInterface,
    MemoryArray, MemoryModule, Need, Note, Power, PrivilegedState, Sensor,
    Snapshot, System,
)


@dataclass
class Draft:
    """Estado mutable durante una recolección. No sale nunca del colector."""

    monotonic_ns: int = field(default_factory=time.monotonic_ns)
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
    gpus: list[dict[str, Any]] = field(default_factory=list)
    network: list = field(default_factory=list)
    privileged: PrivilegedState = field(default_factory=PrivilegedState)
    sensors: list[Sensor] = field(default_factory=list)
    driver_hints: list[DriverHint] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    notes: list[Note] = field(default_factory=list)

    # -- ayudas de escritura ------------------------------------------------

    def type_for(self, key: str) -> dict[str, Any]:
        return self.types.setdefault(key, {"key": key, "label": key, "cpus": []})

    def cpu(self, index: int) -> dict[str, Any]:
        return self.logical.setdefault(index, {"index": index, "core_id": -1, "package_id": 0})

    def gpu(self, index: int) -> dict[str, Any]:
        """La tarjeta número N, creándola si es la primera vez que se la nombra.

        Se guardan como diccionarios y no como `Gpu` porque las rellenan varios
        proveedores por turnos —el kernel primero, las APIs gráficas después— y
        rehacer un dataclass congelado en cada paso se come los campos que otro
        acaba de poner.
        """
        while len(self.gpus) <= index:
            self.gpus.append({"index": len(self.gpus)})
        return self.gpus[index]

    def note(self, path: str, need: Need, message: str, hint: str = "") -> None:
        self.notes.append(Note(path=path, need=need, message=message, hint=hint))

    # -- congelación --------------------------------------------------------

    def freeze(self) -> Snapshot:
        types: list[CpuType] = []
        for raw in self.types.values():
            data = dict(raw)
            data["cpus"] = tuple(sorted(data.get("cpus", ())))
            data["caches"] = tuple(data.get("caches", ()))
            data["features"] = tuple(data.get("features", ()))
            data.setdefault("clocks", Clocks())
            # Descarta cualquier clave que no sea un campo del modelo: evita
            # que un proveedor rompa el congelado escribiendo de más.
            valid = {f for f in CpuType.__dataclass_fields__}
            types.append(CpuType(**{k: v for k, v in data.items() if k in valid}))

        logical = tuple(
            LogicalCpu(**{k: v for k, v in raw.items() if k in LogicalCpu.__dataclass_fields__})
            for _, raw in sorted(self.logical.items())
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
        )

        return Snapshot(
            monotonic_ns=self.monotonic_ns,
            cpu=cpu,
            board=self.board,
            system=self.system,
            modules=tuple(self.modules),
            spd=tuple(self.spd),
            memory_array=self.memory_array,
            network=tuple(self.network),
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
    """Base de todos los proveedores.

    `static` distingue lo que se lee una vez (identidad, topología, cachés) de
    lo que hay que refrescar en cada muestreo (frecuencias, temperaturas, uso).
    """

    name: str = "sin-nombre"
    provides: str = ""
    static: bool = False

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> Optional[tuple[str, Need, str, str]]:
        """(ruta, motivo, mensaje, pista) si no se puede usar. `None` si sí."""
        return None

    def collect(self, draft: Draft) -> None:
        raise NotImplementedError


# --------------------------------------------------------------------------
# lectura de sysfs y procfs, tolerante a ficheros que no existen
# --------------------------------------------------------------------------


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except (OSError, ValueError):
        return None


def read_int(path: str) -> Optional[int]:
    raw = read_text(path)
    if raw is None:
        return None
    try:
        return int(raw, 0)
    except ValueError:
        return None


def parse_cpu_list(raw: Optional[str]) -> tuple[int, ...]:
    """Convierte "0-3,8,10-11" en (0, 1, 2, 3, 8, 10, 11)."""
    if not raw:
        return ()
    out: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
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
    """Convierte "32K" / "12288K" / "8M" a bytes."""
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
