"""The unprivileged side: starts the helper and talks to it.

Never called from the interface thread. `pkexec` opens an authentication
dialog and blocks until the user answers; doing that on Qt's thread would
freeze the window with the dialog open in front of it, the worst
combination.

The process is kept alive for the session. Asking for the password again
every sample would be unacceptable, and keeping a pipe open to a process
that can only do a few reads is little risk for a lot of convenience.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
from typing import NamedTuple, Optional

from .. import sysroot
from ..system_env import system_environment
from . import protocol
from .protocol import (
    ACTION_GPU_PMU,
    ACTION_IMC,
    ACTION_MSR,
    ACTION_PING,
    ACTION_RAPL,
    ACTION_SMART,
    ACTION_SMBIOS,
    MAX_MESSAGE,
)

# pkexec by its absolute path. By name it would be looked up in the user's
# PATH, which any process of theirs can change, and a fake one could draw its
# own password window.
PKEXEC_PATHS = ("/usr/bin/pkexec", "/bin/pkexec")


def pkexec_path() -> str:
    """Where pkexec is; the usual place if it is nowhere (`supported` says so)."""
    return next((path for path in PKEXEC_PATHS if os.path.isfile(path)), PKEXEC_PATHS[0])


# System interpreters to start the helper with when the program's own won't
# do. The helper only needs the standard library, so any will.
SYSTEM_PYTHON = ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3")


def _cache_dir() -> pathlib.Path:
    """The program's cache folder, by the system's convention."""
    base = os.environ.get("XDG_CACHE_HOME") or (pathlib.Path.home() / ".cache")
    return pathlib.Path(base) / "silux"


# What's passed to `python3 -c` to run a script that's in no file. It gets
# through argv the name to compile it under and its whole source, and leaves
# in `sys.argv` what comes after, which is what the script expects.
#
# The name and `linecache` aren't decoration: without them a failure's
# traceback says «File "<string>", line 40» with no text for the line, and
# that's the first thing asked of whoever reports something. With them it
# says «File "silux-helper.py", line 40» with its line below, as if it came
# from a file.
#
# The `excepthook` is the other half, needed up to Python 3.12: until then
# the C writer prints an uncaught exception and looks the code up by opening
# the file by its name, so with no file it has no line even if `linecache`
# has it. The `traceback` module does look there. From 3.13 the default path
# already goes that way, but the declared floor is 3.10, the Python inside
# the AppImage. `SystemExit` doesn't go through the hook, so scripts that
# warn with `raise SystemExit("...")` still print their bare message.
BOOTSTRAP = """\
import linecache, sys, traceback
_name, _source = sys.argv[1], sys.argv[2]
linecache.cache[_name] = (len(_source), None, _source.splitlines(True), _name)
sys.argv = [_name] + sys.argv[3:]
sys.excepthook = lambda *exc_info: traceback.print_exception(*exc_info)
exec(compile(_source, _name, "exec"), {"__name__": "__main__", "__file__": _name})
"""


def inline_command(interpreter: str, name: str, source: str,
                   *arguments: str) -> list[str]:
    """The command that runs `source` without it existing as a file.

    It keeps a path the user could rewrite out of `pkexec`'s command line.
    What goes by `argv` is fixed by `exec()` and nobody can change it later;
    a file can be.
    """
    # `-I`: as root, no PYTHONPATH, PYTHONSTARTUP, user site-packages or
    # current folder, whatever pkexec left in the environment.
    return [interpreter, "-I", "-c", BOOTSTRAP, name, source, *arguments]


# What the versions that copied the scripts into the cache to launch them
# with pkexec left there. Nothing writes or runs them now, but they were the
# hole's surface and there's no reason to leave them on an updater's disk.
OLD_COPIES = ("helper.py", "instalar.py", "cargar_modulo.py")


def clean_old_copies() -> None:
    """Delete the scripts earlier versions left in the cache."""
    folder = _cache_dir()
    for name in OLD_COPIES:
        try:
            (folder / name).unlink()
        except OSError:
            pass
    try:
        folder.rmdir()          # only if nothing else is left inside
    except OSError:
        pass


def interpreter() -> str:
    """Which Python pkexec launches a script passed by `argv` with.

    From an AppImage the one inside won't do, for two different reasons,
    both insurmountable:

    * The mount point is `nosuid`, and pkexec refuses to run anything from
      such a filesystem. It denies before asking, which is why the password
      dialog never appeared.
    * The mount is FUSE and belongs to the user, so **root can't even read
      inside it**.

    So the system's is used, for which the standard library is enough.
    Outside an AppImage ours will do, but only if the user can't rewrite it:
    a virtual environment of theirs can be, and then the path pkexec gets
    becomes replaceable again, which is exactly what's being removed.
    """
    for path in SYSTEM_PYTHON:
        if os.path.exists(path):
            return path
    if (not PrivilegedClient.empaquetado()
            and not writable_by_user(sys.executable)):
        return sys.executable
    raise HelperUnavailable(
        "No hay ningún Python del sistema con el que lanzar el ayudante."
    )


def pkexec_inline(name: str, source: str, *args: str) -> list[str]:
    """The pkexec command that runs `source` as root without a file.

    The only place a pkexec command with code is built: the program and its
    arguments go by argv, so no path the user can rewrite is in it. Raises
    HelperUnavailable without a system Python to run it.
    """
    return [pkexec_path(), *inline_command(interpreter(), name, source, *args)]


def writable_by_user(path) -> bool:
    """Whether this user can change what's at that path.

    The folders above are looked at too: being able to write the directory
    allows replacing the whole file even if the file itself can't be touched.
    """
    if already_root():
        # As root everything is writable and the question means nothing; and
        # as root there's no pkexec in between to protect.
        return False
    target = pathlib.Path(path).resolve()
    if target.exists() and os.access(target, os.W_OK):
        return True
    return any(os.access(parent, os.W_OK)
               for parent in target.parents if parent.exists())


HELPER = pathlib.Path(__file__).resolve().parent / "helper.py"

# The helper installed in the system, if someone pressed the permanent
# permissions button. Preferred to the repository's because it brings its own
# polkit action: the password window says what's read, in our words.
# `silux/privileged/instalar.py` installs it, and also explains why it must
# live where the user can't write.
INSTALLED_HELPER = pathlib.Path("/usr/local/libexec/silux/silux-helper")
# Its polkit action. Without it the installed helper still runs, but through
# the generic action, which shows the command and not what's read. Both paths
# are written by `instalar.py`, and a test keeps them from drifting apart.
INSTALLED_POLICY = pathlib.Path(
    "/usr/share/polkit-1/actions/org.silux.helper.policy")

DEFAULT_TIMEOUT = 15.0
# Authenticating may take as long as the user takes to type.
CONNECT_TIMEOUT = 120.0


class HelperError(RuntimeError):
    """Couldn't talk to the helper."""


class HelperUnavailable(HelperError):
    """pkexec or the helper itself is missing: there's nothing to try."""


class HelperDenied(HelperError):
    """The user cancelled the dialog or isn't authorized."""


class HelperNoAgent(HelperUnavailable):
    """pkexec is there but no polkit agent runs in the session to ask for the
    password (a bare window manager: Hyprland, Sway, i3…)."""


# What pkexec writes then, in English whatever the locale, with exit code 127:
# the same as a refusal, so its words are what tell them apart.
NO_AGENT = "No authentication agent found"


def _of_this_machine(*paths: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """The installed helper's files as the machine being read has them.

    They're files of the machine: with a dump mounted, they're read inside
    it, and a dump has none of this machine's helper. Read directly, a helper
    installed here and older than the code made every dump's snapshot say
    «outdated». Not through `sysroot.path`, which only moves what a dump
    records (/sys, /proc, /etc).
    """
    base = sysroot.root()
    if base is None:
        return paths
    return tuple(pathlib.Path(f"{base}{path}") for path in paths)


class PrivilegedClient:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._last_error: Optional[str] = None
        # Set when the installed helper turns out to be an older version: from
        # then on the one travelling by argv is used, which is always this
        # program's. It costs a password per start, better than a feature that
        # doesn't work and doesn't say why.
        self._skip_installed = False
        # One password window per request: once it has failed, whatever the
        # reason, no other one opens until the user asks again.
        self._failure: Optional[HelperError] = None

    # -- state --------------------------------------------------------------

    @staticmethod
    def supported() -> bool:
        return os.access(pkexec_path(), os.X_OK) and HELPER.is_file()

    @staticmethod
    def empaquetado() -> bool:
        """Whether the program runs from inside an AppImage."""
        return bool(os.environ.get("APPIMAGE")) or "/.mount_" in sys.executable

    def connected(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def allow_asking(self) -> None:
        """The user asked for permissions: `connect` may open the window again."""
        self._failure = None

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> None:
        """Ask for authorization and leave the helper listening. Blocks."""
        if self.connected():
            return
        if self._failure is not None:
            raise self._failure.with_traceback(None)
        try:
            self._open()
        except HelperError as exc:
            self._failure = exc
            raise

    def _open(self) -> None:
        # This is where earlier versions wrote the copy, so this is where it's
        # collected.
        clean_old_copies()
        if not self.supported():
            raise HelperUnavailable(
                "Falta pkexec. Se instala con el paquete polkit de la distribución."
            )

        command = self._command()
        # pkexec's own words, read only if it fails. A file and not a pipe:
        # nobody reads it while the helper runs, and a full pipe would stall it.
        said = tempfile.TemporaryFile()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=said, text=True, bufsize=1,
                env=system_environment(),
            )
        except OSError as exc:
            said.close()
            raise HelperUnavailable(f"no se pudo lanzar pkexec: {exc}") from exc

        self._process = process
        try:
            reply = self.request({"action": ACTION_PING}, timeout=CONNECT_TIMEOUT)
        except HelperError:
            self.close()
            # Waited for, not polled: pkexec may still be exiting when the
            # pipe breaks, and a cancel would then pass for a failure.
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                code = None
            said.seek(0)
            words = said.read(4096).decode(errors="replace")
            said.close()
            if NO_AGENT in words:
                raise HelperNoAgent(words.strip()) from None
            # 126 = the user cancelled the dialog; 127 = not authorized.
            if code in (126, 127):
                raise HelperDenied("Autorización cancelada o denegada.") from None
            if code == 1 and self.empaquetado():
                raise HelperUnavailable(
                    "pkexec no pudo lanzar el ayudante desde el AppImage."
                ) from None
            raise

        said.close()
        if not reply.get("ok") or reply.get("uid") != 0:
            self.close()
            raise HelperError("el ayudante no arrancó con privilegios")

        # And that it's this version's. Installing the permanent permissions
        # leaves a copy in /usr/local/libexec that nobody updates: whoever gave
        # them months ago would still talk to that helper, and whatever this
        # program asked of it anew (an action, a register) would be refused
        # with a message that doesn't mention the cause.
        if reply.get("version", 0) < protocol.HELPER_VERSION and self.installed():
            self.close()
            self._skip_installed = True
            self._open()

    @staticmethod
    def installed() -> bool:
        """Whether the system helper is in place, with its polkit action.

        The policy counts: it's what makes the password window say what's
        read, the reason to install anything. Without it the helper runs all
        the same, but the permanent permissions button hid itself saying it
        was done with half missing. `instalar.installed()` already looked at
        both.
        """
        helper, policy = _of_this_machine(INSTALLED_HELPER, INSTALLED_POLICY)
        return (helper.is_file()
                and os.access(helper, os.X_OK)
                and policy.is_file())

    @staticmethod
    def _body(text: str) -> str:
        """The helper without its first line.

        The installer replaces the shebang with the pinned interpreter, so two
        copies of the same helper always differ in that line and only there.
        """
        return text.split("\n", 1)[1] if text.startswith("#!") else text

    @classmethod
    def up_to_date(cls) -> bool:
        """Whether the installed helper and its rule are this program's.

        The content is compared, not a version number, and the difference
        matters: a number has to be remembered to be bumped, and fixes that
        keep the contract (security ones above all) don't touch it. Content
        doesn't forget to change.

        The rule too: it's what the password window says, and an old rule
        named only memory and disks while the permission also opens voltage,
        power and graphics usage.
        """
        from . import instalar

        helper, policy = _of_this_machine(INSTALLED_HELPER, INSTALLED_POLICY)
        try:
            installed = helper.read_text(encoding="utf-8")
            current = HELPER.read_text(encoding="utf-8")
            rule = policy.read_text(encoding="utf-8")
        except OSError:
            return False
        return (cls._body(installed) == cls._body(current)
                and rule == instalar.policy())

    @classmethod
    def needs_reinstall(cls) -> bool:
        """A helper is installed and it isn't this program's.

        Then it isn't enough to stop using it: it must be replaced. The file
        stays in /usr/local/libexec owned by root, with its polkit action
        pointing at it, so it's still runnable with privileges even if this
        program ignores it. And if it was installed by a version before the
        escalation fixes, there's no guarantee what's there is what was meant
        to be installed.
        """
        return cls.installed() and not cls.up_to_date()

    def _command(self) -> list[str]:
        """What's passed to pkexec, in the order of preference that applies.

        The installed helper goes alone, with no interpreter in front: pkexec
        ties the authorization to the path of the program it runs, so with
        `python3` in front the action would hang off the interpreter and be
        valid for any script on the machine.

        If it isn't installed, the helper travels by `argv`, not as a file.
        **No path the user can rewrite may appear in this list**, and a test
        checks it in the three pkexec commands the program builds.
        """
        # The installed one is only used if it's exactly this program's.
        if (self.installed() and self.up_to_date()
                and not self._skip_installed):
            return [pkexec_path(), str(INSTALLED_HELPER)]
        return pkexec_inline("silux-helper.py", self._helper_source())

    @staticmethod
    def _helper_source() -> str:
        try:
            return HELPER.read_text(encoding="utf-8")
        except OSError as exc:
            raise HelperUnavailable(
                f"no se pudo leer el ayudante: {exc}") from exc


    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()

    # -- requests -----------------------------------------------------------

    def request(self, payload: dict, timeout: float = DEFAULT_TIMEOUT) -> dict:
        process = self._process
        if process is None or process.poll() is not None:
            raise HelperError("el ayudante no está en marcha")

        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            self.close()
            raise HelperError(f"se cortó la comunicación: {exc}") from exc

        ready, _, _ = select.select([process.stdout], [], [], timeout)
        if not ready:
            self.close()
            raise HelperError("el ayudante no respondió a tiempo")

        line = process.stdout.readline()
        if not line:
            self.close()
            raise HelperError("el ayudante se cerró sin responder")
        if len(line) > MAX_MESSAGE:
            self.close()
            raise HelperError("respuesta desmesurada")

        try:
            reply = json.loads(line)
        except ValueError as exc:
            raise HelperError(f"respuesta ilegible: {exc}") from exc
        if not isinstance(reply, dict):
            raise HelperError("la respuesta no es un objeto")
        return reply

    # -- operations ---------------------------------------------------------

    def smbios_table(self) -> bytes:
        reply = self.request({"action": ACTION_SMBIOS})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudo leer SMBIOS"))
        return base64.b64decode(reply.get("table", ""))

    def read_msr(self, cpu: int, registers: list[int]) -> dict[int, int]:
        reply = self.request({"action": ACTION_MSR, "cpu": cpu, "registers": registers})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudieron leer los MSR"))
        return {int(k): v for k, v in reply.get("values", {}).items()}


    def read_smart(self, device: str) -> tuple[bytes, str]:
        """A disk's diagnostic data, and which family it is.

        The bytes are returned untouched: interpreting them is `silux.smart`'s
        job, which runs without privileges.
        """
        reply = self.request({"action": ACTION_SMART, "device": device})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudo leer el diagnóstico"))
        return base64.b64decode(reply.get("data", "")), reply.get("kind", "")

    def rapl(self) -> dict[str, int]:
        """The energy counters in microjoules, per zone.

        Raw: watts are the derivative, computed by the caller, which keeps the
        previous reading. Needed because since kernel 5.10 `energy_uj` can't
        be read without privileges, and on machines where that applies (AMD
        above all) the processor's power came out blank even with permissions
        given.
        """
        reply = self.request({"action": ACTION_RAPL})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            raise HelperError(reply.get("message", "no se pudo leer RAPL"))
        zones = reply.get("zones")
        if not isinstance(zones, dict):
            raise HelperError("el ayudante contestó algo que no encaja")
        return {str(k): int(v) for k, v in zones.items() if isinstance(v, int)}

    def gpu_pmu(self) -> tuple[int, dict[str, dict[str, int]], dict[str, dict[str, float]]]:
        """The graphics counters, raw, with their clock and scales.

        Busy ones are accumulated nanoseconds and energy ones carry the scale
        the kernel publishes. Subtracting them and turning them into a
        percentage or watts is the caller's business: the helper interprets
        nothing.
        """
        reply = self.request({"action": ACTION_GPU_PMU})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            message = reply.get("message", "no se pudo leer el PMU de la gráfica")
            if reply.get("error") == "unsupported":
                raise PmuUnsupported(message)
            raise HelperError(message)

        clock = reply.get("monotonic_ns")
        engines = reply.get("engines")
        if not isinstance(clock, int) or not isinstance(engines, dict):
            raise HelperError("el ayudante contestó algo que no encaja")
        clean = {
            str(pmu): {str(e): v for e, v in events.items() if isinstance(v, int)}
            for pmu, events in engines.items() if isinstance(events, dict)
        }
        raw = reply.get("scales")
        scales = {
            str(pmu): {str(e): float(v) for e, v in values.items()
                       if isinstance(v, (int, float))}
            for pmu, values in (raw or {}).items() if isinstance(values, dict)
        }
        return clock, clean, scales

    def imc(self) -> ImcReading:
        """How much traffic the memory controller has moved, raw.

        Like the graphics ones: counters that only go up, with the factor and
        the unit the kernel publishes next to them. Bytes per second are the
        derivative, computed by the caller, which keeps the previous reading.
        """
        reply = self.request({"action": ACTION_IMC})
        if not reply.get("ok"):
            self._last_error = reply.get("message")
            message = reply.get("message", "no se pudo leer el controlador de memoria")
            if reply.get("error") == "unsupported":
                raise PmuUnsupported(message)
            raise HelperError(message)

        clock = reply.get("monotonic_ns")
        counters = reply.get("counters")
        if not isinstance(clock, int) or not isinstance(counters, dict):
            raise HelperError("el ayudante contestó algo que no encaja")
        clean = {
            str(pmu): {str(e): v for e, v in events.items() if isinstance(v, int)}
            for pmu, events in counters.items() if isinstance(events, dict)
        }
        scales = {
            str(pmu): {str(e): float(v) for e, v in values.items()
                       if isinstance(v, (int, float))}
            for pmu, values in (reply.get("scales") or {}).items()
            if isinstance(values, dict)
        }
        units = {
            str(pmu): {str(e): str(v) for e, v in values.items() if isinstance(v, str)}
            for pmu, values in (reply.get("units") or {}).items()
            if isinstance(values, dict)
        }
        return ImcReading(clock, clean, scales, units,
                          bool(reply.get("truncated")))


class PmuUnsupported(HelperError):
    """This machine doesn't publish the counters asked for.

    Not a failure nor a missing permission: hardware that doesn't have them.
    It lets the asker stop asking every sample, and the notice show in grey
    rather than amber.
    """


class ImcReading(NamedTuple):
    """What the helper returns from the memory controller, uninterpreted.

    `counters` are counts accumulated since each counter was opened, and
    `scales` and `units` what the kernel publishes to convert them. Kept
    together because apart they mean nothing: a count without its scale
    isn't a size.
    """

    monotonic_ns: int
    counters: dict[str, dict[str, int]]
    scales: dict[str, dict[str, float]]
    units: dict[str, dict[str, str]]
    truncated: bool


def already_root() -> bool:
    """If the program already runs as root, no helper is needed."""
    return os.geteuid() == 0
