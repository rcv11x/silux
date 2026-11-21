"""How many execution units an Intel GPU really has.

The number is nowhere in sysfs. Only OpenCL answered, and it answers
something else: its «compute units» are subslices, of sixteen EU each on
Xe-LP, so an 80 EU Iris Xe G7 showed a 5 labelled EU.

The driver knows, through `DRM_IOCTL_I915_GETPARAM` with
`I915_PARAM_EU_TOTAL`, where Mesa and `intel_gpu_top` take it from. The
render node is opened, readable by anyone as in `amdgpu.py`, and only read.
The chip id is a check: if it differs from sysfs's, this is another card and
the answer is dropped.

Only for `i915`: the newer `xe` driver has its own interface.
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

# From <drm/i915_drm.h>. They are ABI: the numbers are never reused.
I915_PARAM_CHIPSET_ID = 4
I915_PARAM_SUBSLICE_TOTAL = 33
I915_PARAM_EU_TOTAL = 34


@dataclass(frozen=True)
class DeviceInfo:
    """None in each field the driver did not answer."""

    chipset_id: Optional[int] = None
    eu_total: Optional[int] = None
    subslices: Optional[int] = None


class _Request(ctypes.Structure):
    """`struct drm_i915_getparam`: what is asked and where to put the answer.

    The pointer is aligned to eight, so ctypes pads four bytes between the
    two fields. The size must come out 16, or the ioctl is not the one the
    kernel expects.
    """

    _fields_ = [("param", ctypes.c_int32),
                ("value", ctypes.POINTER(ctypes.c_int32))]


def query(node: str, expected_device_id: Optional[int] = None) -> Optional[DeviceInfo]:
    """Ask the driver. None at any doubt, without complaining."""
    try:
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None

    try:
        chipset = _param(descriptor, I915_PARAM_CHIPSET_ID)
        # If the chip is not the one sysfs says, this node is another card's
        # and all it answered would be credited to the wrong one.
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
    """A single `GETPARAM`. Those that do not exist answer with an error."""
    value = ctypes.c_int32(0)
    request = _Request(which, ctypes.pointer(value))
    try:
        if fcntl.ioctl(descriptor, _ORDER, request) != 0:
            return None
    except (OSError, ValueError):
        return None
    # Zero is no answer: no GPU has zero units. The driver returns it when it
    # knows the parameter but has nothing to say.
    return value.value or None


def _iowr(letter: str, number: int, size: int) -> int:
    """The same `_IOWR` as <asm/ioctl.h>, which Python does not provide."""
    READ_WRITE = 3
    return (READ_WRITE << 30) | (size << 16) | (ord(letter) << 8) | number


_ORDER = _iowr("d", DRM_COMMAND_BASE + DRM_I915_GETPARAM, ctypes.sizeof(_Request))
