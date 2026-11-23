"""How hot a temperature is, by the limits the hardware itself declares.

Three levels: normal; «alto» (amber) from its `max`; «crítico» (red) from
its `crit`. Where the part declares no limit there's no colour: a limit
made up here would paint a machine's normal work as a warning, and a false
warning costs every true one its trust. Where `max` and `crit` are the same
figure, it goes straight to red there, as the part says.

Every place that colours a temperature (Sensors, Home, the CPU page, the
disks) asks here: the same reading has the same colour everywhere.
"""

from __future__ import annotations

from typing import Optional

OK = "ok"
HIGH = "alto"
CRITICAL = "crítico"

# No part's limit is outside this: what is, is a field nobody filled. 0 K
# (−273.15 °C), 0xFFFF K (65261.85 °C) and 0 are what chips leave there.
CEILING_C = 200.0


def limit(celsius: Optional[float]) -> Optional[float]:
    """A declared limit, or None if it's one nobody filled."""
    if celsius is None or not 0 < celsius <= CEILING_C:
        return None
    return celsius


def limits(high: Optional[float], critical: Optional[float]
           ) -> tuple[Optional[float], Optional[float]]:
    """The pair, each checked; a warning above the critical one warns of
    nothing and goes."""
    high, critical = limit(high), limit(critical)
    if high is not None and critical is not None and high > critical:
        high = None
    return high, critical


def level(celsius: Optional[float], high: Optional[float],
          critical: Optional[float]) -> str:
    """OK, HIGH from `high` on, CRITICAL from `critical` on."""
    high, critical = limits(high, critical)
    if celsius is None:
        return OK
    if critical is not None and celsius >= critical:
        return CRITICAL
    if high is not None and celsius >= high:
        return HIGH
    return OK
