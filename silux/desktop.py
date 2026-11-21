"""El icono y la entrada de menú en el escritorio del usuario.

Sin esto la aplicación no aparece en el lanzador y la barra de tareas le pone
un icono genérico. Todo va a `~/.local/share`, así que no hace falta root y no
toca nada del sistema.

Vive dentro del paquete, y no en `tools/`, porque lo usan dos sitios: la
herramienta `tools/install_desktop.py` y el botón de Ajustes, que también
tiene que funcionar desde el AppImage, donde `tools/` no viaja.

La entrada apunta a lo que se está ejecutando, y cada forma de ejecutarlo
tiene la suya (`current_launcher`):

- desde el AppImage, `silux.desktop` abre el archivo `.AppImage`, no la
  carpeta temporal donde se monta, que desaparece al cerrar;
- desde el código, `silux-dev.desktop`, «Silux (desarrollo)», con su propio
  icono e identificador: la del AppImage y la del repositorio conviven y
  quitar una no deja a la otra sin icono;
- desde un paquete instalado, `silux.desktop` con `silux-gui`.

Los PNG se generan desde el SVG con Qt, que ya es dependencia de la interfaz:
así no hace falta tener rsvg-convert ni Inkscape. Con `QImageReader` y no con
`QtSvg`, que no va dentro del AppImage; el complemento `qsvg`, sí.
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
# Los tamaños que pide la especificación de iconos de freedesktop, más los que
# usan en la práctica Plasma y GNOME para la barra de tareas.
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)

# El nombre que tuvo el proyecto antes de llamarse silux. Su instalador dejó
# `cpuz.desktop` y su juego de iconos, y nada los quitaba: en la oficina seguía
# en el menú una entrada que lanza un módulo que ya no existe desde una carpeta
# que tampoco. Solo se quita si es nuestra; un CPU-Z bajo Wine es otra cosa.
LEGACY_ID = "cpuz"
LEGACY_MODULE = "cpuz.ui.app"
MODULE = "silux.ui.app"

# Las palabras con las que alguien buscaría esto en el lanzador. Van sin tildes
# además de con ellas porque nadie teclea «caché» con acento al buscar, y sin
# marcas registradas: el nombre se cambió justamente para no rozarlas.
KEYWORDS = (
    "hardware;cpu;procesador;processor;gpu;grafica;gráfica;graphics;tarjeta;"
    "radeon;geforce;vram;memoria;memory;ram;dimm;cache;caché;placa;motherboard;"
    "bios;uefi;red;network;ethernet;wifi;ip;monitor;pantalla;display;edid;"
    "sensor;sensores;temperatura;temperature;ventilador;fan;rpm;voltaje;"
    "voltage;vatios;watts;frecuencia;frequency;mhz;ghz;reloj;clock;"
    "monitorizacion;monitorización;monitoring;diagnostico;diagnóstico;info;"
    "sistema;system;"
)

# El identificador va en tres sitios y tienen que coincidir: el nombre del
# archivo (que es el `app_id` de la ventana en Wayland), `Icon=` y
# `StartupWMClass=`, que en X11 se compara con la clase de la ventana.
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
    """Lo que impide instalar, dicho para quien lo lee."""


@dataclass(frozen=True)
class Launcher:
    """Cómo se abre esta copia de silux desde el menú."""

    mode: str                       # "appimage", "development" o "package"
    app_id: str
    name: str
    name_en: str
    # La orden, argumento a argumento. Vacía si no se sabe: un AppImage
    # montado sin `$APPIMAGE` no dice dónde está su archivo.
    command: tuple[str, ...]
    working_dir: str = ""


def source_checkout() -> Optional[pathlib.Path]:
    """La carpeta del repositorio, si este silux se ejecuta desde su código."""
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
    """Todos los iconos con ese nombre en el tema, de cualquier tamaño.

    No solo los de `SIZES`: un tamaño que una versión anterior generaba y
    esta ya no se quedaría para siempre con el logo de entonces, y el
    escritorio lo elige cuando es el que mejor le encaja.
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
    """Lo que dejó una versión vieja y esta ya no escribe.

    La entrada de cuando el proyecto se llamaba cpuz; y, si esta copia es la
    del repositorio, la `silux.desktop` que el instalador escribía antes para
    el código, que ahora es de quien lo ejecute empaquetado.
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


# -- la orden -----------------------------------------------------------------

# Lo que obliga a entrecomillar un argumento según la especificación de las
# entradas de escritorio. Dentro de las comillas, estos cuatro van con barra.
_SHELL_SPECIAL = set(" \t\n\"'\\><~|&;$*?#()`")
_NEEDS_BACKSLASH = re.compile(r'(["`$\\])')


def _quote(argument: str) -> str:
    if argument and not (_SHELL_SPECIAL & set(argument)):
        quoted = argument
    else:
        quoted = '"' + _NEEDS_BACKSLASH.sub(r"\\\1", argument) + '"'
    # `%` abre un código de campo (`%f`, `%U`); el literal se escribe doble.
    return quoted.replace("%", "%%")


def exec_line(command: tuple[str, ...]) -> str:
    """La orden como va en `Exec=`.

    Lleva dos capas: la de las comillas, y encima la del valor de texto del
    archivo, donde una barra se escribe doble.
    """
    return " ".join(_quote(a) for a in command).replace("\\", "\\\\")


def _split(value: str) -> list[str]:
    """Parte la orden con las reglas de la especificación, no las de la shell:
    entre comillas, la barra solo escapa a `"`, `` ` ``, `$` y a sí misma."""
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
    """Lo contrario de `exec_line`, sin los códigos de campo."""
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


# -- escribir -----------------------------------------------------------------


def render_icons(app_id: str = APP_ID) -> list[pathlib.Path]:
    """Rasteriza el SVG a los tamaños de la especificación."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication, QImageReader

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])

    # Fuera lo anterior antes de escribir: archivos nuevos y no reescritos
    # encima, y ninguno de un tamaño que esta versión ya no genera.
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
    """Avisa al escritorio de que hay iconos y entrada nuevos.

    Todas las órdenes son opcionales: si no están, el escritorio acaba
    enterándose igual, solo que más tarde. Pero en Plasma «más tarde» puede
    ser «al reiniciar la sesión»: `plasmashell` guarda en memoria los iconos
    que ya pintó, y cambiar el archivo no le basta. Escucha una señal de
    D-Bus para volver a leerlos, la misma que manda Plasma al cambiar de tema
    de iconos.
    """
    # Que la carpeta del tema parezca cambiada a quien compare fechas.
    if hicolor().is_dir():
        os.utime(hicolor())
    for command in (
        ["update-desktop-database", str(desktop_path().parent)],
        ["gtk-update-icon-cache", "-f", "-t", str(hicolor())],
        # Las entradas de menú de Plasma salen de su caché, no de la carpeta.
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
    """La carpeta del escritorio del usuario («Escritorio» en español).

    Se lee de `user-dirs.dirs`, que es lo que hace `xdg-user-dir`, sin lanzar
    nada: esto se pregunta desde la interfaz.
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
    """La misma entrada, en el escritorio. Ejecutable, que es lo que piden
    Plasma y GNOME para lanzarla; GNOME además quiere que se marque como de
    confianza, y `gio` lo hace si está."""
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


# -- el estado ----------------------------------------------------------------

@dataclass(frozen=True)
class DesktopStatus:
    """Cómo está la entrada de menú de esta copia de silux.

    `state`: «unsupported» (no se puede instalar: un AppImage que no dice
    dónde está su archivo), «missing», «current», «elsewhere» (abre otra
    copia que existe), «broken» (abre algo que ya no existe) u «outdated»
    (abre esta, pero la entrada, los iconos o lo que dejó una versión vieja
    no son los de ahora).
    """

    state: str
    launcher: Launcher
    # A qué apunta la entrada instalada, para decirlo: la orden, o la carpeta
    # si es la del repositorio.
    target: str = ""
    on_desktop: bool = False


def _installed_command(text: str) -> tuple[tuple[str, ...], str]:
    """La orden y la carpeta de una entrada instalada."""
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
    """Lo que hay instalado comparado con lo que se instalaría ahora.

    Se compara el contenido —la entrada entera y el SVG—, no un número de
    versión que alguien tendría que acordarse de subir.
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


# -- instalar y quitar -------------------------------------------------------


def uninstall(launcher: Optional[Launcher] = None) -> int:
    """Quita la entrada, los iconos y el acceso del escritorio; devuelve
    cuántos archivos quitó."""
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
    """Instala los iconos y la entrada; devuelve los dos.

    Reinstalar deja lo mismo que instalar en limpio: quita antes lo que dejó
    una versión vieja. `on_desktop` pone o quita el acceso del escritorio;
    con None se deja como esté, al día si existe.
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
