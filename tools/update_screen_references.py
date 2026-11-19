#!/usr/bin/env python3
"""Rewrite what each dumped machine shows, page by page, as a reference.

    python3 tools/update_screen_references.py          # all dumps
    python3 tools/update_screen_references.py 5800x3d  # one

For every dump in `tests/fixtures/equipos/`, the full report (every page, as
the window shows it) goes to `tests/fixtures/screens/NAME.md`.
`tests/test_screen_references.py` compares against these files, so a change
that alters how a machine is shown fails until this is run again and the
diff is reviewed in the commit.

What depends on the clock or on the build is masked: the header (version,
Python, Qt) and the boot time, which is now minus the dumped uptime.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCREENS = ROOT / "tests" / "fixtures" / "screens"
# "Encendido desde" is computed from the current time: it moves every minute.
_BOOT_TIME = re.compile(r"^(- (?:Encendido desde|Booted at|Up since)): .*$", re.M)


def normalize(report: str) -> str:
    """The report without what changes on its own."""
    body = report[report.index("\n## "):] if "\n## " in report else report
    return _BOOT_TIME.sub(r"\1: (hora de arranque)", body).strip() + "\n"


def screen(dump: pathlib.Path) -> str:
    """What the window shows for a dumped machine, normalized."""
    from silux.ui import full_report
    from tests import qt
    from tests.test_equipos import foto

    qt.app()
    return normalize(full_report.build(foto(dump)[0]))


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # The same language the suite reads (tests/__init__.py).
    os.environ["LANGUAGE"] = "es"
    sys.path.insert(0, str(ROOT))
    from tests.test_equipos import volcados

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="only these dumps")
    args = parser.parse_args()
    SCREENS.mkdir(parents=True, exist_ok=True)
    for dump in volcados():
        if args.names and dump.name not in args.names:
            continue
        target = SCREENS / f"{dump.name}.md"
        text = screen(dump)
        changed = not target.is_file() or target.read_text(encoding="utf-8") != text
        target.write_text(text, encoding="utf-8")
        print(f"{'cambia ' if changed else 'igual  '} {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
