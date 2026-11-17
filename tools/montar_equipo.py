#!/usr/bin/env python3
"""Ejecuta una orden con un equipo volcado montado, como lo montan los tests.

    python3 tools/montar_equipo.py i5-10400 python3 -m silux.ui.app --page Gráficos
    python3 tools/montar_equipo.py 5800x3d python3 -m silux.cli --json

`SILUX_SYSROOT` apuntando a la carpeta del repositorio no es lo mismo: git no
guarda carpetas vacías, y un volcado tiene muchas que cuentan (el
`drm/renderD128` de una gráfica es una). Con la variable a pelo, la integrada
del i5-10400 sale sin sus 23 unidades de ejecución, que están grabadas, y la
captura enseña un guion que el equipo de verdad no enseña. `montado`, de
`volcar_equipo.py`, copia el volcado, rehace las carpetas vacías y quita el
permiso a lo que no se dejaba leer; esto es su puerta desde la terminal.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tools import volcar_equipo  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("nombre", help="la carpeta del volcado: i5-10400, 5800x3d…")
    parser.add_argument("orden", nargs=argparse.REMAINDER,
                        help="lo que se ejecuta con el volcado montado")
    args = parser.parse_args(argv)
    carpeta = volcar_equipo.DESTINO / args.nombre
    if not (carpeta / volcar_equipo.MANIFIESTO).is_file():
        parser.error(f"no hay ningún volcado que se llame {args.nombre}")
    if not args.orden:
        parser.error("falta la orden")
    with volcar_equipo.montado(carpeta):
        # La variable ya está puesta en este proceso; la orden la hereda.
        return subprocess.run(args.orden).returncode


if __name__ == "__main__":
    sys.exit(main())
