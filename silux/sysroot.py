"""Read the system from another root: a dumped machine's.

With `SILUX_SYSROOT` pointing to a dump made by `tools/volcar_equipo.py`,
providers read `/sys`, `/proc` and `/etc` from there instead of from the
machine running the program. It lets a fix be checked on an Intel and an
AMD without having both at hand: each one's dump is in
`tests/fixtures/equipos/` and the suite runs the Collector against all.

What does not come from a file (the CPUID instruction, DRM ioctls, what
OpenGL and Vulkan answer, a disk's free space, IP addresses) is recorded when
dumping and replayed when reading, with `recorded`. A dump of one processor
has to give that processor even if the suite runs on another: asking the
real CPU would mix two machines and say everything fits.

Without the variable nothing changes: `path` returns what it gets and
`recorded` calls the function.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from typing import Any, Callable, Optional, TypeVar

VARIABLE = "SILUX_SYSROOT"
# What is recorded goes in a file of the dump itself, next to `sys/` and `proc/`.
RECORDING_FILE = "grabado.json"

# The prefixes that are redirected. Not `/dev`: what is read from `/dev` are
# ioctls, and those are recorded.
PREFIXES = ("/sys/", "/proc/", "/etc/")

T = TypeVar("T")

# While dumping, what goes through `recorded` is noted here.
_recording: Optional[dict[str, dict[str, Any]]] = None
_cache: dict[pathlib.Path, dict] = {}


def root() -> Optional[pathlib.Path]:
    value = os.environ.get(VARIABLE)
    return pathlib.Path(value) if value else None


def active() -> bool:
    return root() is not None


def path(location):
    """The path inside the active root, of the same type as received.

    Idempotent: a path already inside the root comes back the same, as
    providers pass paths from one function to another and not all know
    whether theirs was translated already.
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
    """The path as the system would see it: without the root in front.

    For what is compared with a system path written in the code, or shown,
    or ends in the model: no dump folder may stay inside the model.
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
    """Whether the active dump recorded anything in that space.

    For what started being recorded after the first dumps were made: in one
    without it, the caller goes on as before it was recorded.
    """
    return space in _recorded()


def recorded(space: str, key: Any, function: Callable[..., T], *args,
             kind: Optional[type] = None, **kwargs) -> Optional[T]:
    """Call `function`, or return what it answered when the machine was dumped.

    `space` and `key` name the question: `("cpuid", "0:7:0")`,
    `("amdgpu", "/dev/dri/renderD128")`. With the root active nothing is
    called; what was not recorded returns None, as the program does when a
    source is missing. `kind` rebuilds a dataclass from the recorded
    dictionary.
    """
    key = str(key)
    if active():
        raw = _recorded().get(space, {}).get(key)
        if raw is None:
            return None
        # Dumping a mounted dump records what it answered, as from a machine.
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
    """For the tests that switch dumps within one process."""
    _cache.clear()
