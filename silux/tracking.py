"""Minimum, maximum and mean per sensor.

What defines a hardware monitor: anyone gives the current value, but knowing
how hot it got while you played (or whether a fan stopped for an instant)
takes remembering. Kept apart from the model on purpose: the snapshot is a
photo, and this is the film.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional

# How many samples each sensor's curve keeps. Sixty at one second is the last
# minute, where one sees whether something is rising. A hundred sensors by
# sixty samples is about 200 KB: within budget, and much more adds no
# reading, it only flattens the curve.
HISTORY_LENGTH = 60


@dataclass
class Extremes:
    minimum: float
    maximum: float
    total: float = 0.0
    samples: int = 0
    last: float = 0.0
    # The recent series. The extremes say where the sensor was; this says
    # where it goes, which is what one looks at when something heats up.
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))

    @property
    def average(self) -> float:
        return self.total / self.samples if self.samples else self.last


@dataclass
class Tracker:
    """Follows a collection of values identified by key."""

    _values: dict[str, Extremes] = field(default_factory=dict)

    def update(self, key: str, value: Optional[float]) -> None:
        if value is None:
            return
        entry = self._values.get(key)
        if entry is None:
            entry = Extremes(minimum=value, maximum=value,
                             total=value, samples=1, last=value)
            entry.history.append(value)
            self._values[key] = entry
            return
        entry.minimum = min(entry.minimum, value)
        entry.maximum = max(entry.maximum, value)
        entry.total += value
        entry.samples += 1
        entry.last = value
        entry.history.append(value)

    def update_many(self, items: Iterable[tuple[str, Optional[float]]]) -> None:
        for key, value in items:
            self.update(key, value)

    def get(self, key: str) -> Optional[Extremes]:
        return self._values.get(key)

    def reset(self, key: Optional[str] = None) -> None:
        """Reset one sensor, or all. The reset-minimum-and-maximum button any
        hardware monitor has."""
        if key is None:
            self._values.clear()
        else:
            self._values.pop(key, None)

    def __len__(self) -> int:
        return len(self._values)
