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

_OS_LINE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
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


def _desentrecomillar(valor: str) -> str:
    """Quita las comillas de un valor de os-release.

    El formato es el de un fragmento de shell, así que las comillas pueden ser
    dobles o simples. Mirando solo las dobles, Gentoo —que usa simples—
    aparecía en la ventana como 'Gentoo Linux' y '2.18', con las comillas
    puestas.
    """
    valor = valor.strip()
    for comilla in ('"', "'"):
        if len(valor) >= 2 and valor[0] == comilla and valor[-1] == comilla:
            valor = valor[1:-1]
            break
    # En las dobles, el shell deja escapar unos cuantos caracteres.
    return re.sub(r"\\([\\$`\"'])", r"\1", valor)


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(OS_RELEASE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("#"):
                    continue
                if match := _OS_LINE.match(line):
                    values[match.group(1)] = _desentrecomillar(match.group(2))
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
        """La fecha y el compilador con que se construyó el kernel.

        Lo interesante empieza en el «#», que es el número de compilación, y
        sigue con la fecha. El compilador va en el último paréntesis anterior.
        Antes se exigía que fuera gcc, y con cualquier otro —CachyOS compila
        con clang— el respaldo devolvía «Linux version 6.18.35-gentoo», que
        es repetir el kernel en el renglón de al lado.
        """
        raw = read_text("/proc/version")
        if not raw:
            return None
        marca = re.search(r"(#\d+.*)$", raw)
        if not marca:
            return None
        build = marca.group(1).strip()
        cabeza = raw[:marca.start()]
        # Quién lo compiló. Nada de fiarse de los paréntesis: Gentoo escribe
        # «gcc (Gentoo 14.3.0 p2) 14.3.0» y Ubuntu «gcc-13 (Ubuntu 13.2.0)
        # 13.2.0», los dos con paréntesis dentro de paréntesis. Vale con
        # buscar el nombre y quedarse con la última versión que va detrás.
        if quien := re.search(r"\b(gcc|clang)\b", cabeza, re.IGNORECASE):
            hasta_la_coma = cabeza[quien.end():].split(",")[0]
            if versiones := re.findall(r"\d+\.\d+(?:\.\d+)?", hasta_la_coma):
                return f"{build} · {quien.group(1).lower()} {versiones[-1]}"
        return build

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
