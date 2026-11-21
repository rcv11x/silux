"""What Silux uses from the system and does not carry inside.

Data files, libraries and programs, each with the package that brings it in
each family of distributions, and what does not come out without it. The
package names were asked to each distribution's own package manager (Debian
13, Ubuntu 24.04, Fedora 45 and Arch), on 21 November 2026; docs/dependencias.md
is this same table in words, and tests/test_system_deps.py keeps them equal.

Nothing that reads the hardware needs any of these: it reads /sys, /proc,
/dev and the CPU itself, from Python. What they add are names (pci.ids,
pnp.ids), what a driver only tells through its library (NVML, Vulkan,
OpenGL, OpenCL, VA-API), asking for permissions (pkexec and the system's
Python) and a few conveniences.

A library is looked up in the dynamic loader's cache, not loaded: loading
Vulkan or NVML to see whether they are there would keep them in memory
(rule 8).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Optional

from . import sysroot
from .system_env import system_environment

FAMILIES = ("debian", "ubuntu", "fedora", "arch")
FAMILY_NAMES = {"debian": "Debian", "ubuntu": "Ubuntu", "fedora": "Fedora", "arch": "Arch"}

LD_CACHE = "/etc/ld.so.cache"
LIBRARY_DIRS = ("/usr/lib", "/usr/lib64", "/lib", "/lib64", "/usr/lib/x86_64-linux-gnu",
                "/usr/lib/aarch64-linux-gnu", "/usr/lib/i386-linux-gnu")
# Where a program may be although a user's PATH does not say so: Debian's
# leaves out /usr/sbin, where modinfo and sensors-detect are.
PROGRAM_DIRS = ("/usr/sbin", "/sbin", "/usr/bin", "/bin", "/usr/local/sbin", "/usr/local/bin")


@dataclass(frozen=True)
class Dependency:
    key: str
    kind: str                         # "data", "library" or "program"
    names: tuple[str, ...]            # paths, sonames or program names
    packages: dict                    # family -> package, None where none brings it
    note: Optional[str] = None        # i18n key of the Diagnóstico note, if it gets one


DEPENDENCIES = (
    Dependency("pci.ids", "data",
               ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids", "/usr/share/pci.ids",
                "/var/lib/pciutils/pci.ids"),
               {"debian": "pci.ids", "ubuntu": "hwdata", "fedora": "hwdata", "arch": "hwdata"},
               "deps.pciids"),
    Dependency("pnp.ids", "data",
               ("/usr/share/hwdata/pnp.ids", "/usr/share/misc/pnp.ids", "/usr/share/pnp.ids"),
               {"debian": "pnp.ids", "ubuntu": "hwdata", "fedora": "hwdata", "arch": "hwdata"},
               "deps.pnpids"),
    Dependency("nvml", "library", ("libnvidia-ml.so.1",),
               # Ubuntu's carries the driver's version: libnvidia-compute-595.
               {"debian": "libnvidia-ml1", "ubuntu": "libnvidia-compute-{nvidia}",
                "fedora": "xorg-x11-drv-nvidia-cuda-libs", "arch": "nvidia-utils"},
               "deps.nvml"),
    Dependency("vulkan", "library", ("libvulkan.so.1",),
               {"debian": "libvulkan1", "ubuntu": "libvulkan1", "fedora": "vulkan-loader",
                "arch": "vulkan-icd-loader"}),
    Dependency("egl", "library", ("libEGL.so.1",),
               {"debian": "libegl1", "ubuntu": "libegl1", "fedora": "libglvnd-egl",
                "arch": "libglvnd"}),
    Dependency("opengl", "library", ("libGL.so.1",),
               {"debian": "libgl1", "ubuntu": "libgl1", "fedora": "libglvnd-glx",
                "arch": "libglvnd"}),
    Dependency("opencl", "library", ("libOpenCL.so.1",),
               {"debian": "ocl-icd-libopencl1", "ubuntu": "ocl-icd-libopencl1",
                "fedora": "ocl-icd", "arch": "ocl-icd"}),
    Dependency("vaapi", "library", ("libva.so.2", "libva-drm.so.2"),
               {"debian": "libva2 libva-drm2", "ubuntu": "libva2 libva-drm2",
                "fedora": "libva", "arch": "libva"}),
    Dependency("pkexec", "program", ("pkexec",),
               {"debian": "pkexec", "ubuntu": "pkexec", "fedora": "polkit", "arch": "polkit"},
               "deps.pkexec"),
    Dependency("python3", "program", ("python3",),
               {"debian": "python3", "ubuntu": "python3", "fedora": "python3", "arch": "python"},
               "deps.python3"),
    Dependency("systemctl", "program", ("systemctl",),
               {"debian": "systemd", "ubuntu": "systemd", "fedora": "systemd", "arch": "systemd"},
               "deps.systemctl"),
    Dependency("kmod", "program", ("modinfo", "modprobe"),
               {"debian": "kmod", "ubuntu": "kmod", "fedora": "kmod", "arch": "kmod"},
               "deps.kmod"),
    Dependency("xdg-open", "program", ("xdg-open",),
               {"debian": "xdg-utils", "ubuntu": "xdg-utils", "fedora": "xdg-utils",
                "arch": "xdg-utils"},
               "deps.xdgopen"),
    Dependency("gio", "program", ("gio",),
               {"debian": "libglib2.0-bin", "ubuntu": "libglib2.0-bin", "fedora": "glib2",
                "arch": "glib2"}),
    Dependency("update-desktop-database", "program", ("update-desktop-database",),
               {"debian": "desktop-file-utils", "ubuntu": "desktop-file-utils",
                "fedora": "desktop-file-utils", "arch": "desktop-file-utils"}),
    Dependency("gtk-update-icon-cache", "program", ("gtk-update-icon-cache",),
               {"debian": "gtk-update-icon-cache", "ubuntu": "gtk-update-icon-cache",
                "fedora": "gtk-update-icon-cache", "arch": "gtk-update-icon-cache"}),
    # Ubuntu 24.04 has Plasma 5 and no KF6: no package brings it there.
    Dependency("kbuildsycoca6", "program", ("kbuildsycoca6",),
               {"debian": "libkf6service-bin", "ubuntu": None,
                "fedora": "kf6-kservice", "arch": "kservice"}),
    Dependency("dbus-send", "program", ("dbus-send",),
               {"debian": "dbus-bin", "ubuntu": "dbus-bin", "fedora": "dbus-tools",
                "arch": "dbus"}),
    Dependency("ca-certificates", "data",
               ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
                "/etc/ssl/ca-bundle.pem", "/etc/pki/tls/cacert.pem", "/etc/ssl/cert.pem"),
               {"debian": "ca-certificates", "ubuntu": "ca-certificates",
                "fedora": "ca-certificates", "arch": "ca-certificates"}),
    Dependency("lm-sensors", "program", ("sensors-detect",),
               {"debian": "lm-sensors", "ubuntu": "lm-sensors", "fedora": "lm_sensors",
                "arch": "lm_sensors"}),
)

BY_KEY = {dep.key: dep for dep in DEPENDENCIES}

# The graphics libraries go in one note: four notes for one missing
# graphical environment would bury the rest.
GRAPHICS_LIBRARIES = ("vulkan", "egl", "opengl", "opencl", "vaapi")


def family(os_release: dict) -> Optional[str]:
    """Which family's package names apply: Ubuntu before Debian (Mint, Pop
    and the rest say both), and None for one that is none of the four."""
    ids = [os_release.get("ID", "")] + os_release.get("ID_LIKE", "").split()
    ids = [i.strip().lower() for i in ids if i.strip()]
    for nombre in ("ubuntu", "debian", "fedora", "arch"):
        if nombre in ids:
            return nombre
    if any(i in ("rhel", "centos", "rocky", "almalinux") for i in ids):
        return "fedora"
    return None


def read_os_release() -> dict:
    datos: dict[str, str] = {}
    for ruta in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(sysroot.ruta(ruta), encoding="utf-8") as archivo:
                for linea in archivo:
                    clave, signo, valor = linea.strip().partition("=")
                    if signo:
                        # Gentoo's quotes are single: ID='gentoo'.
                        datos[clave] = valor.strip().strip('"').strip("'")
            return datos
        except OSError:
            continue
    return datos


def nvidia_major() -> Optional[str]:
    """The proprietary driver's major version, «595», from its module."""
    try:
        with open(sysroot.ruta("/sys/module/nvidia/version"), encoding="ascii") as archivo:
            version = archivo.read().strip()
    except OSError:
        return None
    major = version.split(".")[0]
    return major if major.isdigit() else None


def package_text(dep: Dependency, familia: Optional[str],
                 nvidia: Optional[str] = None) -> str:
    """«libvulkan1», or every family's when the distribution is none of them:
    «libvulkan1 (Debian, Ubuntu), vulkan-loader (Fedora), vulkan-icd-loader (Arch)».
    `nvidia` is the driver's major version, where the package carries it."""
    paquetes = {fam: nombre.replace("{nvidia}", nvidia or "NNN")
                for fam, nombre in dep.packages.items() if nombre}
    if familia is not None:
        return paquetes[familia]
    grupos: dict[str, list[str]] = {}
    for fam in FAMILIES:
        if fam in paquetes:
            grupos.setdefault(paquetes[fam], []).append(FAMILY_NAMES[fam])
    return ", ".join(f"{paquete} ({', '.join(familias)})" for paquete, familias in grupos.items())


def program_path(name: str) -> Optional[str]:
    """Where a system program is, also in the sbin folders a user's PATH may
    leave out (Debian's does: modinfo is in /usr/sbin)."""
    camino = os.pathsep.join([system_environment().get("PATH", ""), *PROGRAM_DIRS])
    return shutil.which(name, path=camino)


def _in_loader_cache(soname: str) -> Optional[bool]:
    """Whether ldconfig's cache knows that soname. Its strings are shared: the
    name is usually the tail of its path («/usr/lib/libvulkan.so.1»)."""
    try:
        with open(LD_CACHE, "rb") as cache:
            datos = cache.read()
    except OSError:
        return None
    nombre = soname.encode() + b"\x00"
    return b"/" + nombre in datos or b"\x00" + nombre in datos


def _present_now(dep: Dependency) -> bool:
    if dep.kind == "data":
        return any(os.path.isfile(ruta) for ruta in dep.names)
    if dep.kind == "library":
        for soname in dep.names:
            en_cache = _in_loader_cache(soname)
            if en_cache is None:
                en_cache = any(os.path.exists(os.path.join(d, soname)) for d in LIBRARY_DIRS)
            if not en_cache:
                return False
        return True
    return all(program_path(nombre) for nombre in dep.names)


def present(key: str) -> Optional[bool]:
    """Whether this machine has it; with a dump mounted, what it had when it
    was dumped (None if that was not recorded)."""
    return sysroot.a_traves("paquetes", key, _present_now, BY_KEY[key])
