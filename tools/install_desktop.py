#!/usr/bin/env python3
"""Instala el icono y la entrada de menú en el escritorio del usuario.

    python3 tools/install_desktop.py            # instalar
    python3 tools/install_desktop.py --uninstall

Lo que hace está en `silux/desktop.py`, que es lo mismo que usa el botón de
Ajustes: una sola implementación para los dos.
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
    args = parser.parse_args()

    if args.uninstall:
        print(f"Eliminados {desktop.uninstall()} ficheros.")
        return 0

    icons, entry = desktop.install()
    print(f"Iconos:  {len(icons)} ficheros en {desktop.data_home() / 'icons' / 'hicolor'}")
    print(f"Entrada: {entry}")
    print(f"Lanzar:  {desktop.resolve_exec()[0]}")
    print("\nSi el lanzador no lo enseña todavía, cierra y vuelve a abrir la sesión.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
