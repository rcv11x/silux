"""Snapshots an interval apart, as the sampler takes them.

A rate needs a window of at least half the sampling interval
(`silux/providers/counters.py`). Two snapshots taken one after the other in
a test are milliseconds apart, which the sampler never does: here the clock
stands still and moves the collector's interval between them, and only then.
`time.monotonic` is patched where it is looked up; the standard library's own
waits (threading, subprocess) took their copy at import and keep real time.
"""

import contextlib
from unittest import mock


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@contextlib.contextmanager
def fake_clock(start: float = 1000.0):
    clock = FakeClock(start)
    with mock.patch("time.monotonic", clock):
        yield clock


def next_snapshot(collector, clock: FakeClock):
    """The collector's next snapshot, one interval after the last."""
    clock.advance(collector.interval_s)
    return collector.snapshot()


def second_snapshot(collector):
    """The first snapshot with its rates: the second one, an interval later."""
    with fake_clock() as clock:
        collector.snapshot()
        return next_snapshot(collector, clock)
