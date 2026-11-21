#!/usr/bin/env python3
"""Vuelca lo que leen los proveedores de este equipo, para la suite.

    python3 tools/volcar_equipo.py NOMBRE

Deja en `tests/fixtures/equipos/NOMBRE/` una copia anonimizada de lo que el
Collector lee de `/sys`, `/proc` y `/etc`, y en `grabado.json` lo que no sale
de un archivo. Cómo se hace y qué se tapa, en `silux/volcado.py`; aquí se
suma a lo que se busca lo que hay en `.privado`.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from silux import volcado  # noqa: E402
from silux.volcado import MANIFEST, mounted, snapshot_of  # noqa: E402,F401
from tools import comprobar_privacidad  # noqa: E402

DESTINO = RAIZ / "tests" / "fixtures" / "equipos"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("nombre", help="cómo se llama la carpeta: i5-10400, 5800x3d…")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", args.nombre):
        parser.error("el nombre, en minúsculas, cifras, puntos y guiones")
    destino = volcado.dump(args.nombre, DESTINO,
                             own=comprobar_privacidad._de_esta_maquina())
    tamano = sum(f.stat().st_size for f in destino.rglob("*") if f.is_file() and not f.is_symlink())
    print(f"  volcado en {destino.relative_to(RAIZ)} ({tamano / 1024:.0f} KB)")
    print("  pasado por privacidad.anonimizar y por los identificadores de "
          "comprobar_privacidad.py: limpio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
