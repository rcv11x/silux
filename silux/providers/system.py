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
import subprocess
import time
from typing import Optional

from ..i18n import _
from ..model import (Boot, DeviceKind, Memory, Need, Sensor, SensorKind, Swap, System,
                     Vulnerability)
from .base import Draft, Provider, read_int, read_text
from .. import sysroot

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
        with open(sysroot.ruta(OS_RELEASE), encoding="utf-8") as handle:
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
        uname = sysroot.a_traves("plataforma", "uname", lambda: platform.uname()._asdict())
        entorno = sysroot.a_traves("plataforma", "entorno", lambda: {
            clave: os.environ.get(clave)
            for clave in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "SHELL")})

        draft.capabilities.add("system")
        draft.system = System(
            distribution=release.get("PRETTY_NAME") or release.get("NAME"),
            distribution_id=release.get("ID"),
            version_id=release.get("VERSION_ID"),
            variant=release.get("VARIANT"),

            kernel=f"{uname['system']} {uname['release']}",
            kernel_build=self._kernel_build(),
            architecture=uname["machine"],

            hostname=read_text("/proc/sys/kernel/hostname") or uname["node"],
            init=self._init_system(),
            desktop=entorno.get("XDG_CURRENT_DESKTOP"),
            session_type=entorno.get("XDG_SESSION_TYPE"),
            shell=os.path.basename(entorno.get("SHELL") or "") or None,
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
            return os.path.basename(os.readlink(sysroot.ruta("/proc/1/exe")))
        except OSError:
            return read_text("/proc/1/comm")


VULNERABILIDADES = "/sys/devices/system/cpu/vulnerabilities"
EFIVARS = "/sys/firmware/efi/efivars"
# El identificador con que los cargadores publican sus variables (la interfaz
# del cargador de arranque de systemd). De ahí solo se leen estas cuatro: las
# demás llevan el UUID de la partición y una ficha del sistema, que no son
# asunto de nadie.
GUID_DEL_CARGADOR = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"


def estado_de(status: str) -> str:
    """Qué dice el kernel de una vulnerabilidad, en una de cuatro palabras."""
    if status.startswith("Not affected"):
        return "unaffected"
    if status.startswith("Vulnerable"):
        return "vulnerable"
    if "Mitigation" in status:
        return "mitigated"
    return "unknown"


def _variable_efi(nombre: str) -> Optional[str]:
    """El texto de una variable del cargador. Cuatro bytes de atributos y
    después UTF-16."""
    try:
        with open(sysroot.ruta(f"{EFIVARS}/{nombre}-{GUID_DEL_CARGADOR}"), "rb") as archivo:
            crudo = archivo.read(4096)
    except OSError:
        return None
    return crudo[4:].decode("utf-16-le", "replace").strip("\x00 ") or None


# La tabla FPDT del firmware: cuándo lanzó al cargador y cuándo este le
# devolvió el control al salir de los servicios de arranque, en ns desde el
# encendido. Es de donde systemd saca firmware y cargador cuando el gestor no
# publica sus variables (el GRUB de Fedora), y se lee sin permisos.
FPDT = "/sys/firmware/acpi/fpdt/boot"

# Lo que systemd sabe del arranque, en µs desde que arrancó el kernel. Por
# D-Bus, sin permisos, con cualquier gestor de arranque.
PROPIEDADES_DE_SYSTEMD = ("InitRDTimestampMonotonic", "UserspaceTimestampMonotonic",
                          "FinishTimestampMonotonic")


def _leer_systemctl(salida: str) -> Optional[dict[str, int]]:
    valores = {}
    for linea in salida.splitlines():
        clave, _sep, valor = linea.partition("=")
        if clave in PROPIEDADES_DE_SYSTEMD and valor.strip().isdigit():
            valores[clave] = int(valor)
    return valores or None


def _tiempos_de_systemd() -> Optional[dict[str, int]]:
    try:
        hecho = subprocess.run(
            ["systemctl", "show", *(f"--property={p}" for p in PROPIEDADES_DE_SYSTEMD)],
            capture_output=True, text=True, timeout=3, env=dict(os.environ, LC_ALL="C"))
    except (OSError, subprocess.SubprocessError):
        return None
    return _leer_systemctl(hecho.stdout) if hecho.returncode == 0 else None


class SystemSecurity(Provider):
    """Lo que no cambia en toda la sesión: mitigaciones y arranque."""

    name = "system-security"
    provides = "system.vulnerabilities"
    static = True

    def collect(self, draft: Draft) -> None:
        draft.system = dataclasses.replace(
            draft.system, vulnerabilities=self._vulnerabilidades(), boot=self._arranque())

    @staticmethod
    def _vulnerabilidades() -> tuple[Vulnerability, ...]:
        salida = []
        for camino in sorted(glob.glob(os.path.join(sysroot.ruta(VULNERABILIDADES), "*"))):
            estado = read_text(sysroot.fuera(camino))
            if estado:
                salida.append(Vulnerability(name=os.path.basename(camino), status=estado,
                                            state=estado_de(estado)))
        return tuple(salida)

    @staticmethod
    def _arranque() -> Boot:
        def segundos(nombre: str) -> Optional[float]:
            valor = _variable_efi(nombre)
            return int(valor) / 1e6 if valor and valor.isdigit() else None

        hasta_el_cargador = segundos("LoaderTimeInitUSec")
        hasta_el_kernel = segundos("LoaderTimeExecUSec")
        if hasta_el_cargador is None or hasta_el_kernel is None:
            lanzado = read_int(f"{FPDT}/bootloader_launch_ns")
            salida = read_int(f"{FPDT}/exitbootservice_end_ns")
            if lanzado and salida:
                hasta_el_cargador, hasta_el_kernel = lanzado / 1e9, salida / 1e9
        cargador = (round(hasta_el_kernel - hasta_el_cargador, 1)
                    if hasta_el_cargador is not None and hasta_el_kernel is not None
                    and hasta_el_kernel >= hasta_el_cargador else None)
        if cargador is None:
            hasta_el_cargador = None

        systemd = sysroot.a_traves("systemd", "arranque", _tiempos_de_systemd) or {}
        initrd = systemd.get("InitRDTimestampMonotonic", 0)
        espacio = systemd.get("UserspaceTimestampMonotonic", 0)
        fin = systemd.get("FinishTimestampMonotonic", 0)

        def tramo(desde: int, hasta: int) -> Optional[float]:
            return round((hasta - desde) / 1e6, 1) if hasta > desde else None

        return Boot(
            loader=_variable_efi("LoaderInfo"),
            entry=_variable_efi("LoaderEntrySelected"),
            firmware_s=round(hasta_el_cargador, 1) if hasta_el_cargador is not None else None,
            loader_s=cargador,
            # Sin initrd, el kernel llega hasta systemd.
            kernel_s=tramo(0, initrd or espacio) if espacio else None,
            initrd_s=tramo(initrd, espacio) if initrd else None,
            userspace_s=tramo(espacio, fin) if espacio and fin else None)


def leer_intercambio() -> tuple[Swap, ...]:
    """Cada espacio de intercambio de `/proc/swaps`; el zram, con lo suyo."""
    crudo = read_text("/proc/swaps") or ""
    salida = []
    for linea in crudo.splitlines()[1:]:
        campos = linea.split()
        if len(campos) < 5:
            continue
        try:
            tamano, usado, prioridad = int(campos[2]) * 1024, int(campos[3]) * 1024, int(campos[4])
        except ValueError:
            continue
        swap = Swap(device=campos[0], kind=campos[1], size_bytes=tamano, used_bytes=usado,
                    priority=prioridad)
        nombre = os.path.basename(campos[0])
        if nombre.startswith("zram"):
            algoritmos = read_text(f"/sys/block/{nombre}/comp_algorithm") or ""
            elegido = next((a.strip("[]") for a in algoritmos.split() if a.startswith("[")), None)
            estado = (read_text(f"/sys/block/{nombre}/mm_stat") or "").split()
            try:
                original, comprimido = int(estado[0]), int(estado[1])
            except (ValueError, IndexError):
                original = comprimido = None
            swap = dataclasses.replace(swap, zram=True, algorithm=elegido,
                                       original_bytes=original, compressed_bytes=comprimido)
        salida.append(swap)
    return tuple(salida)


class SystemState(Provider):
    """Lo que cambia: memoria, tiempo encendido, procesos y descriptores."""

    name = "system-state"
    provides = "system.memory"

    def available(self) -> bool:
        return os.path.exists(sysroot.ruta(MEMINFO))

    def unavailable_reason(self):
        if self.available():
            return None
        return ("system.memory", Need.PLATFORM,
                _("prov.sys.nomeminfo"), "")

    def collect(self, draft: Draft) -> None:
        uptime = self._uptime()
        draft.system = dataclasses.replace(
            draft.system,
            memory=self._memory(),
            uptime_seconds=uptime,
            boot_time=self._boot_time(uptime),
            processes=self._procesos(),
            swaps=leer_intercambio(),
            threads=self._threads(),
            open_files=self._open_files(),
        )
        draft.sensors.extend(self._sensors(draft.system))

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _procesos() -> int:
        """Cuántos procesos hay. Por `a_traves`: un volcado no copia `/proc`
        entero, y contando sus carpetas el equipo volcado decía «Procesos: 1»
        donde el de verdad tenía quinientos."""
        cuenta = sysroot.a_traves(
            "plataforma", "procesos", lambda: len(glob.glob("/proc/[0-9]*")))
        if cuenta is None:                      # un volcado de antes de grabarlo
            cuenta = len(glob.glob(sysroot.ruta("/proc/[0-9]*")))
        return int(cuenta)

    @staticmethod
    def _memory() -> Memory:
        values: dict[str, int] = {}
        try:
            with open(sysroot.ruta(MEMINFO), encoding="ascii") as handle:
                for line in handle:
                    key, _sep, rest = line.partition(":")
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
        # Año-mes-día, como la fecha de la BIOS (`render.bios_date`): «06/08»
        # se lee de dos maneras según quién lo mire, y esto de ninguna más.
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - uptime))

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
            key="memory/ram", chip="meminfo", device=_("sensor.mem"),
            device_kind=DeviceKind.MEMORY,
            label=_("sensor.mem.ram"), kind=SensorKind.USAGE,
            value=memory.used_percent, order=0, high=90.0,
        )]
        if memory.swap_total_bytes:
            sensors.append(Sensor(
                key="memory/swap", chip="meminfo", device=_("sensor.mem"),
                device_kind=DeviceKind.MEMORY,
                label=_("sensor.mem.swap"), kind=SensorKind.USAGE,
                value=memory.swap_used_percent, order=1, high=80.0,
            ))
        return sensors
