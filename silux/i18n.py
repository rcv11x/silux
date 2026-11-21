"""The interface's language.

Keys are symbols (`cpu.card.clocks`), not the Spanish text: rewording a
Spanish sentence does not leave its English translation hanging from the old
one, as the key stays and only the value in `es.json` changes.

The known weakness of symbolic keys is an incomplete translation showing
`cpu.card.clocks` on screen. Not here, as there are two steps: a key missing
in the chosen language falls back to Spanish, and only if that is missing too
does the key show. A half-translated file shows Spanish among English, which
reads; a bare key says the text is missing in both languages.

Languages are JSON files in `db/lang/`, chosen over gettext for whoever
writes them: a `.po` has to be compiled before it works, and these can be
fixed from GitHub's browser and read in the diff line by line.

    _("cpu.card.clocks")       → "Clocks" in English, "Relojes" in Spanish

What is **not** translated comes from the machine itself: the processor's
name, the sensor labels the kernel publishes, the chips' codes. That is not
the program's text, it is the data.
"""

from __future__ import annotations

import json
import pathlib
from typing import Callable, Optional

# The languages the program carries. The key is the ISO code and the value
# the name in its own language: whoever looks for theirs recognizes it as
# they write it, not translated into the interface's.
LANGUAGES: dict[str, str] = {
    "es": "Español",
    "en": "English",
}

FOLDER = pathlib.Path(__file__).resolve().parent / "db" / "lang"

_current = "es"
_table: dict[str, str] = {}
# Spanish is always loaded, whatever language is chosen: the step between a
# missing translation and the bare key.
_fallback: dict[str, str] = {}
_listeners: list[Callable[[], None]] = []


def available() -> dict[str, str]:
    """The languages that have a file."""
    languages = {}
    for path in sorted(FOLDER.glob("*.json")) if FOLDER.is_dir() else ():
        languages[path.stem] = LANGUAGES.get(path.stem, path.stem)
    return languages or {"es": LANGUAGES["es"]}


def _load(code: str) -> dict[str, str]:
    """A language file, or empty if missing or broken.

    Whatever is not text for text is dropped: a half-written file must not
    take the interface down.
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
    """Load a language and tell whoever listens. Returns the one in force.

    A code that does not exist is no error to stop the program: it falls back
    to Spanish, which is always there.
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
    """A key's text in the current language.

    Three steps, and the order is what makes this usable: the chosen
    language, Spanish, and last the key. A half-done `en.json` shows Spanish
    among English, which reads; only a sentence written in neither language
    shows the key, and that is what one needs to see to go and write it.
    """
    if key in _table:
        return _table[key]
    if not _fallback:
        set_language(_current)
    return _fallback.get(key, key)


def in_spanish(key: str) -> str:
    """A key's Spanish text, whatever the interface's language.

    For whoever has to recognize a name written in Spanish wherever it comes
    from: `--page Sensores` must keep working with the interface in English.
    """
    global _fallback
    if not _fallback:
        _fallback = _load("es")
    return _fallback.get(key, key)


def on_change(callback: Callable[[], None]) -> None:
    """Register whoever must repaint when the language changes."""
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
            # A widget Qt already destroyed: dropped, and on we go. A dead
            # listener must not stop the language from changing.
            forget(callback)


def untranslated(code: str) -> list[str]:
    """The strings the chosen language does not cover yet.

    For `tools/gen_lang.py`, which keeps the files up to date when new text
    appears in the program.
    """
    path = FOLDER / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(k for k, v in data.items() if not v)
