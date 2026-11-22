"""The mode each video output is running at, from the kernel's modesetting.

sysfs lists the modes a monitor offers, with its preferred one first; the one
in use is the CRTC's. Four ioctls on the card's primary node give it:
GETRESOURCES, GETCONNECTOR, GETENCODER and GETCRTC, which the kernel lets
any process that can open the node make (drm_ioctl.c declares them with no
flags), without being the display's master. The session's user can open it:
logind gives it the node by ACL.

Opening the node of a card that runtime PM has suspended wakes it, so the
caller only asks a card that is awake and has a screen plugged in.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
from typing import Optional

from . import sysroot

_U32, _U16, _U64 = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint64


class _CardResources(ctypes.Structure):
    _fields_ = [("fb_id_ptr", _U64), ("crtc_id_ptr", _U64), ("connector_id_ptr", _U64),
                ("encoder_id_ptr", _U64), ("count_fbs", _U32), ("count_crtcs", _U32),
                ("count_connectors", _U32), ("count_encoders", _U32), ("min_width", _U32),
                ("max_width", _U32), ("min_height", _U32), ("max_height", _U32)]


class _ModeInfo(ctypes.Structure):
    _fields_ = [("clock", _U32), ("hdisplay", _U16), ("hsync_start", _U16),
                ("hsync_end", _U16), ("htotal", _U16), ("hskew", _U16), ("vdisplay", _U16),
                ("vsync_start", _U16), ("vsync_end", _U16), ("vtotal", _U16), ("vscan", _U16),
                ("vrefresh", _U32), ("flags", _U32), ("type", _U32), ("name", ctypes.c_char * 32)]


class _Crtc(ctypes.Structure):
    _fields_ = [("set_connectors_ptr", _U64), ("count_connectors", _U32), ("crtc_id", _U32),
                ("fb_id", _U32), ("x", _U32), ("y", _U32), ("gamma_size", _U32),
                ("mode_valid", _U32), ("mode", _ModeInfo)]


class _Encoder(ctypes.Structure):
    _fields_ = [("encoder_id", _U32), ("encoder_type", _U32), ("crtc_id", _U32),
                ("possible_crtcs", _U32), ("possible_clones", _U32)]


class _Connector(ctypes.Structure):
    _fields_ = [("encoders_ptr", _U64), ("modes_ptr", _U64), ("props_ptr", _U64),
                ("prop_values_ptr", _U64), ("count_modes", _U32), ("count_props", _U32),
                ("count_encoders", _U32), ("encoder_id", _U32), ("connector_id", _U32),
                ("connector_type", _U32), ("connector_type_id", _U32), ("connection", _U32),
                ("mm_width", _U32), ("mm_height", _U32), ("subpixel", _U32), ("pad", _U32)]


def _iowr(number: int, structure) -> int:
    # _IOWR('d', number, structure): read and write, the size, DRM's type.
    return (3 << 30) | (ctypes.sizeof(structure) << 16) | (ord("d") << 8) | number


GETRESOURCES = _iowr(0xA0, _CardResources)
GETCRTC = _iowr(0xA1, _Crtc)
GETENCODER = _iowr(0xA6, _Encoder)
GETCONNECTOR = _iowr(0xA7, _Connector)

# The connector types as the kernel names them in sysfs («card1-HDMI-A-1»),
# from drm_connector_enum_list in drm_connector.c.
CONNECTOR_TYPES = ("Unknown", "VGA", "DVI-I", "DVI-D", "DVI-A", "Composite", "SVIDEO",
                   "LVDS", "Component", "DIN", "DP", "HDMI-A", "HDMI-B", "TV", "eDP",
                   "Virtual", "DSI", "DPI", "Writeback", "SPI", "USB")
_INTERLACED = 1 << 4             # DRM_MODE_FLAG_INTERLACE


def active_modes(card: str) -> Optional[dict]:
    """{connector: {"width", "height", "refresh_hz"}} for the outputs that
    are on, or None if the card can't be asked. As a dump recorded it."""
    return sysroot.recorded("drm_modes", card, _ask, card)


def _ask(card: str) -> Optional[dict]:
    try:
        descriptor = os.open(f"/dev/dri/{card}", os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        return _modes(descriptor)
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _modes(descriptor: int) -> dict:
    resources = _CardResources()
    fcntl.ioctl(descriptor, GETRESOURCES, resources)
    count = resources.count_connectors
    if not count:
        return {}
    ids = (_U32 * count)()
    asked = _CardResources(connector_id_ptr=ctypes.addressof(ids), count_connectors=count)
    fcntl.ioctl(descriptor, GETRESOURCES, asked)

    found = {}
    for connector_id in ids[:min(count, asked.count_connectors)]:
        # No modes, properties or encoders asked: no probe of the monitor.
        connector = _Connector(connector_id=connector_id)
        fcntl.ioctl(descriptor, GETCONNECTOR, connector)
        if not connector.encoder_id or connector.connector_type >= len(CONNECTOR_TYPES):
            continue
        encoder = _Encoder(encoder_id=connector.encoder_id)
        fcntl.ioctl(descriptor, GETENCODER, encoder)
        if not encoder.crtc_id:
            continue
        crtc = _Crtc(crtc_id=encoder.crtc_id)
        fcntl.ioctl(descriptor, GETCRTC, crtc)
        if not crtc.mode_valid:
            continue
        name = f"{CONNECTOR_TYPES[connector.connector_type]}-{connector.connector_type_id}"
        found[name] = {"width": crtc.mode.hdisplay, "height": crtc.mode.vdisplay,
                       "refresh_hz": _refresh(crtc.mode)}
    return found


def _refresh(mode: _ModeInfo) -> Optional[float]:
    """The refresh to the hundredth, from the pixel clock: `vrefresh` is a
    whole number, and 59.94 Hz is not 60."""
    if not (mode.clock and mode.htotal and mode.vtotal):
        return float(mode.vrefresh) or None
    hertz = mode.clock * 1000 / (mode.htotal * mode.vtotal)
    if mode.flags & _INTERLACED:
        hertz *= 2
    if mode.vscan > 1:
        hertz /= mode.vscan
    return round(hertz, 2)
