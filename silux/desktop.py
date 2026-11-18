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
    viejos: list[pathlib.Path] = []
    texto = _read(desktop_path(LEGACY_ID))
    if texto is not None and LEGACY_MODULE in texto:
        viejos += [desktop_path(LEGACY_ID), *icon_files(LEGACY_ID)]
    if launcher.mode == "development":
        texto = _read(desktop_path(APP_ID))
        if texto is not None and MODULE in texto:
            viejos += [desktop_path(APP_ID), *icon_files(APP_ID)]
    return viejos


# -- la orden -----------------------------------------------------------------

# Lo que obliga a entrecomillar un argumento según la especificación de las
# entradas de escritorio. Dentro de las comillas, estos cuatro van con barra.
_RESERVADOS = set(" \t\n\"'\\><~|&;$*?#()`")
_CON_BARRA = re.compile(r'(["`$\\])')


def _quote(argument: str) -> str:
    if argument and not (_RESERVADOS & set(argument)):
        citado = argument
    else:
        citado = '"' + _CON_BARRA.sub(r"\\\1", argument) + '"'
    # `%` abre un código de campo (`%f`, `%U`); el literal se escribe doble.
    return citado.replace("%", "%%")


def exec_line(command: tuple[str, ...]) -> str:
    """La orden como va en `Exec=`.

    Lleva dos capas: la de las comillas, y encima la del valor de texto del
    archivo, donde una barra se escribe doble.
    """
    return " ".join(_quote(a) for a in command).replace("\\", "\\\\")


def _split(value: str) -> list[str]:
    """Parte la orden con las reglas de la especificación, no las de la shell:
    entre comillas, la barra solo escapa a `"`, `` ` ``, `$` y a sí misma."""
    partes: list[str] = []
    actual: Optional[str] = None
    i = 0
    while i < len(value):
        c = value[i]
        if c in " \t":
            if actual is not None:
                partes.append(actual)
                actual = None
        elif c == '"':
            actual = actual or ""
            i += 1
            while i < len(value) and value[i] != '"':
                if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in '"`$\\':
                    i += 1
                actual += value[i]
                i += 1
        else:
            actual = (actual or "") + c
        i += 1
    if actual is not None:
        partes.append(actual)
    return partes


def parse_exec(value: str) -> tuple[str, ...]:
    """Lo contrario de `exec_line`, sin los códigos de campo."""
    sin_texto = re.sub(r"\\(.)", lambda m: "\\" if m.group(1) == "\\" else m.group(0), value)
    return tuple(p.replace("%%", "%") for p in _split(sin_texto)
                 if not re.fullmatch(r"%[a-zA-Z]", p))


def entry_text(launcher: Launcher) -> str:
    texto = (DESKTOP_TEMPLATE
             .replace("@NAME@", launcher.name)
             .replace("@NAME_EN@", launcher.name_en)
             .replace("@EXEC@", exec_line(launcher.command))
             .replace("@PATH@", launcher.working_dir)
             .replace("@ID@", launcher.app_id))
    if not launcher.working_dir:
        texto = "\n".join(line for line in texto.splitlines() if line != "Path=") + "\n"
    return texto


# -- escribir -----------------------------------------------------------------


def render_icons(app_id: str = APP_ID) -> list[pathlib.Path]:
    """Rasteriza el SVG a los tamaños de la especificación."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication, QImageReader

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])

    # Fuera lo anterior antes de escribir: archivos nuevos y no reescritos
    # encima, y ninguno de un tamaño que esta versión ya no genera.
    for viejo in icon_files(app_id):
        viejo.unlink()

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
                subprocess.run(command, check=False, capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass


def uninstall(launcher: Optional[Launcher] = None) -> int:
    """Quita la entrada y los iconos; devuelve cuántos archivos quitó."""
    launcher = launcher or current_launcher()
    removed = 0
    for path in [desktop_path(launcher.app_id), *icon_files(launcher.app_id),
                 *legacy_files(launcher)]:
        if path.exists():
            path.unlink()
            removed += 1
    refresh_caches()
    return removed


def install(launcher: Optional[Launcher] = None) -> tuple[list[pathlib.Path], pathlib.Path]:
    """Instala los iconos y la entrada; devuelve los dos.

    Reinstalar deja lo mismo que instalar en limpio: quita antes lo que dejó
    una versión vieja.
    """
    launcher = launcher or current_launcher()
    if not launcher.command:
        raise DesktopError("no se sabe dónde está el archivo de este AppImage")
    for viejo in legacy_files(launcher):
        viejo.unlink()
    icons = render_icons(launcher.app_id)
    entry = write_desktop(launcher)
    refresh_caches()
    return icons, entry
