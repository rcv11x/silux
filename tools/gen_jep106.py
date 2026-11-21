#!/usr/bin/env python3
"""The JEDEC manufacturer codes (JEP106), from OpenOCD's copy of the list.

    python3 tools/gen_jep106.py            # downloads jep106.inc and writes the table
    python3 tools/gen_jep106.py --offline  # uses the cached copy

A memory module's SPD says who made it and who made its chips as a JEP106
code: a bank (how many continuation codes come before) and a code in it. A
hand-made table of 15 makers left every other one out, and had Kingston in
the wrong bank. OpenOCD keeps the whole list, revision by revision
(`src/helper/jep106.inc`), under GPL-2.0-or-later; its notice, with the
JEDEC copyright line it carries, is in THIRD_PARTY_NOTICES.md. This writes
`silux/db/jep106.json`, by bank (from 1) and code without its parity bit.

A new revision is a new JEP106_COMMIT, its date and hash, and running this.
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
OUTPUT = ROOT / "silux" / "db" / "jep106.json"
DEFAULT_CACHE = pathlib.Path.home() / ".cache" / "silux" / "sources"

REPO = "https://github.com/openocd-org/openocd"
JEP106_COMMIT = "d3e5f5787bea40f5f13c869647deb44b4c051ae0"
JEP106_DATE = "2026-09-12"
JEP106_FILE = "src/helper/jep106.inc"
JEP106_SHA256 = "92386f15139654b67e7756dcadd25881264bb7d8e8ea88386b96095855f5db5f"
JEP106_URL = f"https://raw.githubusercontent.com/openocd-org/openocd/{JEP106_COMMIT}/{JEP106_FILE}"

# «[1][0x18 - 1] = "Kingston",»: the bank from 0, the code from 1.
ENTRY = re.compile(r'^\[(\d+)\]\[0x([0-9a-fA-F]{2}) - 1\] = "((?:[^"\\]|\\.)*)",\s*$')
REVISION = re.compile(r"revision (JEP106[A-Z]+)")


def table(source: str) -> tuple[str, dict[str, dict[str, str]]]:
    """The revision and {bank (from 1): {code (two hex digits): name}}."""
    revision = REVISION.search(source)
    makers: dict[str, dict[str, str]] = {}
    for line in source.splitlines():
        found = ENTRY.match(line.strip())
        if found:
            bank, code, name = int(found.group(1)) + 1, int(found.group(2), 16), found.group(3)
            makers.setdefault(str(bank), {})[f"{code:02X}"] = name.replace('\\"', '"')
    if not makers or revision is None:
        raise SystemExit("jep106.inc no tiene la forma esperada")
    return revision.group(1), makers


def jep106(cache: pathlib.Path, offline: bool) -> str:
    path = cache / "openocd" / JEP106_COMMIT / "jep106.inc"
    if not path.exists():
        if offline:
            raise SystemExit(f"no hay copia de jep106.inc en {path} y se pidió --offline")
        print(f"  bajando jep106.inc de OpenOCD ({JEP106_COMMIT[:7]})…", file=sys.stderr)
        request = urllib.request.Request(JEP106_URL, headers={"User-Agent": "silux-gen-jep106"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != JEP106_SHA256:
        raise SystemExit(f"{path} no es el jep106.inc esperado (sha256 {digest})")
    return data.decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="no baja nada")
    parser.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    revision, makers = table(jep106(args.cache, args.offline))
    salida = {
        "schema": 1,
        "revision": revision,
        "sources": {"OpenOCD": {"repo": REPO, "commit": JEP106_COMMIT, "date": JEP106_DATE,
                                "file": JEP106_FILE}},
        "makers": makers,
    }
    OUTPUT.write_text(json.dumps(salida, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")
    total = sum(len(codes) for codes in makers.values())
    print(f"  {total} fabricantes en {len(makers)} bancos ({revision}) → "
          f"{OUTPUT.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
