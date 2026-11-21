"""The user's preferences, saved on disk.

Small on purpose: a dataclass, a JSON file at the path the XDG specification
says, and nothing more. A corrupt file or one from a future version is
ignored and the defaults are used, rather than crashing at startup.
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

    Silux always started in Spanish, and people with the system in English
    found it that way. Same order gettext uses: LANGUAGE (a list, the first
    wins), then LC_ALL, LC_MESSAGES and LANG.
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
    # Charts glide between samples instead of jumping. It reads nothing more,
    # only repaints more often, and only the four on screen: about 2 % of a
    # core on a desktop CPU. Off by default anyway: on a laptop that is
    # battery.
    fluid_charts: bool = False
    theme: str = "system"                 # system | light | dark
    temperature_unit: str = "c"           # c | f
    density: str = "normal"               # spacious | normal | compact
    # «grande» by default: on a 27" monitor at 1440p the base size reads small,
    # and whoever wants it tighter lowers it in two clicks.
    font_scale: str = "grande"            # normal | grande | mayor | máximo
    # No accent colour to choose: it is the brand's amber, on every page. An
    # old `settings.json` with «accent» loads anyway: `load` drops the keys it
    # does not know.
    # In bytes or bits per second. Makers measure links in bits and download
    # programs in bytes, eight times apart: whoever compares with a speed test
    # wants bits.
    network_unit: str = "bytes"           # bytes | bits
    show_all_features: bool = False
    # Look for a new version on opening. Off by default: the program connects
    # to nothing unless asked (docs/arquitectura.md#el-actualizador).
    check_updates: bool = False
    # «stable» or «testing»; empty follows the running version (a test
    # version looks for the next test version, a final for finals).
    update_channel: str = ""
    # The width of each column of the sensor tree. Empty = from the content.
    # The interface's language. Spanish is the original and not one more
    # translation: it shows wherever a string is missing in another.
    # Without a saved setting, the system's (see `system_language`).
    language: str = field(default_factory=lambda: system_language())
    sensor_columns: tuple[int, ...] = ()
    # The sensor tree branches left folded. The folded ones are kept, not the
    # open ones, since most is usually open: an empty list means «as it was»,
    # which is what someone who never touched anything wants.
    sensor_collapsed: tuple[str, ...] = ()
    # And those opened by hand among the ones born closed: the long ones
    # («Clocks · 16») and those without activity. What is in neither list
    # follows the rule, and the rule can change between versions without
    # overriding what the user chose.
    sensor_expanded: tuple[str, ...] = ()
    window_width: int = 900
    window_height: int = 680
    # The Home notice that data is missing for lack of permissions, dismissed
    # with «Do not show again». The status bar's link stays.
    permission_notice_dismissed: bool = False

    # -- validation ---------------------------------------------------------

    def normalized(self) -> "Preferences":
        from .i18n import available

        return replace(
            self,
            interval_s=min(10.0, max(0.2, float(self.interval_s))),
            fluid_charts=_yes_or_no(self.fluid_charts, False),
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
        )

    @property
    def fahrenheit(self) -> bool:
        return self.temperature_unit == "f"

    @property
    def interval_ms(self) -> int:
        return int(round(self.interval_s * 1000))


def _yes_or_no(setting_value: Any, default: bool) -> bool:
    """A yes or a no, without taking anything non-empty for a yes.

    `bool("false")` is `True`: a hand-edited `settings.json` with
    `"fluid_charts": "false"` turned smooth motion on.
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

    A file that cannot be read, or is not a JSON object, gives the defaults.
    A bad field keeps its default without taking the others down.
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
    return Preferences(**valid).normalized()


def save(preferences: Preferences) -> bool:
    """Save and say whether it worked. Not critical: on failure, carry on."""
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        # Atomic write: a power cut must not leave half a JSON.
        temporary = config_path().with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(preferences.normalized()), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(config_path())
        return True
    except OSError:
        return False
