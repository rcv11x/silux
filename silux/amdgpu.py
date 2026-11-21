"""What amdgpu only tells when asked by ioctl.

Some data of a Radeon is in no sysfs file: the memory type, the bus width,
how many compute units are really active and how many ROPs the chip has.
The driver has them, but only gives them through `DRM_IOCTL_AMDGPU_INFO`,
as Mesa and LACT ask.

The render node (`/dev/dri/renderD128`) is opened, readable by everyone on
any desktop distribution so any program can draw. No root or `video` group
is needed, and nothing is written: the request only reads.

The memory bandwidth comes from here too: not a driver value but a
multiplication, and one people look for.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
import pathlib
import struct
from dataclasses import dataclass
from typing import Optional

from . import sysroot

# DRM_IOCTL_AMDGPU_INFO = DRM_IOWR(DRM_COMMAND_BASE + DRM_AMDGPU_INFO, …)
DRM_COMMAND_BASE = 0x40
DRM_AMDGPU_INFO = 0x05
AMDGPU_INFO_DEV_INFO = 0x16
REPLY_SIZE = 1024                      # plenty: the structure is about 300 B

# Offsets inside `struct drm_amdgpu_info_device`. They are ABI: the kernel can
# only add fields at the end, never move existing ones, so fixing them here is
# safe. `device_id` is a check: if it differs from sysfs's, this table does
# not apply and everything is dropped.
FIELDS = {
    "device_id": 0, "chip_rev": 4, "external_rev": 8, "pci_rev": 12, "family": 16,
    "num_shader_engines": 20, "num_shader_arrays_per_engine": 24,
    "cu_active_number": 48, "enabled_rb_pipes_mask": 120, "num_rb_pipes": 124,
    "num_hw_gfx_contexts": 128, "vram_type": 176, "vram_bit_width": 180,
}
# `ids_flags` comes after num_hw_gfx_contexts (128) and a 4-byte gap. Its bit
# 0 is AMDGPU_IDS_FLAGS_FUSION: the driver sets it when the chip is fused with
# the processor, an APU. The only reliable way to know; VRAM cannot tell, as
# an APU reserves system RAM and seems to have its own.
FIELDS_64 = {"max_engine_clock": 32, "max_memory_clock": 40, "ids_flags": 136}

AMDGPU_IDS_FLAGS_FUSION = 0x1

VRAM_TYPES = {
    1: "GDDR1", 2: "DDR2", 3: "GDDR3", 4: "GDDR4", 5: "GDDR5", 6: "HBM",
    7: "DDR3", 8: "DDR4", 9: "GDDR6", 10: "DDR5", 11: "LPDDR4", 12: "LPDDR5",
}

# How many transfers each type makes per cycle of the clock the driver
# publishes. Not readable: it comes from how each memory works, checked
# against known cards (an RX 9070 XT gives 20 Gbps at 1258 MHz, an RX 580 gave
# 8 at 2000, a Vega 1.89 at 945). Types not here get no bandwidth rather than
# a made-up one.
TRANSFERS = {
    "GDDR6": 16, "GDDR5": 4, "GDDR4": 4, "GDDR3": 4,
    "HBM": 2, "DDR3": 2, "DDR4": 2, "DDR5": 2, "LPDDR4": 2, "LPDDR5": 2,
}


class _Request(ctypes.Structure):
    """`struct drm_amdgpu_info`: where to put the answer and what is asked."""

    _fields_ = [
        ("return_pointer", ctypes.c_uint64),
        ("return_size", ctypes.c_uint32),
        ("query", ctypes.c_uint32),
        # The query's parameter union. DEV_INFO uses none, but the size must be
        # the whole structure's or the ioctl fails.
        ("_union", ctypes.c_uint32 * 4),
    ]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """What the driver knows of the chip and does not publish in sysfs."""

    device_id: Optional[int] = None
    family: Optional[int] = None
    vram_type: Optional[str] = None
    vram_bits: Optional[int] = None
    compute_units: Optional[int] = None
    shader_engines: Optional[int] = None
    arrays_per_engine: Optional[int] = None
    render_backends: Optional[int] = None
    max_engine_hz: Optional[int] = None
    max_memory_hz: Optional[int] = None
    # None when the ioctl did not answer: not knowing is not being false.
    is_apu: Optional[bool] = None

    @property
    def rops(self) -> Optional[int]:
        """The units that write pixels, spread over each array."""
        if not (self.render_backends and self.shader_engines
                and self.arrays_per_engine):
            return None
        return self.render_backends * self.shader_engines * self.arrays_per_engine

    @property
    def memory_data_rate_hz(self) -> Optional[int]:
        """The real rate data travels at, not the command clock."""
        factor = TRANSFERS.get(self.vram_type or "")
        if not (factor and self.max_memory_hz):
            return None
        return self.max_memory_hz * factor

    @property
    def bandwidth_bytes(self) -> Optional[int]:
        """Memory bandwidth, in bytes per second."""
        if not (self.memory_data_rate_hz and self.vram_bits):
            return None
        return int(self.memory_data_rate_hz * self.vram_bits / 8)


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


def query(node: str, expected_device_id: Optional[int] = None) -> Optional[DeviceInfo]:
    """Ask the driver. None at any doubt, without complaining."""
    try:
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None

    try:
        buffer = ctypes.create_string_buffer(REPLY_SIZE)
        request = _Request(ctypes.addressof(buffer), REPLY_SIZE,
                             AMDGPU_INFO_DEV_INFO, (ctypes.c_uint32 * 4)())
        order = _iowr("d", DRM_COMMAND_BASE + DRM_AMDGPU_INFO, ctypes.sizeof(_Request))
        if fcntl.ioctl(descriptor, order, request) != 0:
            return None
    except (OSError, ValueError):
        return None
    finally:
        os.close(descriptor)

    read_fields = {name: struct.unpack_from("<I", buffer, place)[0]
              for name, place in FIELDS.items()}
    # If the id does not match sysfs's, the structure is not the expected one
    # and everything else would be read from the wrong places.
    if expected_device_id is not None and read_fields["device_id"] != expected_device_id:
        return None

    khz = {name: struct.unpack_from("<Q", buffer, place)[0]
           for name, place in FIELDS_64.items()}
    return DeviceInfo(
        device_id=read_fields["device_id"] or None,
        family=read_fields["family"] or None,
        vram_type=VRAM_TYPES.get(read_fields["vram_type"]),
        vram_bits=read_fields["vram_bit_width"] or None,
        compute_units=read_fields["cu_active_number"] or None,
        shader_engines=read_fields["num_shader_engines"] or None,
        arrays_per_engine=read_fields["num_shader_arrays_per_engine"] or None,
        render_backends=read_fields["num_rb_pipes"] or None,
        is_apu=bool(khz["ids_flags"] & AMDGPU_IDS_FLAGS_FUSION),
        max_engine_hz=khz["max_engine_clock"] * 1000 or None,
        max_memory_hz=khz["max_memory_clock"] * 1000 or None,
    )


def _iowr(letter: str, number: int, size: int) -> int:
    """The same `_IOWR` as <asm/ioctl.h>, which Python does not provide."""
    READ_WRITE = 3
    return (READ_WRITE << 30) | (size << 16) | (ord(letter) << 8) | number
