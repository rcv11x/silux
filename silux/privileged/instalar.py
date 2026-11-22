#!/usr/bin/env python3
"""Installs the privileged helper with its own polkit action.

Without it, Silux launches the helper with `pkexec python3 -c …`, which
falls into polkit's generic action, whose window shows the command and not
what's read. With its own action the window says it in our words. The
password is still asked when permissions are given (`auth_admin_keep`).

There's a security reason to copy the helper rather than point to where it
is: `pkexec` ties the authorization to the path of the program it runs and
**doesn't look at the arguments**. With the helper in the user's folder, a
permanent rule would give root without a password to any process running
as that user that could rewrite the file before silux launches it. Copied
to a place only root can write, that door doesn't exist.

For the same reason it's installed as an executable with a shebang and not
as an argument to `python3`: if the action pointed at the interpreter, the
authorization would hold for any Python script on the machine.

    sudo python3 -m silux.privileged.instalar
    sudo python3 -m silux.privileged.instalar --uninstall

The interface calls it on its own from the permissions notice; by hand it's
only needed to install it on a machine without a graphical environment.

It lives in the package and not in `tools/` because the end user runs it,
not whoever develops: `tools/` isn't in the AppImage, where the
interface's button had no installer to launch. For the same reason it
imports nothing from `silux`: it's copied as a loose file outside the mount
point, where the rest of the package isn't.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import stat
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent / "helper.py"

TARGET = pathlib.Path("/usr/local/libexec/silux/silux-helper")
POLICY = pathlib.Path("/usr/share/polkit-1/actions/org.silux.helper.policy")

ACTION = "org.silux.helper"

# What the password window says with the rule in place, in each interface
# language: everything the permission opens, no more, no less. Copied here
# rather than read from `db/lang` because root writes the rule, and root
# can't read inside the user's AppImage. `tests/test_privileged.py` compares
# it with the `perm.polkit.message` key of `es.json` and `en.json`.
MESSAGES = {
    "es": ("Silux necesita permiso para leer datos del hardware reservados al "
           "administrador: memoria, discos, voltaje, consumo y uso de la "
           "gráfica. Solo lee, no cambia nada."),
    "en": ("Silux needs permission to read hardware data reserved to the "
           "administrator: memory, disks, voltage, power and graphics usage. "
           "It only reads; it changes nothing."),
}

# `auth_admin_keep` and not `yes`: the password is asked when permissions
# are given (polkit remembers it a few minutes, for that process only),
# instead of leaving the door open to any process of the session. What
# installing gains is the window saying what's read, not dropping the
# password (docs/privilegios.md).
#
# `allow_inactive` set to `no` because a session that isn't in front of the
# machine has no business reading its sensors: that includes SSH sessions.
TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>silux</vendor>
  <vendor_url>https://github.com/rcv11x/silux</vendor_url>

  <action id="{action}">
    <description>Leer la identificación y los sensores del hardware</description>
    <description xml:lang="en">Read hardware identification and sensors</description>
    <message>{message_es}</message>
    <message xml:lang="en">{message_en}</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>no</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{target}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""


def policy() -> str:
    """The rule as it's written, to install it and to compare it.

    The client compares it with the installed one: changing the window's
    text must also reach whoever already had it in place.
    """
    return TEMPLATE.format(action=ACTION, target=TARGET,
                           message_es=MESSAGES["es"], message_en=MESSAGES["en"])


def installed() -> bool:
    """Whether the helper and its action are in place and usable."""
    return TARGET.is_file() and os.access(TARGET, os.X_OK) and POLICY.is_file()


def _interpreter() -> str:
    """A system Python for the shebang.

    An AppImage's won't do: its mount point is `nosuid` and belongs to the
    user, so pkexec refuses to run anything from there and root can't even
    read it.
    """
    for path in ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3"):
        if os.path.exists(path):
            return path
    raise SystemExit("No hay ningún Python del sistema con el que ejecutar el ayudante.")


# Who has to own what the installer writes into. A constant so the tests,
# which cannot be root, can say «me».
OWNER = 0


def _check_folders(folder: pathlib.Path) -> None:
    """Root's and nobody else's, all the way up.

    Whoever can write a folder can swap what is inside it, file and checks
    included. The folder of its own must be a real folder owned by root and
    writable only by root; the ones above are followed to where they really
    are (on Silverblue /usr/local is a link to /var/usrlocal) and must be
    root's and not writable by everyone. A group may write them: on older
    Debian /usr/local belongs to `staff`, which the distribution counts as
    root.
    """
    info = os.lstat(folder)
    if not stat.S_ISDIR(info.st_mode):
        raise SystemExit(f"{folder} no es una carpeta: no instalo nada ahí.")
    if info.st_uid != OWNER or info.st_mode & 0o022:
        raise SystemExit(f"{folder} la puede cambiar alguien que no es root: no instalo nada ahí.")
    for part in pathlib.Path(os.path.realpath(folder.parent)).joinpath("x").parents:
        info = os.stat(part)
        # Writable by everyone only with the sticky bit, like /tmp: then nobody
        # can rename or delete what belongs to someone else.
        abierta = info.st_mode & 0o002 and not info.st_mode & stat.S_ISVTX
        if info.st_uid not in (OWNER, 0) or abierta:
            raise SystemExit(f"{part} la puede cambiar alguien que no es root: no instalo nada ahí.")


def _write(target: pathlib.Path, text: str, mode: int) -> None:
    """Writes the file whole and atomically, and never through a link.

    A temporary file created new in the same folder (`mkstemp` opens it with
    O_EXCL and O_NOFOLLOW), owned and moded before it has its name, and then
    renamed over the old one: a rename replaces a link, it does not follow it.
    Writing in place followed whatever was at that path.
    """
    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), OWNER, OWNER)
            os.fchmod(handle.fileno(), mode)
        os.replace(temp_path, target)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def from_package() -> str:
    """The helper that comes alongside, for when this is run by hand."""
    if not SOURCE.is_file():
        raise SystemExit(f"No encuentro el ayudante en {SOURCE}")
    return SOURCE.read_text(encoding="utf-8")


def install(body: str) -> None:
    """Put the helper in the system with its polkit action.

    It takes the helper's **text** and not a path, a security decision and
    not one of style: with a path to a file the user can write, any process
    of theirs could change it while the password was typed (seconds, not a
    race), and what got installed, owned by root with the polkit action
    pointing at it, would be the attacker's. A text arriving through a pipe
    has no name to swap.
    """
    if not body.strip():
        raise SystemExit("No me han pasado ningún ayudante que instalar.")
    # The file's shebang is `/usr/bin/env python3`, which resolves against
    # the PATH of whoever runs it. Here root runs it through pkexec, so the
    # interpreter is pinned and the environment stops mattering.
    # `-I`: as root, no PYTHONPATH, PYTHONSTARTUP or user site-packages.
    if body.startswith("#!"):
        body = body.split("\n", 1)[1]
    body = f"#!{_interpreter()} -I\n" + body

    TARGET.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    _check_folders(TARGET.parent)
    _check_folders(POLICY.parent)
    # 0755 and root's: anyone can run it (pkexec decides whether they may),
    # nobody but root can change what it does.
    _write(TARGET, body, 0o755)
    _write(POLICY, policy(), 0o644)

    print(f"ayudante:  {TARGET}")
    print(f"política:  {POLICY}")
    print("Listo. La ventana de la contraseña dirá qué se lee.")


def uninstall_command() -> str:
    """The command that removes the helper, however silux is installed.

    Two files, deleted. `python3 -m silux.privileged.instalar --uninstall`
    does the same, but only exists where silux is installed as a package:
    whoever uses the AppImage doesn't have that module in their Python, and
    that's exactly who installed the helper from the window.
    """
    return f"sudo rm {TARGET} {POLICY}"


def uninstall() -> None:
    for path in (POLICY, TARGET):
        if path.exists():
            path.unlink()
            print(f"borrado: {path}")
    if TARGET.parent.is_dir() and not any(TARGET.parent.iterdir()):
        TARGET.parent.rmdir()
    print("Al dar permisos vuelve a salir el aviso.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--uninstall", action="store_true",
                        help="quita el ayudante y su acción de polkit")
    parser.add_argument("--check", action="store_true",
                        help="dice si están instalados y sale")
    parser.add_argument("--from-stdin", action="store_true",
                        help="lee el ayudante de la entrada estándar en vez de "
                             "usar el del paquete. Es como lo instala la "
                             "interfaz desde un AppImage, donde root no puede "
                             "leer dentro del punto de montaje. No se acepta "
                             "una ruta a propósito: la que había que dar era "
                             "de una carpeta del usuario, y eso deja instalar "
                             "como root lo que otro proceso ponga ahí")
    args = parser.parse_args(argv)

    if args.check:
        print("instalado" if installed() else "no instalado")
        return 0 if installed() else 1

    if os.geteuid() != 0:
        raise SystemExit(
            "Hay que ejecutarlo como root: escribe en /usr/local/libexec y en "
            "/usr/share/polkit-1/actions.\n"
            "  sudo python3 -m silux.privileged.instalar"
        )

    if args.uninstall:
        uninstall()
    else:
        install(sys.stdin.read() if args.from_stdin else from_package())
    return 0


if __name__ == "__main__":
    sys.exit(main())
