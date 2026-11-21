"""Minimum, maximum and mean per sensor.

Anyone can show the current value; knowing how hot it got during a game, or
whether a fan stopped for a moment, takes memory. Kept out of the model: the
snapshot is a photo, this is the film.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Sixty samples at one second is the last minute, enough to see a trend. A
# hundred sensors by sixty samples is about 200 KB; more would only flatten
# the curve.
HISTORY_LENGTH = 60


@dataclass
class Extremes:
    minimum: float
    maximum: float
    total: float = 0.0
    samples: int = 0
    last: float = 0.0
    # The recent series: the extremes say where the sensor has been, this
    # says where it is heading.
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))

    @property
    def average(self) -> float:
        return self.total / self.samples if self.samples else self.last


@dataclass
class Tracker:
    """Tracks a set of values by key."""

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
        """Reset one sensor, or all of them: the usual reset min/max button."""
        if key is None:
            self._values.clear()
        else:
            self._values.pop(key, None)

    def __len__(self) -> int:
        return len(self._values)
