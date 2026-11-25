"""Operating system, kernel, memory and activity.

Two providers because the data differ in kind: the distribution and kernel
don't change while Silux runs, while memory and process counts change every
second, and rereading /etc/os-release each sample would be wasted work.
"""

from __future__ import annotations

import dataclasses
import glob
import os
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

# The taint bits a module can set (P, F, C, O, E, K, X, T, N): those whose
# culprit /sys/module/<name>/taint can name.
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
    """Strip an os-release value's quotes.

    The format is a shell fragment, so quotes may be double or single.
    """
    value = value.strip()
    for quote in ('"', "'"):
        if len(value) >= 2 and value[0] == quote and value[-1] == quote:
            value = value[1:-1]
            break
    # Inside double quotes the shell allows a few escaped characters.
    return re.sub(r"\\([\\$`\"'])", r"\1", value)


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(sysroot.path(OS_RELEASE), encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("#"):
                    continue
                if match := _OS_LINE.match(line):
                    values[match.group(1)] = _unquote(match.group(2))
    except OSError:
        pass
    return values


def desktop(environment: dict) -> Optional[str]:
    """The desktop: XDG's variable, and else what the display manager set.
    Without logind (runit, sysvinit) the first is often missing."""
    for key in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "GDMSESSION"):
        if value := (environment.get(key) or "").strip():
            if key == "XDG_CURRENT_DESKTOP":
                return _xdg_desktop(value)
            # A display manager may give the session file's path.
            return os.path.basename(value)
    return None


def _xdg_desktop(value: str) -> str:
    """The desktop in XDG's variable: «ubuntu:GNOME» is GNOME, «X-Cinnamon»
    Cinnamon.

    The variable is a list, most specific first, and a name not registered
    with freedesktop.org starts with «X-». Distributions put their own tag
    first in lower case (ubuntu, pop, zorin), which is no desktop, while a
    desktop's name has capitals: «Budgie:GNOME» is Budgie.
    """
    names = [re.sub(r"^X-", "", part.strip()) for part in value.split(":") if part.strip()]
    if not names:
        return value
    return next((name for name in names if not name.islower()), names[0])


def session_type(environment: dict) -> Optional[str]:
    """x11 or wayland: XDG's variable, and else the display this runs on."""
    if value := (environment.get("XDG_SESSION_TYPE") or "").strip():
        return value
    if environment.get("WAYLAND_DISPLAY"):
        return "wayland"
    if environment.get("DISPLAY"):
        return "x11"
    return None


class SystemIdentity(Provider):
    """What doesn't change: distribution, kernel, desktop, machine name."""

    name = "system-identity"
    provides = "system"
    static = True

    def collect(self, draft: Draft) -> None:
        release = _os_release()
        uname = sysroot.uname()
        environment = sysroot.recorded("plataforma", "entorno", lambda: {
            key: os.environ.get(key)
            for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "SHELL",
                        "DESKTOP_SESSION", "GDMSESSION", "WAYLAND_DISPLAY", "DISPLAY")}) or {}

        draft.capabilities.add("system")
        draft.system = System(
            distribution=release.get("PRETTY_NAME") or release.get("NAME"),
            distribution_id=release.get("ID"),
            version_id=release.get("VERSION_ID"),
            variant=release.get("VARIANT"),

            kernel=" ".join(p for p in (uname.get("system"), uname.get("release")) if p) or None,
            kernel_build=on_its_own(draft, "system.kernel_build", self._kernel_build),
            architecture=uname.get("machine"),

            hostname=read_text("/proc/sys/kernel/hostname") or uname.get("node"),
            init=on_its_own(draft, "system.init", self._init_system),
            desktop=desktop(environment),
            session_type=session_type(environment),
            shell=os.path.basename(environment.get("SHELL") or "") or None,
        )
        running = kernel.version(uname.get("release") or "")
        if running is not None and running < kernel.MINIMUM:
            # What appeared after the minimum is explained value by value;
            # below it, something could be missing without anything saying why.
            draft.note("system.kernel", Need.KERNEL, _("kernel.belowminimum").format(
                tuyo=f"{running[0]}.{running[1]}",
                minimo=f"{kernel.MINIMUM[0]}.{kernel.MINIMUM[1]}"), key="kernel.belowminimum",
                title=_("kernel.belowminimum.title").format(
                    minimo=f"{kernel.MINIMUM[0]}.{kernel.MINIMUM[1]}"))

    @staticmethod
    def _kernel_build() -> Optional[str]:
        """The date and compiler the kernel was built with.

        What matters starts at «#», the build number, followed by the date.
        The compiler is in the last parenthesised group before it, and may
        be gcc or clang.
        """
        raw = read_text("/proc/version")
        if not raw:
            return None
        hash_mark = re.search(r"(#\d+.*)$", raw)
        if not hash_mark:
            return None
        build = hash_mark.group(1).strip()
        head = raw[:hash_mark.start()]
        # Who built it. Parentheses can't be trusted, since «gcc (Gentoo 14.3.0
        # p2) 14.3.0» and «gcc-13 (Ubuntu 13.2.0) 13.2.0» nest them: find the
        # name and take the last version after it.
        if compiler := re.search(r"\b(gcc|clang)\b", head, re.IGNORECASE):
            up_to_comma = head[compiler.end():].split(",")[0]
            if versions := re.findall(r"\d+\.\d+(?:\.\d+)?", up_to_comma):
                return f"{build} · {compiler.group(1).lower()} {versions[-1]}"
        return build

    @staticmethod
    def _init_system() -> Optional[str]:
        return init_system()


def init_system() -> Optional[str]:
    """What runs as PID 1: «systemd», «runit», «openrc»…"""
    try:
        name = os.path.basename(os.readlink(sysroot.path("/proc/1/exe")))
    except OSError:
        name = read_text("/proc/1/comm")
    # OpenRC runs under sysvinit's `init`, which would read «Init: init».
    # Its runlevels live in /etc, which sysroot translates and a dump
    # carries (/run is neither, so a test would read this machine's).
    if name == "init" and os.path.isdir(sysroot.path("/etc/runlevels")):
        return "openrc"
    if name == "openrc-init":
        return "openrc"
    return name


VULNERABILITIES = "/sys/devices/system/cpu/vulnerabilities"
EFIVARS = "/sys/firmware/efi/efivars"
# The id boot loaders publish their variables under (systemd's Boot Loader
# Interface). Only these four are read; the rest carry the partition's UUID
# and a system id, which are nobody's business.
LOADER_GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"


def state_of(status: str) -> str:
    """The kernel's verdict on a vulnerability, as one of four words."""
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
        with open(sysroot.path(f"{EFIVARS}/{name}-{LOADER_GUID}"), "rb") as handle:
            raw = handle.read(4096)
    except OSError:
        return None
    return raw[4:].decode("utf-16-le", "replace").strip("\x00 ") or None


# The firmware's FPDT table: when it launched the loader and when the loader
# left boot services, in ns since power-on. systemd reads firmware and loader
# times here when the boot manager publishes none; no permissions needed.
FPDT = "/sys/firmware/acpi/fpdt/boot"

# What systemd knows about the boot, in µs since the kernel started, over
# D-Bus, without permissions and with any boot loader.
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
    """What doesn't change during the session: mitigations and boot."""

    name = "system-security"
    provides = "system.vulnerabilities"
    static = True

    def collect(self, draft: Draft) -> None:
        draft.system = dataclasses.replace(
            draft.system, vulnerabilities=self._vulnerabilities(), boot=self._boot())

    @staticmethod
    def _vulnerabilities() -> tuple[Vulnerability, ...]:
        out = []
        for path in sorted(glob.glob(os.path.join(sysroot.path(VULNERABILITIES), "*"))):
            status = read_text(sysroot.unrooted(path))
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

        systemd = sysroot.recorded("systemd", "arranque", _systemd_times) or {}
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
            # Without an initrd, the kernel stage runs up to systemd.
            kernel_s=span(0, initrd or userspace) if userspace else None,
            initrd_s=span(initrd, userspace) if initrd else None,
            userspace_s=span(userspace, finish) if userspace and finish else None,
            cmdline=privacidad.hide_cmdline_identifiers(read_text("/proc/cmdline") or ""))


def read_swaps() -> tuple[Swap, ...]:
    """Each swap space in `/proc/swaps`, with zram's own details."""
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
        return os.path.exists(sysroot.path(MEMINFO))

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
            # Can change during the session: loading a module may taint it.
            tainted=(mask := read_int("/proc/sys/kernel/tainted")),
            tainting_modules=self._tainting_modules(mask),
        )
        draft.sensors.extend(self._sensors(draft.system))

    # -- internals ----------------------------------------------------------

    def _tainting_modules(self, mask: Optional[int]) -> tuple[tuple[str, str], ...]:
        """Which loaded modules tainted the kernel, and how.

        Reread only when the mask or the number of loaded modules changes,
        and skipped when no set bit is one a module can set.
        """
        if not mask or not mask & MODULE_TAINT_BITS:
            return ()
        try:
            loaded = len(os.listdir(sysroot.path("/sys/module")))
        except OSError:
            return ()
        key = (mask, loaded)
        if getattr(self, "_taint_key", None) != key:
            found = []
            for path in sorted(glob.glob(os.path.join(sysroot.path("/sys/module"), "*", "taint"))):
                if letters := read_text(sysroot.unrooted(path)):
                    found.append((os.path.basename(os.path.dirname(path)), letters))
            self._taint_key, self._taint_modules = key, tuple(found)
        return self._taint_modules

    @staticmethod
    def _processes() -> int:
        """How many processes there are, through `recorded`: a dump doesn't
        copy all of `/proc`, and counting its folders gave «Processes: 1»."""
        count = sysroot.recorded(
            "plataforma", "procesos", lambda: len(glob.glob("/proc/[0-9]*")))
        if count is None:                      # a dump older than this recording
            count = len(glob.glob(sysroot.path("/proc/[0-9]*")))
        return int(count)

    @staticmethod
    def _memory() -> Memory:
        values: dict[str, int] = {}
        try:
            with open(sysroot.path(MEMINFO), encoding="ascii") as handle:
                for line in handle:
                    key, _sep, rest = line.partition(":")
                    field = _MEM_FIELDS.get(key)
                    if field is None:
                        continue
                    # /proc/meminfo is in kibibytes, with rare exceptions.
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
        # reads two ways, this only one.
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
        """Memory use is a value worth tracking too."""
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
