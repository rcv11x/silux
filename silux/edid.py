"""Decodes the EDID, a monitor's identification plate.

Every display carries 128 bytes (sometimes with extensions after them) that
the kernel leaves as they are in `/sys/class/drm/<connector>/edid`, readable
without permissions. Inside is what sysfs doesn't tell any other way: who
made it, which model it is, when it was made, its real size, and the
resolution and refresh it wants to run at.

The format dates from 1994 and shows it. The maker's three letters are
packed in five bits each, sizes are split across bytes with the top four
bits of a third, and the model's name may be in any of four descriptors or
in none. The same kind of work as `spd.py`.

The three letters are turned into a name with `pnp.ids`, from the same
hwdata package `pci.ids` comes from.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional

HEADER = bytes((0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00))
BLOCK = 128

PNP_CANDIDATES = (
    "/usr/share/hwdata/pnp.ids",
    "/usr/share/misc/pnp.ids",
    "/usr/share/pnp.ids",
)

# The four 18-byte descriptors from byte 54 on.
DESCRIPTORS = range(54, 126, 18)
TYPE_SERIAL = 0xFF
TYPE_TEXT = 0xFE
TYPE_RANGES = 0xFD
TYPE_NAME = 0xFC


@dataclass(frozen=True, slots=True)
class VideoMode:
    """A video mode the monitor declares it supports."""

    width: int
    height: int
    refresh_hz: float
    interlaced: bool = False
    native: bool = False

    @property
    def label(self) -> str:
        suffix = "i" if self.interlaced else ""
        return f"{self.width} × {self.height}{suffix} @ {self.refresh_hz:g} Hz"


@dataclass(frozen=True, slots=True)
class Edid:
    """What a display says about itself."""

    manufacturer_id: Optional[str] = None      # the three letters: GBT, GSM…
    manufacturer: Optional[str] = None         # already translated
    model: Optional[str] = None
    product_code: Optional[int] = None
    serial: Optional[str] = None
    year: Optional[int] = None
    week: Optional[int] = None
    version: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    # Whether those two sizes are to the millimetre. The EDID's base block
    # gives them in whole centimetres, which made a 27" monitor «26.6"»: half
    # a centimetre per side moves the diagonal a quarter of an inch. The
    # native mode's timing has them in millimetres; when it doesn't, or they
    # don't match the others, the centimetres stay and the diagonal is shown
    # for what it is, approximate.
    size_exact: bool = False
    # Some TVs put their aspect ratio where the size goes, in centimetres
    # (16 × 9) or tenfold (160 × 90): a 32" TV read 72.3". No size, then.
    size_is_ratio: bool = False
    native_width: Optional[int] = None
    native_height: Optional[int] = None
    native_refresh_hz: Optional[float] = None
    # The range the monitor declares, which isn't the preferred mode: a 240 Hz
    # OLED may prefer 60 and still reach 240. Showing only the preferred mode
    # falls far short.
    refresh_min_hz: Optional[int] = None
    refresh_max_hz: Optional[int] = None
    # From the CTA-861 extensions. The base block only has room for the
    # preferred mode and a few standard ones, so without them a monitor that
    # does 4K at 120 looks like it only does 1080p at 60.
    modes: tuple[VideoMode, ...] = ()
    hdr: tuple[str, ...] = ()
    color_spaces: tuple[str, ...] = ()
    audio: tuple[str, ...] = ()

    @property
    def best_mode(self) -> Optional[VideoMode]:
        """The most demanding mode declared.

        Sorted by pixels and then refresh: between 4K at 60 and 1080p at 240,
        4K wins, which is what defines what the panel can do.
        """
        if not self.modes:
            return None
        return max(self.modes, key=lambda m: (m.width * m.height, m.refresh_hz))

    @property
    def diagonal_inches(self) -> Optional[float]:
        """The panel's diagonal. One decimal if the sizes are to the
        millimetre; rounded to the inch if there are only centimetres."""
        if not (self.width_mm and self.height_mm) or self.size_is_ratio:
            return None
        diagonal = (self.width_mm ** 2 + self.height_mm ** 2) ** 0.5 / 25.4
        return round(diagonal, 1) if self.size_exact else float(round(diagonal))

    @property
    def refresh_range(self) -> Optional[str]:
        if not self.refresh_max_hz:
            return None
        if self.refresh_min_hz and self.refresh_min_hz != self.refresh_max_hz:
            return f"{self.refresh_min_hz}–{self.refresh_max_hz} Hz"
        return f"{self.refresh_max_hz} Hz"

    @property
    def refresh_summary(self) -> Optional[str]:
        """The refresh shown, wherever it comes from.

        The 0xFD descriptor's range is the right one and rules: a 240 Hz OLED
        declares 60 as its preferred mode, so showing the preferred mode as
        the ceiling falls far short.

        But that descriptor is optional and laptop panels almost never carry
        it. With no range, the native mode is all there is, and saying it
        beats silence, with the caveat, which the label next to it makes,
        that it is the preferred and not necessarily the maximum.
        """
        if self.refresh_range:
            return self.refresh_range
        if self.native_refresh_hz:
            return f"{self.native_refresh_hz:g} Hz"
        return None

    @property
    def refresh_is_native_only(self) -> bool:
        """Whether what's shown is the preferred mode rather than a declared range."""
        return not self.refresh_range and bool(self.native_refresh_hz)


def parse(raw: bytes) -> Optional[Edid]:
    """None if this isn't an EDID; never crashes on garbage."""
    if len(raw) < BLOCK or not raw.startswith(HEADER):
        return None
    # The block must add up to zero modulo 256. An EDID that doesn't is
    # usually a bad cable or an adapter making one up, and its data is no good.
    if sum(raw[:BLOCK]) % 256 != 0:
        return None

    packed = int.from_bytes(raw[8:10], "big")
    letters = "".join(chr(((packed >> shift) & 0x1F) + 0x40)
                     for shift in (10, 5, 0))
    if not letters.isalpha():
        return None

    model_name, serial_text = _from_descriptors(raw)
    width_mm, height_mm, exact = _panel_size(raw)
    width, height, refresh = _preferred_mode(raw)
    refresh_min, refresh_max = _refresh_range(raw)
    serial_number = int.from_bytes(raw[12:16], "little")

    return Edid(
        manufacturer_id=letters,
        model=model_name,
        product_code=int.from_bytes(raw[10:12], "little"),
        # The text one is what the sticker on the back shows; the number is the
        # fallback, and 0 or 0x01010101 mean «no number».
        serial=serial_text or (str(serial_number)
                               if serial_number not in (0, 0x01010101) else None),
        year=raw[17] + 1990 if raw[17] else None,
        week=raw[16] if 1 <= raw[16] <= 53 else None,
        version=f"{raw[18]}.{raw[19]}",
        width_mm=width_mm,
        height_mm=height_mm,
        size_exact=exact,
        size_is_ratio=(width_mm, height_mm) in RATIO_SIZES_MM,
        native_width=width,
        native_height=height,
        native_refresh_hz=refresh,
        refresh_min_hz=refresh_min,
        refresh_max_hz=refresh_max,
        **_extensions(raw),
    )


def read(connector: pathlib.Path | str) -> Optional[Edid]:
    """Read and decode the EDID of a `/sys/class/drm` connector."""
    try:
        raw = pathlib.Path(connector, "edid").read_bytes()
    except OSError:
        return None
    return parse(raw) if raw else None


def resolve_vendors(edids: Iterable[Edid]) -> dict[str, str]:
    """Turn the three letters into names, in a single pass over `pnp.ids`."""
    wanted = {e.manufacturer_id for e in edids if e.manufacturer_id}
    if not wanted:
        return {}
    path = next((p for p in map(pathlib.Path, PNP_CANDIDATES) if p.is_file()), None)
    if path is None:
        return {}

    found: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                code, _tab, name = line.partition("\t")
                if code in wanted:
                    found[code] = name.strip()
                    if len(found) == len(wanted):
                        break
    except OSError:
        pass
    return found


# -- internals ----------------------------------------------------------------

def _descriptor_text(chunk: bytes) -> str:
    """Text descriptors are padded with 0x0A and spaces."""
    text_bytes = chunk[5:18].split(b"\x0a")[0]
    return re.sub(r"\s+", " ", text_bytes.decode("cp437", "replace")).strip()


def _from_descriptors(raw: bytes) -> tuple[Optional[str], Optional[str]]:
    name = serial = None
    for start in DESCRIPTORS:
        chunk = raw[start:start + 18]
        if len(chunk) < 18 or chunk[0:2] != b"\x00\x00":
            continue                      # a timing, not text
        kind = chunk[3]
        if kind == TYPE_NAME:
            name = _descriptor_text(chunk) or name
        elif kind == TYPE_SERIAL:
            serial = _descriptor_text(chunk) or serial
    return name, serial


def _refresh_range(raw: bytes) -> tuple[Optional[int], Optional[int]]:
    """The 0xFD descriptor says which refresh rates the display can run at.

    The values haven't fit in a byte since monitors went past 255 Hz, so the
    standard added carry bits in the byte before, to add before reading them.
    """
    for start in DESCRIPTORS:
        chunk = raw[start:start + 18]
        if len(chunk) < 18 or chunk[0:2] != b"\x00\x00" or chunk[3] != TYPE_RANGES:
            continue
        carry = chunk[4]
        low = chunk[5] + (255 if carry & 0x01 else 0)
        high = chunk[6] + (255 if carry & 0x02 else 0)
        if high:
            return low or None, high
    return None, None


# The sizes, in millimetres, that are an aspect ratio and not a panel: 16:9
# and 16:10 in centimetres, as written or tenfold. A real 72" panel measures
# 1594 × 897 mm.
RATIO_SIZES_MM = frozenset({(160, 90), (1600, 900), (160, 100), (1600, 1000)})


def _panel_size(raw: bytes) -> tuple[Optional[int], Optional[int], bool]:
    """The image's width and height in millimetres, and whether exact.

    The base block gives them in centimetres (bytes 21 and 22). The first
    detailed timing, the native mode's, repeats them in millimetres. Those
    are taken when they match the centimetres: some displays put the aspect
    ratio there («16 × 9») or a zero, and a projector has no size.
    """
    width_cm, height_cm = raw[21], raw[22]
    chunk = raw[54:72]
    if int.from_bytes(chunk[0:2], "little"):            # a timing
        width = chunk[12] | ((chunk[14] >> 4) << 8)
        height = chunk[13] | ((chunk[14] & 0x0F) << 8)
        matches = (abs(width - width_cm * 10) <= 10 and abs(height - height_cm * 10) <= 10
                  if width_cm and height_cm else False)
        if width and height and matches:
            return width, height, True
    return width_cm * 10 or None, height_cm * 10 or None, False


def _preferred_mode(raw: bytes) -> tuple[Optional[int], Optional[int], Optional[float]]:
    """The first detailed timing is the display's native mode."""
    chunk = raw[54:72]
    pixel_clock = int.from_bytes(chunk[0:2], "little") * 10_000      # in hertz
    if not pixel_clock:
        return None, None, None

    width = chunk[2] | ((chunk[4] & 0xF0) << 4)
    width_blank = chunk[3] | ((chunk[4] & 0x0F) << 8)
    height = chunk[5] | ((chunk[7] & 0xF0) << 4)
    height_blank = chunk[6] | ((chunk[7] & 0x0F) << 8)
    if not (width and height):
        return None, None, None

    total = (width + width_blank) * (height + height_blank)
    refresh = round(pixel_clock / total, 1) if total else None
    return width, height, refresh


# --------------------------------------------------------------------------
# CTA-861 extensions
# --------------------------------------------------------------------------

CTA_TAG = 0x02
# The codes of CTA-861's table 3: (width, height, refresh, interlaced). The
# common ones, not all 219; a code not here is skipped rather than given a
# made-up resolution.
VIC = {
    1: (640, 480, 59.94, False),
    2: (720, 480, 59.94, False), 3: (720, 480, 59.94, False),
    4: (1280, 720, 60.0, False),
    5: (1920, 1080, 60.0, True),
    6: (720, 480, 59.94, True), 7: (720, 480, 59.94, True),
    16: (1920, 1080, 60.0, False),
    17: (720, 576, 50.0, False), 18: (720, 576, 50.0, False),
    19: (1280, 720, 50.0, False),
    20: (1920, 1080, 50.0, True),
    31: (1920, 1080, 50.0, False),
    32: (1920, 1080, 24.0, False), 33: (1920, 1080, 25.0, False),
    34: (1920, 1080, 30.0, False),
    60: (1280, 720, 24.0, False), 61: (1280, 720, 25.0, False),
    62: (1280, 720, 30.0, False),
    63: (1920, 1080, 120.0, False), 64: (1920, 1080, 100.0, False),
    65: (1280, 720, 24.0, False), 68: (1280, 720, 50.0, False),
    69: (1280, 720, 60.0, False), 70: (1280, 720, 100.0, False),
    71: (1280, 720, 120.0, False),
    72: (1920, 1080, 24.0, False), 75: (1920, 1080, 50.0, False),
    76: (1920, 1080, 60.0, False), 77: (1920, 1080, 100.0, False),
    78: (1920, 1080, 120.0, False),
    93: (3840, 2160, 24.0, False), 94: (3840, 2160, 25.0, False),
    95: (3840, 2160, 30.0, False), 96: (3840, 2160, 50.0, False),
    97: (3840, 2160, 60.0, False),
    98: (4096, 2160, 24.0, False), 99: (4096, 2160, 25.0, False),
    100: (4096, 2160, 30.0, False), 101: (4096, 2160, 50.0, False),
    102: (4096, 2160, 60.0, False),
    103: (3840, 2160, 24.0, False), 104: (3840, 2160, 25.0, False),
    105: (3840, 2160, 30.0, False), 106: (3840, 2160, 50.0, False),
    107: (3840, 2160, 60.0, False),
    108: (3840, 2160, 100.0, False), 109: (3840, 2160, 120.0, False),
    114: (3840, 2160, 60.0, False),
    117: (3840, 2160, 100.0, False), 118: (3840, 2160, 120.0, False),
    120: (5120, 2160, 60.0, False),
    124: (7680, 4320, 24.0, False), 125: (7680, 4320, 25.0, False),
    126: (7680, 4320, 30.0, False),
    193: (5120, 2160, 100.0, False), 194: (5120, 2160, 120.0, False),
    218: (5120, 2880, 60.0, False), 219: (5120, 2880, 120.0, False),
}

# The block types in the data collection.
BLOCK_AUDIO, BLOCK_VIDEO, BLOCK_VENDOR = 1, 2, 3
BLOCK_SPEAKERS, BLOCK_EXTENDED = 4, 7

# And the extended blocks' subtypes, where the modern things live.
EXT_COLORIMETRY, EXT_HDR = 5, 6

AUDIO_FORMATS = {
    1: "LPCM", 2: "AC-3", 3: "MPEG-1", 4: "MP3", 5: "MPEG-2", 6: "AAC",
    7: "DTS", 8: "ATRAC", 9: "DSD", 10: "E-AC-3", 11: "DTS-HD",
    12: "Dolby TrueHD", 13: "DST", 14: "WMA Pro",
}

# The transfer curves of the static HDR block. The first is the usual one,
# so only the others are shown: a monitor supporting traditional gamma isn't
# news.
HDR_CURVES = {1: "HDR gamma", 2: "HDR10 (PQ)", 3: "HLG"}

COLOR_SPACES = {
    0: "xvYCC601", 1: "xvYCC709", 2: "sYCC601", 3: "opYCC601",
    4: "opRGB", 5: "BT.2020 cYCC", 6: "BT.2020 YCC", 7: "BT.2020 RGB",
}


def _cta_modes(data: bytes) -> list[VideoMode]:
    """The video block's modes: one byte per code, bit 7 marks native."""
    modes = []
    for byte in data:
        code, native = byte & 0x7F, bool(byte & 0x80)
        if (dims := VIC.get(code)) is None:
            continue
        width, height, hz, interlaced = dims
        modes.append(VideoMode(width, height, hz, interlaced, native))
    return modes


def _cta_extension(block: bytes) -> dict:
    """What a CTA-861 extension says: modes, HDR, colour and audio.

    The data block collection runs from byte 4 to where byte 2 says, and each
    block carries its type and length in its header. It is walked carefully
    so as not to overrun: a badly written EDID is among the easiest things to
    come across, and here it can't bring down any other reading.
    """
    found: dict = {"modes": [], "hdr": [], "color_spaces": [], "audio": []}
    if len(block) < 4 or block[0] != CTA_TAG:
        return found

    end = block[2]
    if not 4 <= end <= len(block):
        return found

    i = 4
    while i < end:
        header = block[i]
        tag, length = header >> 5, header & 0x1F
        data = block[i + 1:i + 1 + length]
        if len(data) < length:
            break

        if tag == BLOCK_VIDEO:
            found["modes"].extend(_cta_modes(data))
        elif tag == BLOCK_AUDIO:
            # Triplets of bytes: the first one's top five bits are the format.
            for j in range(0, len(data) - 2, 3):
                name = AUDIO_FORMATS.get((data[j] >> 3) & 0x0F)
                if name and name not in found["audio"]:
                    found["audio"].append(name)
        elif tag == BLOCK_EXTENDED and data:
            if data[0] == EXT_HDR and len(data) >= 2:
                found["hdr"] = [name for bit, name in HDR_CURVES.items()
                                 if data[1] & (1 << bit)]
            elif data[0] == EXT_COLORIMETRY and len(data) >= 2:
                found["color_spaces"] = [
                    name for bit, name in COLOR_SPACES.items()
                    if data[1] & (1 << bit)]
        i += length + 1
    return found


def _extensions(raw: bytes) -> dict:
    """Walk the blocks after the main one and gather what they bring."""
    merged: dict = {"modes": [], "hdr": [], "color_spaces": [], "audio": []}
    for start in range(BLOCK, len(raw) - BLOCK + 1, BLOCK):
        chunk = raw[start:start + BLOCK]
        if len(chunk) < BLOCK or chunk[0] != CTA_TAG:
            continue
        for key, values in _cta_extension(chunk).items():
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)
    # Tuples: the Snapshot is immutable top to bottom, and a list inside a
    # frozen dataclass is a promise not kept.
    return {key: tuple(values) for key, values in merged.items()}
