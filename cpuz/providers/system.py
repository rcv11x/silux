"""Sistema operativo, kernel, memoria y actividad.

Se parte en dos proveedores porque la naturaleza de los datos es distinta: la
distribución y el kernel no cambian mientras el programa está abierto, y la
memoria y el número de procesos cambian cada segundo. Leer /etc/os-release una
vez por muestreo sería tirar trabajo.
"""

from __future__ import annotations

import dataclasses
import glob
import os
import platform
import re
import time
from typing import Optional

from ..model import Memory, Need, Sensor, SensorKind, System
from .base import Draft, Provider, read_text

OS_RELEASE = "/etc/os-release"
MEMINFO = "/proc/meminfo"

_OS_LINE = re.compile(r'^([A-Z_]+)=(?:"(.*)"|(.*))$')
_MEM_FIELDS = {
    "MemTotal": "total_bytes",
    "MemAvailable": "available_bytes",
    "MemFree": "free_bytes",
    "Buffers": "buffers_bytes",
    "Cached": "cached_bytes",
    "Shmem": "shared_bytes",
    "SReclaimable": "reclaimable_bytes",
    "SwapTotal": "swap_total_bytes",
    "SwapFree": "swap_free_bytes",
}


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(OS_RELEASE, encoding="utf-8") as handle:
            for line in handle:
                if match := _OS_LINE.match(line.strip()):
                    values[match.group(1)] = match.group(2) or match.group(3) or ""
    except OSError:
        pass
    return values


class SystemIdentity(Provider):
    """Lo que no cambia: distribución, kernel, escritorio, nombre del equipo."""

    name = "system-identity"
    provides = "system"
    static = True

    def collect(self, draft: Draft) -> None:
        release = _os_release()
        uname = platform.uname()

        draft.capabilities.add("system")
        draft.system = System(
            distribution=release.get("PRETTY_NAME") or release.get("NAME"),
            distribution_id=release.get("ID"),
            version_id=release.get("VERSION_ID"),
            variant=release.get("VARIANT"),

            kernel=f"{uname.system} {uname.release}",
            kernel_build=self._kernel_build(),
            architecture=uname.machine,

            hostname=read_text("/proc/sys/kernel/hostname") or uname.node,
            init=self._init_system(),
            desktop=os.environ.get("XDG_CURRENT_DESKTOP"),
            session_type=os.environ.get("XDG_SESSION_TYPE"),
            shell=os.path.basename(os.environ.get("SHELL", "")) or None,
        )

    @staticmethod
    def _kernel_build() -> Optional[str]:
        """La fecha y el compilador con que se construyó el kernel."""
        raw = read_text("/proc/version")
        if not raw:
            return None
        if match := re.search(r"\(gcc[^)]*\)[^#]*(#\S+\s+.*)$", raw):
            return match.group(1).strip()
        return raw.split("(")[0].strip() or None

    @staticmethod
    def _init_system() -> Optional[str]:
        try:
            return os.path.basename(os.readlink("/proc/1/exe"))
        except OSError:
            return read_text("/proc/1/comm")


class SystemState(Provider):
    """Lo que cambia: memoria, tiempo encendido, procesos y descriptores."""

    name = "system-state"
    provides = "system.memory"

    def available(self) -> bool:
        return os.path.exists(MEMINFO)

    def unavailable_reason(self):
        if self.available():
            return None
        return ("system.memory", Need.PLATFORM,
                "No hay /proc/meminfo en este sistema.", "")

    def collect(self, draft: Draft) -> None:
        uptime = self._uptime()
        draft.system = dataclasses.replace(
            draft.system,
            memory=self._memory(),
            uptime_seconds=uptime,
            boot_time=self._boot_time(uptime),
            processes=len(glob.glob("/proc/[0-9]*")),
            threads=self._threads(),
            open_files=self._open_files(),
        )
        draft.sensors.extend(self._sensors(draft.system))

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _memory() -> Memory:
        values: dict[str, int] = {}
        try:
            with open(MEMINFO, encoding="ascii") as handle:
                for line in handle:
                    key, _, rest = line.partition(":")
                    field = _MEM_FIELDS.get(key)
                    if field is None:
                        continue
                    # /proc/meminfo va en kibibytes salvo excepciones raras.
                    values[field] = int(rest.split()[0]) * 1024
                    if len(values) == len(_MEM_FIELDS):
                        break
        except (OSError, ValueError, IndexError):
            return Memory()
        return Memory(**values)

    @staticmethod
    def _uptime() -> float:
        raw = read_text("/proc/uptime")
        try:
            return float(raw.split()[0]) if raw else 0.0
        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def _boot_time(uptime: float) -> Optional[str]:
        if uptime <= 0:
            return None
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(time.time() - uptime))

    @staticmethod
    def _threads() -> int:
        """El cuarto campo de /proc/loadavg cuenta entidades del planificador,
        que son hilos: mucho más barato que recorrer /proc/*/task."""
        raw = read_text("/proc/loadavg")
        try:
            return int(raw.split()[3].split("/")[1]) if raw else 0
        except (ValueError, IndexError):
            return 0

    @staticmethod
    def _open_files() -> int:
        raw = read_text("/proc/sys/fs/file-nr")
        try:
            return int(raw.split()[0]) if raw else 0
        except (ValueError, IndexError):
            return 0

    @staticmethod
    def _sensors(system: System) -> list[Sensor]:
        """La ocupación de memoria también es una magnitud que se sigue."""
        memory = system.memory
        if not memory.total_bytes:
            return []
        sensors = [Sensor(
            key="memory/ram", chip="meminfo", device="Memoria",
            label="RAM usada", kind=SensorKind.USAGE,
            value=memory.used_percent, order=0, high=90.0,
        )]
        if memory.swap_total_bytes:
            sensors.append(Sensor(
                key="memory/swap", chip="meminfo", device="Memoria",
                label="Intercambio usado", kind=SensorKind.USAGE,
                value=memory.swap_used_percent, order=1, high=80.0,
            ))
        return sensors
