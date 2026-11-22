"""What amdgpu only reports through its ioctl.

Some of a Radeon's details are in no sysfs file: the memory type, the bus
width, how many compute units are enabled and how many ROPs it has. The
driver returns them for `DRM_IOCTL_AMDGPU_INFO`, the same query Mesa and
LACT use.

The query goes to the render node (`/dev/dri/renderD128`), which desktop
distributions leave readable by everyone so any program can draw: no root,
no `video` group, and nothing is written.
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
# The video BIOS's identity: AMDGPU_INFO_VBIOS with its INFO subquery, which
# answers `struct drm_amdgpu_info_vbios` (name, part number, version, the
# version string and the build date), 200 bytes. Not its image.
AMDGPU_INFO_VBIOS, AMDGPU_INFO_VBIOS_INFO, VBIOS_REPLY = 0x1B, 0x3, 200
REPLY_SIZE = 1024                      # the struct is about 300 bytes

# Offsets in `struct drm_amdgpu_info_device`. The struct is ABI: the kernel
# only appends fields, so these never move. `device_id` doubles as a check:
# if it differs from sysfs, the layout is not what we expect and nothing is
# trusted.
FIELDS = {
    "device_id": 0, "chip_rev": 4, "external_rev": 8, "pci_rev": 12, "family": 16,
    "num_shader_engines": 20, "num_shader_arrays_per_engine": 24,
    "cu_active_number": 48, "enabled_rb_pipes_mask": 120, "num_rb_pipes": 124,
    "num_hw_gfx_contexts": 128, "vram_type": 176, "vram_bit_width": 180,
}
# Bit 0 of `ids_flags` (after num_hw_gfx_contexts and 4 bytes of padding) is
# AMDGPU_IDS_FLAGS_FUSION, set when the GPU is part of the processor. That is
# the reliable way to spot an APU: it carves its VRAM out of system RAM, so
# the VRAM size can't tell.
FIELDS_64 = {"max_engine_clock": 32, "max_memory_clock": 40, "ids_flags": 136}
# The caches, appended for gfx11 (older chips leave them at 0): L2 in KiB,
# the Infinity Cache («MALL») in bytes. Offsets from amdgpu_drm.h at v6.15,
# where `family` and `ids_flags` above fall at 16 and 136 too.
GL2C_CACHE_SIZE, MALL_SIZE = 404, 408

AMDGPU_IDS_FLAGS_FUSION = 0x1

VRAM_TYPES = {
    1: "GDDR1", 2: "DDR2", 3: "GDDR3", 4: "GDDR4", 5: "GDDR5", 6: "HBM",
    7: "DDR3", 8: "DDR4", 9: "GDDR6", 10: "DDR5", 11: "LPDDR4", 12: "LPDDR5",
}

# Transfers per cycle of the clock the driver reports, per memory type. This
# comes from how each memory works, checked against known cards (an RX 9070
# XT does 20 Gbps at 1258 MHz). A type missing here gets no bandwidth rather
# than a guessed one.
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
        # DEV_INFO takes no parameters, but the ioctl checks the size of the
        # whole struct, union included.
        ("_union", ctypes.c_uint32 * 4),
    ]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """What the driver knows about the chip and doesn't publish in sysfs."""

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
    l2_cache_bytes: Optional[int] = None
    infinity_cache_bytes: Optional[int] = None
    # None when the ioctl didn't answer, which is not the same as false.
    is_apu: Optional[bool] = None

    @property
    def rops(self) -> Optional[int]:
        """The units that write pixels, across all shader arrays."""
        if not (self.render_backends and self.shader_engines
                and self.arrays_per_engine):
            return None
        return self.render_backends * self.shader_engines * self.arrays_per_engine

    @property
    def memory_data_rate_hz(self) -> Optional[int]:
        """The effective data rate, not the command clock."""
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
    """Ask the driver. None on any doubt, without complaining."""
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
    # A different id means a different struct layout: every other field would
    # be read from the wrong offset.
    if expected_device_id is not None and read_fields["device_id"] != expected_device_id:
        return None

    khz = {name: struct.unpack_from("<Q", buffer, place)[0]
           for name, place in FIELDS_64.items()}
    l2_kib = struct.unpack_from("<I", buffer, GL2C_CACHE_SIZE)[0]
    mall = struct.unpack_from("<Q", buffer, MALL_SIZE)[0]
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
        l2_cache_bytes=l2_kib * 1024 or None,
        infinity_cache_bytes=mall or None,
    )


@dataclass(frozen=True, slots=True)
class VbiosInfo:
    """The video BIOS as the driver reads it from the card."""

    version: Optional[str] = None       # «023.008.000.068.000001»
    date: Optional[str] = None          # ISO: «2024-12-04»


def vbios(node: str) -> Optional[VbiosInfo]:
    """Ask the driver for its video BIOS's version and date."""
    try:
        descriptor = os.open(node, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        buffer = ctypes.create_string_buffer(VBIOS_REPLY)
        request = _Request(ctypes.addressof(buffer), VBIOS_REPLY, AMDGPU_INFO_VBIOS,
                           (ctypes.c_uint32 * 4)(AMDGPU_INFO_VBIOS_INFO, 0, 0, 0))
        order = _iowr("d", DRM_COMMAND_BASE + DRM_AMDGPU_INFO, ctypes.sizeof(_Request))
        if fcntl.ioctl(descriptor, order, request) != 0:
            return None
    except (OSError, ValueError):
        return None
    finally:
        os.close(descriptor)

    def text(start: int, end: int) -> Optional[str]:
        return buffer.raw[start:end].split(b"\0")[0].decode("ascii", "replace").strip() or None

    # «2024/12/04 21:24»: the day is what is shown, in ISO.
    raw_date = text(168, 200) or ""
    date = raw_date[:10].replace("/", "-") if len(raw_date) >= 10 else None
    return VbiosInfo(version=text(136, 168), date=date)


def _iowr(letter: str, number: int, size: int) -> int:
    """`_IOWR` from <asm/ioctl.h>, which Python doesn't provide."""
    READ_WRITE = 3
    return (READ_WRITE << 30) | (size << 16) | (ord(letter) << 8) | number
