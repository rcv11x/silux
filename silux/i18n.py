"""The interface language.

Keys are symbols (`cpu.card.clocks`), not the Spanish text, so rewording a
Spanish string doesn't orphan its translation: only the value in `es.json`
changes.

A key missing from the chosen language falls back to Spanish, and only if
Spanish lacks it too does the key itself show. A half-translated file reads
as Spanish among English; a bare key means the string is missing in both.

Languages are JSON files in `db/lang/` rather than gettext catalogs: they
need no compile step, can be fixed in GitHub's web editor and diff line by
line.

What comes from the machine (the processor's name, the kernel's sensor
labels, chip codes) is data and is never translated.
"""

from __future__ import annotations

import json
import pathlib
from typing import Callable, Optional

# ISO code to the language's own name for itself, so people find theirs the
# way they would write it.
LANGUAGES: dict[str, str] = {
    "es": "Español",
    "en": "English",
}

FOLDER = pathlib.Path(__file__).resolve().parent / "db" / "lang"

_current = "es"
_table: dict[str, str] = {}
# Spanish is always loaded: it is the fallback before the bare key.
_fallback: dict[str, str] = {}
_listeners: list[Callable[[], None]] = []


def available() -> dict[str, str]:
    """The languages that have a file."""
    languages = {}
    for path in sorted(FOLDER.glob("*.json")) if FOLDER.is_dir() else ():
        languages[path.stem] = LANGUAGES.get(path.stem, path.stem)
    return languages or {"es": LANGUAGES["es"]}


def _load(code: str) -> dict[str, str]:
    """A language file, or {} if it is missing or broken.

    Non-string entries are dropped: a half-written file must not take the
    interface down.
    """
    try:
        data = json.loads((FOLDER / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str) and v}


def current() -> str:
    return _current


def set_language(code: Optional[str]) -> str:
    """Load a language, notify the listeners and return the code in use.

    An unknown code falls back to Spanish instead of failing.
    """
    global _current, _table, _fallback

    if not _fallback:
        _fallback = _load("es")

    code = (code or "es").lower()
    if code == "es":
        _current, _table = "es", {}
    else:
        loaded = _load(code)
        _current, _table = (code, loaded) if loaded else ("es", {})
    _notify()
    return _current


def _(key: str) -> str:
    """A key's text in the current language, else in Spanish, else the key."""
    if key in _table:
        return _table[key]
    if not _fallback:
        set_language(_current)
    return _fallback.get(key, key)


def in_spanish(key: str) -> str:
    """A key's Spanish text whatever the interface language.

    So that `--page Sensores` keeps working with the interface in English.
    """
    global _fallback
    if not _fallback:
        _fallback = _load("es")
    return _fallback.get(key, key)


def on_change(callback: Callable[[], None]) -> None:
    """Register a callback to repaint when the language changes."""
    if callback not in _listeners:
        _listeners.append(callback)


def forget(callback: Callable[[], None]) -> None:
    if callback in _listeners:
        _listeners.remove(callback)


def _notify() -> None:
    for callback in list(_listeners):
        try:
            callback()
        except RuntimeError:
            # A widget Qt already destroyed; it must not block the change.
            forget(callback)


def untranslated(code: str) -> list[str]:
    """The strings the chosen language doesn't cover yet, for gen_lang.py."""
    path = FOLDER / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(k for k, v in data.items() if not v)
