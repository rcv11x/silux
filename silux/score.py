"""A score that can be compared between two machines.

Two things make a raw figure useless for that, and both are handled here:

**Workloads of different magnitudes.** Summed as operations per second, the
heaviest one decides: on a 5800X3D heavy compression gave 28 494 op/s and
memory 533, so the first was 82 % of the total. Each workload is divided by
what a reference part gives, so all of them weigh the same.

**The duration of each measurement.** Three seconds get all the turbo and
thirty lose it halfway, so the same part gives very different figures
depending on what it is asked. Only runs at the canonical duration score.

And not every workload can score: three of the five rest on a library each
distribution builds its own way, and there the figure stops being the
processor's. They are still measured and shown; which ones and why, in
`SCORED_WORKLOADS`.

What doesn't meet those conditions gets no score, which beats a figure that
looks comparable and isn't. The formula carries a version: changing the
references or the workloads moves every score at once.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import pathlib
from typing import Optional

# Bumped when the references, the workloads or how they combine change. A
# score from another version isn't compared with this one. What each version
# changed and why: docs/decisiones/escala-del-benchmark.md.
VERSION = 6

# The workloads that count towards the score: those that measure the
# processor and not the distribution.
#
# Measured, not assumed. The same part, three distributions and two major
# OpenSSL versions:
#
#     digest              190.05 · 190.13 · 190.17 op/s   ±0.1 %
#     heavy compression    99.54 · 100.96 · 102.84        ±3 %
#     key derivation      123.53 · 152.12 · 170.00        ×1.38
#     compression           (zlib)                        ×2.75
#     verification          (zlib)                        ×9.7
#
# The other three are still measured and shown, with the library that
# measured them next to them: they are good diagnostics, and exactly what
# gives away what's underneath. They just can't go into a figure compared
# between machines. The cost is written where it's paid: in `benchmark.py`,
# next to the workload left without a replacement.
SCORED_WORKLOADS = ("hash", "compresion_dura")

# How long each measurement must last for the run to score. Fifteen seconds
# is where most processors have left the start-up turbo behind and haven't
# yet run long enough for the case's cooling to decide. Below it the turbo
# is measured; above, the heatsink.
CANONICAL_SECONDS = 15.0

# How far the real duration may drift and still count. The loop doesn't stop
# mid-operation, so fifteen seconds asked come out as fifteen and a bit.
SECONDS_TOLERANCE = 1.5

# What the reference part scores, by definition. A round figure reads better
# than a percentage and leaves room for parts that do better than a thousand.
SCALE = 1000

# The reference part's operations per second live in a data file, not here:
# they are measured, not chosen, and redoing them on another machine
# shouldn't mean touching code. It keeps all five, describing the reference
# part whole; its role is to put the scoring ones on one scale. Changing them
# moves every score at once, which is why the file says which formula
# version it is for.
_TABLE = pathlib.Path(__file__).parent / "db" / "scores.json"


@functools.lru_cache(maxsize=1)
def references() -> dict:
    """The reference table, or empty if missing.

    Without it there's no score: it is the scale. And without a scale, no
    figure beats one that doesn't mean the same on two machines.
    """
    try:
        with _TABLE.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if data.get("version_formula") == VERSION else {}


def reference_machine() -> dict:
    """Which machine, and under what conditions, the scale was taken on."""
    return references().get("patron", {})

def compute(scores: dict[str, float], threads: int) -> Optional[tuple[int, int]]:
    """The single-thread score and the all-threads one.

    `scores` is what the history keeps: «compresion/1» and «compresion/16»
    with their operations per second.

    The duration is deliberately not looked at. Putting the workloads on one
    scale is right for any run, and a better figure than the raw sum within
    one machine too. What the duration decides is something else: whether
    this figure can sit next to another machine's, which `comparable`
    answers.
    """
    table = references()
    single = _combined(scores, 1, table.get("un_hilo", {}))
    multi = _combined(scores, threads, table.get("multihilo", {}))
    if single is None or multi is None:
        return None
    return single, multi


def comparable(seconds: float) -> bool:
    """Whether this score can sit next to another machine's.

    Three seconds get all the turbo and thirty lose it halfway, so the same
    part gives different figures depending on what it is asked. Within one
    machine that's fine (the history already requires the same duration to
    compare), but not between two.
    """
    return abs(seconds - CANONICAL_SECONDS) <= SECONDS_TOLERANCE


def is_scored(workload: str) -> bool:
    """Whether this workload counts towards the score.

    It lives here and not in `benchmark.WORKLOADS` because it is the scale's
    decision, not the workload's: the same run, measured the same, counts or
    not depending on what the formula can compare. A mark on each workload
    would keep it in two places that could drift apart unnoticed.
    """
    return workload in SCORED_WORKLOADS


def exact_multithread(scores: dict[str, float], threads: int) -> Optional[float]:
    """The all-threads score, unrounded.

    The figure the history compares two runs of the same machine by:
    `compute` rounds for display, which would shift small differences when
    comparing.
    """
    return _fraction(scores, threads, references().get("multihilo", {}))


def _combined(scores: dict[str, float], threads: int,
              reference: dict[str, float]) -> Optional[int]:
    fraction = _fraction(scores, threads, reference)
    return None if fraction is None else round(fraction)


def _fraction(scores: dict[str, float], threads: int,
              reference: dict[str, float]) -> Optional[float]:
    """The mean of the scoring workloads, each against its reference.

    It walks `SCORED_WORKLOADS`, not the whole table: the reference keeps all
    five workloads, describing the reference part whole, and the formula
    decides which score. If the table ruled, adding a measurement to it
    would change the scale without anyone bumping the version.

    All are needed: with one missing, the gap would skew the comparison with
    any complete run, and the figure would look just as valid.
    """
    if not reference:
        return None
    fractions = []
    for workload in SCORED_WORKLOADS:
        reference_value = reference.get(workload)
        measured = scores.get(f"{workload}/{threads}")
        if measured is None or not reference_value:
            return None
        fractions.append(measured / reference_value)
    return sum(fractions) / len(fractions) * SCALE


# How many measurements make a range. With two, the ends are the two there
# are, and the bar would call anything normal or nothing, by luck. Three is
# few, and already allows a median.
MIN_SAMPLES = 3

# How far a score may stray from its part's median before it's worth a
# comment. 8 % either way is what separates two machines with the same CPU:
# the board, the memory, the heatsink and the governor.
NORMAL_MARGIN = 0.08


@dataclasses.dataclass(frozen=True, slots=True)
class Placement:
    """Where a score falls among those of the same part."""

    value: int
    minimum: int
    maximum: int
    median: int
    samples: int

    @property
    def fraction(self) -> float:
        """Where to put it on the bar, from 0 to 1.

        Clamped to the ends: a part beating everything recorded must show at
        the end of the bar, not past it.
        """
        if self.maximum <= self.minimum:
            return 0.5
        raw = (self.value - self.minimum) / (self.maximum - self.minimum)
        return max(0.0, min(1.0, raw))

    @property
    def deviation(self) -> float:
        """How far it is from the median, as a fraction."""
        return (self.value - self.median) / self.median if self.median else 0.0

    @property
    def normal(self) -> bool:
        return abs(self.deviation) <= NORMAL_MARGIN


def compare(cpu: str, value: int,
             multithread: bool = True) -> Optional[Placement]:
    """Where this score falls among the known ones for the same part.

    `None` when nothing is known about that CPU, which today is almost
    always: the table starts with the little measured so far and fills as
    more comes in. Saying nothing beats placing someone against two lone
    measurements.
    """
    part = references().get("piezas", {}).get(cpu)
    if not part:
        return None
    samples = sorted(part.get("multihilo" if multithread else "un_hilo", []))
    if len(samples) < MIN_SAMPLES:
        return None
    middle = len(samples) // 2
    median = (samples[middle] if len(samples) % 2
               else (samples[middle - 1] + samples[middle]) / 2)
    return Placement(
        value=value,
        minimum=int(samples[0]),
        maximum=int(samples[-1]),
        median=int(round(median)),
        samples=len(samples),
    )


def known_parts() -> int:
    """How many parts have enough measurements to compare."""
    return sum(1 for p in references().get("piezas", {}).values()
               if len(p.get("multihilo", [])) >= MIN_SAMPLES)
