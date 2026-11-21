"""What Silux reads that does not exist in every kernel it supports.

The minimum is Linux 5.15. Some values appeared later, and when missing on
an older kernel the machine does not lack them: its kernel does not publish
them yet. That is said differently from «this machine does not have it»
(«Your kernel (5.15) does not publish this; it exists since Linux 6.10»), as
it has a fix, and the fix is not other hardware.

Each value's version, with its source (the kernel commit or documentation),
is in `docs/kernel.md`; `tests/test_kernel.py` checks both tables agree.
"""

from __future__ import annotations

import platform
import re
from typing import Optional

from . import sysroot
from .i18n import _

MINIMUM = (5, 15)

# Value → the first mainline version that publishes it. Only what is newer
# than the minimum; the rest is in every kernel Silux supports.
SINCE = {
    "cpufreq.cpuinfo_avg_freq": (6, 15),
    "amd_pstate": (5, 17),
    "amd_pstate.epp": (6, 3),
    "amd_pstate.prefcore_ranking": (6, 9),
    "amdgpu.power1_input": (6, 6),
    "amdgpu.vcn_busy_percent": (6, 10),
    "i915.gt": (5, 19),
    "i915.throttle_reason": (5, 19),
    "spd5118": (6, 11),
    "xe": (6, 8),
}


def version(text: Optional[str]) -> Optional[tuple[int, int]]:
    """(6, 10) from «6.10.3-arch1-1» or «Linux 6.10.3-arch1-1»."""
    match = re.search(r"(\d+)\.(\d+)", text or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def running() -> Optional[tuple[int, int]]:
    """The running kernel's; on a dumped machine, the one it had when dumped."""
    uname = sysroot.recorded("plataforma", "uname", lambda: platform.uname()._asdict())
    return version((uname or {}).get("release"))


def too_old(key: str, current: Optional[tuple[int, int]] = None,
            feature: str = "") -> Optional[str]:
    """The sentence that explains the absence if the kernel predates the value.

    None if the kernel already publishes it, or if it is unknown: then the
    absence is the machine's and is explained as always. With `feature`, the
    sentence names it, for a foot note that says several things at once.
    """
    since = SINCE[key]
    current = current or running()
    if current is None or current >= since:
        return None
    running_now, since = f"{current[0]}.{current[1]}", f"{since[0]}.{since[1]}"
    if feature:
        return _("kernel.tooold.what").format(dato=feature, tuyo=running_now, desde=since)
    return _("kernel.tooold").format(tuyo=running_now, desde=since)
