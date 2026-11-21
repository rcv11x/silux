"""Since when something has been throttling, and why.

Throttle reasons are already read (`indep_throttle_status` on AMD, NVML on
NVIDIA) and showed as one more row: «throttling for hotspot temperature».
That says what happens now, not what one wants to know: whether it has been
so for an instant or forty seconds.

It matters. A card touching its power limit half a second at each scene
change works as designed; one a whole minute against its thermal limit has a
cooling problem. Same value, opposite conclusion.

Kept apart from the model, as `tracking.py`: the snapshot is a photo and
this is the film. What just ended is remembered a while, since whoever looks
right after the peak wants to know too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# How long an episode that ended is still shown. Half a minute is what it
# takes to look away from a game and at the program.
MEMORY_S = 30.0

# Below this nothing is said: a two-tenths throttle at a scene change is how
# any modern card works, and warning of it turns the warning into noise.
MIN_S = 1.5


@dataclass
class Episode:
    """A continuous stretch of throttling."""

    since_ns: int
    until_ns: Optional[int] = None          # None = still going on
    # Every reason seen during the episode, not only the last: a card that
    # starts on power and ends on temperature did both, and keeping only the
    # current one loses half the story.
    reasons: set[str] = field(default_factory=set)

    def ongoing(self) -> bool:
        return self.until_ns is None

    def duration_s(self, now_ns: int) -> float:
        end = self.until_ns if self.until_ns is not None else now_ns
        return max(0.0, (end - self.since_ns) / 1e9)


@dataclass
class ThrottleTracker:
    """Follows the throttling episodes of several things at once.

    The caller sets the key: in practice each GPU's PCI slot, the one thing
    that does not change between samples.
    """

    _open: dict[str, Episode] = field(default_factory=dict)
    _last: dict[str, Episode] = field(default_factory=dict)

    def update(self, key: str, active: Optional[bool],
               reasons: Iterable[str], now_ns: int) -> None:
        """One sample. `active` at None is «not known», and opens or closes nothing."""
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
        """The ongoing episode, if it has lasted long enough to count."""
        return self._open.get(key)

    def recent(self, key: str, now_ns: int) -> Optional[Episode]:
        """The last one that ended, while it is still recent."""
        episode = self._last.get(key)
        if episode is None or episode.until_ns is None:
            return None
        if (now_ns - episode.until_ns) / 1e9 > MEMORY_S:
            return None
        return episode

    def relevant(self, key: str, now_ns: int) -> Optional[Episode]:
        """The one to show: the current one, or the one that just ended.

        Both must have lasted enough. A blink is not counted, during or after.
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
