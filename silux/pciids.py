"""PCI device names from the pci.ids database.

Distributions ship the file (from the hwdata project), so it is read from
the system rather than bundled. It is 1.7 MB and only a handful of ids
matter, so it is scanned once for all of them instead of loaded whole.

The format:

    8086  Intel Corporation
    <tab>9b53  Comet Lake-S 6c Host Bridge/DRAM Controller
    <tab><tab>1462 7d23  Subsystem
"""

from __future__ import annotations

import functools
import pathlib
from typing import Iterable, Optional

from . import sysroot

CANDIDATE_PATHS = (
    "/usr/share/hwdata/pci.ids",
    "/usr/share/misc/pci.ids",
    "/usr/share/pci.ids",
    "/var/lib/pciutils/pci.ids",
)


def database_path() -> Optional[pathlib.Path]:
    for candidate in CANDIDATE_PATHS:
        path = pathlib.Path(candidate)
        if path.is_file():
            return path
    return None


def _key(numbers) -> str:
    return ":".join(f"{n:04x}" for n in numbers)


# Devices pci.ids doesn't list. QEMU's standard VGA uses the unregistered
# vendor 0x1234.
NOT_IN_PCI_IDS = {(0x1234, 0x1111): ("QEMU", "QEMU Standard VGA")}


def lookup(
    pairs: Iterable[tuple[int, int]],
    subsystems: Iterable[tuple[int, int, int, int]] = (),
) -> dict[tuple[int, int], tuple[str, str]]:
    """`_lookup`, or what a mounted dump recorded.

    pci.ids belongs to the running system, not the dumped one, and it differs
    between distributions: the same card can be «Radeon RX 9070 XT 16GB» with
    one and «AMD Radeon RX 9070 XT» with an older file.
    """
    pair_list = sorted({(int(v), int(d)) for v, d in pairs})
    subs = sorted({tuple(int(n) for n in key) for key in subsystems})
    if sysroot.active() and not sysroot.did_record("pciids"):
        names = _lookup(pair_list, subs)           # a dump older than this recording
    else:
        query = "|".join(_key(k) for k in (*pair_list, *subs))
        flat = sysroot.recorded(
            "pciids", query,
            lambda: {_key(k): list(v) for k, v in _lookup(pair_list, subs).items()})
        names = {tuple(int(n, 16) for n in lookup_key.split(":")): tuple(value_text)
                   for lookup_key, value_text in (flat or {}).items()}
    for pair in pair_list:
        if pair not in names and pair in NOT_IN_PCI_IDS:
            names[pair] = NOT_IN_PCI_IDS[pair]
    return names


# Answers by question and by file version (path, mtime, size). Scanning
# pci.ids takes milliseconds of Python, and the network page asks for its
# card's name every sample.
_answered: dict[tuple, dict] = {}


def _lookup(
    pairs: Iterable[tuple[int, int]],
    subsystems: Iterable[tuple[int, int, int, int]] = (),
) -> dict[tuple[int, int], tuple[str, str]]:
    """`_walk`, cached until the file changes."""
    pair_list = tuple(sorted({(int(v), int(d)) for v, d in pairs}))
    subs = tuple(sorted({tuple(int(n) for n in key) for key in subsystems}))
    path = database_path()
    if path is None:
        return {}
    try:
        state = path.stat()
    except OSError:
        return {}
    lookup_key = (str(path), state.st_mtime_ns, state.st_size, pair_list, subs)
    if lookup_key not in _answered:
        _answered[lookup_key] = _walk(path, pair_list, subs)
    return dict(_answered[lookup_key])


def _walk(
    path: pathlib.Path,
    pairs: Iterable[tuple[int, int]],
    subsystems: Iterable[tuple[int, int, int, int]] = (),
) -> dict[tuple[int, int], tuple[str, str]]:
    """{(vendor, device): (vendor name, model name)}.

    Ids not in the database are left out; the caller decides what to show.
    `subsystems` also resolves the nested third-level lines, which name the
    exact board («Radeon RX 9070/9070 XT/9070 GRE» becomes one model). They
    come back under the four-id key, from the same pass.
    """
    wanted = {(int(v), int(d)) for v, d in pairs}
    subs_wanted = {tuple(int(n) for n in key) for key in subsystems}
    # The board maker is a top-level vendor too: ask for its section as well.
    wanted |= {(key[0], key[1]) for key in subs_wanted}
    if not wanted and not subs_wanted:
        return {}

    vendors_wanted = {vendor for vendor, _ in wanted}
    vendors_wanted |= {key[2] for key in subs_wanted}
    found: dict = {}
    vendor_names: dict[int, str] = {}
    # Subsystems are collected as they appear and named at the end: the board
    # maker's section may come after the chip's.
    raw_subs: dict[tuple[int, int, int, int], str] = {}

    current_vendor: Optional[int] = None
    current_device: Optional[int] = None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("\t"):
                    # A vendor line. Sections we don't need are marked None so
                    # their models are skipped.
                    code, _, name = line.partition("  ")
                    try:
                        current_vendor = int(code, 16)
                    except ValueError:
                        current_vendor = None
                        continue
                    current_device = None
                    if current_vendor in vendors_wanted:
                        vendor_names[current_vendor] = name.strip()
                    else:
                        current_vendor = None
                elif current_vendor is not None and not line.startswith("\t\t"):
                    code, _, name = line.strip().partition("  ")
                    try:
                        device = int(code, 16)
                    except ValueError:
                        current_device = None
                        continue
                    current_device = device
                    key = (current_vendor, device)
                    if key in wanted:
                        found[key] = (vendor_names[current_vendor], name.strip())
                        # Can't stop early: the board maker's section may still
                        # be ahead.
                        if len(found) == len(wanted) and not subs_wanted:
                            return found
                elif current_device is not None and current_vendor is not None:
                    code, _, name = line.strip().partition("  ")
                    subvendor, _, subdevice = code.partition(" ")
                    try:
                        lookup_key = (current_vendor, current_device,
                                 int(subvendor, 16), int(subdevice, 16))
                    except ValueError:
                        continue
                    if lookup_key in subs_wanted:
                        raw_subs[lookup_key] = name.strip()
    except OSError:
        return found

    for lookup_key, entry_name in raw_subs.items():
        found[lookup_key] = (vendor_names.get(lookup_key[2], ""), entry_name)
    return found


def vendor_name(vendor: int) -> Optional[str]:
    """A vendor's name, or the one a mounted dump recorded."""
    if sysroot.active() and not sysroot.did_record("pciids"):
        return _vendor_name(int(vendor))
    return sysroot.recorded("pciids_fabricante", f"{int(vendor):04x}",
                            _vendor_name, int(vendor))


@functools.lru_cache(maxsize=64)
def _vendor_name(vendor: int) -> Optional[str]:
    """Only a vendor's name, for a card's «Built by».

    pci.ids only has the full subsystem line for combinations someone added,
    and recent boards usually aren't there. The vendor is: 0x1462 is MSI
    whether or not that card is listed.
    """
    path = database_path()
    if path is None:
        return None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line or line.startswith(("#", "\t")):
                    continue
                code, _, name = line.partition("  ")
                try:
                    if int(code, 16) == vendor:
                        return name.strip() or None
                except ValueError:
                    continue
    except OSError:
        return None
    return None
