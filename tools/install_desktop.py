#!/usr/bin/env python3
"""Instala el icono y la entrada de menú en el escritorio del usuario.

Sin esto la aplicación no aparece en el lanzador y la barra de tareas le pone
un icono genérico. Todo va a `~/.local/share`, así que no hace falta root y no
toca nada del sistema.

    python3 tools/install_desktop.py            # instalar
    python3 tools/install_desktop.py --uninstall

Los PNG se generan desde el SVG con Qt, que ya es dependencia de la interfaz:
así no hace falta tener rsvg-convert ni Inkscape.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SVG = ROOT / "cpuz" / "ui" / "assets" / "cpuz.svg"
DESKTOP_TEMPLATE = ROOT / "data" / "cpuz.desktop.in"

APP_ID = "cpuz"
# Los tamaños que pide la especificación de iconos de freedesktop, más los que
# usan en la práctica Plasma y GNOME para la barra de tareas.
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)


def data_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share"))


def icon_path(size: int) -> pathlib.Path:
    return data_home() / "icons" / "hicolor" / f"{size}x{size}" / "apps" / f"{APP_ID}.png"


def scalable_path() -> pathlib.Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def desktop_path() -> pathlib.Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


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
    if (script := shutil.which("cpuz-gui")):
        return script, ""
    return f"{sys.executable} -m cpuz.ui.app", str(ROOT)


def write_desktop() -> pathlib.Path:
    command, working_dir = resolve_exec()
    content = (
        DESKTOP_TEMPLATE.read_text(encoding="utf-8")
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
    """Avisa al escritorio. Ambas órdenes son opcionales: si no están, Plasma
    y GNOME acaban enterándose igual, solo que más tarde."""
    for command in (
        ["update-desktop-database", str(desktop_path().parent)],
        ["gtk-update-icon-cache", "-f", "-t", str(data_home() / "icons" / "hicolor")],
    ):
        if shutil.which(command[0]):
            subprocess.run(command, check=False, capture_output=True)


def uninstall(quiet: bool = False) -> int:
    removed = 0
    for path in [desktop_path(), scalable_path(), *(icon_path(s) for s in SIZES)]:
        if path.exists():
            path.unlink()
            removed += 1
    refresh_caches()
    if not quiet:
        print(f"Eliminados {removed} ficheros.")
    return 0


def install() -> int:
    icons = render_icons()
    entry = write_desktop()
    refresh_caches()

    print(f"Iconos:  {len(icons)} ficheros en {data_home() / 'icons' / 'hicolor'}")
    print(f"Entrada: {entry}")
    print(f"Lanzar:  {resolve_exec()[0]}")
    print("\nSi el lanzador no lo enseña todavía, cierra y vuelve a abrir la sesión.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uninstall", action="store_true", help="quitar icono y entrada de menú")
    args = parser.parse_args()
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())
