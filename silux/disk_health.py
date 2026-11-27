"""A drive's health at a glance: fine, watch, or back it up now.

Every level comes from what the NVMe specification or the drive itself
declares, never from a threshold of ours: the Critical Warning bits, the
wear the drive counts, the data it couldn't give back, the sectors it
replaced. With nothing read there is nothing to judge, and that is said:
«no data», or «with permissions» when that is what it waits for.

SATA goes as far as «watch»: «back it up now» would need each attribute's
own threshold, which is another ATA command the helper doesn't send.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .model import DiskHealth

FINE, WATCH, BACKUP, NO_DATA, LOCKED = "fine", "watch", "backup", "no_data", "locked"

# The Critical Warning bits (NVM Express Base, SMART / Health Information,
# byte 0): those that say the drive is on its way to losing data, and those
# to keep an eye on.
NVME_BACKUP_BITS = {0: "nvme.spare", 2: "nvme.reliability", 3: "nvme.readonly"}
NVME_WATCH_BITS = {1: "nvme.temperature", 4: "nvme.backup_device", 5: "nvme.pmr"}

# Below this share of its life left, a drive is worth watching. It is the
# one figure of ours, and it only ever says «watch».
LOW_LIFE_PCT = 10

# SATA's UDMA CRC error count: errors on the way between the drive and the
# board, which is the cable or its connector, not the drive.
SATA_CRC_ATTRIBUTE = 199


@dataclass(frozen=True)
class Reason:
    """Why: a code, and the count or figures it goes with."""

    code: str
    count: int = 0
    figures: tuple[int, ...] = ()


@dataclass(frozen=True)
class Verdict:
    level: str
    reasons: tuple[Reason, ...] = ()


def backup_reason(reason: Reason) -> bool:
    """Whether `reason` alone means «back it up now»."""
    return reason.code in NVME_BACKUP_BITS.values() or reason.code == "worn_out"


def _read(health: DiskHealth) -> bool:
    return (health.power_on_hours is not None or health.critical_warning is not None
            or bool(health.attributes))


def verdict(health: Optional[DiskHealth], locked: bool = False) -> Verdict:
    """The level of `health` and its reasons, most serious first. `locked`:
    nothing was read for lack of permissions."""
    if health is None or not _read(health):
        return Verdict(LOCKED if locked else NO_DATA)
    reasons: list[Reason] = []
    warning = health.critical_warning or 0
    for bit in range(8):
        if not warning & (1 << bit):
            continue
        if bit in NVME_BACKUP_BITS:
            reasons.append(Reason(NVME_BACKUP_BITS[bit]))
        elif bit in NVME_WATCH_BITS:
            reasons.append(Reason(NVME_WATCH_BITS[bit]))
        else:
            # A bit the specification doesn't define yet: said, as watch.
            reasons.append(Reason("nvme.unknown", warning))
    if health.percentage_used is not None and health.percentage_used >= 100:
        # The specification: its estimated life is used up.
        reasons.append(Reason("worn_out"))
    elif health.life_left_percent is not None and health.life_left_percent <= LOW_LIFE_PCT:
        reasons.append(Reason("life_low", health.life_left_percent))
    if health.media_errors:
        reasons.append(Reason("media_errors", health.media_errors))
    sectors = (health.reallocated_sectors or 0, health.pending_sectors or 0,
               health.uncorrectable_sectors or 0)
    if any(sectors):
        reasons.append(Reason("sectors", figures=sectors))
    crc = next((raw for number, _normalized, raw in health.attributes
                if number == SATA_CRC_ATTRIBUTE), 0)
    if crc:
        reasons.append(Reason("cable", crc))
    reasons.sort(key=lambda r: not backup_reason(r))
    level = (BACKUP if any(backup_reason(r) for r in reasons)
             else WATCH if reasons else FINE)
    return Verdict(level, tuple(reasons))
