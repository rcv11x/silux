"""How many execution units an Intel GPU has.

sysfs doesn't say. OpenCL does answer, but its «compute units» are
subslices (sixteen EUs each on Xe-LP), so an 80 EU Iris Xe would show 5.

The driver knows: `DRM_IOCTL_I915_GETPARAM` with `I915_PARAM_EU_TOTAL`, the
same query Mesa and `intel_gpu_top` use, on the render node (readable by
everyone, as in `amdgpu.py`). The chip id is checked against sysfs so the
answer can't be credited to another card.

Only for `i915`: the newer `xe` driver has a different interface.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
import pathlib
from dataclasses import dataclass
from typing import Optional

from . import sysroot

# DRM_IOCTL_I915_GETPARAM = DRM_IOWR(DRM_COMMAND_BASE + DRM_I915_GETPARAM, …)
DRM_COMMAND_BASE = 0x40
DRM_I915_GETPARAM = 0x06

# From <drm/i915_drm.h>. ABI: numbers are never reused.
I915_PARAM_CHIPSET_ID = 4
I915_PARAM_SUBSLICE_TOTAL = 33
I915_PARAM_EU_TOTAL = 34


@dataclass(frozen=True)
class DeviceInfo:
    """Each field is None where the driver didn't answer."""

    chipset_id: Optional[int] = None
    eu_total: Optional[int] = None
    subslices: Optional[int] = None


class _Request(ctypes.Structure):
    """`struct drm_i915_getparam`: the parameter and where to write it.

    The pointer is 8-byte aligned, so ctypes pads 4 bytes after the first
    field. The size must be 16 or the kernel won't recognise the ioctl.
    """

    _fields_ = [("param", ctypes.c_int32),
                ("value", ctypes.POINTER(ctypes.c_int32))]


def query(node: str, expected_device_id: Optional[int] = None) -> Optional[DeviceInfo]:
    """Ask the driver. None on any doubt, without complaining."""
    try:
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None

    try:
        chipset = _param(descriptor, I915_PARAM_CHIPSET_ID)
        # Another chip id means this node belongs to another card.
        if expected_device_id is not None and chipset != expected_device_id:
            return None
        return DeviceInfo(
            chipset_id=chipset,
            eu_total=_param(descriptor, I915_PARAM_EU_TOTAL),
            subslices=_param(descriptor, I915_PARAM_SUBSLICE_TOTAL),
        )
    finally:
        os.close(descriptor)


def render_node(device: pathlib.Path | str) -> Optional[str]:
    """A card's `/dev/dri/renderD*`, from its PCI node."""
    folder = pathlib.Path(sysroot.path(device), "drm")
    if not folder.is_dir():
        return None
    for entry in sorted(folder.glob("renderD*")):
        path = f"/dev/dri/{entry.name}"
        if sysroot.active() or os.path.exists(path):
            return path
    return None


def _param(descriptor: int, which: int) -> Optional[int]:
    """A single GETPARAM; unknown parameters answer with an error."""
    value = ctypes.c_int32(0)
    request = _Request(which, ctypes.pointer(value))
    try:
        if fcntl.ioctl(descriptor, _ORDER, request) != 0:
            return None
    except (OSError, ValueError):
        return None
    # No GPU has zero units: the driver answers 0 when it knows the parameter
    # but has no value for it.
    return value.value or None


def _iowr(letter: str, number: int, size: int) -> int:
    """`_IOWR` from <asm/ioctl.h>, which Python doesn't provide."""
    READ_WRITE = 3
    return (READ_WRITE << 30) | (size << 16) | (ord(letter) << 8) | number


_ORDER = _iowr("d", DRM_COMMAND_BASE + DRM_I915_GETPARAM, ctypes.sizeof(_Request))
