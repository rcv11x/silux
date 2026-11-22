"""Read the system from another root: a dumped machine's.

With `SILUX_SYSROOT` pointing at a dump made by `tools/volcar_equipo.py`,
providers read `/sys`, `/proc` and `/etc` from there instead of from the
running machine. That is how a fix gets checked on an Intel and an AMD
without having both: their dumps are in `tests/fixtures/equipos/` and the
suite runs the Collector against each.

What doesn't come from a file (CPUID, DRM ioctls, OpenGL and Vulkan, free
disk space, IP addresses) is recorded at dump time and replayed through
`recorded`. A dump has to answer for its own processor even when the suite
runs on another; asking the real CPU would mix two machines.

Without the variable, `path` returns its argument and `recorded` just calls
the function.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import os
import pathlib
import re
from typing import Any, Callable, Optional, TypeVar

VARIABLE = "SILUX_SYSROOT"
# The recordings live in the dump itself, next to `sys/` and `proc/`.
RECORDING_FILE = "grabado.json"

# Not `/dev`: what is read there goes through ioctls, which are recorded.
PREFIXES = ("/sys/", "/proc/", "/etc/")

T = TypeVar("T")

# What goes through `recorded` while dumping.
_recording: Optional[dict[str, dict[str, Any]]] = None
_cache: dict[pathlib.Path, dict] = {}


def root() -> Optional[pathlib.Path]:
    value = os.environ.get(VARIABLE)
    return pathlib.Path(value) if value else None


def active() -> bool:
    return root() is not None


def path(location):
    """The path inside the active root, of the same type it was given.

    Idempotent: a path already inside the root comes back unchanged, since
    providers hand paths to each other without knowing whether they were
    translated.
    """
    base = root()
    if base is None:
        return location
    text = os.fspath(location)
    if text.startswith(str(base) + os.sep) or text == str(base):
        return location
    if not (text.startswith(PREFIXES) or text in ("/sys", "/proc", "/etc")):
        return location
    new_value = str(base) + text
    return pathlib.Path(new_value) if isinstance(location, pathlib.PurePath) else new_value


def unrooted(location) -> str:
    """The path as the system sees it, without the root prefix.

    For comparing with a system path in the code, showing it, or storing it
    in the model, which must never contain a dump folder.
    """
    base = root()
    text = os.fspath(location)
    if base is not None and text.startswith(str(base) + os.sep):
        return text[len(str(base)):]
    return text


def _recorded() -> dict:
    base = root()
    if base is None:
        return {}
    if base not in _cache:
        try:
            _cache[base] = json.loads((base / RECORDING_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache[base] = {}
    return _cache[base]


def did_record(space: str) -> bool:
    """Whether the active dump recorded anything under `space`.

    For what started being recorded after the first dumps: without it, the
    caller falls back to how it worked before.
    """
    return space in _recorded()


def recorded(space: str, key: Any, function: Callable[..., T], *args,
             kind: Optional[type] = None, **kwargs) -> Optional[T]:
    """Call `function`, or return what it answered when the machine was dumped.

    `space` and `key` name the question: `("cpuid", "0:7:0")`,
    `("amdgpu", "/dev/dri/renderD128")`. With a root active nothing is
    called, and an unrecorded question returns None, as a missing source
    does. `kind` rebuilds a dataclass from the recorded dict.
    """
    key = str(key)
    if active():
        raw = _recorded().get(space, {}).get(key)
        if raw is None:
            return None
        # Dumping a mounted dump records its answers, as with a real machine.
        if _recording is not None:
            _recording.setdefault(space, {})[key] = raw
        if kind is not None and dataclasses.is_dataclass(kind):
            return kind(**raw)
        if isinstance(raw, list):
            return tuple(raw)
        return raw
    value = function(*args, **kwargs)
    if _recording is not None:
        storable = dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value
        _recording.setdefault(space, {})[key] = storable
    return value


def uname() -> dict:
    """The kernel's uname, recorded with the dump; {} where it wasn't.

    `os.uname()` and not `platform.uname()`, whose `processor` runs
    `uname -p` in another process: in one report's annex the whole record
    went missing.
    """
    fields = ("system", "node", "release", "version", "machine")
    return recorded("plataforma", "uname", lambda: dict(zip(fields, os.uname()))) or {}


def start_recording() -> None:
    global _recording
    _recording = {}


def recorded_data() -> dict:
    global _recording
    result, _recording = _recording or {}, None
    return result


def forget() -> None:
    """For tests that switch dumps within one process."""
    _cache.clear()
    _second_applied.clear()


# A dump's second reading: the files whose difference between two samples
# is a usage, a rate or a rest, read again an interval after the dump's copy.
# Only these, and only plain counters, are taken or written back.
SECOND_READING = "segunda_lectura"
COUNTER_FILES = (
    "/proc/stat", "/proc/net/dev", "/proc/self/net/dev", "/proc/diskstats",
    "/sys/devices/system/cpu/cpu*/cpuidle/state*/usage",
    "/sys/devices/system/cpu/cpu*/cpuidle/state*/time",
    "/sys/devices/system/cpu/cpu*/cpuidle/state*/above",
    "/sys/devices/system/cpu/cpu*/cpuidle/state*/below",
    "/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq",
    "/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq",
    "/sys/devices/*/net/*/statistics/*",
    "/sys/devices/*/block/*/stat",
    "/sys/devices/*/drm/card*/gt/gt*/rc6_residency_ms",
    "/sys/devices/*/drm/card*/power/rc6_residency_ms",
    "/sys/devices/*/drm/card*/gt/gt*/rps_act_freq_mhz",
    "/sys/devices/*/gpu_busy_percent",
    "/sys/devices/*/hwmon/hwmon*/*_input",
    "/sys/devices/*/hwmon/hwmon*/*_average",
)
# What a counter file holds: printable ASCII, and not much of it.
_COUNTER_TEXT = re.compile(r"[\x20-\x7e\t\n]{0,65536}")
_second_applied: set[pathlib.Path] = set()


def is_counter_file(location: str) -> bool:
    return ".." not in location.split("/") and any(
        fnmatch.fnmatchcase(location, pattern) for pattern in COUNTER_FILES)


def is_counter_text(text: str) -> bool:
    return bool(_COUNTER_TEXT.fullmatch(text))


def apply_second_reading() -> None:
    """The active dump's second reading of its counters, written over its
    first: the Collector's second snapshot finds them as a machine would an
    interval later. Once per mount. Only counter files that are already
    there take it; the rest of what a dump says is left alone."""
    base = root()
    if base is None or base in _second_applied:
        return
    _second_applied.add(base)
    readings = _recorded().get(SECOND_READING)
    if not isinstance(readings, dict):
        return
    inside = base.resolve()
    for location, text in readings.items():
        if not (isinstance(location, str) and isinstance(text, str)
                and is_counter_file(location) and is_counter_text(text)):
            continue
        target = inside / location.lstrip("/")
        if target.is_symlink() or not target.is_file() or inside not in target.resolve().parents:
            continue
        target.write_text(text)
