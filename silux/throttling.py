"""How long something has been throttling, and why.

The current throttle reasons already show as a row («throttling for hotspot
temperature»), but that only says what is happening now, not whether it has
been going on for an instant or forty seconds. A card touching its power
limit for half a second at a scene change works as designed; one held at its
thermal limit for a minute has a cooling problem.

Kept out of the model, like `tracking.py`. An episode that just ended stays
visible for a while, for whoever looks right after the peak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# Long enough to look away from a game and back at Silux.
MEMORY_S = 30.0

# Shorter throttles are how any modern card works; warning about them would
# turn the warning into noise.
MIN_S = 1.5


@dataclass
class Episode:
    """A continuous stretch of throttling."""

    since_ns: int
    until_ns: Optional[int] = None          # None while it lasts
    # Every reason seen during the episode: a card that starts on power and
    # ends on temperature hit both limits.
    reasons: set[str] = field(default_factory=set)

    def ongoing(self) -> bool:
        return self.until_ns is None

    def duration_s(self, now_ns: int) -> float:
        end = self.until_ns if self.until_ns is not None else now_ns
        return max(0.0, (end - self.since_ns) / 1e9)


@dataclass
class ThrottleTracker:
    """Tracks throttling episodes for several devices.

    The caller picks the key; in practice each GPU's PCI slot, the one thing
    that never changes between samples.
    """

    _open: dict[str, Episode] = field(default_factory=dict)
    _last: dict[str, Episode] = field(default_factory=dict)

    def update(self, key: str, active: Optional[bool],
               reasons: Iterable[str], now_ns: int) -> None:
        """One sample. `active=None` means unknown and opens or closes nothing."""
        if active is None:
            return

        episode = self._open.get(key)
        if active:
            if episode is None:
                episode = Episode(since_ns=now_ns)
                self._open[key] = episode
            episode.reasons.update(m for m in reasons if m)
        elif episode is not None:
            episode.until_ns = now_ns
            self._last[key] = episode
            del self._open[key]

    def current(self, key: str) -> Optional[Episode]:
        """The ongoing episode, once it has lasted long enough to count."""
        return self._open.get(key)

    def recent(self, key: str, now_ns: int) -> Optional[Episode]:
        """The last finished episode, while it is still recent."""
        episode = self._last.get(key)
        if episode is None or episode.until_ns is None:
            return None
        if (now_ns - episode.until_ns) / 1e9 > MEMORY_S:
            return None
        return episode

    def relevant(self, key: str, now_ns: int) -> Optional[Episode]:
        """The episode to show: the ongoing one, or the one that just ended.

        Either must have lasted long enough; a blip doesn't count.
        """
        for episode in (self.current(key), self.recent(key, now_ns)):
            if episode is not None and episode.duration_s(now_ns) >= MIN_S:
                return episode
        return None

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self._open.clear()
            self._last.clear()
        else:
            self._open.pop(key, None)
            self._last.pop(key, None)
