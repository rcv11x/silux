#!/usr/bin/env python3
"""Genera `silux/db/cpu_ids.json` a partir de las fuentes de libcpuid y CPU-X.

La identificación de un procesador (nombre en clave, nodo de fabricación,
socket) no se puede deducir del hardware: es una tabla de correspondencias que
alguien tiene que mantener. libcpuid lleva más de una década manteniéndola, y
sus tablas son datos tabulares regulares, no lógica. Este script las convierte
a JSON para que actualizar la base de datos sea volver a ejecutarlo, no editar
código y recompilar.

    python3 tools/gen_cpu_db.py                # clona/actualiza y genera
    python3 tools/gen_cpu_db.py --offline      # usa lo que ya haya en caché

Fuentes y licencias:
  · libcpuid  ( BSD 2 cláusulas ) https://github.com/anrieff/libcpuid
  · CPU-X     ( GPL-3.0         ) https://github.com/TheTumultuousUnicornOfDarkness/CPU-X
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CACHE = pathlib.Path.home() / ".cache" / "silux" / "sources"

REPOS = {
    "libcpuid": "https://github.com/anrieff/libcpuid.git",
    "cpu-x": "https://github.com/TheTumultuousUnicornOfDarkness/CPU-X.git",
}

# --------------------------------------------------------------------------
# utilidades de texto C
# --------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def strip_comments(source: str) -> str:
    """Quita comentarios para que una fila comentada no acabe en la base."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))


def extract_array(source: str, declaration: str) -> str:
    """Devuelve el cuerpo de un array de C, desde `= {` hasta su `};`."""
    start = source.find(declaration)
    if start < 0:
        raise LookupError(f"no encuentro la declaración: {declaration!r}")
    open_brace = source.index("{", start)
    depth = 0
    for i in range(open_brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : i]
    raise LookupError(f"array sin cerrar: {declaration!r}")


def unquote(token: str) -> str | None:
    """Traduce un literal de C a un valor de Python (`UNKN_STR`/`NULL` -> None)."""
    token = token.strip()
    if token in ("UNKN_STR", "NULL", ""):
        return None
    if token.startswith('"') and token.endswith('"'):
        value = token[1:-1].encode().decode("unicode_escape")
        return value or None
    return token


# --------------------------------------------------------------------------
# tablas x86 de libcpuid: struct match_entry_t
# --------------------------------------------------------------------------

# Las tablas mezclan decimal y hexadecimal en el mismo campo (ext_model de AMD).
_INT = r"\s*(-?(?:0[xX][0-9A-Fa-f]+|\d+))\s*"
_STR = r'\s*"((?:[^"\\]|\\.)*)"\s*'
_X86_ROW = re.compile(
    r"\{" + _INT + r"," + _INT + r"," + _INT + r"," + _INT + r"," + _INT + r","
    + _INT + r"," + _INT + r"," + _INT + r","
    r"\s*\{" + _STR + r"," + _INT + r"\}\s*,"
    + _STR + r","
    r"\s*(UNKN_STR|\"(?:[^\"\\]|\\.)*\")\s*\}"
)


def parse_x86_table(source: str, declaration: str) -> list[dict]:
    body = extract_array(strip_comments(source), declaration)
    rows: list[dict] = []
    for m in _X86_ROW.finditer(body):
        (family, model, stepping, ext_family, ext_model, ncores, l2, l3,
         brand_pattern, brand_score, name, technology) = m.groups()
        rows.append(
            {
                "f": int(family, 0), "m": int(model, 0), "s": int(stepping, 0),
                "xf": int(ext_family, 0), "xm": int(ext_model, 0),
                "nc": int(ncores, 0), "l2": int(l2, 0), "l3": int(l3, 0),
                "bp": brand_pattern or None,
                "bs": int(brand_score, 0),
                "name": name,
                "tech": unquote(technology),
            }
        )
    if not rows:
        raise LookupError(f"la tabla {declaration!r} salió vacía; ¿cambió el formato?")
    return rows


# --------------------------------------------------------------------------
# tablas ARM de libcpuid: implementer -> part number -> nombre
# --------------------------------------------------------------------------

_ARM_PART_ROW = re.compile(
    r"\{\s*(-?(?:0x)?[0-9A-Fa-f]+)\s*,"
    + _STR + r","
    r"\s*(UNKN_STR|\"(?:[^\"\\]|\\.)*\")\s*,"
    r"\s*(UNKN_STR|\"(?:[^\"\\]|\\.)*\")\s*\}"
)
_ARM_IMPL_ROW = re.compile(
    r"\{\s*(-?(?:0x)?[0-9A-Fa-f]+)\s*,\s*VENDOR_\w+\s*,\s*(\w+)\s*," + _STR + r"\}"
)


def parse_arm_tables(source: str) -> dict:
    clean = strip_comments(source)

    parts_by_symbol: dict[str, dict[str, dict]] = {}
    for m in re.finditer(r"static const struct arm_id_part (\w+)\[\]", clean):
        symbol = m.group(1)
        body = extract_array(clean[m.start():], f"arm_id_part {symbol}[]")
        entries: dict[str, dict] = {}
        for row in _ARM_PART_ROW.finditer(body):
            part_id = int(row.group(1), 0)
            if part_id < 0:            # centinela de fin de tabla
                continue
            entries[str(part_id)] = {
                "name": row.group(2),
                "codename": unquote(row.group(3)),
                "tech": unquote(row.group(4)),
            }
        parts_by_symbol[symbol] = entries

    implementers: dict[str, dict] = {}
    for row in _ARM_IMPL_ROW.finditer(extract_array(clean, "arm_hw_impl hw_implementer[]")):
        impl_id = int(row.group(1), 0)
        if impl_id < 0:
            continue
        implementers[str(impl_id)] = {
            "vendor": row.group(3),
            "parts": parts_by_symbol.get(row.group(2), {}),
        }
    return implementers


# --------------------------------------------------------------------------
# tabla de sockets de CPU-X: struct Package_DB
# --------------------------------------------------------------------------

_SOCKET_ROW = re.compile(
    r"\{\s*(NULL|\"(?:[^\"\\]|\\.)*\")\s*,"
    r"\s*(NULL|\"(?:[^\"\\]|\\.)*\")\s*,"
    r"\s*(NULL|\"(?:[^\"\\]|\\.)*\")\s*\}"
)


def parse_socket_table(source: str, declaration: str) -> list[dict]:
    body = extract_array(strip_comments(source), declaration)
    rows = []
    for m in _SOCKET_ROW.finditer(body):
        codename, model, socket = (unquote(g) for g in m.groups())
        if socket is None:
            continue                   # centinela de fin de tabla
        rows.append({"codename": codename, "model": model, "socket": socket})
    return rows


# --------------------------------------------------------------------------
# obtención de las fuentes
# --------------------------------------------------------------------------


def git(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def ensure_source(name: str, cache: pathlib.Path, offline: bool) -> pathlib.Path:
    path = cache / name
    if path.exists():
        if not offline:
            print(f"  actualizando {name}…", file=sys.stderr)
            try:
                git("fetch", "--depth", "1", "origin", cwd=path)
                git("reset", "--hard", "FETCH_HEAD", cwd=path)
            except subprocess.CalledProcessError as exc:
                print(f"  aviso: no se pudo actualizar {name} ({exc}); sigo con la copia local",
                      file=sys.stderr)
        return path
    if offline:
        raise SystemExit(f"no hay copia de {name} en {path} y se pidió --offline")
    print(f"  clonando {name}…", file=sys.stderr)
    cache.mkdir(parents=True, exist_ok=True)
    git("clone", "--depth", "1", REPOS[name], str(path))
    return path


def provenance(path: pathlib.Path, url: str) -> dict:
    return {
        "repo": url,
        "commit": git("rev-parse", "--short", "HEAD", cwd=path),
        "date": git("log", "-1", "--format=%cd", "--date=short", cwd=path),
    }


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE,
                        help=f"dónde guardar los clones (por defecto {DEFAULT_CACHE})")
    parser.add_argument("--libcpuid", type=pathlib.Path, help="ruta a un clon de libcpuid ya existente")
    parser.add_argument("--cpux", type=pathlib.Path, help="ruta a un clon de CPU-X ya existente")
    parser.add_argument("--offline", action="store_true", help="no tocar la red")
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "silux" / "db" / "cpu_ids.json")
    args = parser.parse_args()

    print("Obteniendo fuentes:", file=sys.stderr)
    libcpuid = args.libcpuid or ensure_source("libcpuid", args.cache, args.offline)
    cpux = args.cpux or ensure_source("cpu-x", args.cache, args.offline)

    print("Parseando tablas:", file=sys.stderr)
    intel_src = (libcpuid / "libcpuid" / "recog_intel.c").read_text(encoding="utf-8")
    amd_src = (libcpuid / "libcpuid" / "recog_amd.c").read_text(encoding="utf-8")
    arm_src = (libcpuid / "libcpuid" / "recog_arm.c").read_text(encoding="utf-8")
    databases_src = (cpux / "src" / "core" / "databases.h").read_text(encoding="utf-8")

    x86 = {
        "GenuineIntel": parse_x86_table(intel_src, "match_entry_t cpudb_intel[]"),
        "AuthenticAMD": parse_x86_table(amd_src, "match_entry_t cpudb_amd[]"),
    }
    arm = parse_arm_tables(arm_src)
    sockets = {
        "GenuineIntel": parse_socket_table(databases_src, "Package_DB package_intel[]"),
        "AuthenticAMD": parse_socket_table(databases_src, "Package_DB package_amd[]"),
    }

    payload = {
        "schema": 1,
        "sources": {
            "libcpuid": provenance(libcpuid, REPOS["libcpuid"]),
            "cpu-x": provenance(cpux, REPOS["cpu-x"]),
        },
        "counts": {
            "x86_intel": len(x86["GenuineIntel"]),
            "x86_amd": len(x86["AuthenticAMD"]),
            "arm_implementers": len(arm),
            "arm_parts": sum(len(v["parts"]) for v in arm.values()),
            "sockets": sum(len(v) for v in sockets.values()),
        },
        "x86": x86,
        "arm": arm,
        "sockets": sockets,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")

    size_kb = args.out.stat().st_size / 1024
    print(f"\nEscrito {args.out} ({size_kb:.0f} KB)", file=sys.stderr)
    for key, value in payload["counts"].items():
        print(f"  {key:<18} {value:>5}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
