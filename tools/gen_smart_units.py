#!/usr/bin/env python3
"""The unit of each disk's write and read counters, from smartmontools.

    python3 tools/gen_smart_units.py            # downloads drivedb.h and writes the table
    python3 tools/gen_smart_units.py --offline  # uses the cached copy

SMART attribute 241 is called «LBAs written» and most drives count 512-byte
sectors, but not all: a Kingston A400 counts GiB, and read as sectors its
73 TB came out as 33 MB. smartmontools' drive database names each attribute
per model, and the name says the unit (`Lifetime_Writes_GiB`,
`Host_Writes_32MiB`, `Total_LBAs_Written`). This keeps, for every entry
whose names say it, the model and firmware patterns and the bytes per unit
of 241, 242, 246 and 247, in `silux/db/smart_units.json`.

drivedb.h is GPL-2.0-or-later; its notice is in THIRD_PARTY_NOTICES.md. A new
version is a new DRIVEDB_COMMIT and its hash, and running this again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "silux" / "db" / "smart_units.json"
DEFAULT_CACHE = pathlib.Path.home() / ".cache" / "silux" / "sources"

REPO = "https://github.com/smartmontools/smartmontools"
# The drivedb/8.0 branch, which smartmontools keeps updating between releases.
DRIVEDB_BRANCH = "drivedb/8.0"
DRIVEDB_COMMIT = "a8be76c60557f67b15eca314d56e166764521059"
DRIVEDB_DATE = "2026-09-09"
DRIVEDB_FILE = "drivedb/drivedb.h"
DRIVEDB_SHA256 = "285d8c3ce5fd90082bce24b5d09765656d2d935f8adb348c8b2d7c5bcc771242"
DRIVEDB_URL = (f"https://raw.githubusercontent.com/smartmontools/smartmontools/"
               f"{DRIVEDB_COMMIT}/{DRIVEDB_FILE}")

# The counters Silux reads: written (241, and 246 on Crucial and Micron) and
# read (242, 247).
ATTRIBUTES = (241, 242, 246, 247)

MIB = 1024 ** 2
GIB = 1024 ** 3
# How the end of an attribute's name says its unit. What counts the flash
# instead of the host (NAND programs, sectors written to NAND) is not what
# the computer wrote: `None`, so Silux shows nothing rather than that.
UNITS = (
    (re.compile(r"_32MiB$"), 32 * MIB),
    (re.compile(r"_MiB$"), MIB),
    (re.compile(r"_GiB$"), GIB),
    (re.compile(r"_GB$"), 1000 ** 3),
    (re.compile(r"LBAs?_(Written|Read)$"), 512),
    (re.compile(r"NAND|Nand", re.I), None),
)
PRESET = re.compile(r"-v\s+(\d+),([^,\s]+),(\S+)")


def tokens(source: str):
    """The C tokens that matter: string literals, braces and commas.

    Comments are skipped only outside strings, because the warnings carry
    URLs with «//» inside.
    """
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if source.startswith("//", i):
            i = source.find("\n", i)
            i = n if i < 0 else i
        elif source.startswith("/*", i):
            i = source.index("*/", i) + 2
        elif c == '"':
            j, out = i + 1, []
            while source[j] != '"':
                if source[j] == "\\":
                    out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(
                        source[j + 1], source[j + 1]))
                    j += 2
                else:
                    out.append(source[j])
                    j += 1
            yield ("str", "".join(out))
            i = j + 1
        elif c in "{},":
            yield (c, c)
            i += 1
        else:
            i += 1


def entries(source: str) -> list[list[str]]:
    """Each `{ family, model, firmware, warning, presets }`, strings joined.

    The innermost braces: the file in smartmontools' drivedb branches is the
    bare list, without the array declaration that wraps it in its source.
    """
    found, current, field = [], None, None
    for kind, value in tokens(source):
        if kind == "{":
            current, field = [], ""
        elif kind == "}":
            if current is not None:
                current.append(field)
                found.append(current)
                current = None
        elif kind == "," and current is not None:
            current.append(field)
            field = ""
        elif kind == "str" and current is not None:
            field += value
    return [e for e in found if len(e) == 5]


def unit_of(name: str):
    for pattern, unit in UNITS:
        if pattern.search(name):
            return True, unit
    return False, None


def table(source: str) -> list[dict]:
    rows = []
    for family, model, firmware, _warning, presets in entries(source):
        # «$» disables an entry, «USB:» describes a bridge, and DEFAULT and
        # VERSION are not drives.
        if (not model or family.startswith(("$", "USB:"))
                or family in ("DEFAULT", "VERSION")):
            continue
        units = {}
        for attribute, raw_format, name in PRESET.findall(presets):
            if int(attribute) not in ATTRIBUTES or not raw_format.startswith("raw"):
                continue
            known, unit = unit_of(name)
            if known:
                units[attribute] = unit
        if units:
            rows.append({"family": family, "model": model, "firmware": firmware,
                         "units": units})
    return rows


def drivedb(cache: pathlib.Path, offline: bool) -> str:
    path = cache / "smartmontools" / DRIVEDB_COMMIT / "drivedb.h"
    if not path.exists():
        if offline:
            raise SystemExit(f"no hay copia de drivedb.h en {path} y se pidió --offline")
        print(f"  bajando drivedb.h de {DRIVEDB_BRANCH} ({DRIVEDB_COMMIT[:7]})…", file=sys.stderr)
        request = urllib.request.Request(DRIVEDB_URL,
                                         headers={"User-Agent": "silux-gen-smart-units"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != DRIVEDB_SHA256:
        raise SystemExit(f"{path} no es el drivedb.h esperado (sha256 {digest})")
    return data.decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="no baja nada")
    parser.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    rows = table(drivedb(args.cache, args.offline))
    for row in rows:
        re.compile(row["model"])
        re.compile(row["firmware"] or "")
    salida = {
        "schema": 1,
        "sources": {"smartmontools": {
            "repo": REPO, "branch": DRIVEDB_BRANCH, "commit": DRIVEDB_COMMIT,
            "date": DRIVEDB_DATE, "file": DRIVEDB_FILE}},
        "drives": rows,
    }
    OUTPUT.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  {len(rows)} entradas con la unidad de sus contadores → {OUTPUT.relative_to(ROOT)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
