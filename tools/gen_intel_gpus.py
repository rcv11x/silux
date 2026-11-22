#!/usr/bin/env python3
"""Intel graphics' commercial names by device ID, from Mesa's PCI ID tables.

    python3 tools/gen_intel_gpus.py            # downloads the tables and writes the JSON
    python3 tools/gen_intel_gpus.py --offline  # uses the cached copies

pci.ids names some Intel integrated graphics only by their family
(«4th Gen Core Processor Integrated Graphics Controller» for an HD Graphics
4600). Mesa keeps the name each device ID is sold as, from the HD Graphics
to the Arc, in `include/pci_ids/` (MIT, like most of Mesa; its notice is in
THIRD_PARTY_NOTICES.md); for older ones it gives the chipset's, which is
left out. This writes `silux/db/intel_gpus.json`: the lowercase hex ID and
its name, without «Intel(R)».

A new Mesa is a new MESA_TAG, the files' hashes, and running this.
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
OUTPUT = ROOT / "silux" / "db" / "intel_gpus.json"
DEFAULT_CACHE = pathlib.Path.home() / ".cache" / "silux" / "sources"

REPO = "https://gitlab.freedesktop.org/mesa/mesa"
MESA_TAG = "mesa-25.2.0"
FILES = {
    "include/pci_ids/crocus_pci_ids.h":
        "403b0aba8533e423b6ec2beb6c65a593db1ea4f31f16b4dcd1f543a8df0e95ff",
    "include/pci_ids/iris_pci_ids.h":
        "3c6a8c6d107a9f4f58e838dc926d435ce8950f88276a29653b06dd13f1e0184b",
}

# «CHIPSET(0x0416, hsw_gt2, "HSW GT2", "Intel(R) HD Graphics 4600")».
ENTRY = re.compile(r'^CHIPSET\(0x([0-9a-fA-F]{4}),\s*\w+,\s*"[^"]*",\s*"([^"]+)"\)')


def _url(path: str) -> str:
    return f"{REPO}/-/raw/{MESA_TAG}/{path}"


def _fetch(path: str, cache: pathlib.Path, offline: bool) -> str:
    local = cache / MESA_TAG / pathlib.Path(path).name
    if not local.exists():
        if offline:
            raise SystemExit(f"falta {local}: sin --offline se descarga")
        local.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(_url(path), timeout=60) as response:
            local.write_bytes(response.read())
    data = local.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != FILES[path]:
        raise SystemExit(f"{path} no es el de {MESA_TAG}: {digest}")
    return data.decode("utf-8")


def clean(name: str) -> str:
    """«Intel(R) Iris(R) Xe Graphics» → «Iris Xe Graphics»."""
    name = re.sub(r"\((?:R|TM|tm)\)", "", name)
    return " ".join(name.removeprefix("Intel").split())


def names_a_gpu(name: str) -> bool:
    """«HD Graphics 4600», «Data Center GPU Flex 170»: a graphics product.
    Not a chipset («965GM», «G41»), nor a bare «Graphics»."""
    return name != "Graphics" and ("Graphics" in name or "GPU" in name)


def parse(text: str) -> dict[str, str]:
    names = {}
    for line in text.splitlines():
        if (match := ENTRY.match(line.strip())) and names_a_gpu(clean(match.group(2))):
            names[match.group(1).lower()] = clean(match.group(2))
    return names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE)
    args = parser.parse_args(argv)
    names: dict[str, str] = {}
    for path in FILES:
        names.update(parse(_fetch(path, args.cache, args.offline)))
    table = {
        "schema": 1,
        "sources": {"Mesa": {"repo": REPO, "tag": MESA_TAG, "files": sorted(FILES)}},
        "devices": dict(sorted(names.items())),
    }
    OUTPUT.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(names)} gráficas de Intel → {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
