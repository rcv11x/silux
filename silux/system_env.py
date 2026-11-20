"""The environment for a program of the system, without what the AppImage adds.

The AppRun prepends its own libraries to `LD_LIBRARY_PATH` and points Python
and Qt inside the AppImage. Whatever Silux launches inherits that: in Debian
13, `systemctl` loaded the compat build's `libcrypto` and died with
«version `OPENSSL_3.4.0' not found», so the boot times were missing; a file
manager opened from a page would load the AppImage's Qt. A program of the
system gets its environment back; Silux's own children (`gpuapi`, `membench`)
run the AppImage's Python and keep it.
"""

from __future__ import annotations

import os
import subprocess
from typing import Mapping, Optional

# What the AppRun sets, path lists and single paths.
PATH_LISTS = ("LD_LIBRARY_PATH", "PYTHONPATH", "QT_PLUGIN_PATH",
              "QT_QPA_PLATFORM_PLUGIN_PATH")
SINGLE_PATHS = ("PYTHONHOME",)
# The AppRun's own (set even when the AppImage is run extracted), and the
# runtime's.
APPDIR_VARIABLES = ("SILUX_APPDIR", "APPDIR")


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.abspath(path), root)) == root
    except ValueError:
        return False


def system_environment(base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """`base` (the current environment by default) without the AppImage's paths.

    Only the entries inside the AppImage go: what the user had in
    `LD_LIBRARY_PATH` before launching it stays. Outside an AppImage it is
    the same environment.
    """
    env = dict(os.environ if base is None else base)
    root = next((env[v] for v in APPDIR_VARIABLES if env.get(v)), None)
    if not root:
        return env
    root = os.path.abspath(root)
    for name in PATH_LISTS:
        if name not in env:
            continue
        kept = [p for p in env[name].split(os.pathsep) if p and not _inside(p, root)]
        if kept:
            env[name] = os.pathsep.join(kept)
        else:
            del env[name]
    for name in SINGLE_PATHS:
        if name in env and _inside(env[name], root):
            del env[name]
    return env


def open_path(path: str) -> bool:
    """Open a folder or file with the desktop's program, like
    `QDesktopServices.openUrl` but with the system's environment."""
    try:
        subprocess.Popen(["xdg-open", path], env=system_environment(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True
