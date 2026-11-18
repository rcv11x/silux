"""El icono y la entrada de menú en el escritorio del usuario.

Sin esto la aplicación no aparece en el lanzador y la barra de tareas le pone
un icono genérico. Todo va a `~/.local/share`, así que no hace falta root y no
toca nada del sistema.

Vive dentro del paquete, y no en `tools/`, porque lo usan dos sitios: la
herramienta `tools/install_desktop.py` y el botón de Ajustes, que también
tiene que funcionar desde el AppImage, donde `tools/` no viaja.

Los PNG se generan desde el SVG con Qt, que ya es dependencia de la interfaz:
así no hace falta tener rsvg-convert ni Inkscape.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SVG = pathlib.Path(__file__).resolve().parent / "ui" / "assets" / "silux.svg"

APP_ID = "silux"
# Los tamaños que pide la especificación de iconos de freedesktop, más los que
# usan en la práctica Plasma y GNOME para la barra de tareas.
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)

# El nombre que tuvo el proyecto antes de llamarse silux. Su instalador dejó
# `cpuz.desktop` y su juego de iconos, y nada los quitaba: en la oficina seguía
# en el menú una entrada que lanza un módulo que ya no existe desde una carpeta
# que tampoco. Solo se quita si es nuestra; un CPU-Z bajo Wine es otra cosa.
LEGACY_ID = "cpuz"
LEGACY_MODULE = "cpuz.ui.app"

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

DESKTOP_TEMPLATE = f"""[Desktop Entry]
Type=Application
Version=1.5
Name=Silux
GenericName=Información y sensores del equipo
GenericName[en]=Hardware information and sensors
Comment=Qué hardware tienes y qué está haciendo ahora mismo
Comment[en]=What hardware you have and what it is doing right now
Exec=@EXEC@
Path=@PATH@
Icon=silux
Terminal=false
Categories=System;Monitor;
Keywords={KEYWORDS}
StartupNotify=true
StartupWMClass=silux
"""


def data_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share"))


def icon_path(size: int) -> pathlib.Path:
    return data_home() / "icons" / "hicolor" / f"{size}x{size}" / "apps" / f"{APP_ID}.png"


def scalable_path() -> pathlib.Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def desktop_path() -> pathlib.Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


def hicolor() -> pathlib.Path:
    return data_home() / "icons" / "hicolor"


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


def legacy_files() -> list[pathlib.Path]:
    """Lo que dejó el instalador de cuando el proyecto se llamaba cpuz."""
    entrada = data_home() / "applications" / f"{LEGACY_ID}.desktop"
    try:
        nuestra = LEGACY_MODULE in entrada.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [entrada, *icon_files(LEGACY_ID)] if nuestra else []


# --------------------------------------------------------------------------


def render_icons() -> list[pathlib.Path]:
    """Rasteriza el SVG a los tamaños de la especificación."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])

    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"el SVG no es válido: {SVG}")

    # Fuera lo anterior antes de escribir: archivos nuevos y no reescritos
    # encima, y ninguno de un tamaño que esta versión ya no genera.
    for viejo in icon_files(APP_ID):
        viejo.unlink()

    written = []
    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()

        target = icon_path(size)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target), "PNG"):
            raise SystemExit(f"no se pudo escribir {target}")
        written.append(target)

    scalable = scalable_path()
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SVG, scalable)
    written.append(scalable)
    del app
    return written


def resolve_exec() -> tuple[str, str]:
    """Cómo lanzar la aplicación, y desde dónde.

    Si el paquete está instalado hay un ejecutable en el PATH. Si se está
    trabajando sobre el código fuente no lo hay, así que se apunta al
    intérprete actual y se fija el directorio de trabajo con `Path=`, que es
    justo para lo que existe ese campo.
    """
    if (script := shutil.which("silux-gui")):
        return script, ""
    return f"{sys.executable} -m silux.ui.app", str(ROOT)


def write_desktop() -> pathlib.Path:
    command, working_dir = resolve_exec()
    content = (
        DESKTOP_TEMPLATE
        .replace("@EXEC@", command)
        .replace("@PATH@", working_dir)
    )
    if not working_dir:
        content = "\n".join(line for line in content.splitlines() if line != "Path=") + "\n"

    target = desktop_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
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


def uninstall() -> int:
    """Quita la entrada y los iconos; devuelve cuántos archivos quitó."""
    removed = 0
    for path in [desktop_path(), *icon_files(APP_ID), *legacy_files()]:
        if path.exists():
            path.unlink()
            removed += 1
    refresh_caches()
    return removed


def install() -> tuple[list[pathlib.Path], pathlib.Path]:
    """Instala los iconos y la entrada; devuelve los dos.

    Reinstalar deja lo mismo que instalar en limpio: quita antes lo que dejó
    una versión vieja.
    """
    for viejo in legacy_files():
        viejo.unlink()
    icons = render_icons()
    entry = write_desktop()
    refresh_caches()
    return icons, entry
