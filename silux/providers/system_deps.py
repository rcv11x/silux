"""What this machine needs from the system and does not have, with its package.

The table and the checks are in `system_deps`; here, which of them this
machine needs (an NVIDIA with its own driver needs NVML; one with no screen
connected, no pnp.ids) and the note that says what does not come out, and
which package of this distribution brings it.
"""

from __future__ import annotations

import os
import re

from .. import render, sysroot, system_deps
from ..i18n import _
from ..model import Need
from ..privileged.client import PrivilegedClient, already_root
from .base import Draft, Provider, read_text

# The graphics libraries by the name everyone knows them by.
GRAPHICS_NAMES = {"vulkan": "Vulkan", "egl": "EGL", "opengl": "OpenGL", "opencl": "OpenCL",
                  "vaapi": "VA-API"}
PCI_ADDRESS = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def _entries(path: str) -> list[str]:
    try:
        return os.listdir(sysroot.ruta(path))
    except OSError:
        return []


def _has_pci() -> bool:
    return bool(_entries("/sys/bus/pci/devices"))


def _a_screen_is_connected() -> bool:
    return any(read_text(f"/sys/class/drm/{name}/status") == "connected"
               for name in _entries("/sys/class/drm") if "-" in name)


def _graphics_with_a_driver() -> bool:
    return any(os.path.exists(sysroot.ruta(f"/sys/class/drm/{name}/device/driver"))
               for name in _entries("/sys/class/drm") if re.fullmatch(r"card\d+", name))


def _nvidia_driver_in_use() -> bool:
    return any(PCI_ADDRESS.match(name) for name in _entries("/sys/bus/pci/drivers/nvidia"))


def _hint(packages: list[str], family) -> str:
    """«It comes in the package hwdata», «They come in the packages libva2
    and libva-drm2», or every family's where the distribution is none of them."""
    if family is None:
        return _("deps.hint.any").format(paquete="; ".join(packages))
    names = [n for text in packages for n in text.split()]
    if len(names) == 1:
        return _("deps.hint").format(paquete=names[0])
    return _("deps.hint.many").format(paquetes=render.enumeration(names))


def _missing(key: str) -> bool:
    """Only what is known to be missing: with a dump that did not record it,
    nothing is said."""
    return system_deps.present(key) is False


class SystemDependencies(Provider):
    name = "system-deps"
    provides = "packages"
    static = True

    def collect(self, draft: Draft) -> None:
        family = system_deps.family(system_deps.read_os_release())

        def note(path: str, key: str, message: str) -> None:
            package = system_deps.package_text(system_deps.BY_KEY[key], family,
                                               system_deps.nvidia_major())
            draft.note(path, Need.PACKAGE, message, _hint([package], family))

        if _has_pci() and _missing("pci.ids"):
            note("board.packages.pciids", "pci.ids", _("deps.pciids"))
        if _a_screen_is_connected() and _missing("pnp.ids"):
            note("gpus.packages.pnpids", "pnp.ids", _("deps.pnpids"))
        if _nvidia_driver_in_use() and _missing("nvml"):
            # It says what the driver's own note says, and which package.
            draft.notes = [n for n in draft.notes
                           if not (n.path.startswith("gpus.") and n.need is Need.DRIVER
                                   and n.key == "prov.drm.nvidia")]
            note("gpus.packages.nvml", "nvml", _("deps.nvml"))
        if _graphics_with_a_driver():
            self._graphics(draft, family)
        if not already_root():
            if _missing("pkexec"):
                note("privileged.pkexec", "pkexec", _("deps.pkexec"))
            if PrivilegedClient.empaquetado() and _missing("python3"):
                note("privileged.python3", "python3", _("deps.python3"))
        if os.path.isdir(sysroot.ruta("/run/systemd/system")) and _missing("systemctl"):
            note("system.boot.systemctl", "systemctl", _("deps.systemctl"))
        if _missing("kmod"):
            note("system.kmod", "kmod", _("deps.kmod"))
        if (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")) \
                and _missing("xdg-open"):
            note("system.xdg-open", "xdg-open", _("deps.xdgopen"))

    @staticmethod
    def _graphics(draft: Draft, family) -> None:
        """One note for the graphics libraries that are missing, with their
        packages. With all of them missing it says what gpu-apis' «none» said."""
        missing = [key for key in system_deps.GRAPHICS_LIBRARIES if _missing(key)]
        if not missing:
            return
        if all(key in missing for key in ("vulkan", "egl", "opengl", "opencl")):
            draft.notes = [n for n in draft.notes if n.path != "gpus.apis"]
        packages = []
        for key in missing:
            text = system_deps.package_text(system_deps.BY_KEY[key], family)
            if text not in packages:
                packages.append(text)
        listed = ", ".join(GRAPHICS_NAMES[key] for key in missing)
        draft.note("gpus.packages.apis", Need.PACKAGE,
                   _("deps.graphics").format(cuales=listed), _hint(packages, family))
