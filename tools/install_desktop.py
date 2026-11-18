#!/usr/bin/env python3
"""Instala el icono y la entrada de menú en el escritorio del usuario.

    python3 tools/install_desktop.py              # instalar o poner al día
    python3 tools/install_desktop.py --escritorio # y un acceso en el escritorio
    python3 tools/install_desktop.py --estado     # cómo está, sin tocar nada
    python3 tools/install_desktop.py --uninstall

Desde el repositorio instala «Silux (desarrollo)», `silux-dev.desktop`, que
no pisa la entrada del AppImage. Lo que hace está en `silux/desktop.py`, que
es lo mismo que usa el botón de Ajustes: una sola implementación para los dos.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from silux import desktop  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uninstall", action="store_true", help="quitar icono y entrada de menú")
    parser.add_argument("--escritorio", action="store_true",
                        help="poner también un acceso en el escritorio")
    parser.add_argument("--estado", action="store_true",
                        help="decir cómo está la entrada y no tocar nada")
    args = parser.parse_args()

    lanzador = desktop.current_launcher()
    estado = desktop.status(lanzador)
    print(f"Ahora:   {estado.state}" + (f" ({estado.target})" if estado.target else "")
          + (" · con acceso en el escritorio" if estado.on_desktop else ""))
    if args.estado:
        return 0
    if args.uninstall:
        print(f"Eliminados {desktop.uninstall(lanzador)} ficheros.")
        return 0

    try:
        icons, entry = desktop.install(lanzador, on_desktop=True if args.escritorio else None)
    except desktop.DesktopError as error:
        print(f"No se pudo instalar: {error}", file=sys.stderr)
        return 1
    print(f"Entrada: {entry} («{lanzador.name}»)")
    print(f"Iconos:  {len(icons)} ficheros en {desktop.hicolor()}")
    print(f"Lanzar:  {desktop.exec_line(lanzador.command)}")
    if lanzador.working_dir:
        print(f"Desde:   {lanzador.working_dir}")
    if desktop.shortcut_path(lanzador.app_id).is_file():
        print(f"Acceso:  {desktop.shortcut_path(lanzador.app_id)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
