"""Loads a kernel sensor module and keeps it for the next boot.

The program already detects which module would give missing data and says
so: «loading drivetemp you'd have the SATA disks' temperature». That leaves
the user with a command to copy into a terminal, and for most the road ends
there.

It does two things: `modprobe` for now and a line in `/etc/modules-load.d/`
for the following boots. The second is the half that matters (a lone
`modprobe` is lost on reboot) and also the one nobody remembers.

**The module's name doesn't come from outside.** It's checked against the
list below before touching anything: a helper running as root that loads
whatever module it's told loads any module on the system, which isn't what's
needed. The list is what the program itself may suggest, and they only read
sensors.

    sudo python3 -m silux.privileged.cargar_modulo drivetemp

It lives in the package and imports nothing from `silux` for the same
reason as `instalar.py`: from an AppImage it's copied as a loose file
outside the mount point, where the rest of the package isn't.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

# What the program suggests, and nothing else. All read-only: they read a
# sensor chip or the memory's SPD, and none changes any setting.
ALLOWED = frozenset({
    # the SATA disks' temperature
    "drivetemp",
    # the memory's identification chip
    "spd5118", "ee1004", "at24",
    # the buses that chip is reached over
    "i2c-piix4", "i2c-i801", "i2c-dev",
    # the most common boards' Super I/O, in case they're suggested one day
    "nct6775", "nct6683", "it87", "w83627ehf", "f71882fg",
})

TARGET = pathlib.Path("/etc/modules-load.d/silux.conf")
# modprobe by its absolute path, not looked up in whatever PATH there is.
MODPROBE = ("/usr/sbin/modprobe", "/sbin/modprobe", "/usr/bin/modprobe")


def _modprobe() -> str:
    for path in MODPROBE:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise SystemExit("No encuentro modprobe en " + ", ".join(MODPROBE) + ".")

# A kernel module name carries nothing but this. The check goes before the
# allow list, not instead of it: if someone ever builds the list from a
# variable, the name still can't be a shell command.
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def is_allowed(module: str) -> bool:
    """Whether this helper can load that module.

    The interface asks, to decide whether to show the button: a notice with
    a button that will fail is worse than a notice with a command to copy.
    """
    return bool(NAME.match(module)) and module in ALLOWED


def load(module: str) -> None:
    if not NAME.match(module):
        raise SystemExit(f"«{module}» no tiene forma de módulo del kernel.")
    if module not in ALLOWED:
        raise SystemExit(
            f"«{module}» no está en la lista de módulos que este ayudante carga.\n"
            "Solo carga los que el programa sugiere, y todos son de solo lectura."
        )

    result = subprocess.run([_modprobe(), module],
                               capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise SystemExit(f"modprobe {module}: {detail[-1] if detail else 'falló'}")

    _persist(module)
    print(f"{module} cargado y anotado en {TARGET}")


def _persist(module: str) -> None:
    """Add the module to the list of those loaded at boot.

    What the file already holds is kept: another module may be there from
    an earlier session, and rewriting it whole would lose it.
    """
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    listed = []
    if TARGET.exists():
        listed = [line.strip() for line in
                   TARGET.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.startswith("#")]
    if module in listed:
        return
    listed.append(module)
    text = ("# Módulos de sensores que pidió Silux. Borrar una línea basta para\n"
             "# que deje de cargarse en el arranque siguiente.\n"
             + "\n".join(listed) + "\n")
    # Whole and atomically, never through a link: a new temporary file in the
    # same folder (O_EXCL, O_NOFOLLOW), renamed over the old one.
    fd, temp_path = tempfile.mkstemp(prefix=".silux.conf.", dir=TARGET.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            os.fchmod(handle.fileno(), 0o644)
        os.replace(temp_path, TARGET)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("module", help="el módulo que cargar")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        raise SystemExit(
            "Hay que ejecutarlo como root: carga un módulo y escribe en "
            "/etc/modules-load.d.\n"
            f"  sudo python3 -m silux.privileged.cargar_modulo {args.module}"
        )
    load(args.module)
    return 0


if __name__ == "__main__":
    sys.exit(main())
