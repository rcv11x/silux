"""Operating system, kernel, memory and activity.

Two providers, because the data differ in kind: the distribution and the
kernel do not change while the program runs, and memory and the number of
processes change every second. Reading /etc/os-release on every sample
would be wasted work.
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

from .. import kernel, privacidad, sysroot
from ..i18n import _
from ..model import Boot, DeviceKind, Memory, Need, Sensor, SensorKind, Swap, System, Vulnerability
from ..system_env import system_environment
from .base import Draft, Provider, on_its_own, read_int, read_text

OS_RELEASE = "/etc/os-release"

# The taint bits a module can set (P, F, C, O, E, K, X, T, N): the ones
# whose culprit /sys/module/<name>/taint can name.
MODULE_TAINT_BITS = sum(1 << bit for bit in (0, 1, 10, 12, 13, 15, 16, 17, 18))

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


def _unquote(value: str) -> str:
    """Strip the quotes of an os-release value.

    The format is a shell fragment, so quotes can be double or single; with
    only the double ones, single-quoted values showed with their quotes.
    """
    value = value.strip()
    for quote in ('"', "'"):
        if len(value) >= 2 and value[0] == quote and value[-1] == quote:
            value = value[1:-1]
            break
    # In double quotes, the shell lets a few characters be escaped.
    return re.sub(r"\\([\\$`\"'])", r"\1", value)


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(sysroot.ruta(OS_RELEASE), encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("#"):
                    continue
                if match := _OS_LINE.match(line):
                    values[match.group(1)] = _unquote(match.group(2))
    except OSError:
        pass
    return values


class SystemIdentity(Provider):
    """What does not change: distribution, kernel, desktop, machine name."""

    name = "system-identity"
    provides = "system"
    static = True

    def collect(self, draft: Draft) -> None:
        release = _os_release()
        uname = sysroot.a_traves("plataforma", "uname", lambda: platform.uname()._asdict())
        environment = sysroot.a_traves("plataforma", "entorno", lambda: {
            key: os.environ.get(key)
            for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "SHELL")})

        draft.capabilities.add("system")
        draft.system = System(
            distribution=release.get("PRETTY_NAME") or release.get("NAME"),
            distribution_id=release.get("ID"),
            version_id=release.get("VERSION_ID"),
            variant=release.get("VARIANT"),

            kernel=f"{uname['system']} {uname['release']}",
            kernel_build=on_its_own(draft, "system.kernel_build", self._kernel_build),
            architecture=uname["machine"],

            hostname=read_text("/proc/sys/kernel/hostname") or uname["node"],
            init=on_its_own(draft, "system.init", self._init_system),
            desktop=environment.get("XDG_CURRENT_DESKTOP"),
            session_type=environment.get("XDG_SESSION_TYPE"),
            shell=os.path.basename(environment.get("SHELL") or "") or None,
        )
        running = kernel.version(uname["release"])
        if running is not None and running < kernel.MINIMO:
            # What appeared after the minimum is explained value by value;
            # below it, something may be missing and nothing would say why.
            draft.note("system.kernel", Need.KERNEL, _("kernel.belowminimum").format(
                tuyo=f"{running[0]}.{running[1]}",
                minimo=f"{kernel.MINIMO[0]}.{kernel.MINIMO[1]}"), key="kernel.belowminimum")

    @staticmethod
    def _kernel_build() -> Optional[str]:
        """The date and compiler the kernel was built with.

        What matters starts at «#», the build number, and goes on with the
        date. The compiler is in the last parenthesis before it; with only gcc
        accepted, a kernel built with clang repeated the kernel's own name.
        """
        raw = read_text("/proc/version")
        if not raw:
            return None
        hash_mark = re.search(r"(#\d+.*)$", raw)
        if not hash_mark:
            return None
        build = hash_mark.group(1).strip()
        head = raw[:hash_mark.start()]
        # Who built it. Parentheses cannot be trusted: «gcc (Gentoo 14.3.0
        # p2) 14.3.0» and «gcc-13 (Ubuntu 13.2.0) 13.2.0» nest them. Finding
        # the name and taking the last version after it is enough.
        if compiler := re.search(r"\b(gcc|clang)\b", head, re.IGNORECASE):
            up_to_comma = head[compiler.end():].split(",")[0]
            if versions := re.findall(r"\d+\.\d+(?:\.\d+)?", up_to_comma):
                return f"{build} · {compiler.group(1).lower()} {versions[-1]}"
        return build

    @staticmethod
    def _init_system() -> Optional[str]:
        try:
            name = os.path.basename(os.readlink(sysroot.ruta("/proc/1/exe")))
        except OSError:
            name = read_text("/proc/1/comm")
        # OpenRC runs under sysvinit's `init`, which would read «Init: init».
        # Its runlevels are in /etc, which sysroot translates and a dump
        # carries (/run is neither: a test would read this machine).
        if name == "init" and os.path.isdir(sysroot.ruta("/etc/runlevels")):
            return "openrc"
        if name == "openrc-init":
            return "openrc"
        return name


VULNERABILITIES = "/sys/devices/system/cpu/vulnerabilities"
EFIVARS = "/sys/firmware/efi/efivars"
# The id under which boot loaders publish their variables (systemd's Boot
# Loader Interface). Only these four are read: the rest carry the partition's
# UUID and a system id, nobody's business.
LOADER_GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"


def state_of(status: str) -> str:
    """What the kernel says of a vulnerability, in one of four words."""
    if status.startswith("Not affected"):
        return "unaffected"
    if status.startswith("Vulnerable"):
        return "vulnerable"
    if "Mitigation" in status:
        return "mitigated"
    return "unknown"


def _efi_variable(name: str) -> Optional[str]:
    """A boot loader variable's text: four bytes of attributes, then
    UTF-16."""
    try:
        with open(sysroot.ruta(f"{EFIVARS}/{name}-{LOADER_GUID}"), "rb") as handle:
            raw = handle.read(4096)
    except OSError:
        return None
    return raw[4:].decode("utf-16-le", "replace").strip("\x00 ") or None


# The firmware's FPDT table: when it launched the loader and when the loader
# handed back control on leaving boot services, in ns since power-on. Where
# systemd takes firmware and loader times when the boot manager publishes no
# variables, readable without permissions.
FPDT = "/sys/firmware/acpi/fpdt/boot"

# What systemd knows of the boot, in µs since the kernel started. Over D-Bus,
# without permissions, with any boot loader.
SYSTEMD_PROPERTIES = ("InitRDTimestampMonotonic", "UserspaceTimestampMonotonic",
                          "FinishTimestampMonotonic")


def _parse_systemctl(out: str) -> Optional[dict[str, int]]:
    values = {}
    for line in out.splitlines():
        key, _sep, value = line.partition("=")
        if key in SYSTEMD_PROPERTIES and value.strip().isdigit():
            values[key] = int(value)
    return values or None


def _systemd_times() -> Optional[dict[str, int]]:
    try:
        done = subprocess.run(
            ["systemctl", "show", *(f"--property={p}" for p in SYSTEMD_PROPERTIES)],
            capture_output=True, text=True, timeout=3,
            env=dict(system_environment(), LC_ALL="C"))
    except (OSError, subprocess.SubprocessError):
        return None
    return _parse_systemctl(done.stdout) if done.returncode == 0 else None


class SystemSecurity(Provider):
    """What does not change all session: mitigations and boot."""

    name = "system-security"
    provides = "system.vulnerabilities"
    static = True

    def collect(self, draft: Draft) -> None:
        draft.system = dataclasses.replace(
            draft.system, vulnerabilities=self._vulnerabilities(), boot=self._boot())

    @staticmethod
    def _vulnerabilities() -> tuple[Vulnerability, ...]:
        out = []
        for path in sorted(glob.glob(os.path.join(sysroot.ruta(VULNERABILITIES), "*"))):
            status = read_text(sysroot.fuera(path))
            if status:
                out.append(Vulnerability(name=os.path.basename(path), status=status,
                                            state=state_of(status)))
        return tuple(out)

    @staticmethod
    def _boot() -> Boot:
        def seconds(name: str) -> Optional[float]:
            value = _efi_variable(name)
            return int(value) / 1e6 if value and value.isdigit() else None

        to_loader = seconds("LoaderTimeInitUSec")
        to_kernel = seconds("LoaderTimeExecUSec")
        if to_loader is None or to_kernel is None:
            launched = read_int(f"{FPDT}/bootloader_launch_ns")
            exited = read_int(f"{FPDT}/exitbootservice_end_ns")
            if launched and exited:
                to_loader, to_kernel = launched / 1e9, exited / 1e9
        loader = (round(to_kernel - to_loader, 1)
                    if to_loader is not None and to_kernel is not None
                    and to_kernel >= to_loader else None)
        if loader is None:
            to_loader = None

        systemd = sysroot.a_traves("systemd", "arranque", _systemd_times) or {}
        initrd = systemd.get("InitRDTimestampMonotonic", 0)
        userspace = systemd.get("UserspaceTimestampMonotonic", 0)
        finish = systemd.get("FinishTimestampMonotonic", 0)

        def span(start: int, end: int) -> Optional[float]:
            return round((end - start) / 1e6, 1) if end > start else None

        return Boot(
            loader=_efi_variable("LoaderInfo"),
            entry=_efi_variable("LoaderEntrySelected"),
            firmware_s=round(to_loader, 1) if to_loader is not None else None,
            loader_s=loader,
            # Without an initrd, the kernel runs up to systemd.
            kernel_s=span(0, initrd or userspace) if userspace else None,
            initrd_s=span(initrd, userspace) if initrd else None,
            userspace_s=span(userspace, finish) if userspace and finish else None,
            cmdline=privacidad.hide_cmdline_identifiers(read_text("/proc/cmdline") or ""))


def read_swaps() -> tuple[Swap, ...]:
    """Each swap space in `/proc/swaps`; zram with its own details."""
    raw = read_text("/proc/swaps") or ""
    out = []
    for line in raw.splitlines()[1:]:
        campos = line.split()
        if len(campos) < 5:
            continue
        try:
            size, used, priority = int(campos[2]) * 1024, int(campos[3]) * 1024, int(campos[4])
        except ValueError:
            continue
        swap = Swap(device=campos[0], kind=campos[1], size_bytes=size, used_bytes=used,
                    priority=priority)
        name = os.path.basename(campos[0])
        if name.startswith("zram"):
            algorithms = read_text(f"/sys/block/{name}/comp_algorithm") or ""
            chosen = next((a.strip("[]") for a in algorithms.split() if a.startswith("[")), None)
            status = (read_text(f"/sys/block/{name}/mm_stat") or "").split()
            try:
                original, compressed = int(status[0]), int(status[1])
            except (ValueError, IndexError):
                original = compressed = None
            swap = dataclasses.replace(swap, zram=True, algorithm=chosen,
                                       original_bytes=original, compressed_bytes=compressed)
        out.append(swap)
    return tuple(out)


class SystemState(Provider):
    """What changes: memory, uptime, processes and file descriptors."""

    name = "system-state"
    provides = "system.memory"

    def available(self) -> bool:
        return os.path.exists(sysroot.ruta(MEMINFO))

    def unavailable_reason(self):
        if self.available():
            return None
        return ("system.memory", Need.PLATFORM,
                _("prov.sys.nomeminfo"), "", "",
                _("prov.missing.detail").format(ruta="/proc/meminfo"))

    def collect(self, draft: Draft) -> None:
        uptime = self._uptime()
        draft.system = dataclasses.replace(
            draft.system,
            memory=self._memory(),
            uptime_seconds=uptime,
            boot_time=self._boot_time(uptime),
            processes=self._processes(),
            swaps=read_swaps(),
            threads=self._threads(),
            open_files=self._open_files(),
            # Can change during the session: loading a module taints it.
            tainted=(mask := read_int("/proc/sys/kernel/tainted")),
            tainting_modules=self._tainting_modules(mask),
        )
        draft.sensors.extend(self._sensors(draft.system))

    # -- internals ----------------------------------------------------------

    def _tainting_modules(self, mask: Optional[int]) -> tuple[tuple[str, str], ...]:
        """Which loaded modules tainted the kernel, and with what.

        Read again only when the mask or the number of loaded modules
        changes, not on every sample; and not at all when no bit set is one
        a module can set.
        """
        if not mask or not mask & MODULE_TAINT_BITS:
            return ()
        try:
            loaded = len(os.listdir(sysroot.ruta("/sys/module")))
        except OSError:
            return ()
        key = (mask, loaded)
        if getattr(self, "_taint_key", None) != key:
            found = []
            for path in sorted(glob.glob(os.path.join(sysroot.ruta("/sys/module"), "*", "taint"))):
                if letters := read_text(sysroot.fuera(path)):
                    found.append((os.path.basename(os.path.dirname(path)), letters))
            self._taint_key, self._taint_modules = key, tuple(found)
        return self._taint_modules

    @staticmethod
    def _processes() -> int:
        """How many processes there are. Through `a_traves`: a dump does not
        copy all of `/proc`, and counting its folders gave «Processes: 1»."""
        count = sysroot.a_traves(
            "plataforma", "procesos", lambda: len(glob.glob("/proc/[0-9]*")))
        if count is None:                      # a dump from before it was recorded
            count = len(glob.glob(sysroot.ruta("/proc/[0-9]*")))
        return int(count)

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
                    # /proc/meminfo is in kibibytes but for rare exceptions.
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
        # Year-month-day, like the firmware date (`render.bios_date`): «06/08»
        # reads two ways depending on who looks, this only one.
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - uptime))

    @staticmethod
    def _threads() -> int:
        """The fourth field of /proc/loadavg counts scheduler entities, which
        are threads: far cheaper than walking /proc/*/task."""
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
        """Memory use is a value worth following too."""
        memory = system.memory
        if not memory.total_bytes:
            return []
        sensors = [Sensor(
            key="memory/ram", chip="meminfo", device=_("sensor.mem"),
            device_key="memory",
            device_kind=DeviceKind.MEMORY,
            label=_("sensor.mem.ram"), kind=SensorKind.USAGE,
            value=memory.used_percent, order=0, high=90.0,
        )]
        if memory.swap_total_bytes:
            sensors.append(Sensor(
                key="memory/swap", chip="meminfo", device=_("sensor.mem"),
            device_key="memory",
                device_kind=DeviceKind.MEMORY,
                label=_("sensor.mem.swap"), kind=SensorKind.USAGE,
                value=memory.swap_used_percent, order=1, high=80.0,
            ))
        return sensors
