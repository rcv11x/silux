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
import json
import os
import pathlib
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
