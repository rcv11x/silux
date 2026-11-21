"""Rates from two readings of a counter, and when two readings give none.

A rate is how much a counter rose divided by the time between the readings,
and that time can be wrong in ways the difference doesn't show: 9 J over a
window of nanoseconds is a billion watts. Every such calculation goes
through here, with the same rules:

- a window that isn't positive, or is shorter than half the sampling
  interval, gives nothing;
- a counter that went backwards (reset, reopened, a device that came back)
  gives nothing, unless it wraps at a known value;
- either way, the new reading becomes the baseline for the next, as every
  caller keeps its last reading whatever came of it.

The impossible-value check (`rapl.Discarded`) stays behind this as a safety
net for what a valid window still can't explain.
"""

from __future__ import annotations

from typing import Optional

# A window shorter than this share of the sampling interval gives no rate.
MIN_WINDOW_SHARE = 0.5


def window_s(before_s: float, after_s: float, interval_s: float) -> Optional[float]:
    """Seconds between two readings, or None if they don't make a window."""
    seconds = after_s - before_s
    if seconds <= 0 or seconds < interval_s * MIN_WINDOW_SHARE:
        return None
    return seconds


def increase(before: float, after: float, wrap: Optional[float] = None) -> Optional[float]:
    """How much a monotonic counter rose, or None if it went backwards.

    `wrap` is where the counter rolls over to zero (RAPL's
    `max_energy_range_uj`); going backwards is then one wraparound.
    """
    grown = after - before
    if grown >= 0:
        return grown
    if wrap and grown + wrap >= 0:
        return grown + wrap
    return None


def rate(before: float, before_s: float, after: float, after_s: float,
         interval_s: float, wrap: Optional[float] = None) -> Optional[float]:
    """The per-second rate between two readings, or None if they can't say."""
    seconds = window_s(before_s, after_s, interval_s)
    if seconds is None:
        return None
    grown = increase(before, after, wrap)
    return None if grown is None else grown / seconds
