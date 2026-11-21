"""Command line help in the interface language.

Shared by the terminal (`cli.py`) and the window (`ui/app.py`). Options are
in English, each with a hidden Spanish alias (`--informe` is `--report`),
and everything `--help` prints comes from `db/lang`, including the parts
argparse writes in English on its own («usage», «options», «show this help
message and exit»).

No Qt here: terminal help must work without a display, PySide6, or a CPU Qt
can start on.
"""

from __future__ import annotations

import argparse
import os
import sys

from .i18n import _


class _Format(argparse.RawDescriptionHelpFormatter):
    """argparse's formatter, with «usage:» translated and the epilog kept as
    written."""

    def add_usage(self, usage, actions, groups, prefix=None):  # noqa: D401
        return super().add_usage(usage, actions, groups, prefix=_("cli.usage"))


class Parser(argparse.ArgumentParser):
    """An `ArgumentParser` that speaks the interface language.

    `alias` adds a hidden Spanish spelling of an option, sharing its
    destination.
    """

    def __init__(self, prog: str, description: str, epilog: str = "") -> None:
        super().__init__(prog=prog, description=description, epilog=epilog or None,
                         formatter_class=_Format, add_help=False)
        self._optionals.title = _("cli.options")
        self.add_argument("-h", "--help", action="help", help=_("cli.help"))
        self.add_argument("--ayuda", action="help", help=argparse.SUPPRESS)

    def alias(self, spanish: str, *, of: str) -> None:
        """`spanish` does what `of` does, without showing in the help."""
        original = next(a for a in self._actions if of in a.option_strings)
        arguments = dict(dest=original.dest, help=argparse.SUPPRESS)
        if isinstance(original, argparse._StoreTrueAction):
            arguments["action"] = "store_true"
        elif isinstance(original, argparse._VersionAction):
            arguments.update(action="version", version=original.version)
            arguments.pop("dest")
        else:
            arguments.update(nargs=original.nargs, const=original.const,
                              type=original.type, metavar=original.metavar,
                              choices=original.choices)
        self.add_argument(spanish, **arguments)

    def error(self, message: str):  # noqa: D401
        """argparse's error with its prefix translated; the message itself
        stays as argparse wrote it."""
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {_('cli.error')}: {message}\n")


def how_to_call() -> tuple[str, str]:
    """How to run the window and the terminal from wherever Silux runs.

    The AppImage file and `--cli`; with pip, the package's two commands; from
    a checkout, the two modules. The help's examples use them so they can be
    copied as they are.
    """
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        file_name = "./" + os.path.basename(appimage)
        return file_name, file_name
    program = os.path.basename(sys.argv[0] if sys.argv else "")
    if program in ("silux", "silux-gui"):
        return "silux-gui", "silux"
    return "python3 -m silux.ui.app", "python3 -m silux.cli"


def _examples(rows: list[tuple[str, str]]) -> str:
    """Commands and what they do, in two aligned columns whatever the
    command's length (`python3 -m silux.cli` or `./silux-x86_64.AppImage`)."""
    width = max(len(order) for order, _text in rows) + 3
    return "\n".join(f"  {order.ljust(width)}{text}" for order, text in rows)


def epilog_for_terminal() -> str:
    """What the window's help says about the terminal and the report."""
    _window, cli = how_to_call()
    help_text = f"{cli} --cli --help" if os.environ.get("APPIMAGE") else f"{cli} --help"
    rows = [(f"{cli} --report {_('cli.example.reportfile')}", _("cli.example.report")),
             (f"{cli} --json", _("cli.example.json")),
             (f"{cli} --sensors --watch", _("cli.example.sensors")),
             (help_text, _("gui.example.clihelp"))]
    return "\n\n".join([_("gui.epilog.title") + "\n" + _examples(rows),
                         _("gui.epilog.report")])


def epilog_for_cli() -> str:
    """The terminal help's examples."""
    _window, cli = how_to_call()
    rows = [(cli, _("cli.example.all")),
             (f"{cli} --report {_('cli.example.reportfile')}", _("cli.example.report")),
             (f"{cli} --sensors --watch", _("cli.example.sensors")),
             (f"{cli} --json", _("cli.example.json"))]
    return "\n\n".join([_("cli.epilog.title") + "\n" + _examples(rows),
                         _("cli.epilog.report")])
