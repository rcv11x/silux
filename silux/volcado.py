"""Dumps what this machine's providers read, for the test suite.

Run by `tools/volcar_equipo.py NAME`, which leaves it in
`tests/fixtures/equipos/NAME/`: a copy of what the Collector reads from
`/sys`, `/proc` and `/etc` (and nothing else), and in `grabado.json` what
doesn't come from a file: each core type's CPUID, the graphics ioctls, what
OpenGL and Vulkan answer, each mount's space, the addresses. With
`SILUX_SYSROOT` pointing there, the Collector gives this machine on any
other.

It only reads. No permissions, no helper: the dump is that of a machine
without permissions, which is how most people open it.

**The Collector itself decides what is copied**, not a list written here: it
runs for real while every file it opens, every folder it walks, every `stat`
and every link is noted. A hand list would go stale the day a provider read
a new file, and the dump would say the machine lacks it.

**What identifies someone is replaced** with what `privacidad.anonymize`
writes (the machine's name, addresses, serial numbers, interfaces named by
hand, mount points that aren't the system's, the user), and before the dump
is accepted two things are checked: that `privacidad.anonymize` finds
nothing more to cover in the snapshot it gives, and that none of this
machine's identifiers that `tools/comprobar_privacidad.py` looks for appears
in any byte. If anything fails, nothing is written.
"""

from __future__ import annotations

import builtins
import contextlib
import dataclasses
import errno
import getpass
import io
import itertools
import json
import os
import pathlib
import re
import shutil
import tempfile
import time
from typing import Optional

from . import privacidad, spd, sysroot
from .providers.sysfs_cpu import FREQUENCY_SOURCES

WATCHED_TREES = ("/sys/", "/proc/", "/etc/")
# A sysfs or procfs file larger than this isn't what's read to describe a
# machine; copying it would only bloat the repository.
MAX_BYTES = 512 * 1024
# Between a dump's two readings of its counters: the Collector's interval,
# which is what the tests' clock moves between two snapshots.
COUNTER_INTERVAL_S = 1.0
MANIFEST = "manifiesto.json"

# Files whose content identifies one specific part and says nothing about
# the model: replaced with zeros of the same length.
SERIAL_FILES = {"serial", "serial_number", "wwid", "vpd_pg80", "vpd_pg83",
            "unique_id", "product_uuid", "product_serial", "board_serial",
            "chassis_serial", "uuid", "eui", "nguid", "perm_addr"}
ADDRESS_FILES = {"address", "perm_address"}
# What a USB device writes about itself, which can name whose it is. Its
# vendor:product ids stay: they name the model, not the person.
USB_IDENTIFYING_FILES = {"product", "manufacturer"}
# Names that point to nobody: a hub's or a controller's.
USB_GENERIC = re.compile(r"hub|host controller|usb\s*receiver", re.I)
MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
EMAIL_SUBSTITUTE = "usuario@example.org"
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


# -- sleeping graphics cards ------------------------------------------------------

SYS_DRM = "/sys/class/drm"
SYS_PCI = "/sys/bus/pci/devices"

# What can be read from a sleeping card without waking it:
# - `power/runtime_status` and `power/control` are the PM core's and return
#   what the kernel already holds (`drivers/base/power/sysfs.c`;
#   `Documentation/ABI/testing/sysfs-devices-power`).
# - `power_state` is `pdev->current_state`, also held
#   (`drivers/pci/pci-sysfs.c`; `Documentation/ABI/testing/sysfs-bus-pci`,
#   since 5.11).
# - The identity: `pci_config_attr` (`drivers/pci/pci-sysfs.c`) prints the
#   `struct pci_dev` fields read when the bus was enumerated, without going
#   back to config space. `driver` is a link: it isn't opened.
# Everything else is taken as dangerous. The link (`current_link_*`) calls
# `pci_config_pm_runtime_get()` since 6.18 and takes the card out of D3cold;
# amdgpu's hwmon woke it before `amdgpu_pm_get_access_if_active()`; NVML,
# per NVIDIA's README (ch. 22, RTD3), makes it active when opened.
IDENTITY_FILES = ("vendor", "device", "subsystem_vendor", "subsystem_device",
             "revision", "class")
POWER_FILES = ("power/runtime_status", "power_state", "power/control")
NO_WAKE_FILES = IDENTITY_FILES + POWER_FILES
# `runtime_status` and `power_state` while the card sleeps.
SUSPENDED = ("suspended",)
POWERED_OFF = ("D3hot", "D3cold")

def _read(path) -> str | None:
    try:
        return pathlib.Path(sysroot.path(str(path))).read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _resolved(path) -> pathlib.Path:
    """The path without links, as the system would see it."""
    return pathlib.Path(sysroot.unrooted(pathlib.Path(sysroot.path(str(path))).resolve()))


def power_state(device) -> dict[str, str]:
    """A PCI device's power state. Doesn't wake it."""
    return {name: value for name in POWER_FILES
            if (value := _read(f"{device}/{name}")) is not None}


def is_asleep(state: dict[str, str]) -> bool:
    return (state.get("power/runtime_status") in SUSPENDED
            or state.get("power_state") in POWERED_OFF)


def gpu_devices() -> list[str]:
    """The graphics cards on the PCI bus (class 0x03), with a driver or not."""
    try:
        names = sorted(p.name for p in pathlib.Path(sysroot.path(SYS_PCI)).iterdir())
    except OSError:
        return []
    return [f"{SYS_PCI}/{n}" for n in names
            if (_read(f"{SYS_PCI}/{n}/class") or "").startswith("0x03")]


def bridge_chain(device) -> list[pathlib.Path]:
    """The bridges the device goes through to the root, without itself.

    The same walk as `providers.drm._pcie_chain`: up while the folder looks
    like a PCI address.
    """
    current = _resolved(device).parent
    links = []
    while re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", current.name):
        links.append(current)
        current = current.parent
    return links


# -- what the Collector reads --------------------------------------------------

def _watched(path) -> str | None:
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    # With a root set (the tests), the path is noted as the system would see
    # it: that's the one copied afterwards.
    text = sysroot.unrooted(text)
    return text if text.startswith(WATCHED_TREES) else None


# Where Python 3.10's pathlib keeps its own copy of these: it took them from
# os and io when imported (`_NormalAccessor`) and, unlike 3.11, does not look
# them up again. Patching os and io alone missed everything the providers
# read, list and look at with pathlib, and let it past the sleeping card's
# guard.
_VIA_PATHLIB = {"open": (io, builtins), "listdir": (os,), "scandir": (os,),
                "stat": (os,), "lstat": (os,), "readlink": (os,)}


def _with_pathlib(patches: dict) -> dict:
    """The same patches, also in 3.10's `_NormalAccessor`."""
    accessor = getattr(pathlib, "_NormalAccessor", None)
    if accessor is None:
        return patches
    every = dict(patches)
    for name, modules in _VIA_PATHLIB.items():
        function = next((patches[(m, name)] for m in modules if (m, name) in patches), None)
        if function is not None and name in vars(accessor):
            every[(accessor, name)] = staticmethod(function)
    return every


@contextlib.contextmanager
def _patching(patches: dict):
    """Put each function in place and leave everything as it was. From a
    class, what it really holds is kept (a `staticmethod`, a builtin), not
    what `getattr` gives."""
    def original(owner, name):
        return vars(owner)[name] if isinstance(owner, type) else getattr(owner, name)

    patches = _with_pathlib(patches)
    originals = {key: original(*key) for key in patches}
    try:
        for (owner, name), function in patches.items():
            setattr(owner, name, function)
        yield
    finally:
        for (owner, name), function in originals.items():
            setattr(owner, name, function)


@contextlib.contextmanager
def _noting():
    """Note what the Collector touches: files, folders, `stat` and links."""
    read_paths: set[str] = set()
    listed: set[str] = set()
    checked: set[str] = set()

    def note(bucket, function):
        def wrapped(path, *args, **kwargs):
            if (text := _watched(path)) is not None:
                bucket.add(text)
            return function(path, *args, **kwargs)
        return wrapped

    patches = {
        (builtins, "open"): note(read_paths, builtins.open),
        (io, "open"): note(read_paths, io.open),
        (os, "listdir"): note(listed, os.listdir),
        (os, "scandir"): note(listed, os.scandir),
        (os, "stat"): note(checked, os.stat),
        (os, "lstat"): note(checked, os.lstat),
        (os, "readlink"): note(checked, os.readlink),
    }
    with _patching(patches):
        yield read_paths, listed, checked


class _SleepingCards:
    """The cards the system has asleep, and what isn't touched on them.

    Dumping a laptop with its discrete card asleep must not wake it: an
    awake card would be recorded only because the tool woke it, which is
    exactly what the dump has to show. From each sleeping card only
    `NO_WAKE_FILES` is read; the same from the other functions of its slot
    (the HDMI audio sleeps with it) and from the bridges of its chain, which
    in D3cold have the slot unpowered. Nor are its `/dev/dri` nodes opened
    (the ioctls), nor NVML if it's an NVIDIA, nor the graphics APIs, which
    enumerate every card.
    """

    def __init__(self) -> None:
        self.states: dict[str, dict[str, str]] = {}
        self.asleep: list[str] = []
        self.nodes: list[str] = []
        self.dev: set[str] = set()
        self.nvidia = False
        for gpu in gpu_devices():
            state = power_state(gpu)
            slot = gpu.rsplit("/", 1)[1]
            self.states[slot] = state
            if not is_asleep(state):
                continue
            self.asleep.append(slot)
            real_path = _resolved(gpu)
            siblings = [f"{real_path.parent}/{h.name}"
                        for h in pathlib.Path(sysroot.path(str(real_path.parent))).iterdir()
                        if h.name.rsplit(".", 1)[0] == slot.rsplit(".", 1)[0]]
            self.nodes += siblings + [str(p) for p in bridge_chain(gpu)]
            drm = pathlib.Path(sysroot.path(f"{real_path}/drm"))
            if drm.is_dir():
                self.dev.update(f"/dev/dri/{n.name}" for n in drm.iterdir()
                                if n.name.startswith(("card", "renderD")))
            if _read(f"{gpu}/vendor") == "0x10de":
                self.nvidia = True
        # Longest first: the card hangs from its bridges.
        self.nodes = sorted(set(self.nodes), key=len, reverse=True)

    def __bool__(self) -> bool:
        return bool(self.asleep)

    def power_files(self) -> set[str]:
        """Each card's power files, asleep or not, for the dump."""
        return {f"{SYS_PCI}/{slot}/{name}"
                for slot, state in self.states.items() for name in state}

    def forbidden(self, path) -> bool:
        if not self:
            return False
        text = os.fspath(path)
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        text = sysroot.unrooted(text)
        if text in self.dev:
            return True
        if not text.startswith("/sys/"):
            return False
        real_path = sysroot.unrooted(os.path.realpath(sysroot.path(text)))
        for node in self.nodes:
            if real_path.startswith(node + "/"):
                return real_path[len(node) + 1:] not in NO_WAKE_FILES
        return False

    def not_recorded(self) -> list[str]:
        if not self:
            return []
        lines = [f"de las gráficas dormidas ({', '.join(self.asleep)}), todo menos "
                  "su identidad y su estado de energía, y lo mismo de las otras "
                  "funciones de su ranura y de sus puentes: leerlo las despierta",
                  "lo que contestan OpenGL, Vulkan, OpenCL y VA-API: enumeran todas "
                  "las tarjetas, también la dormida"]
        if self.nvidia:
            lines.append("NVML: abrirla despierta la NVIDIA dormida")
        return lines


@contextlib.contextmanager
def _without_waking(sleeping: _SleepingCards | None):
    """Keep the Collector from reading what wakes a sleeping card.

    What it's denied comes back as a file that doesn't exist, which is how
    it will see it reading the dump.
    """
    if not sleeping:
        yield
        return
    from silux import gpuapi, nvml

    def guard(function):
        def wrapped(path, *args, **kwargs):
            if sleeping.forbidden(path):
                raise FileNotFoundError(errno.ENOENT, "gráfica dormida: no se lee",
                                        os.fspath(path))
            return function(path, *args, **kwargs)
        return wrapped

    patches = {
        (builtins, "open"): guard(builtins.open),
        (io, "open"): guard(io.open),
        (os, "open"): guard(os.open),
        (gpuapi, "query"): lambda *a, **k: {},
    }
    if sleeping.nvidia:
        patches[(nvml.Nvml, "open")] = lambda self: False
    with _patching(patches):
        yield


# Read while dumping, but its answer is recorded (`system_deps.present`,
# under «paquetes»), so a dump never reads it back. On a distribution with
# many libraries it is a few hundred kilobytes: most of a report's annex.
RECORDED_ELSEWHERE = frozenset({"/etc/ld.so.cache"})
# Raw firmware tables, readable only by root: run as root, the Collector reads
# the SMBIOS table itself, and it carries every serial number of the machine
# and its modules (an ACPI table can carry a licence key). Parsed, what
# Silux shows of them leaves those out; raw, they never go into a dump.
NEVER_COPIED = ("/sys/firmware/dmi/tables/", "/sys/firmware/dmi/entries/",
                "/sys/firmware/acpi/tables/")


def never_copied(path: str) -> bool:
    return path in RECORDED_ELSEWHERE or path.startswith(NEVER_COPIED)


def _to_copy(read_paths: set[str], sleeping: _SleepingCards) -> set[str]:
    """What was read that goes into the dump. Copying is reading too: what's
    on a sleeping card doesn't even pass here."""
    return {path for path in read_paths
            if not never_copied(path) and not sleeping.forbidden(path)}


def _collect(sleeping: _SleepingCards | None = None):
    """Run the real Collector, noting and recording what it asks for."""
    from silux.collector import Collector

    sysroot.start_recording()
    with _noting() as (read_paths, listed, checked), _without_waking(sleeping):
        collector = Collector()
        try:
            collector.snapshot()
            collector.snapshot()
        finally:
            collector.close()
    return read_paths, listed, checked, sysroot.recorded_data()


def _alternatives(read_paths: set[str]) -> set[str]:
    """The other sources of a datum the provider read from the first.

    The one exception to the Collector deciding what's copied: for each
    thread's frequency it keeps the first source that answers and doesn't
    open the rest. Without them, the dump of a kernel that has
    `cpuinfo_avg_freq` can't show what one without it gives. The list is the
    provider's, not one written here.
    """
    return {os.path.join(os.path.dirname(path), source)
            for path in read_paths if os.path.basename(path) in FREQUENCY_SOURCES
            for source in FREQUENCY_SOURCES}


# What's copied from each awake card even if the Collector doesn't read it
# yet: without it the fixes for `xe`, the Arc cards and the counters can't be
# written.
#
# - With `xe`, the frequencies and idle state hang from the PCI node, not the
#   DRM one (`tile*/gt*/freq0/`, with its `throttle/`, and `gtidle/`), and
#   its hwmon has named channels (`pkg`, `vram`) not read today: the whole
#   hwmon.
# - From each bridge of its chain up to the root, the link and who it is: an
#   Arc carries a switch inside and the link that counts is the outer one.
# - From `/sys/bus/event_source/devices`, each PMU's type, format and
#   events: an Arc's on i915 and xe's events. None of it identifies anyone.
GPU_EXTRAS = ("tile*/gt*/freq0/*", "tile*/gt*/freq0/throttle/*",
                     "tile*/gt*/gtidle/*", "hwmon/hwmon*/*")
BRIDGE_EXTRAS = ("vendor", "device", "class", "current_link_speed",
                    "current_link_width", "max_link_speed", "max_link_width")
EVENT_SOURCE = "/sys/bus/event_source/devices"


def _gpu_extras() -> set[str]:
    """The paths of `GPU_EXTRAS`, of the bridges and of event_source."""
    import glob

    def existing(pattern: str) -> set[str]:
        return {sysroot.unrooted(c) for c in glob.glob(sysroot.path(pattern))
                if os.path.isfile(c)}

    paths: set[str] = set()
    for gpu in gpu_devices():
        if is_asleep(power_state(gpu)):
            continue
        real_path = str(_resolved(gpu))
        for pattern in GPU_EXTRAS:
            paths |= existing(f"{real_path}/{pattern}")
        for bridge in bridge_chain(gpu):
            for name in BRIDGE_EXTRAS:
                paths |= existing(f"{sysroot.unrooted(str(bridge))}/{name}")
    for pattern in ("*/type", "*/format/*", "*/events/*"):
        paths |= existing(f"{EVENT_SOURCE}/{pattern}")
    return paths


# -- copying --------------------------------------------------------------------

class _Copy:
    """Reproduce caminos del sistema dentro del volcado, con sus enlaces.

    Through `sysroot`: with a dump mounted, it dumps that one. That is how the
    dumper is tested on machines that are not this one, and on the dumps of
    the suite, whose values are already the substitutes.
    """

    def __init__(self, target: pathlib.Path):
        self.target = target
        self.unreadable: set[str] = set()
        # When each counter file was copied, for its second reading.
        self.counters: dict[str, float] = {}

    def _inside(self, path: str) -> pathlib.Path:
        return self.target / path.lstrip("/")

    def _link(self, path: str) -> None:
        inside = self._inside(path)
        if inside.is_symlink() or inside.exists():
            return
        try:
            target = os.readlink(sysroot.path(path))
        except OSError:
            # `/proc/1/exe` without permissions: left out, and whoever reads
            # it gets an error just as on the real machine.
            return
        inside.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, inside)

    def resolve(self, path: str) -> str | None:
        """Recreate each link of the path and return where it really is."""
        current = "/"
        for part in pathlib.PurePosixPath(path).parts[1:]:
            following = os.path.join(current, part)
            hops = 0
            while os.path.islink(sysroot.path(following)) and hops < 40:
                self._link(following)
                try:
                    target = os.readlink(sysroot.path(following))
                except OSError:
                    return None
                following = os.path.normpath(os.path.join(os.path.dirname(following), target))
                hops += 1
            if not os.path.lexists(sysroot.path(following)):
                return None
            if not following.startswith(WATCHED_TREES) and following not in ("/sys", "/proc", "/etc"):
                # A link leaving the system (`/proc/1/exe`): the link is enough.
                return None
            current = following
        return current

    def copy_file(self, path: str) -> None:
        real_path = self.resolve(path)
        if real_path is None:
            self._from_outside(path)
            return
        inside = self._inside(real_path)
        if os.path.isdir(sysroot.path(real_path)):
            inside.mkdir(parents=True, exist_ok=True)
            return
        if inside.exists():
            return
        inside.parent.mkdir(parents=True, exist_ok=True)
        try:
            if os.path.basename(real_path) == "eeprom":
                # An SPD chip may read only page by page: what read goes, up
                # to the first page that didn't, and those are recorded.
                pages, _error = spd.read_pages(sysroot.path(real_path))
                data = b"".join(itertools.takewhile(lambda page: page is not None, pages))
            else:
                with open(sysroot.path(real_path), "rb") as source:
                    data = source.read(MAX_BYTES)
        except PermissionError:
            # The file is left and noted: when the dump is mounted it loses
            # its permissions, so reading it fails the same way as here.
            inside.write_bytes(b"")
            self.unreadable.add(real_path)
            return
        except OSError:
            return
        inside.write_bytes(data)
        if sysroot.is_counter_file(real_path):
            self.counters[real_path] = time.monotonic()

    def second_reading(self, interval: float) -> dict[str, str]:
        """Each counter file read again `interval` after it was copied: the
        second snapshot of a mounted dump finds what a machine shows an
        interval later. Printable counters only."""
        readings = {}
        for real_path, copied in sorted(self.counters.items(), key=lambda item: item[1]):
            wait = copied + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                with open(sysroot.path(real_path), "rb") as source:
                    text = source.read(MAX_BYTES).decode("ascii")
            except (OSError, UnicodeDecodeError):
                continue
            if sysroot.is_counter_text(text):
                readings[real_path] = text
        return readings

    def _from_outside(self, path: str) -> None:
        """A link that leaves the dumped trees and ends in a file.

        `/etc/os-release` points to `../usr/lib/os-release`. Copying `/usr`
        makes no sense, so the file goes where the link was.
        """
        try:
            real_path = sysroot.unrooted(os.path.realpath(sysroot.path(path)))
        except OSError:
            # Python 3.10 lets out the error of reading an unreadable link
            # (`/proc/1/exe`); later versions swallow it.
            return
        if real_path.startswith(WATCHED_TREES) or not os.path.isfile(sysroot.path(real_path)):
            return
        try:
            with open(sysroot.path(real_path), "rb") as source:
                data = source.read(MAX_BYTES)
        except OSError:
            return
        inside = self._inside(path)
        if inside.is_symlink():
            inside.unlink()
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(data)

    def directory(self, path: str) -> None:
        real_path = self.resolve(path)
        if real_path is None or not os.path.isdir(sysroot.path(real_path)):
            return
        inside = self._inside(real_path)
        inside.mkdir(parents=True, exist_ok=True)
        try:
            entries = os.listdir(sysroot.path(real_path))
        except OSError:
            return
        for name in entries:
            child = os.path.join(real_path, name)
            if os.path.islink(sysroot.path(child)):
                self._link(child)
            elif os.path.isdir(sysroot.path(child)):
                (inside / name).mkdir(exist_ok=True)
            # Files of a walked folder that weren't read aren't copied: nobody
            # looks at them, and in /proc there would be thousands.


# -- anonymizing ----------------------------------------------------------------

def _text_of(path: pathlib.Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _edid_serial_text(data: bytes) -> str | None:
    """The serial number a display writes in its 0xFF descriptor, if any."""
    for start in range(54, 126, 18):
        chunk = data[start:start + 18]
        if len(chunk) == 18 and chunk[:3] == b"\x00\x00\x00" and chunk[3] == 0xFF:
            text = chunk[5:].split(b"\n", 1)[0].decode("ascii", "replace").strip()
            return text if len(text) >= 4 else None
    return None


def _edid_without_serial(data: bytes) -> bytes:
    """The EDID with its serial number zeroed and its checksum updated."""
    if len(data) < 128 or data[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return data
    block = bytearray(data[:128])
    block[12:16] = b"\x00\x00\x00\x00"
    for start in range(54, 126, 18):
        if block[start:start + 3] == b"\x00\x00\x00" and block[start + 3] == 0xFF:
            block[start + 5:start + 18] = b"0" * 13
    block[127] = (-sum(block[:127])) % 256
    return bytes(block) + data[128:]


# Where the SPD keeps the module's serial number, by memory type (byte 2):
# DDR2, DDR3, DDR4 and DDR5. silux doesn't decode it, so neither the snapshot
# nor the checker would see it: it's erased here, by position. DDR4's and
# DDR5's checksums end before it; DDR3's covers it only when byte 0's top bit
# is clear, and silux doesn't check that one.
SPD_SERIAL = {0x08: (95, 99), 0x0B: (122, 126), 0x0C: (325, 329), 0x12: (517, 521)}


def _spd_without_serial(data: bytes) -> tuple[bytes, bytes]:
    """The SPD with its serial number zeroed, and the number taken out."""
    if len(data) < 3 or data[2] not in SPD_SERIAL:
        return data, b""
    start, end = SPD_SERIAL[data[2]]
    if len(data) < end:
        return data, b""
    return data[:start] + bytes(end - start) + data[end:], data[start:end]


# NVML's throttle reasons as 0.4-prueba7 and earlier recorded them, written
# in Spanish, and the key each is now.
OLD_NVML_REASONS = {
    "en reposo": "gpu.throttle.nv.idle",
    "relojes fijados por la aplicación": "gpu.throttle.nv.appclocks",
    "límite de potencia del driver": "gpu.throttle.nv.swpower",
    "protección del hardware": "gpu.throttle.nv.hwslowdown",
    "sincronización entre tarjetas": "gpu.throttle.nv.sync",
    "temperatura (driver)": "gpu.throttle.nv.swthermal",
    "temperatura (hardware)": "gpu.throttle.nv.hwthermal",
    "freno de potencia del hardware": "gpu.throttle.nv.hwpower",
    "relojes fijados por la pantalla": "gpu.throttle.nv.display",
}


def _nvml_reasons_as_keys(folder: pathlib.Path) -> None:
    """The recorded NVML cards' throttle reasons, as keys."""
    recording = folder / "grabado.json"
    if not recording.is_file():
        return
    data = json.loads(recording.read_text(encoding="utf-8"))
    cards = (data.get("nvml") or {}).get("tarjetas") or []
    changed = False
    for card in cards:
        reasons = card.get("throttle_reasons") or []
        keys = [OLD_NVML_REASONS.get(r, r) for r in reasons]
        if keys != reasons:
            card["throttle_reasons"] = keys
            changed = True
    if changed:
        recording.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")


def bring_up_to_date(folder: pathlib.Path) -> None:
    """Do to a dump already written what the dumper does today, for an annex
    made by an older version: zero the serial numbers it erases by position,
    which the privacy check can't see (they're bytes, not text), drop what is
    recorded elsewhere, and turn texts it recorded into today's keys."""
    for path in RECORDED_ELSEWHERE:
        (folder / path.lstrip("/")).unlink(missing_ok=True)
    for prefix in NEVER_COPIED:
        shutil.rmtree(folder / prefix.strip("/"), ignore_errors=True)
    _nvml_reasons_as_keys(folder)
    for top, _dirs, files in os.walk(folder):
        for name in files:
            path = pathlib.Path(top) / name
            if path.is_symlink():
                continue
            if name == "eeprom":
                path.write_bytes(_spd_without_serial(path.read_bytes())[0])
            elif name == "edid":
                path.write_bytes(_edid_without_serial(path.read_bytes()))
            elif name == "id" and "/ata_device/" in path.as_posix():
                path.write_text(_identify_without_serial(path.read_text(errors="replace"))[0])


# The interfaces a tool creates in series: Docker, a bridge per network and a
# `veth` per running container. They say how much runs on the machine and add
# nothing to the dump: one of each family stays.
IN_SERIES = (re.compile(r"br-[0-9a-f]{12}"), re.compile(r"veth[0-9a-f]+"))


# An ATA IDENTIFY's words that identify the piece: serial number, WWN and
# media serial number.
IDENTIFY_SERIAL = (*range(10, 20), *range(108, 112), *range(176, 206))


def _identify_without_serial(text: str) -> tuple[str, str]:
    """`ata_device/*/id` with its serial words at zero, and the serial.

    The model stays: it is what says the unit of the disk's counters.
    """
    try:
        words = [int(p, 16) for p in text.split()]
    except ValueError:
        return re.sub(r"[0-9a-fA-F]", "0", text), ""
    serial = b"".join(words[i].to_bytes(2, "big") for i in range(10, 20)
                     if i < len(words)).decode("ascii", "replace").strip()
    for i in IDENTIFY_SERIAL:
        if i < len(words):
            words[i] = 0
    lines = [" ".join(f"{p:04x}" for p in words[i:i + 8]) for i in range(0, len(words), 8)]
    return "\n".join(lines) + "\n", serial


def _cards_without_names(text: str) -> str:
    """`/proc/asound/cards` without the USB sound devices' names.

    Each card is two lines. Of the USB ones, that they are USB and where they
    hang stays, and their name goes; the board's and the graphics card's stay
    as they are, identifying nobody.
    """
    lines = text.splitlines()
    out = []
    for first, second in zip(lines[::2], lines[1::2]):
        if "USB-Audio" in first:
            first = first.split("USB-Audio", 1)[0] + "USB-Audio - "
            second = re.sub(r"^(\s*).*?( at usb-)", r"\1Audio USB\2", second)
        out += [first, second]
    return "\n".join(out) + "\n"


def _extra_in_series(names) -> set[str]:
    """Of each family of interfaces in series, all but the first."""
    names = list(names)
    extra: set[str] = set()
    for pattern in IN_SERIES:
        extra.update(sorted(n for n in names if pattern.fullmatch(n))[1:])
    return extra


def _ipv4_hex(ip: str) -> str:
    """An address as /proc/net/route writes it: hexadecimal, reversed."""
    return "".join(f"{int(x):02X}" for x in reversed(ip.split(".")))


# What the dumper itself writes in place of something, as it writes it: the
# router and its network in /proc/net/route, the IPv6 in if_inet6.
HEX_SUBSTITUTES = frozenset(s.lower() for s in (
    _ipv4_hex(privacidad.GATEWAY), _ipv4_hex(privacidad.GATEWAY.rsplit(".", 1)[0] + ".0"),
    "20010db8" + "0" * 20 + "0011", EMAIL_SUBSTITUTE))


# What kind of thing each looked-for value is: the annex says it in words
# (`render.annex_what`), never the value.
QUE = {
    "email": "una dirección de correo", "serial": "un número de serie",
    "disk_serial": "el número de serie de un disco",
    "monitor_serial": "el número de serie de un monitor",
    "memory_serial": "el número de serie de un módulo de memoria",
    "mac": "una dirección física de red", "usb": "el nombre de algo enchufado por USB",
    "camera": "el nombre de una cámara", "router": "la dirección del router",
    "ip": "una dirección IP de este equipo", "ipv6": "una dirección IPv6 de este equipo",
    "gpu_id": "el identificador de una gráfica", "interface": "el nombre de una conexión de red",
    "machine": "un dato de este equipo",
}


class _Anonymizer:
    def __init__(self, target: pathlib.Path, recording: dict):
        self.target = target
        self.recording = recording
        # What was taken out, by kind (`SECRET_KINDS`), to look for it at the end.
        self.secrets: dict[str, str] = {}
        # What was taken out of a binary file, not looked for as text.
        self.raw_secrets: dict[bytes, str] = {}
        name = pathlib.Path(sysroot.path("/proc/sys/kernel/hostname"))
        self.host = name.read_text().strip() if name.is_file() else ""
        # A machine named as everyone's (the distribution, the brand): it is
        # neither replaced in the texts nor looked for.
        if privacidad.is_common_host_name(self.host, privacidad.machine_words(str(target))):
            self.host = ""
        self.user = getpass.getuser()
        self.home = str(pathlib.Path.home())
        self.interfaces = self._interfaces()
        # Numbered once the interfaces in series are gone (`clean_contents`),
        # as the snapshot read back lists them.
        self.macs: dict[str, str] = {}
        # The name someone gave an interface is theirs: besides replacing it
        # where it's known to appear, it's looked for in every byte at the end.
        for old in self.interfaces:
            self._secret(old, "mac" if privacidad.MAC_IN_NAME.fullmatch(old)
                          else "interface")
        self.mounts: dict[str, str] = {}

    def _secret(self, value: Optional[str], kind: str) -> None:
        """What was taken out, to look for later in every byte. Not what's a
        substitute: a real gateway can be 192.168.1.1, and finding it at the
        end was finding the substitute."""
        value = (value or "").strip()
        if len(value) >= 4 and not privacidad.is_substitute(value) \
                and value.lower() not in HEX_SUBSTITUTES:
            self.secrets.setdefault(value, kind)

    def _interfaces(self) -> dict[str, str]:
        names = {}
        net_dir = self.target / "sys" / "class" / "net"
        entries = sorted(e.name for e in net_dir.iterdir()) if net_dir.is_dir() else []
        for entry in entries:
            if not privacidad.is_system_name(entry):
                names[entry] = privacidad.INTERFACE.format(len(names) + 1)
        # A USB adapter's name carries its MAC: the same substitute the report
        # gives it, in the same order.
        with_mac = [e for e in entries if privacidad.MAC_IN_NAME.fullmatch(e)]
        for index, entry in enumerate(with_mac):
            if (new := privacidad.name_without_mac(entry, index)) != entry:
                names[entry] = new
        return names

    def _macs(self) -> dict[str, str]:
        """Each interface's real address and its substitute, numbered as the
        report numbers them: by interface name, one per distinct address.
        Any other address found in the files takes the next number."""
        macs: dict[str, str] = {}
        net_dir = self.target / "sys" / "class" / "net"
        entries = sorted(e.name for e in net_dir.iterdir()) if net_dir.is_dir() else []
        for entry in entries:
            path = net_dir / entry / "address"
            real = path.read_text(errors="replace").strip().lower() if path.is_file() else ""
            if MAC.fullmatch(real) and real != privacidad.NO_MAC:
                macs.setdefault(real, privacidad.fake_mac(len(macs)))
        return macs

    def _mac(self, real: str) -> str:
        if real in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
            return real
        return self.macs.setdefault(real.lower(), privacidad.fake_mac(len(self.macs)))

    def drop_serial_interfaces(self) -> int:
        """Remove the surplus interfaces in series and say how many there were.

        From everywhere: their folder, their link, their lines in the
        `/proc/net` tables and what was recorded of them.
        """
        net_dir = self.target / "sys" / "class" / "net"
        if not net_dir.is_dir():
            return 0
        extra = _extra_in_series(e.name for e in net_dir.iterdir())
        for name in extra:
            link = net_dir / name
            folder = link.resolve()
            if link.is_symlink():
                link.unlink()
            if folder.is_dir() and self.target in folder.parents:
                shutil.rmtree(folder)
        for table in ("route", "if_inet6"):
            for path in (self.target / "proc").glob(f"*/net/{table}"):
                if path.is_symlink() or not path.is_file():
                    continue
                lines = path.read_text().splitlines()
                path.write_text("".join(
                    line + "\n" for line in lines if not extra.intersection(line.split())))
        addresses = self.recording.get("ioctl_red")
        if isinstance(addresses, dict):
            for key in [c for c in addresses if c.partition(":")[0] in extra]:
                del addresses[key]
        return len(extra)

    def _replace_text(self, text: str) -> str:
        for old, new in self.interfaces.items():
            text = re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w.-])", new, text)
        text = privacidad._without_host(text, self.host) or text
        text = text.replace(self.home, "/home/usuario")
        if len(self.user) >= 3:
            text = re.sub(rf"(?<![\w.-]){re.escape(self.user)}(?![\w.-])", "usuario", text)
        text = MAC.sub(lambda m: self._mac(m.group(0)), text)
        text = UUID.sub("00000000-0000-0000-0000-000000000000", text)
        # An address, wherever it is: /proc/version names whoever built the
        # kernel, and a kernel compiled at home names its owner. The same
        # rule as the checker that runs before publishing.
        def email(m: re.Match) -> str:
            if privacidad.ALLOWED_EMAILS.search(m.group()):
                return m.group()
            self._secret(m.group(), "email")
            return EMAIL_SUBSTITUTE
        return privacidad.EMAIL.sub(email, text)

    def _mount(self, mount_point: str) -> str:
        if mount_point in privacidad._SYSTEM_MOUNTS:
            return mount_point
        return self.mounts.setdefault(mount_point, privacidad.MOUNT.format(len(self.mounts) + 1))

    def clean_contents(self) -> None:
        self.macs = self._macs()
        models = {(_text_of(m) or "").strip().lower() for m in self.target.rglob("model")
                   if m.is_file() and not m.is_symlink()}
        for path in sorted(self.target.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            name = path.name
            relative = "/" + str(path.relative_to(self.target))
            data = path.read_bytes()
            if name in SERIAL_FILES and data.strip():
                self._secret(data.strip().decode(errors="replace"), "serial")
                path.write_bytes(re.sub(rb"[^\n\x00]", b"0", data))
                continue
            if name == "id" and "/ata_device/" in relative:
                clean, serial = _identify_without_serial(data.decode(errors="replace"))
                if serial:
                    self._secret(serial, "disk_serial")
                path.write_text(clean)
                continue
            if name == "edid":
                # Its number is covered where it is, and looked for anywhere
                # else. Zero and 01 01 01 01 are the EDID's «no number»: the
                # second is in every EDID's unused standard timings, and as a
                # secret it took a TV's whole EDID out of the annex.
                if len(data) >= 16 and data[12:16] not in (bytes(4), b"\x01" * 4):
                    self.raw_secrets[data[12:16]] = "monitor_serial"
                if text := _edid_serial_text(data):
                    self._secret(text, "monitor_serial")
                path.write_bytes(_edid_without_serial(data))
                continue
            if name == "eeprom":
                clean, serial = _spd_without_serial(data)
                if any(serial):
                    self.raw_secrets[serial] = "memory_serial"
                path.write_bytes(clean)
                continue
            if name in ADDRESS_FILES and "/net/" in relative:
                if data.strip() and data.strip() not in (b"00:00:00:00:00:00",):
                    real = data.strip().decode(errors="replace")
                    self._secret(real, "mac")
                    path.write_text((self._mac(real) if MAC.fullmatch(real)
                                     else privacidad.MAC) + "\n")
                continue
            # What's plugged in. Someone's inventory points to them too: a
            # security key, a specific microphone. Of USB, the vendor:product
            # ids, the class, the speed and what hangs from what stay; the
            # names the device writes go, and with them the Bluetooth
            # adapter's name, from the same file. The file is deleted rather
            # than filled: the provider must read «nothing». Its serial is
            # zeroed with every other serial (`SERIAL_FILES`).
            # The maker goes too, but is not looked for afterwards: it is a
            # company, and «Realtek» or «Generic» are also the sound codec,
            # the PHY or the HDA card.
            if name in USB_IDENTIFYING_FILES and re.search(r"/usb\d+/", relative):
                usb_text = data.decode(errors="replace").strip()
                # A USB stick's name is also its disk's model, which the dump
                # keeps as any disk's (and the report shows): not looked for.
                if name == "product" and len(usb_text) >= 6 \
                        and not USB_GENERIC.search(usb_text) \
                        and usb_text.lower() not in models:
                    self._secret(usb_text, "usb")
                path.unlink()
                continue
            if relative.startswith("/sys/") and "/video4linux/" in relative and name == "name":
                if len(data.strip()) >= 6:
                    self._secret(data.decode(errors="replace").strip().split(":")[0], "camera")
                path.unlink()
                continue
            if relative == "/proc/asound/cards":
                path.write_text(_cards_without_names(data.decode(errors="replace")))
                continue
            if relative == "/proc/sys/kernel/hostname":
                path.write_text(privacidad.HOST_NAME + "\n")
                continue
            if relative == "/proc/cmdline":
                # The disks' UUIDs, an encrypted volume, the machine's name.
                path.write_text(" ".join(privacidad.hide_cmdline_identifiers(
                    data.decode(errors="replace"))) + "\n")
                continue
            # /proc/net is a link to self/net: the real file ends up in
            # /proc/<pid>/net/, so it's recognized by how it ends.
            if relative.startswith("/proc/") and relative.endswith("/net/route"):
                path.write_text(self._replace_text(self._network_path(data.decode())))
                continue
            if relative.startswith("/proc/") and relative.endswith("/net/if_inet6"):
                path.write_text(self._replace_text(self._ipv6(data.decode())))
                continue
            if relative.startswith("/proc/") and relative.endswith("/mounts"):
                path.write_text(self._replace_text(self._mounts(data.decode())))
                continue
            text = _text_of(path)
            if text is not None:
                changed = self._replace_text(text)
                if changed != text:
                    path.write_text(changed)

    def _network_path(self, text: str) -> str:
        lines = text.splitlines()
        out = lines[:1]
        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) > 2:
                if fields[1] != "00000000":
                    fields[1] = _ipv4_hex(privacidad.GATEWAY.rsplit(".", 1)[0] + ".0")
                if fields[2] != "00000000":
                    self._secret(fields[2], "router")
                    fields[2] = _ipv4_hex(privacidad.GATEWAY)
            out.append("\t".join(fields))
        return "\n".join(out) + "\n"

    def _ipv6(self, text: str) -> str:
        # privacidad.IPV6, 2001:db8::11, in the 32 digits of /proc/net/if_inet6.
        substitute = "20010db8" + "0" * 20 + "0011"
        out = []
        for line in text.splitlines():
            fields = line.split()
            if fields and fields[0] != "0" * 31 + "1":
                self._secret(fields[0], "ipv6")
                line = line.replace(fields[0], substitute, 1)
            out.append(line)
        return "\n".join(out) + "\n"

    def _mounts(self, text: str) -> str:
        """The disks' mounts, with the mount points someone set covered.

        Only a device's lines stay, the ones the provider reads. The rest
        describe the session, not the machine: the open AppImage, the
        containers, the user's folder.
        """
        out = []
        for line in text.splitlines():
            fields = line.split(" ")
            if not fields[0].startswith("/dev/"):
                continue
            if len(fields) > 1:
                mount_point = fields[1].replace("\\040", " ")
                new = self._mount(mount_point)
                if new != mount_point:
                    fields[1] = new
            out.append(" ".join(fields))
        return "\n".join(out) + "\n"

    def rename_interfaces(self) -> None:
        """The interfaces with names of their own, also in folders and links."""
        if not self.interfaces:
            return
        for path in sorted(self.target.rglob("*"), key=lambda r: -len(r.parts)):
            if path.is_symlink():
                target = os.readlink(path)
                new = self._replace_text(target)
                if new != target:
                    path.unlink()
                    os.symlink(new, path)
            if path.name in self.interfaces:
                path.rename(path.with_name(self.interfaces[path.name]))

    def clean_recording(self) -> dict:
        # NVML's UUID («GPU-» and a UUID) names the card. The rule for UUIDs
        # zeroed the UUID and left «GPU-», which anonymize still covered. It
        # goes as anonymize leaves it, and the real one is looked for in
        # every byte.
        for card in (self.recording.get("nvml") or {}).get("tarjetas") or ():
            if isinstance(card, dict) and card.get("uuid"):
                self._secret(card["uuid"], "gpu_id")
                self._secret(card["uuid"].removeprefix("GPU-"), "gpu_id")
        # Mount points are numbered by their real path, as in /proc/mounts:
        # covered first, a path holding the user's name became another one.
        mounted_points = {space: {self._mount(p): v for p, v in (self.recording.get(space) or {}).items()}
                          for space in ("statvfs", "statfs")}
        clean = json.loads(self._replace_text(json.dumps(self.recording, ensure_ascii=False)))
        for card in (clean.get("nvml") or {}).get("tarjetas") or ():
            if isinstance(card, dict) and card.get("uuid"):
                card["uuid"] = privacidad._mask(card["uuid"])
        for key in list(clean.get("ioctl_red", {})):
            value = clean["ioctl_red"][key]
            name, _sep, code = key.partition(":")
            if value and code == "0x8915" and not value.startswith("127."):
                self._secret(value, "ip")
                clean["ioctl_red"][key] = privacidad.IPV4
        for space, points in mounted_points.items():
            if space in clean:
                clean[space] = points
        env = clean.get("plataforma", {}).get("uname")
        if isinstance(env, dict) and env.get("node"):
            env["node"] = privacidad.HOST_NAME
        return clean


# -- checking -------------------------------------------------------------------

# Looked for as a word and not inside another: a machine's or a
# connection's name is part of driver names (a «thinkpad» in thinkpad_hwmon),
# and an IP is the start of a longer one. A serial number is looked for
# anywhere.
AS_WORD = frozenset({"machine_name", "interface", "usb", "ip"})
_AROUND = rb"[A-Za-z0-9_.-]"


def _own_class(description: str) -> str:
    """The kind of one of `privacidad.of_this_machine`'s identifiers."""
    if description == "el nombre de este equipo":
        return "machine_name"
    if "interfaz" in description:
        return "interface"
    if "IPv4" in description:
        return "ip"
    return "machine"


def found_in(target: pathlib.Path, secrets, raw_secrets=(),
                own: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Where something of this machine is in the dump: (path, kind), the
    kinds of `SECRET_KINDS`. Empty if nothing.

    `secrets` and `raw_secrets`, what the dumper took away (a dict by kind,
    or any collection); `own`, what identifies this machine, without which
    `privacidad.of_this_machine`'s. A substitute is never looked for.
    """
    if own is None:
        own = privacidad.of_this_machine()
    by_kind = lambda group, kind: (group.items() if isinstance(group, dict)
                                      else ((g, kind) for g in group))
    wanted: list[tuple[bytes, str]] = []
    for value, kind in [*((d, _own_class(q)) for d, q in own.items()),
                         *by_kind(secrets, "machine")]:
        if value and len(value) >= 4 and not privacidad.is_substitute(value):
            wanted.append((value.encode(), kind))
    wanted += [(c, kind) for c, kind in by_kind(raw_secrets, "serial") if any(c)]
    patterns = [(re.compile(rb"(?<!" + _AROUND + rb")" + re.escape(b) + rb"(?!" + _AROUND + rb")")
                 if kind in AS_WORD else None, b, kind) for b, kind in wanted]
    findings = []
    for path in sorted(target.rglob("*")):
        if path.is_symlink():
            content = os.readlink(path).encode()
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b""
        relative = str(path.relative_to(target))
        for pattern, raw, kind in patterns:
            for where in (content, relative.encode()):
                if (pattern.search(where) if pattern is not None else raw in where):
                    findings.append((relative, kind, pattern or raw))
                    break
    return findings


def check(target: pathlib.Path, secrets, raw_secrets=(),
              own: dict[str, str] | None = None) -> list[str]:
    """What gives this machine away in the dump, in words. Empty if nothing."""
    return [f"{path}: {QUE.get(kind, kind)}"
            for path, kind, _wanted in found_in(target, secrets, raw_secrets, own)]


class Refusal(SystemExit):
    """Nothing is written: anonymize would still cover these fields of the
    snapshot. Named by position («gpus[1].unique_id»), never by value, with
    the dump's files that hold each one (`files`)."""

    def __init__(self, fields: list[str], files: dict[str, list[str]] | None = None):
        self.fields = list(fields)
        self.files = dict(files or {})
        where = sorted({path for paths in self.files.values() for path in paths})
        super().__init__("anonimizar todavía encuentra qué tapar: "
                         + "; ".join(self.fields[:10])
                         + (f" (en {', '.join(where[:5])})" if where else "")
                         + ". No se escribe nada.")


_FIELD_STEP = re.compile(r"\.?([A-Za-z_]\w*)|\[(\d+)\]")


def _value_at(snapshot, field: str):
    """The value at a field path («disks[5].serial»), or None."""
    value = snapshot
    for name, index in _FIELD_STEP.findall(field):
        try:
            value = value[int(index)] if index else getattr(value, name)
        except (AttributeError, IndexError, TypeError):
            return None
    return value


def _where_in_dump(work: pathlib.Path, snapshot, fields: list[str]) -> dict[str, list[str]]:
    """The dump's files that hold each field's value, with the value covered
    if it is in the path itself: where to look next time, never what it was.
    Values shorter than four characters would be found everywhere."""
    contents = {"/" + str(path.relative_to(work)): path.read_bytes()
                for path in sorted(work.rglob("*")) if path.is_file() and not path.is_symlink()}
    where: dict[str, list[str]] = {}
    for field in fields:
        value = _value_at(snapshot, field)
        wanted = [v.encode() for v in (value if isinstance(value, tuple) else (value,))
                  if isinstance(v, str) and len(v) >= 4]
        found = []
        for path, content in contents.items():
            hit = next((w for w in wanted if w in content or w in path.encode()), None)
            if hit is not None:
                found.append(_covered(path, hit))
            if len(found) == 3:
                break
        if found:
            where[field] = found
    return where


def _contains(wanted, text: str) -> bool:
    data = text.encode()
    return bool(wanted.search(data)) if isinstance(wanted, re.Pattern) else wanted in data


def _json_without(datum, wanted, path: str = "") -> tuple[object, list[str]]:
    """The JSON without what holds `wanted`: a string goes to None, a key or
    a list item goes. And where it was, as a path of keys."""
    if isinstance(datum, dict):
        out, removed = {}, []
        for key, value in datum.items():
            key_path = f"{path}.{key}" if path else str(key)
            if _contains(wanted, str(key)):
                removed.append(key_path)
                continue
            out[key], inside = _json_without(value, wanted, key_path)
            removed += inside
        return out, removed
    if isinstance(datum, list):
        out, removed = [], []
        for i, value in enumerate(datum):
            if isinstance(value, str) and _contains(wanted, value):
                removed.append(f"{path}[{i}]")
                continue
            clean, inside = _json_without(value, wanted, f"{path}[{i}]")
            out.append(clean)
            removed += inside
        return out, removed
    if isinstance(datum, str) and _contains(wanted, datum):
        return None, [path]
    return datum, []


def _covered(text: str, wanted) -> str:
    """The path as the annex says it, with what was found covered: it can
    be in the name of a folder (it was, on the CI's machine)."""
    data = text.encode()
    data = (wanted.sub(b"\xe2\x80\xa6", data) if isinstance(wanted, re.Pattern)
             else data.replace(wanted, "…".encode()))
    return data.decode(errors="replace")


def _without_found(work: pathlib.Path, findings) -> list[dict]:
    """Takes away what could not be covered safely, instead of writing
    nothing: the file, or in the two JSON files the answer that holds it.
    Says what each was, by kind, and where, with it covered."""
    removed: list[dict] = []
    for relative, kind, wanted in findings:
        path = work / relative
        if relative in (sysroot.RECORDING_FILE, MANIFEST) and path.is_file():
            clean, paths = _json_without(json.loads(path.read_text()), wanted)
            path.write_text(json.dumps(clean, ensure_ascii=False, indent=1,
                                       sort_keys=relative == sysroot.RECORDING_FILE) + "\n")
            removed += [{"ruta": _covered(f"{relative}: {c}", wanted), "dato": kind}
                         for c in paths]
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            continue
        removed.append({"ruta": _covered("/" + relative, wanted), "dato": kind})
    return removed


def _second_reading_of_what_is_left(work: pathlib.Path) -> None:
    """The second reading of the files the dump still has, and no other."""
    path = work / sysroot.RECORDING_FILE
    recording = json.loads(path.read_text())
    readings = recording.get(sysroot.SECOND_READING)
    if not isinstance(readings, dict):
        return
    kept = {location: text for location, text in readings.items()
            if (work / location.lstrip("/")).is_file()}
    if kept != readings:
        recording[sysroot.SECOND_READING] = kept
        path.write_text(json.dumps(recording, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


@contextlib.contextmanager
def mounted(folder: pathlib.Path):
    """The dump ready to read: a copy with the unreadable files unreadable."""
    with tempfile.TemporaryDirectory(prefix="silux-equipo-") as tmp:
        copy = pathlib.Path(tmp) / "raiz"
        shutil.copytree(folder, copy, symlinks=True)
        manifest = json.loads((copy / MANIFEST).read_text())
        for empty_dir in manifest.get("vacios", []):
            (copy / empty_dir.lstrip("/")).mkdir(parents=True, exist_ok=True)
        for unreadable_path in manifest.get("ilegibles", []):
            path = copy / unreadable_path.lstrip("/")
            if path.exists():
                path.chmod(0)
        previous = os.environ.get(sysroot.VARIABLE)
        os.environ[sysroot.VARIABLE] = str(copy)
        sysroot.forget()
        try:
            yield copy
        finally:
            for unreadable_path in manifest.get("ilegibles", []):
                path = copy / unreadable_path.lstrip("/")
                if path.exists():
                    path.chmod(0o600)
            if previous is None:
                os.environ.pop(sysroot.VARIABLE, None)
            else:
                os.environ[sysroot.VARIABLE] = previous
            sysroot.forget()


def snapshot_of(folder: pathlib.Path):
    """The snapshot the Collector gives reading the dump."""
    from silux.collector import Collector

    with mounted(folder):
        collector = Collector()
        try:
            collector.snapshot()
            return collector.snapshot()
        finally:
            collector.close()


# -- main -----------------------------------------------------------------------

def dump(name: str, base: pathlib.Path,
           own: dict[str, str] | None = None) -> pathlib.Path:
    target = base / name
    if target.exists():
        raise SystemExit(f"ya existe {target}: bórralo antes para volcar otra vez")

    # First, before anything wakes it: how each card is.
    sleeping = _SleepingCards()
    read_paths, listed, checked, recording = _collect(sleeping)
    read_paths |= _alternatives(read_paths) | sleeping.power_files() | _gpu_extras()
    read_paths = _to_copy(read_paths, sleeping)
    checked = {c for c in checked if not sleeping.forbidden(c) and not never_copied(c)}
    with tempfile.TemporaryDirectory(prefix="silux-volcado-") as tmp:
        work = pathlib.Path(tmp) / name
        work.mkdir()
        copy = _Copy(work)
        for path in sorted(listed):
            copy.directory(path)
        for path in sorted(read_paths):
            copy.copy_file(path)
        for path in sorted(checked - read_paths - listed):
            # An `exists()` or `is_dir()` that said yes: let it keep saying so.
            if os.path.lexists(sysroot.path(path)):
                (copy.directory(path) if os.path.isdir(sysroot.path(path))
                 else copy.copy_file(path))

        # The counters again, an interval later: usage, rates and rests come
        # from the difference, and one reading has none.
        recording[sysroot.SECOND_READING] = copy.second_reading(COUNTER_INTERVAL_S)

        clean = _Anonymizer(work, recording)
        dropped = clean.drop_serial_interfaces()
        clean.clean_contents()
        clean.rename_interfaces()
        (work / sysroot.RECORDING_FILE).write_text(
            json.dumps(clean.clean_recording(), ensure_ascii=False, indent=1, sort_keys=True)
            + "\n")
        # Of what was left out (the interfaces in series), nothing goes.
        _second_reading_of_what_is_left(work)

        # Git doesn't keep empty folders, and some count: /proc's processes,
        # or a /sys/firmware/efi only checked for existence. They're noted and
        # recreated when mounting.
        empty_dirs = sorted("/" + str(d.relative_to(work)) for d in work.rglob("*")
                        if d.is_dir() and not d.is_symlink() and not any(d.iterdir()))
        (work / MANIFEST).write_text(json.dumps({
            "herramienta": 1,
            "vacios": empty_dirs,
            "ilegibles": sorted(clean._replace_text(c) for c in copy.unreadable),
            # How each card was before anything was read, by its slot.
            "energia_de_las_graficas": sleeping.states,
            "sin_grabar": [
                "de NVML, el número de serie de cada tarjeta",
                "todo lo que lee el ayudante privilegiado",
                "el consumo (RAPL): su contador de energía solo lo lee root, y el "
                "volcado guarda lo que se lee sin permisos",
                "de lo enchufado por USB: la marca y el modelo que escribe el propio "
                "aparato, y su número de serie; y el nombre de las cámaras y de las "
                "tarjetas de sonido USB. Quedan sus identificadores (vendor:product), "
                "la clase, la velocidad y de qué cuelga cada cosa",
                "las variables del cargador de arranque que no se leen "
                "(LoaderDevicePartUUID, LoaderSystemToken)",
            ] + sleeping.not_recorded() + ([f"{dropped} interfaces de red en serie (puentes de Docker y "
                  "veth): queda una de cada"] if dropped else []),
        }, ensure_ascii=False, indent=1) + "\n")

        # What wasn't covered goes, file by file, and the annex says so: a
        # dump missing a file is still a dump, and with nothing written there
        # would be no annex at all.
        def findings():
            return found_in(work, clean.secrets, clean.raw_secrets, own)

        # The files first; the second reading of a file that went goes with it,
        # unsaid; then what is still found in the two JSON files.
        found = findings()
        removed = _without_found(work, [f for f in found if f[0] not in (
            sysroot.RECORDING_FILE, MANIFEST)])
        _second_reading_of_what_is_left(work)
        removed += _without_found(work, findings())
        if removed:
            manifest = json.loads((work / MANIFEST).read_text())
            manifest["quitados"] = removed
            (work / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
        snapshot = snapshot_of(work)
        if left := _what_anonymize_would_cover(snapshot):
            raise Refusal(left, _where_in_dump(work, snapshot, left))
        if findings := check(work, clean.secrets, clean.raw_secrets, own):
            raise SystemExit("El volcado delata a esta máquina; no se escribe nada:\n  "
                             + "\n  ".join(findings[:20]))

        manifest = json.loads((work / MANIFEST).read_text())
        cpu = snapshot.cpu.types[0].brand if snapshot.cpu.types else None
        manifest.update(cpu=cpu, kernel=snapshot.system.kernel if snapshot.system else None,
                          gpus=[g.name for g in snapshot.gpus], fuentes=sorted(snapshot.capabilities))
        (work / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, target, symlinks=True)
    return target


# What `anonymize` replaces though it identifies nobody: the loopback and an
# all-zero MAC. That it changes them doesn't mean the dump left them.
HARMLESS = {"127.0.0.1", "::1", "00:00:00:00:00:00", None, ()}
ALREADY_SUBSTITUTED = re.compile(re.escape(privacidad.MOUNT).replace(r"\{\}", r"\d+"))


def _unnumbered(disks):
    """The disks with already replaced mounts, without their number.

    `anonymize` numbers by disk order and the dump by `/proc/mounts`': a
    `/media/unidad3` becoming `/media/unidad1` isn't a datum left to cover.
    """
    return tuple(
        dataclasses.replace(d, partitions=tuple(
            dataclasses.replace(p, mountpoint=privacidad.MOUNT.format(""))
            if p.mountpoint and ALREADY_SUBSTITUTED.fullmatch(p.mountpoint) else p
            for p in d.partitions))
        for d in disks)


def _differences(before, after, path: str) -> list[str]:
    """Where two values differ, as field paths («gpus[1].unique_id»): what
    the refusal says, without the value, which is what it protects."""
    if before == after:
        return []
    if (dataclasses.is_dataclass(before) and type(before) is type(after)):
        return [d for field in dataclasses.fields(before)
                for d in _differences(getattr(before, field.name), getattr(after, field.name),
                                      f"{path}.{field.name}")]
    if isinstance(before, tuple) and isinstance(after, tuple) and len(before) == len(after):
        return [d for i, (a, b) in enumerate(zip(before, after))
                for d in _differences(a, b, f"{path}[{i}]")]
    return [path]


def _what_anonymize_would_cover(snapshot) -> list[str]:
    """What `privacidad.anonymize` would change in the dump's snapshot.

    If it changes anything, the dump left a datum that identifies someone.
    Only what anonymize covers by rule without it being anyone's is
    accepted, such as `127.0.0.1`.
    """
    covered = privacidad.anonymize(snapshot)
    left = []
    for field in dataclasses.fields(snapshot):
        before, after = getattr(snapshot, field.name), getattr(covered, field.name)
        if before == after:
            continue
        if field.name == "network":
            for i, j in zip(before, after):
                for sub in dataclasses.fields(i):
                    a, b = getattr(i, sub.name), getattr(j, sub.name)
                    leftovers = [x for x in (a if isinstance(a, tuple) else (a,))
                              if x not in HARMLESS and x not in privacidad.OLD_SUBSTITUTES]
                    if a != b and leftovers:
                        # By position: the name may be what is protected.
                        left.append(f"network[{before.index(i)}].{sub.name}")
            continue
        if field.name == "disks":
            # The dump numbers mounts by /proc/mounts and anonymize by disk:
            # only what differs without the number is left.
            left += _differences(_unnumbered(before), _unnumbered(after), field.name)
            continue
        if (field.name == "system" and before.hostname in privacidad.OLD_SUBSTITUTES
                and dataclasses.replace(before, hostname=after.hostname) == after):
            continue
        left += _differences(before, after, field.name)
    return left
