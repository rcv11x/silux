# Contributing

Thanks for wanting to help. The detailed guide, with the reason behind each
convention, is [docs/convenciones.md](docs/convenciones.md) (in Spanish
until 0.4); this is the short version.

## The most useful contribution: your machine's report

Silux gets better with every machine it sees. Open it, go to Settings and
save the full report, or run

```bash
./silux-x86_64.AppImage --report report.md
```

and attach it to an [issue](https://github.com/rcv11x/silux/issues/new/choose).
It covers the machine's name, addresses and serial numbers, but read it
before publishing. Its annex lets us replay your machine in the tests.

## Setting up

```bash
uv sync --extra gui
QT_QPA_PLATFORM=offscreen uv run pytest -n auto -m "not a_solas"
QT_QPA_PLATFORM=offscreen uv run pytest -m a_solas
```

The floor is Python 3.10: passing on a recent Python says nothing about
3.10. `tools/probar_en_minimo.py --container` runs the suite there.

## Changes

- One branch per topic, from `master`, and a pull request.
- What touches privileges (the helper, polkit, what is read as root) is
  proposed in an issue before it is written.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/),
  in English and short: `fix(providers/hwmon): what changes`. One commit
  per logical change, with its test.
- New code, comments and docstrings in English, PEP 8. Comments say why the
  code is the way it is, not what it does, and never name a person or a
  specific machine: that goes in the test or its dump.
- The interface is in Spanish and English (`silux/db/lang/`). Logic never
  decides on a translated text, and `_()` is never called in a module
  constant.

## Tests

- A check nobody has seen fail is not a check: run each new test against
  the case it is meant to catch.
- A new value is not done until a test sees it on screen, on a real page.
- No test builds by hand a state the real program cannot produce.
- A test that reads the machine running it does not require finding
  something specific: CI machines have none of it.
- A visual change is checked in a screenshot (`--screenshot`, see the
  README), never only in the code.

## Reporting a security problem

Privately, as [SECURITY.md](SECURITY.md) says.
