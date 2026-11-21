#!/usr/bin/env python3
"""Save, and later compare, what each dump gives: its JSON and its report.

    python3 tools/dump_fingerprint.py --save       # before a change
    python3 tools/dump_fingerprint.py --compare    # after: exit 1 if anything moved

A change that only moves or renames code must leave every dump's `--json`
and `--report` exactly as they were. The screen references
(`tests/fixtures/screens/`) cover what the window shows; this covers the
model and the report, which hold what no page paints (notes' details,
failures, raw values).

The fingerprint lives outside the repository (`$XDG_CACHE_HOME/silux/fingerprint/`,
or `--dir`): it depends on the machine that runs it (which programs and
kernel modules it has), so it is only compared on the same machine.

What moves on its own is masked: the report's header (version, build,
Python, Qt), the boot time and the monotonic clock.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Fields that depend on when it runs, not on the dump.
CLOCK_FIELDS = ("monotonic_ns", "boot_time")
BOOT_TIME = re.compile(r"^(- (?:Encendido desde|Booted at|Up since)): .*$", re.M)


def default_dir() -> pathlib.Path:
    base = os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache"
    return pathlib.Path(base) / "silux" / "fingerprint"


def without_clock(value):
    if isinstance(value, dict):
        return {k: ("(clock)" if k in CLOCK_FIELDS else without_clock(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [without_clock(v) for v in value]
    return value


def normalized_report(text: str) -> str:
    body = text[text.index("\n## "):] if "\n## " in text else text
    return BOOT_TIME.sub(r"\1: (boot time)", body).strip() + "\n"


def fingerprint(dump: pathlib.Path) -> dict[str, str]:
    """The dump's JSON and report, as text that only changes with the code."""
    from silux import report
    from silux.model import to_jsonable
    from tests.test_equipos import foto

    snapshot = foto(dump)[0]
    data = json.dumps(without_clock(to_jsonable(snapshot)), indent=1,
                      ensure_ascii=False, sort_keys=True) + "\n"
    return {f"{dump.name}.json": data,
            f"{dump.name}.md": normalized_report(report.build(snapshot))}


def main() -> int:
    # Before importing the tests, which point the cache to a temporary folder.
    folder = default_dir()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # The same language the suite reads (tests/__init__.py).
    os.environ["LANGUAGE"] = "es"
    sys.path.insert(0, str(ROOT))
    from tests.test_equipos import volcados

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--save", action="store_true", help="save the fingerprint")
    mode.add_argument("--compare", action="store_true", help="compare with the saved one")
    parser.add_argument("--dir", type=pathlib.Path, default=folder)
    args = parser.parse_args()

    if args.save:
        args.dir.mkdir(parents=True, exist_ok=True)
        for old in args.dir.glob("*"):
            old.unlink()
    elif not args.dir.is_dir():
        print(f"No fingerprint in {args.dir}: run --save before the change.")
        return 2
    changed = 0
    for dump in volcados():
        for name, text in fingerprint(dump).items():
            saved = args.dir / name
            if args.save:
                saved.write_text(text, encoding="utf-8")
                continue
            before = saved.read_text(encoding="utf-8") if saved.is_file() else ""
            if before == text:
                print(f"same     {name}")
                continue
            changed += 1
            print(f"changed  {name}")
            sys.stdout.writelines(list(difflib.unified_diff(
                before.splitlines(True), text.splitlines(True), "before", "now", n=1))[:40])
    if args.save:
        print(f"Fingerprint saved in {args.dir}")
        return 0
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
