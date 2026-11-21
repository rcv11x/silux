"""The icon and the menu entry on the user's desktop.

Without them the application doesn't appear in the launcher and the taskbar
gives it a generic icon. Everything goes to `~/.local/share`, so no root is
needed and nothing of the system is touched.

It lives in the package, not in `tools/`, because two places use it: the
`tools/install_desktop.py` tool and the button in Settings, which must also
work from the AppImage, where `tools/` doesn't travel.

The entry points at what is running, and each way of running it has its own
(`current_launcher`):

- from the AppImage, `silux.desktop` opens the `.AppImage` file, not the
  temporary folder it is mounted on, which goes away on exit;
- from source, `silux-dev.desktop`, «Silux (desarrollo)», with its own icon
  and identifier: the AppImage's and the repository's live side by side, and
  removing one doesn't leave the other without an icon;
- from an installed package, `silux.desktop` with `silux-gui`.

The PNGs are rendered from the SVG with Qt, already a dependency of the
interface, so neither rsvg-convert nor Inkscape is needed. With
`QImageReader` rather than `QtSvg`, which isn't in the AppImage; the `qsvg`
plugin is.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Mapping, Optional

from .system_env import system_environment

ROOT = pathlib.Path(__file__).resolve().parent.parent
SVG = pathlib.Path(__file__).resolve().parent / "ui" / "assets" / "silux.svg"

APP_ID = "silux"
DEV_APP_ID = "silux-dev"
# The sizes freedesktop's icon specification asks for, plus those Plasma and
# GNOME use in practice for the taskbar.
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)

# The project's name before it was called silux. Its installer left
# `cpuz.desktop` and its icon set, and nothing removed them: the menu kept an
# entry launching a module that no longer exists from a folder that doesn't
# either. Removed only if it is ours; a CPU-Z under Wine is something else.
LEGACY_ID = "cpuz"
LEGACY_MODULE = "cpuz.ui.app"
MODULE = "silux.ui.app"

# The words someone would search the launcher with. Without accents as well
# as with them, since nobody types «caché» with its accent when searching,
# and without trademarks: the name was changed precisely to stay clear of
# them.
KEYWORDS = (
    "hardware;cpu;procesador;processor;gpu;grafica;gráfica;graphics;tarjeta;"
    "radeon;geforce;vram;memoria;memory;ram;dimm;cache;caché;placa;motherboard;"
    "bios;uefi;red;network;ethernet;wifi;ip;monitor;pantalla;display;edid;"
    "sensor;sensores;temperatura;temperature;ventilador;fan;rpm;voltaje;"
    "voltage;vatios;watts;frecuencia;frequency;mhz;ghz;reloj;clock;"
    "monitorizacion;monitorización;monitoring;diagnostico;diagnóstico;info;"
    "sistema;system;"
)

# The identifier goes in three places that must match: the file's name (the
# window's `app_id` on Wayland), `Icon=` and `StartupWMClass=`, which X11
# compares with the window's class.
DESKTOP_TEMPLATE = f"""[Desktop Entry]
Type=Application
Version=1.5
Name=@NAME@
Name[en]=@NAME_EN@
GenericName=Información y sensores del equipo
GenericName[en]=Hardware information and sensors
Comment=Qué hardware tienes y qué está haciendo ahora mismo
Comment[en]=What hardware you have and what it is doing right now
Exec=@EXEC@
Path=@PATH@
Icon=@ID@
Terminal=false
Categories=System;Monitor;
Keywords={KEYWORDS}
StartupNotify=true
StartupWMClass=@ID@
"""


class DesktopError(RuntimeError):
    """What prevents installing, said for whoever reads it."""


@dataclass(frozen=True)
class Launcher:
    """How this copy of silux is opened from the menu."""

    mode: str                       # "appimage", "development" or "package"
    app_id: str
    name: str
    name_en: str
    # The command, argument by argument. Empty if unknown: an AppImage
    # mounted without `$APPIMAGE` doesn't say where its file is.
    command: tuple[str, ...]
    working_dir: str = ""


def source_checkout() -> Optional[pathlib.Path]:
    """The repository's folder, if this silux runs from its source."""
    if (ROOT / "pyproject.toml").is_file() and (ROOT / "tools" / "install_desktop.py").is_file():
        return ROOT
    return None


def current_launcher(environ: Optional[Mapping[str, str]] = None) -> Launcher:
    env = os.environ if environ is None else environ
    if env.get("APPIMAGE"):
        return Launcher("appimage", APP_ID, "Silux", "Silux", (env["APPIMAGE"],))
    if "/.mount_" in sys.executable:
        return Launcher("appimage", APP_ID, "Silux", "Silux", ())
    if (root := source_checkout()) is not None:
        return Launcher("development", DEV_APP_ID, "Silux (desarrollo)",
                        "Silux (development)", (sys.executable, "-m", MODULE), str(root))
    if (script := shutil.which("silux-gui")):
        return Launcher("package", APP_ID, "Silux", "Silux", (script,))
    return Launcher("package", APP_ID, "Silux", "Silux", (sys.executable, "-m", MODULE))


def data_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share"))


def hicolor() -> pathlib.Path:
    return data_home() / "icons" / "hicolor"


def icon_path(size: int, app_id: str = APP_ID) -> pathlib.Path:
    return hicolor() / f"{size}x{size}" / "apps" / f"{app_id}.png"


def scalable_path(app_id: str = APP_ID) -> pathlib.Path:
    return hicolor() / "scalable" / "apps" / f"{app_id}.svg"


def desktop_path(app_id: str = APP_ID) -> pathlib.Path:
    return data_home() / "applications" / f"{app_id}.desktop"


def icon_files(app_id: str) -> list[pathlib.Path]:
    """Every icon with that name in the theme, of any size.

    Not only those in `SIZES`: a size an earlier version rendered and this
    one no longer does would keep the old logo forever, and the desktop picks
    it when it fits best.
    """
    if not hicolor().is_dir():
        return []
    return sorted(p for p in hicolor().glob(f"*/apps/{app_id}.*")
                  if p.suffix in (".png", ".svg"))


def _read(path: pathlib.Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def legacy_files(launcher: Launcher) -> list[pathlib.Path]:
    """What an old version left and this one no longer writes.

    The entry from when the project was called cpuz; and, if this copy is the
    repository's, the `silux.desktop` the installer used to write for the
    source, which now belongs to whoever runs it packaged.
    """
    old_files: list[pathlib.Path] = []
    text = _read(desktop_path(LEGACY_ID))
    if text is not None and LEGACY_MODULE in text:
        old_files += [desktop_path(LEGACY_ID), *icon_files(LEGACY_ID)]
    if launcher.mode == "development":
        text = _read(desktop_path(APP_ID))
        if text is not None and MODULE in text:
            old_files += [desktop_path(APP_ID), *icon_files(APP_ID)]
    return old_files


# -- the command --------------------------------------------------------------

# What makes an argument need quotes under the desktop entry specification.
# Inside the quotes, these four take a backslash.
_SHELL_SPECIAL = set(" \t\n\"'\\><~|&;$*?#()`")
_NEEDS_BACKSLASH = re.compile(r'(["`$\\])')


def _quote(argument: str) -> str:
    if argument and not (_SHELL_SPECIAL & set(argument)):
        quoted = argument
    else:
        quoted = '"' + _NEEDS_BACKSLASH.sub(r"\\\1", argument) + '"'
    # `%` starts a field code (`%f`, `%U`); a literal one is written twice.
    return quoted.replace("%", "%%")


def exec_line(command: tuple[str, ...]) -> str:
    """The command as it goes in `Exec=`.

    Two layers: the quoting, and on top the file's string value, where a
    backslash is written twice.
    """
    return " ".join(_quote(a) for a in command).replace("\\", "\\\\")


def _split(value: str) -> list[str]:
    """Split the command by the specification's rules, not the shell's:
    inside quotes, a backslash only escapes `"`, `` ` ``, `$` and itself."""
    parts: list[str] = []
    current: Optional[str] = None
    i = 0
    while i < len(value):
        c = value[i]
        if c in " \t":
            if current is not None:
                parts.append(current)
                current = None
        elif c == '"':
            current = current or ""
            i += 1
            while i < len(value) and value[i] != '"':
                if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in '"`$\\':
                    i += 1
                current += value[i]
                i += 1
        else:
            current = (current or "") + c
        i += 1
    if current is not None:
        parts.append(current)
    return parts


def parse_exec(value: str) -> tuple[str, ...]:
    """The reverse of `exec_line`, without the field codes."""
    empty = re.sub(r"\\(.)", lambda m: "\\" if m.group(1) == "\\" else m.group(0), value)
    return tuple(p.replace("%%", "%") for p in _split(empty)
                 if not re.fullmatch(r"%[a-zA-Z]", p))


def entry_text(launcher: Launcher) -> str:
    text = (DESKTOP_TEMPLATE
             .replace("@NAME@", launcher.name)
             .replace("@NAME_EN@", launcher.name_en)
             .replace("@EXEC@", exec_line(launcher.command))
             .replace("@PATH@", launcher.working_dir)
             .replace("@ID@", launcher.app_id))
    if not launcher.working_dir:
        text = "\n".join(line for line in text.splitlines() if line != "Path=") + "\n"
    return text


# -- writing ------------------------------------------------------------------


def render_icons(app_id: str = APP_ID) -> list[pathlib.Path]:
    """Rasterize the SVG to the specification's sizes."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication, QImageReader

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])

    # Out with the old before writing: new files rather than rewritten ones,
    # and none of a size this version no longer renders.
    for old in icon_files(app_id):
        old.unlink()

    written = []
    for size in SIZES:
        reader = QImageReader(str(SVG))
        reader.setScaledSize(QSize(size, size))
        image = reader.read()
        if image.isNull():
            raise DesktopError(f"no se pudo dibujar {SVG}: {reader.errorString()}")

        target = icon_path(size, app_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target), "PNG"):
            raise DesktopError(f"no se pudo escribir {target}")
        written.append(target)

    scalable = scalable_path(app_id)
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SVG, scalable)
    written.append(scalable)
    del app
    return written


def write_desktop(launcher: Launcher) -> pathlib.Path:
    if not launcher.command:
        raise DesktopError("no se sabe dónde está el archivo de este AppImage")
    target = desktop_path(launcher.app_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(entry_text(launcher), encoding="utf-8")
    target.chmod(0o755)
    return target


def refresh_caches() -> None:
    """Tell the desktop there are new icons and a new entry.

    Every command is optional: without them the desktop finds out anyway,
    only later. But on Plasma «later» can mean «at the next login»:
    `plasmashell` keeps the icons it already drew in memory, and a changed
    file isn't enough. It listens for a D-Bus signal to reload them, the one
    Plasma sends when the icon theme changes.
    """
    # Make the theme's folder look changed to anyone comparing dates.
    if hicolor().is_dir():
        os.utime(hicolor())
    for command in (
        ["update-desktop-database", str(desktop_path().parent)],
        ["gtk-update-icon-cache", "-f", "-t", str(hicolor())],
        # Plasma's menu entries come from its cache, not from the folder.
        ["kbuildsycoca6"],
        ["dbus-send", "--session", "--type=signal", "/KIconLoader",
         "org.kde.KIconLoader.iconChanged", "int32:0"],
    ):
        if shutil.which(command[0]):
            try:
                subprocess.run(command, check=False, capture_output=True, timeout=30,
                               env=system_environment())
            except (OSError, subprocess.TimeoutExpired):
                pass


def desktop_dir() -> pathlib.Path:
    """The user's desktop folder («Escritorio» in Spanish).

    Read from `user-dirs.dirs`, as `xdg-user-dir` does, without launching
    anything: the interface asks this.
    """
    home = pathlib.Path.home()
    config = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    try:
        for line in (config / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DESKTOP_DIR="):
                value = line.split("=", 1)[1].strip().strip('"')
                return pathlib.Path(value.replace("$HOME", str(home)))
    except OSError:
        pass
    return home / "Desktop"


def shortcut_path(app_id: str = APP_ID) -> pathlib.Path:
    return desktop_dir() / f"{app_id}.desktop"


def _write_shortcut(launcher: Launcher) -> pathlib.Path:
    """The same entry, on the desktop. Executable, which Plasma and GNOME
    require to launch it; GNOME also wants it marked as trusted, and `gio`
    does that if present."""
    target = shortcut_path(launcher.app_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(entry_text(launcher), encoding="utf-8")
    target.chmod(0o755)
    if shutil.which("gio"):
        try:
            subprocess.run(["gio", "set", str(target), "metadata::trusted", "true"],
                           check=False, capture_output=True, timeout=10,
                           env=system_environment())
        except (OSError, subprocess.TimeoutExpired):
            pass
    return target


# -- the state ----------------------------------------------------------------

@dataclass(frozen=True)
class DesktopStatus:
    """How this copy of silux's menu entry stands.

    `state`: «unsupported» (it can't be installed: an AppImage that doesn't
    say where its file is), «missing», «current», «elsewhere» (opens another
    copy that exists), «broken» (opens something that no longer exists) or
    «outdated» (opens this one, but the entry, the icons or what an old
    version left aren't today's).
    """

    state: str
    launcher: Launcher
    # What the installed entry points at, to say so: the command, or the
    # folder if it is the repository's.
    target: str = ""
    on_desktop: bool = False


def _installed_command(text: str) -> tuple[tuple[str, ...], str]:
    """The command and folder of an installed entry."""
    command, folder = (), ""
    for line in text.splitlines():
        if line.startswith("Exec="):
            command = parse_exec(line[len("Exec="):])
        elif line.startswith("Path="):
            folder = line[len("Path="):]
    return command, folder


def _runs(command: tuple[str, ...], folder: str) -> bool:
    if not command:
        return False
    program = command[0]
    found = (os.path.isfile(program) and os.access(program, os.X_OK)) \
        if os.sep in program else shutil.which(program) is not None
    return found and (not folder or os.path.isdir(folder))


def _icons_up_to_date(app_id: str) -> bool:
    try:
        if scalable_path(app_id).read_bytes() != SVG.read_bytes():
            return False
    except OSError:
        return False
    return all(icon_path(size, app_id).is_file() for size in SIZES)


def status(launcher: Optional[Launcher] = None) -> DesktopStatus:
    """What is installed compared with what would be installed now.

    The content is compared (the whole entry and the SVG), not a version
    number someone would have to remember to bump.
    """
    launcher = launcher or current_launcher()
    on_the_desktop = shortcut_path(launcher.app_id).is_file()
    if not launcher.command:
        return DesktopStatus("unsupported", launcher, on_desktop=on_the_desktop)
    text = _read(desktop_path(launcher.app_id))
    if text is None:
        return DesktopStatus("missing", launcher, on_desktop=on_the_desktop)
    command, folder = _installed_command(text)
    target = folder or (command[0] if command else "")
    if (command, folder) != (launcher.command, launcher.working_dir):
        state = "elsewhere" if _runs(command, folder) else "broken"
        return DesktopStatus(state, launcher, target, on_the_desktop)
    up_to_date = (text == entry_text(launcher) and _icons_up_to_date(launcher.app_id)
              and not legacy_files(launcher))
    if on_the_desktop and _read(shortcut_path(launcher.app_id)) != entry_text(launcher):
        up_to_date = False
    return DesktopStatus("current" if up_to_date else "outdated", launcher, target, on_the_desktop)


# -- installing and removing -------------------------------------------------


def uninstall(launcher: Optional[Launcher] = None) -> int:
    """Remove the entry, the icons and the desktop shortcut; return how many
    files were removed."""
    launcher = launcher or current_launcher()
    removed = 0
    for path in [desktop_path(launcher.app_id), *icon_files(launcher.app_id),
                 *legacy_files(launcher), shortcut_path(launcher.app_id)]:
        if path.exists():
            path.unlink()
            removed += 1
    refresh_caches()
    return removed


def install(launcher: Optional[Launcher] = None,
            on_desktop: Optional[bool] = None) -> tuple[list[pathlib.Path], pathlib.Path]:
    """Install the icons and the entry; return both.

    Reinstalling leaves the same as a clean install: it first removes what an
    old version left. `on_desktop` adds or removes the desktop shortcut; None
    leaves it as it is, updated if it exists.
    """
    launcher = launcher or current_launcher()
    if not launcher.command:
        raise DesktopError("no se sabe dónde está el archivo de este AppImage")
    for old in legacy_files(launcher):
        old.unlink()
    icons = render_icons(launcher.app_id)
    entry = write_desktop(launcher)
    shortcut = shortcut_path(launcher.app_id)
    if on_desktop is None:
        on_desktop = shortcut.is_file()
    if on_desktop:
        _write_shortcut(launcher)
    elif shortcut.is_file():
        shortcut.unlink()
    refresh_caches()
    return icons, entry
