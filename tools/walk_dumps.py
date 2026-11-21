#!/usr/bin/env python3
"""Open every page of every dump in both languages, and fail on any error.

    python3 tools/walk_dumps.py

The suite checks what pages show; this checks that nothing breaks on the way,
which matters after renaming code: a name left behind only fails when its
line runs. For each language and dump it takes the snapshot (which must have
no failures of Silux's own), opens the window, visits every section, gives it
a second sample and builds the full report. Exceptions raised in Qt slots
reach `sys.excepthook` and are counted too.
"""

from __future__ import annotations

import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from silux import i18n
    from silux.ui import full_report
    from tests import pantalla, qt
    from tests.test_equipos import foto, volcados

    errors: list[str] = []
    sys.excepthook = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
    qt.app()
    pages = 0
    for language in ("es", "en"):
        i18n.set_language(language)
        for dump in volcados():
            where = f"{language} {dump.name}"
            try:
                snapshot = foto(dump)[0]
                for failure in snapshot.failures:
                    errors.append(f"{where}: {failure.where}: {failure.error}\n{failure.trace}")
                with pantalla.Ventana(snapshot) as window:
                    for _key, _page in pantalla.recorrer(window):
                        pages += 1
                        window._on_sample(snapshot)
                full_report.build(snapshot)
            except Exception:                                      # noqa: BLE001
                errors.append(f"{where}:\n{traceback.format_exc()}")
    i18n.set_language("es")
    for error in errors:
        print(error)
    print(f"{pages} pages opened, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
