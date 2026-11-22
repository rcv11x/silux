"""USB device names from the usb.ids database.

As with pci.ids, distributions ship the file (hwdata, usb.ids), so it is read
from the system rather than bundled, and scanned once for the ids asked.

The format:

    0bda  Realtek Semiconductor Corp.
    <tab>818b  RTL8192EU 802.11b/g/n WLAN Adapter

After the vendors come other lists («C 00  (Defined at Interface level)»),
which a vendor line's four hex digits never match.
"""

from __future__ import annotations

import pathlib
import re
from typing import Optional

CANDIDATE_PATHS = (
    "/usr/share/hwdata/usb.ids",
    "/usr/share/misc/usb.ids",
    "/usr/share/usb.ids",
    "/var/lib/usbutils/usb.ids",
)

_VENDOR = re.compile(r"^([0-9a-f]{4})\s+(.+)$")
_PRODUCT = re.compile(r"^\t([0-9a-f]{4})\s+(.+)$")


def database_path() -> Optional[pathlib.Path]:
    for candidate in CANDIDATE_PATHS:
        path = pathlib.Path(candidate)
        if path.is_file():
            return path
    return None


# Answers by id and by file version (path, mtime, size): the network page
# asks for its card's name every sample.
_answered: dict[tuple, Optional[tuple[str, str]]] = {}


def lookup(vendor: int, product: int) -> Optional[tuple[str, str]]:
    """(vendor name, product name), or None if the database lacks either."""
    path = database_path()
    if path is None:
        return None
    try:
        state = path.stat()
    except OSError:
        return None
    key = (str(path), state.st_mtime_ns, state.st_size, vendor, product)
    if key not in _answered:
        _answered[key] = _walk(path, vendor, product)
    return _answered[key]


def _walk(path: pathlib.Path, vendor: int, product: int) -> Optional[tuple[str, str]]:
    vendor_name = None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if vendor_name is None:
                    match = _VENDOR.match(line)
                    if match and int(match.group(1), 16) == vendor:
                        vendor_name = match.group(2).strip()
                    continue
                if match := _PRODUCT.match(line):
                    if int(match.group(1), 16) == product:
                        return vendor_name, match.group(2).strip()
                elif not line.startswith(("\t", "#")) and line:
                    return None            # the vendor's section is over
    except OSError:
        return None
    return None
