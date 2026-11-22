"""The telemetry table a Radeon's firmware publishes moment to moment.

`gpu_metrics` is a binary the driver leaves in sysfs with what the card's
microcontroller reports. It has things found nowhere else:

- **Why the card is throttling**, if it is. The question anyone asks when a
  game runs slower than it should, otherwise answered only by eyeing the
  temperature.
- **The voltage regulators' temperatures**, which hwmon doesn't expose.
- **The memory's effective clock**, the one on spec sheets: a GDDR6 at a
  1258 MHz command clock runs at 2505 effective.

The format carries its version in the header and has changed several times,
not always by appending. So each version has its own explicit offset table
here: reading a v1.4 with a v1.3's offsets gives no error, only believable
wrong numbers, which is worse. A version not in the table is let through
with a note instead of guessed.
"""

from __future__ import annotations

import pathlib
import struct
from dataclasses import dataclass
from typing import Optional

HEADER = "<HBB"          # size, format revision, content revision

# Why the card throttles. The bits of `indep_throttle_status`, which AMD
# defined precisely so they don't depend on the chip model.
THROTTLE_REASONS = {
    0: "gpu.throttle.amd.ppt0",
    1: "gpu.throttle.amd.ppt1",
    2: "gpu.throttle.amd.ppt2",
    3: "gpu.throttle.amd.ppt3",
    4: "gpu.throttle.amd.tdcgfx",
    5: "gpu.throttle.amd.tdcsoc",
    6: "gpu.throttle.amd.tdcmem",
    7: "gpu.throttle.amd.tgpu",
    8: "gpu.throttle.amd.tmem",
    9: "gpu.throttle.amd.tedge",
    10: "gpu.throttle.amd.thotspot",
    11: "gpu.throttle.amd.tsoc",
    12: "gpu.throttle.amd.tvrgfx",
    13: "gpu.throttle.amd.tvrsoc",
    14: "gpu.throttle.amd.tvrmem",
    15: "gpu.throttle.amd.tvrmem",
    16: "gpu.throttle.amd.apcc",
    17: "gpu.throttle.amd.ppm",
    18: "gpu.throttle.amd.fit",
    19: "gpu.throttle.amd.vrhot",
    20: "gpu.throttle.amd.vrhot",
}

# The offsets in each version of the table. v1.0 to v1.3 share the whole
# first half (each added fields at the end), so each is built on the one
# before; v1.4 and later reordered and don't fit.
_V1_0 = {
    "temp_edge": ("H", 4), "temp_hotspot": ("H", 6), "temp_mem": ("H", 8),
    "temp_vr_gfx": ("H", 10), "temp_vr_soc": ("H", 12), "temp_vr_mem": ("H", 14),
    "gfx_activity": ("H", 16), "memory_activity": ("H", 18), "video_activity": ("H", 20),
    "socket_power": ("H", 22),
    "gfx_clock_average": ("H", 40), "soc_clock_average": ("H", 42),
    "memory_clock_average": ("H", 44),
    "gfx_clock": ("H", 54), "soc_clock": ("H", 56), "memory_clock": ("H", 58),
    "throttle_status": ("I", 68),
    "fan_rpm": ("H", 72), "link_width": ("H", 74), "link_speed": ("H", 76),
}
_V1_3 = _V1_0 | {
    "voltage_soc": ("H", 104), "voltage_gfx": ("H", 106), "voltage_mem": ("H", 108),
    "throttle_independent": ("Q", 112),
}

# The 2.x are the APUs', and not a 1.x with fields added: the layout is
# different. They come from `gpu_metrics_v2_1` in
# `drivers/gpu/drm/amd/include/kgd_pp_interface.h`, with offsets worked out
# by C's alignment rules (the clock's `uint64` forces 8-byte alignment) for a
# total of 120 bytes, which is what the table declares.
#
# What an APU lacks isn't there: no VRAM of its own to measure, no separate
# voltage regulators, no PCIe link to negotiate. It brings its own instead:
# each CPU core's temperature and clock, and the power split between CPU,
# SoC and graphics. For now only the fields the model can already show are
# read.
#
# `fan_pwm` is deliberately not read as `fan_rpm`: one is a 0 to 255 duty
# cycle, the other revolutions per minute. A PWM shown as a speed would be a
# fan at 200 RPM that doesn't exist.
#
# Left unread on purpose, because they aren't what they seem:
# `temperature_soc` (offset 6) is the SoC's, not a graphics hot spot; and
# `average_socket_power` (offset 40) is the whole package's power, CPU cores
# included (smu_v13_0_4_get_gpu_metrics and yellow_carp_get_gpu_metrics copy
# it from `metrics.SocketPower`). Shown as the graphics' «Hot spot» and
# «Power», they lied.
#
# Nor the activity (`average_gfx_activity` and `average_mm_activity`,
# offsets 28 and 30): on APUs it comes in hundredths of a point, and 0.45 %
# of video would show as «45 %». Graphics usage comes from
# `gpu_busy_percent` and video's from `vcn_busy_percent` (6.10).
_V2_1 = {
    "temp_edge": ("H", 4),           # temperature_gfx
    "gfx_clock_average": ("H", 64),
    "soc_clock_average": ("H", 66),
    "memory_clock_average": ("H", 68),
    "gfx_clock": ("H", 76),
    "soc_clock": ("H", 78),
    "memory_clock": ("H", 80),
    "throttle_status": ("I", 108),
}

# 1.0 is left out on purpose. In `gpu_metrics_v1_0` (kgd_pp_interface.h)
# the first thing after the header is the `uint64_t system_clock_counter`,
# and the kernel warns that this structure «is not naturally aligned»: its
# fields aren't where 1.1's are. Read with these offsets it gave
# temperatures and clocks taken from the time counter's bytes, believable
# and false. It goes through `uninterpreted`, which says so, until a dump
# can check its table.
VERSIONS = {
    (1, 1): _V1_0,
    (1, 2): _V1_0,
    (1, 3): _V1_3,
    (2, 1): _V2_1,
}

# The versions whose temperatures come in centidegrees rather than degrees.
# The driver copies what the firmware gives without converting it, while the
# usual sensor functions divide by a hundred, so on 2.x a 44.1 arrives as
# 4410.
CENTIDEGREES = {(2, 1)}

# A field of all ones is «this chip doesn't measure it». It must be dropped
# before showing 65 535 degrees or a four-billion clock.
NO_DATA = {"H": 0xFFFF, "I": 0xFFFFFFFF, "Q": 0xFFFFFFFFFFFFFFFF}


@dataclass(frozen=True, slots=True)
class Metrics:
    """A telemetry snapshot, already in the model's units."""

    version: str = ""
    temp_edge_c: Optional[float] = None
    temp_hotspot_c: Optional[float] = None
    temp_memory_c: Optional[float] = None
    temp_vr_gfx_c: Optional[float] = None
    temp_vr_soc_c: Optional[float] = None
    temp_vr_mem_c: Optional[float] = None
    gfx_activity_percent: Optional[float] = None
    memory_activity_percent: Optional[float] = None
    video_activity_percent: Optional[float] = None
    socket_power_w: Optional[float] = None
    gfx_clock_hz: Optional[int] = None
    gfx_clock_average_hz: Optional[int] = None
    soc_clock_hz: Optional[int] = None
    memory_clock_hz: Optional[int] = None
    # The memory's effective clock: the one on spec sheets.
    memory_clock_effective_hz: Optional[int] = None
    fan_rpm: Optional[int] = None
    link_width: Optional[int] = None
    link_speed_gts: Optional[float] = None
    voltage_gfx_v: Optional[float] = None
    voltage_soc_v: Optional[float] = None
    voltage_memory_v: Optional[float] = None
    throttle_reasons: tuple[str, ...] = ()
    throttled: Optional[bool] = None


def parse(raw: bytes) -> Optional[Metrics]:
    """None if the table is empty or of an unknown version."""
    if len(raw) < 4:
        return None
    size, format_rev, content_rev = struct.unpack_from(HEADER, raw, 0)
    layout = VERSIONS.get((format_rev, content_rev))
    if layout is None:
        return None
    # The firmware itself says how long it is: if what was read falls short,
    # the table is cut and there's no telling which fields are good.
    usable = min(size, len(raw))

    def field(name: str) -> Optional[int]:
        if name not in layout:
            return None
        field_format, offset = layout[name]
        if offset + struct.calcsize(field_format) > usable:
            return None
        value = struct.unpack_from("<" + field_format, raw, offset)[0]
        return None if value == NO_DATA[field_format] else value

    mhz = lambda name: (lambda v: v * 1_000_000 if v else None)(field(name))
    def temperature(name: str) -> Optional[float]:
        """A temperature, whether in degrees or centidegrees.

        The version says which to expect, but the range is checked too,
        because a mistake here would go unnoticed. A GPU runs between 0 and
        125 degrees, so 4410 can't be degrees and 44 can't be centidegrees:
        the two cases are told apart without ambiguity and without relying on
        the version.
        """
        value = field(name)
        if value is None:
            return None
        if value > 200:                  # no GPU reaches 200 degrees
            return round(value / 100, 1)
        return float(value)
    volts = lambda name: (lambda v: round(v / 1000, 3) if v else None)(field(name))
    percent = lambda name: (lambda v: float(v) if v is not None and v <= 100 else None)(field(name))

    # The chip-independent one goes first; the other only makes sense knowing
    # the ASIC underneath, and then the reason can't be named.
    flags = field("throttle_independent")
    reasons = _reasons(flags) if flags is not None else ()
    if flags is None:
        status = field("throttle_status")
        throttled = None if status is None else bool(status)
    else:
        throttled = bool(flags)

    width = field("link_width")
    speed = field("link_speed")
    return Metrics(
        version=f"{format_rev}.{content_rev}",
        temp_edge_c=temperature("temp_edge"),
        temp_hotspot_c=temperature("temp_hotspot"),
        temp_memory_c=temperature("temp_mem"),
        temp_vr_gfx_c=temperature("temp_vr_gfx"),
        temp_vr_soc_c=temperature("temp_vr_soc"),
        temp_vr_mem_c=temperature("temp_vr_mem"),
        gfx_activity_percent=percent("gfx_activity"),
        memory_activity_percent=percent("memory_activity"),
        video_activity_percent=percent("video_activity"),
        socket_power_w=(lambda v: float(v) if v is not None else None)(field("socket_power")),
        gfx_clock_hz=mhz("gfx_clock"),
        gfx_clock_average_hz=mhz("gfx_clock_average"),
        soc_clock_hz=mhz("soc_clock"),
        memory_clock_hz=mhz("memory_clock"),
        memory_clock_effective_hz=mhz("memory_clock_average"),
        fan_rpm=field("fan_rpm"),
        link_width=width or None,
        # In tenths of a gigatransfer: 160 is 16.0 GT/s.
        link_speed_gts=round(speed / 10, 1) if speed else None,
        voltage_gfx_v=volts("voltage_gfx"),
        voltage_soc_v=volts("voltage_soc"),
        voltage_memory_v=volts("voltage_mem"),
        throttle_reasons=reasons,
        throttled=throttled,
    )


def read(device: pathlib.Path | str) -> Optional[Metrics]:
    """Read the table from a card's PCI node."""
    raw = raw_of(device)
    return parse(raw) if raw else None


def raw_of(device: pathlib.Path | str) -> Optional[bytes]:
    """The table as is, uninterpreted."""
    try:
        return pathlib.Path(device, "gpu_metrics").read_bytes() or None
    except OSError:
        return None


def uninterpreted(device: pathlib.Path | str) -> Optional[tuple[str, int]]:
    """The version and size of a table that exists and can't be read.

    None when there is no table or when it is understood. It lets the user
    be told that the card publishes telemetry this program doesn't interpret
    yet, rather than saying nothing, and puts the version in the report,
    which is where its offset table can come from without the part at hand.

    Interpreting a version with another's offsets gives no error, only
    believable wrong numbers: until a real dump can check it, it is said to
    be unread rather than guessed.
    """
    raw = raw_of(device)
    if not raw or len(raw) < 4:
        return None
    size, format_rev, content_rev = struct.unpack_from(HEADER, raw, 0)
    if (format_rev, content_rev) in VERSIONS:
        return None
    return f"{format_rev}.{content_rev}", min(size, len(raw))


def version_of(raw: bytes) -> Optional[str]:
    """A table's version, even when its content can't be interpreted."""
    if len(raw) < 4:
        return None
    _size, format_rev, content_rev = struct.unpack_from(HEADER, raw, 0)
    return f"{format_rev}.{content_rev}"


def _reasons(flags: int) -> tuple[str, ...]:
    """The reasons set, without repeats: several bits name the same thing."""
    seen: list[str] = []
    for bit, reason in THROTTLE_REASONS.items():
        if flags & (1 << bit) and reason not in seen:
            seen.append(reason)
    return tuple(seen)
