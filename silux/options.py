"""La ayuda de la línea de órdenes, en el idioma de la interfaz.

Lo comparten el volcado en terminal (`cli.py`) y la ventana (`ui/app.py`):
las opciones van en inglés, cada una con su alias en español que no sale en
la ayuda (`--informe` es `--report`), y todo lo que dice `--help` sale de
`db/lang`, también lo que argparse escribe en inglés por su cuenta: «usage»,
«options», «show this help message and exit».

No importa Qt: la ayuda de la terminal tiene que salir aunque no haya
pantalla, ni PySide6, ni un procesador en el que arranque Qt.
"""

from __future__ import annotations

import argparse
import os
import sys

from .i18n import _


class _Formato(argparse.RawDescriptionHelpFormatter):
    """El de argparse, con «uso:» traducido y el epílogo tal y como se
    escribe (con sus saltos de línea y su sangría)."""

    def add_usage(self, usage, actions, groups, prefix=None):  # noqa: D401
        return super().add_usage(usage, actions, groups, prefix=_("cli.usage"))


class Parser(argparse.ArgumentParser):
    """Un `ArgumentParser` que habla el idioma de la interfaz.

    `alias` añade la versión en español de una opción sin enseñarla en la
    ayuda: comparte destino con la inglesa.
    """

    def __init__(self, prog: str, description: str, epilog: str = "") -> None:
        super().__init__(prog=prog, description=description, epilog=epilog or None,
                         formatter_class=_Formato, add_help=False)
        self._optionals.title = _("cli.options")
        self.add_argument("-h", "--help", action="help", help=_("cli.help"))
        self.add_argument("--ayuda", action="help", help=argparse.SUPPRESS)

    def alias(self, espanol: str, *, de: str) -> None:
        """`espanol` hace lo mismo que la opción `de`, sin salir en la ayuda."""
        original = next(a for a in self._actions if de in a.option_strings)
        argumentos = dict(dest=original.dest, help=argparse.SUPPRESS)
        if isinstance(original, argparse._StoreTrueAction):
            argumentos["action"] = "store_true"
        elif isinstance(original, argparse._VersionAction):
            argumentos.update(action="version", version=original.version)
            argumentos.pop("dest")
        else:
            argumentos.update(nargs=original.nargs, const=original.const,
                              type=original.type, metavar=original.metavar,
                              choices=original.choices)
        self.add_argument(espanol, **argumentos)

    def error(self, message: str):  # noqa: D401
        """El error de argparse, con el prefijo en el idioma de la interfaz.
        El mensaje en sí lo escribe argparse y se deja como viene."""
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {_('cli.error')}: {message}\n")


def how_to_call() -> tuple[str, str]:
    """Cómo se llama a la ventana y a la terminal desde donde se esté.

    Desde el AppImage, el archivo que se descargó y `--cli`; instalado con
    pip, las dos órdenes del paquete; desde el código, los dos módulos. Es lo
    que la ayuda pone en sus ejemplos, para que se puedan copiar tal cual.
    """
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        archivo = "./" + os.path.basename(appimage)
        return archivo, archivo
    programa = os.path.basename(sys.argv[0] if sys.argv else "")
    if programa in ("silux", "silux-gui"):
        return "silux-gui", "silux"
    return "python3 -m silux.ui.app", "python3 -m silux.cli"


def _ejemplos(filas: list[tuple[str, str]]) -> str:
    """Órdenes y lo que hacen, en dos columnas, sea cual sea el largo de la
    orden: desde el código se llama `python3 -m silux.cli` y desde el
    AppImage `./silux-x86_64.AppImage`."""
    ancho = max(len(orden) for orden, _texto in filas) + 3
    return "\n".join(f"  {orden.ljust(ancho)}{texto}" for orden, texto in filas)


def epilog_for_terminal() -> str:
    """Lo que la ayuda de la ventana cuenta de la terminal y del informe."""
    _ventana, cli = how_to_call()
    ayuda = f"{cli} --cli --help" if os.environ.get("APPIMAGE") else f"{cli} --help"
    filas = [(f"{cli} --report {_('cli.example.reportfile')}", _("cli.example.report")),
             (f"{cli} --json", _("cli.example.json")),
             (f"{cli} --sensors --watch", _("cli.example.sensors")),
             (ayuda, _("gui.example.clihelp"))]
    return "\n\n".join([_("gui.epilog.title") + "\n" + _ejemplos(filas),
                         _("gui.epilog.report")])


def epilog_for_cli() -> str:
    """Los ejemplos de la ayuda de la terminal."""
    _ventana, cli = how_to_call()
    filas = [(cli, _("cli.example.all")),
             (f"{cli} --report {_('cli.example.reportfile')}", _("cli.example.report")),
             (f"{cli} --sensors --watch", _("cli.example.sensors")),
             (f"{cli} --json", _("cli.example.json"))]
    return "\n\n".join([_("cli.epilog.title") + "\n" + _ejemplos(filas),
                         _("cli.epilog.report")])
