"""Tests saved on the user's disk, read and written so that nothing is lost.

A history lives across versions: someone goes back to an older one, measures
and comes forward again. So a row is read without the fields this version
has no name for, and written back with them; a file another version wrote in
another format, or one cut short while it was saved, is moved out of the
way under a name that says which, never written over.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import json
import os
import pathlib
from typing import Callable, Optional, Sequence

# A part of a saved test that is a list of rows of its own: the field it is
# in, the dataclass of its rows, the fields that tell one row from another,
# and the parts those rows have in turn.
Part = tuple[str, type, tuple[str, ...], tuple]


def known(kind, row: dict) -> dict:
    """`row` without the fields this version has no name for: a newer one
    may have saved more."""
    names = {f.name for f in dataclasses.fields(kind)}
    return {name: value for name, value in row.items() if name in names}


def from_dict(kind, row: dict, parts: Sequence[Part] = ()):
    """`row` as a `kind`, with each of its parts as a tuple of theirs."""
    row = known(kind, row)
    for field, of, _names, inner in parts:
        row[field] = tuple(from_dict(of, r, inner) for r in row.get(field, ()))
    return kind(**row)


def _identity(kind, names: Sequence[str], row: dict) -> tuple:
    """What tells `row` from the others in its list. A field the file left
    out counts as its default, which is what reading it gives."""
    defaults = {f.name: f.default for f in dataclasses.fields(kind)}
    return tuple(row.get(name, defaults[name]) for name in names)


def _by_identity(rows, identity: Callable[[dict], object]) -> dict:
    """Each row under what identifies it, without those that share it: there
    is no telling which of them is which."""
    found, shared = {}, set()
    for row in rows if isinstance(rows, (list, tuple)) else ():
        if not isinstance(row, dict):
            continue
        try:
            key = identity(row)
            if key in found:
                shared.add(key)
            found[key] = row
        except TypeError:
            # A list or an object where a number or a name goes.
            continue
    return {key: row for key, row in found.items() if key not in shared}


def merged(row: dict, saved: Optional[dict], parts: Sequence[Part]) -> dict:
    """The row to write over `saved`, the one the file has for that test.
    What this version has no name for stays in it: going back a version and
    measuring mustn't strip what the newer one saved.

    Each row of each part keeps what its own saved row had, matched by what
    it is and never by its place in the list.
    """
    if saved is None:
        return row
    row = dict(row)
    for field, kind, names, inner in parts:
        identity = functools.partial(_identity, kind, names)
        before = _by_identity(saved.get(field), identity)
        unmistakable = _by_identity(row[field], identity)
        rows = []
        for new in row[field]:
            key = identity(new)
            old = before.get(key) if key in unmistakable else None
            rows.append(merged(new, old, inner))
        row[field] = rows
    return {**saved, **row}


def _file(path: pathlib.Path) -> Optional[dict]:
    """The history file as it is written, when there is one and it is a
    JSON object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _version(data: Optional[dict]) -> Optional[int]:
    """The version a history file says it is, when it says one."""
    version = None if data is None else data.get("version")
    return version if type(version) is int else None


def _rows(data: Optional[dict], version: int) -> Optional[list[dict]]:
    """The tests of a file of this version, as they are written. None for a
    file that isn't one."""
    if _version(data) != version or not isinstance(data.get("tests"), list):
        return None
    return [row for row in data["tests"] if isinstance(row, dict)]


def _set_aside(path: pathlib.Path, data: Optional[dict], version: int) -> None:
    """Move out of the way a history this version can't read, so that
    nothing is written over it: another version's under a name that says
    which, and one that is cut short or isn't a history as broken. Raises
    `OSError` when it can't be moved."""
    if _rows(data, version) is not None or not os.path.lexists(path):
        return
    theirs = _version(data)
    kind = "broken" if theirs in (None, version) else f"v{theirs}"
    aside = path.with_name(f"{path.name}.{kind}")
    number = 0
    while os.path.lexists(aside):
        number += 1
        aside = path.with_name(f"{path.name}.{kind}.{number}")
    path.rename(aside)


def load(path: pathlib.Path, version: int, read: Callable[[dict], object]) -> list:
    """The saved tests, in the file's order, each through `read`. A row that
    can't be read is left out without taking the rest with it."""
    results = []
    for row in _rows(_file(path), version) or ():
        try:
            results.append(read(row))
        except (TypeError, ValueError, AttributeError):
            continue
    return results


def save(path: pathlib.Path, version: int, results: Sequence, parts: Sequence[Part]) -> bool:
    """Write `results`, dataclasses with a `timestamp`, as the file's tests."""
    data = _file(path)
    saved = _by_identity(_rows(data, version) or (), lambda row: row.get("timestamp"))
    times = collections.Counter(r.timestamp for r in results)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _set_aside(path, data, version)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(
            {"version": version,
             "tests": [merged(dataclasses.asdict(r),
                              saved.get(r.timestamp) if times[r.timestamp] == 1 else None, parts)
                       for r in results]},
            indent=1), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        return False
    return True
