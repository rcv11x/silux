#!/usr/bin/env python3
"""Convierte el anexo de un informe en un volcado para los tests.

    python3 tools/importar_informe.py INFORME NOMBRE

Lee el bloque `silux-annex` del final de un informe completo (el que manda la
gente) y deja en `tests/fixtures/equipos/NOMBRE/` el volcado que
`tools/volcar_equipo.py` habría escrito en ese equipo. Antes de darlo por
bueno comprueba que se monta y que no lleva nada de lo que
`tools/comprobar_privacidad.py` caza en un volcado; si algo falla, no deja
nada. Después, como con cualquier volcado nuevo:
`tools/update_screen_references.py`, y revisar el diff.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from silux import annex, volcado  # noqa: E402
from tools import comprobar_privacidad  # noqa: E402

TARGET = ROOT / "tests" / "fixtures" / "equipos"


def import_report(report: pathlib.Path, name: str, base: pathlib.Path = TARGET):
    """The dump in `base/name`, and the snapshot the Collector reads from it."""
    target = base / name
    if target.exists():
        raise SystemExit(f"ya existe {target}: bórralo antes para importarlo otra vez")
    try:
        block = annex.find(pathlib.Path(report).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, annex.AnnexError) as error:
        raise SystemExit(f"{report}: {error}") from None
    with tempfile.TemporaryDirectory(prefix="silux-importar-") as tmp:
        work = pathlib.Path(tmp) / name
        try:
            annex.to_folder(block, work)
        except (annex.AnnexError, OSError) as error:
            raise SystemExit(f"{report}: {error}") from None
        if not (work / volcado.MANIFEST).is_file():
            raise SystemExit(f"{report}: el anexo no trae {volcado.MANIFEST}; no es un volcado")
        volcado.bring_up_to_date(work)
        # Checked as what it will be: a dump of the suite.
        found = comprobar_privacidad.revisar(
            [p for p in sorted(work.rglob("*")) if p.is_file() and not p.is_symlink()], {},
            where=lambda p: f"tests/fixtures/equipos/{name}/{p.relative_to(work).as_posix()}")
        if found:
            raise SystemExit("El anexo lleva lo que un volcado no puede llevar; no se deja "
                             "nada:\n  " + "\n  ".join(found[:20]))
        photo = volcado.snapshot_of(work)
        # What an older version wrote of it may not be what this one reads.
        volcado.describe(work, photo)
        shutil.copytree(work, target, symlinks=True)
    return target, photo


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("informe", type=pathlib.Path, help="el informe completo que mandaron")
    parser.add_argument("nombre", help="cómo se llama la carpeta: i5-12450h, 7800x3d…")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", args.nombre):
        parser.error("el nombre, en minúsculas, cifras, puntos y guiones")
    target, photo = import_report(args.informe, args.nombre)
    cpu = photo.cpu.types[0].brand if photo.cpu.types else "sin procesador"
    print(f"  volcado en {target.relative_to(ROOT)}: {cpu}")
    print("  lo siguiente: tools/update_screen_references.py, y revisar el diff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
