"""Rates from two readings of a counter, and when two readings give none.

A rate is what a counter went up between two readings over the time between
them, and that time can be wrong in ways the difference does not show. A
power chart got 1336648637.3 W from an Iris Xe drawing 9 W: 9 J over a window
of nanoseconds gives exactly that. So every such calculation goes through
here, with the same rules:

- a window that is not positive, or shorter than half the sampling interval,
  gives nothing;
- a counter that went back (reset, re-opened, a device that came back) gives
  nothing, unless it is one that wraps at a known value;
- either way, the new reading is the base for the next one, which is what
  every caller does by keeping the last reading whatever came of it.

The impossible-value check (`rapl.Discarded`) stays behind this, as a safety
net for what a valid window still cannot explain.
"""

from __future__ import annotations

from typing import Optional

# A window shorter than this share of the sampling interval gives no rate.
MIN_WINDOW_SHARE = 0.5


def window_s(before_s: float, after_s: float, interval_s: float) -> Optional[float]:
    """The seconds between two readings, or None if they do not make a window."""
    seconds = after_s - before_s
    if seconds <= 0 or seconds < interval_s * MIN_WINDOW_SHARE:
        return None
    return seconds


def increase(before: float, after: float, wrap: Optional[float] = None) -> Optional[float]:
    """How much a counter that only goes up went up, or None if it went back.

    `wrap` is the value at which the counter starts again from zero (RAPL's
    `max_energy_range_uj`): going back is then going round, once.
    """
    grown = after - before
    if grown >= 0:
        return grown
    if wrap and grown + wrap >= 0:
        return grown + wrap
    return None


def rate(before: float, before_s: float, after: float, after_s: float,
         interval_s: float, wrap: Optional[float] = None) -> Optional[float]:
    """Per second between two readings, or None when they cannot say."""
    seconds = window_s(before_s, after_s, interval_s)
    if seconds is None:
        return None
    grown = increase(before, after, wrap)
    return None if grown is None else grown / seconds
