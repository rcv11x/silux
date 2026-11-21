"""The command line's help, in the interface's language.

Shared by the terminal output (`cli.py`) and the window (`ui/app.py`):
options are in English, each with a Spanish alias that the help does not
show (`--informe` is `--report`), and everything `--help` says comes from
`db/lang`, also what argparse writes in English on its own: «usage»,
«options», «show this help message and exit».

It does not import Qt: the terminal help must work without a screen,
PySide6 or a processor Qt starts on.
"""

from __future__ import annotations

import argparse
import os
import sys

from .i18n import _


class _Format(argparse.RawDescriptionHelpFormatter):
    """argparse's, with «usage:» translated and the epilog as written (with
    its line breaks and indentation)."""

    def add_usage(self, usage, actions, groups, prefix=None):  # noqa: D401
        return super().add_usage(usage, actions, groups, prefix=_("cli.usage"))


class Parser(argparse.ArgumentParser):
    """An `ArgumentParser` that speaks the interface's language.

    `alias` adds an option's Spanish version without showing it in the help:
    it shares the English one's destination.
    """

    def __init__(self, prog: str, description: str, epilog: str = "") -> None:
        super().__init__(prog=prog, description=description, epilog=epilog or None,
                         formatter_class=_Format, add_help=False)
        self._optionals.title = _("cli.options")
        self.add_argument("-h", "--help", action="help", help=_("cli.help"))
        self.add_argument("--ayuda", action="help", help=argparse.SUPPRESS)

    def alias(self, spanish: str, *, of: str) -> None:
        """`spanish` does the same as the option `of`, without showing in the help."""
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
        """argparse's error, with its prefix in the interface's language. The
        message itself is argparse's and stays as it comes."""
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {_('cli.error')}: {message}\n")


def how_to_call() -> tuple[str, str]:
    """How the window and the terminal are called from wherever it runs.

    From the AppImage, the downloaded file and `--cli`; installed with pip,
    the package's two commands; from the code, the two modules. It is what
    the help puts in its examples, so they can be copied as they are.
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
    """Commands and what they do, in two columns whatever the command's length:
    from the code it is `python3 -m silux.cli`, from the AppImage
    `./silux-x86_64.AppImage`."""
    width = max(len(order) for order, _text in rows) + 3
    return "\n".join(f"  {order.ljust(width)}{text}" for order, text in rows)


def epilog_for_terminal() -> str:
    """What the window's help says of the terminal and the report."""
    _window, cli = how_to_call()
    help_text = f"{cli} --cli --help" if os.environ.get("APPIMAGE") else f"{cli} --help"
    rows = [(f"{cli} --report {_('cli.example.reportfile')}", _("cli.example.report")),
             (f"{cli} --json", _("cli.example.json")),
             (f"{cli} --sensors --watch", _("cli.example.sensors")),
             (help_text, _("gui.example.clihelp"))]
    return "\n\n".join([_("gui.epilog.title") + "\n" + _examples(rows),
                         _("gui.epilog.report")])


def epilog_for_cli() -> str:
    """The examples of the terminal's help."""
    _window, cli = how_to_call()
    rows = [(cli, _("cli.example.all")),
             (f"{cli} --report {_('cli.example.reportfile')}", _("cli.example.report")),
             (f"{cli} --sensors --watch", _("cli.example.sensors")),
             (f"{cli} --json", _("cli.example.json"))]
    return "\n\n".join([_("cli.epilog.title") + "\n" + _examples(rows),
                         _("cli.epilog.report")])
