"""User preferences, saved on disk.

A dataclass and a JSON file where XDG says. A corrupt file, or one from a
newer version, falls back to the defaults instead of breaking startup.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Mapping, Optional


def config_dir() -> pathlib.Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (pathlib.Path.home() / ".config")
    return pathlib.Path(base) / "silux"


def config_path() -> pathlib.Path:
    return config_dir() / "settings.json"


def system_language(environ: Optional[Mapping[str, str]] = None) -> str:
    """Spanish when the system is in Spanish, English otherwise.

    Reads the same variables as gettext, in its order: LANGUAGE (a list, the
    first wins), LC_ALL, LC_MESSAGES and LANG.
    """
    env = os.environ if environ is None else environ
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = (env.get(variable) or "").split(":")[0].strip().lower()
        if value:
            return "es" if value.startswith("es") else "en"
    return "en"


@dataclass(frozen=True)
class Preferences:
    interval_s: float = 1.0
    # Charts glide between samples instead of jumping. Nothing more is read,
    # the four visible charts just repaint more often (about 2 % of a desktop
    # core). Off by default: on a laptop that costs battery.
    fluid_charts: bool = False
    # The sidebar's mark slides to the section opened, for 150 ms.
    nav_slide: bool = True
    theme: str = "system"                 # system | light | dark
    temperature_unit: str = "c"           # c | f
    density: str = "normal"               # spacious | normal | compact
    # Larger by default: the base size reads small on a 27" 1440p monitor.
    font_scale: str = "grande"            # normal | grande | mayor | máximo
    # There is no accent colour setting; an old settings.json with «accent»
    # still loads, since `load` drops unknown keys.
    # Link speeds are quoted in bits and download speeds in bytes; people
    # checking against a speed test want bits.
    network_unit: str = "bytes"           # bytes | bits
    show_all_features: bool = False
    # Off by default: Silux connects to nothing unless asked
    # (docs/arquitectura.md#el-actualizador).
    check_updates: bool = False
    # «stable» or «testing»; empty follows the running build (a test build
    # looks for test builds).
    update_channel: str = ""
    # Empty follows the system's language (`system_language`).
    language: str = field(default_factory=lambda: system_language())
    # One width per sensor tree column; empty sizes them to their content.
    sensor_columns: tuple[int, ...] = ()
    # Sensor tree branches the user folded. Folded ones are stored because
    # most branches are open, so an empty list means «leave it as it was».
    sensor_collapsed: tuple[str, ...] = ()
    # Branches the user opened among those that start folded (long ones,
    # idle ones). Anything in neither list follows the default rule, which
    # can change between versions without overriding the user's choice.
    sensor_expanded: tuple[str, ...] = ()
    window_width: int = 900
    window_height: int = 680
    # The Home notice about data missing for lack of permissions, dismissed
    # with «Don't show again». The status bar link stays.
    permission_notice_dismissed: bool = False
    # The welcome of the first time, seen (or skipped).
    welcome_shown: bool = False
    # The sidebar folded to its icons.
    nav_folded: bool = False
    # The drive Storage's tiles show: its model and size (and its name
    # between two alike); empty for every drive.
    storage_disk: str = ""
    # The sensors pinned on top of the tree, by key, in their order.
    sensor_pinned: tuple[str, ...] = ()

    # -- validation ---------------------------------------------------------

    def normalized(self) -> "Preferences":
        from .i18n import available

        return replace(
            self,
            interval_s=min(10.0, max(0.2, float(self.interval_s))),
            fluid_charts=_yes_or_no(self.fluid_charts, False),
            nav_slide=_yes_or_no(self.nav_slide, True),
            theme=self.theme if self.theme in ("system", "light", "dark") else "system",
            temperature_unit="f" if self.temperature_unit == "f" else "c",
            density=self.density if self.density in ("spacious", "normal", "compact") else "normal",
            font_scale=(self.font_scale
                        if self.font_scale in ("normal", "grande", "mayor", "máximo")
                        else "grande"),
            network_unit="bits" if self.network_unit == "bits" else "bytes",
            show_all_features=_yes_or_no(self.show_all_features, False),
            check_updates=_yes_or_no(self.check_updates, False),
            update_channel=(self.update_channel
                            if self.update_channel in ("stable", "testing") else ""),
            language=(str(self.language).lower()
                      if str(self.language).lower() in available() else system_language()),
            sensor_columns=tuple(min(900, max(30, int(w))) for w in (self.sensor_columns or ())),
            sensor_collapsed=tuple(str(c) for c in (self.sensor_collapsed or ()))[:400],
            sensor_expanded=tuple(str(c) for c in (self.sensor_expanded or ()))[:400],
            # Only a rough clamp here; the window sets the real floor, knowing
            # which density is active.
            window_width=min(3840, max(380, int(self.window_width))),
            window_height=min(2160, max(320, int(self.window_height))),
            permission_notice_dismissed=_yes_or_no(self.permission_notice_dismissed, False),
            welcome_shown=_yes_or_no(self.welcome_shown, False),
            nav_folded=_yes_or_no(self.nav_folded, False),
            storage_disk=str(self.storage_disk or "")[:300],
            sensor_pinned=tuple(str(k) for k in (self.sensor_pinned or ()))[:100],
        )

    @property
    def fahrenheit(self) -> bool:
        return self.temperature_unit == "f"

    @property
    def interval_ms(self) -> int:
        return int(round(self.interval_s * 1000))


def _yes_or_no(setting_value: Any, default: bool) -> bool:
    """A yes or a no, without taking any non-empty value for a yes.

    `bool("false")` is True: a hand-edited `"fluid_charts": "false"` used to
    turn smooth motion on.
    """
    if isinstance(setting_value, bool):
        return setting_value
    if isinstance(setting_value, (int, float)) and setting_value in (0, 1):
        return bool(setting_value)
    if isinstance(setting_value, str) and setting_value.strip().lower() in ("true", "false"):
        return setting_value.strip().lower() == "true"
    return default


def load() -> Preferences:
    """The saved preferences, field by field.

    An unreadable file, or one that isn't a JSON object, gives the defaults;
    a bad field keeps its default without spoiling the rest.
    """
    try:
        raw: Any = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Preferences()
    if not isinstance(raw, dict):
        return Preferences()
    base = Preferences()
    valid: dict[str, Any] = {}
    for pref_field in fields(Preferences):
        if pref_field.name not in raw:
            continue
        try:
            replace(base, **{pref_field.name: raw[pref_field.name]}).normalized()
        except (TypeError, ValueError, OverflowError):
            continue
        valid[pref_field.name] = raw[pref_field.name]
    # Saved preferences from before the welcome existed: not the first time.
    valid.setdefault("welcome_shown", True)
    return Preferences(**valid).normalized()


def save(preferences: Preferences) -> bool:
    """Save and say whether it worked. Failing is not fatal."""
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        # Write and rename, so a power cut can't leave half a JSON.
        temporary = config_path().with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(preferences.normalized()), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(config_path())
        return True
    except OSError:
        return False
