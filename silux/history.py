"""This machine's benchmark history.

A lone score says nothing: 610 op/s only means something next to another
figure. Outside figures (an internet table) rarely help, being measured with
another governor, another room temperature and another program. What does
compare well is the same machine against itself: before and after new
thermal paste, in winter and in August, a laptop on the charger and on
battery.

Kept on the user's disk, never sent anywhere, and each entry carries the
conditions it was measured in: without them, two different figures from the
same machine can't be read.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import time
from typing import Optional

from .benchmark import Result

# How many runs are kept. Enough to see a trend over months, and few enough
# for the file to stay a JSON read in one go and openable in an editor.
MAX_ENTRIES = 60


def data_dir() -> pathlib.Path:
    base = os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "silux"


def history_path() -> pathlib.Path:
    return data_dir() / "benchmarks.json"


def reports_dir() -> pathlib.Path:
    """Where «Enviar mi informe» keeps each report it prepares."""
    return data_dir() / "informes"


def same_duration(a: float, b: float) -> bool:
    """Whether two runs asked for the same duration per measurement.

    What is stored is how long the longest measurement took: what was asked
    plus finishing the operation in flight, from a few milliseconds to 128
    with the AppImage's zlib. The margin covers that excess and stays under
    the second between the two closest durations offered, the quick 2 s and
    3 s. Not `score.comparable`'s on purpose: its 1.5 s would join those two.
    """
    return abs(a - b) <= max(0.25, 0.02 * max(a, b))


@dataclasses.dataclass(frozen=True, slots=True)
class Entry:
    """A saved run, with just enough to interpret it again."""

    timestamp: float
    cpu: str                       # so as not to compare against another machine
    threads: int
    seconds: float                 # how long each measurement lasted
    scores: dict[str, float]       # «compresion/1», «compresion/16» → op/s
    # A name the user gives it: «new paste», «summer», «after raising PBO».
    # Without it, a list of dates doesn't say what changed between them,
    # which is what comparing is for.
    label: str = ""
    governor: Optional[str] = None
    temperature_peak_c: Optional[float] = None
    frequency_avg_hz: Optional[int] = None
    background_load: Optional[float] = None
    # The most another program took from it during the measurement. The one
    # above is taken before starting and doesn't see what happens later.
    background_peak: Optional[float] = None
    # The scale its score was computed with. Without it, two runs measured on
    # different scales sit in the same table as if comparable, and the
    # difference read there doesn't exist: redoing the scale moved the
    # single-thread figure 68 % with the machine unchanged.
    score_version: Optional[int] = None
    # The libraries it was measured with, and the processor's extensions.
    # They no longer decide the score (since v6 the three workloads that
    # depend on the system don't score), but they are still kept because
    # they explain those figures: the same part gives 14.9 GB/s in the
    # verification workload with zlib-ng and 1.5 with Ubuntu 22.04's zlib,
    # the one inside the AppImage.
    #
    # The extensions go with the version because alone they say nothing: a
    # classic zlib has no `pclmulqdq` instruction and no `cpuid` at all, so
    # it runs the same path on a 2009 Nehalem as on a Zen 5. They only matter
    # with zlib-ng underneath, which dispatches by CPU.
    zlib_version: Optional[str] = None
    zlib_simd: tuple[str, ...] = ()
    # And the OpenSSL, the other library workloads hang from. Kept because
    # the split is odd: the digest gives the same everywhere (190.05, 190.13,
    # 190.17 op/s on three distributions with two major versions), while key
    # derivation moves ×1.38 between 3.0 and 3.5, since what changed isn't
    # the algorithm but the cost of each of its twelve thousand rounds.
    openssl_version: Optional[str] = None

    @property
    def when(self) -> str:
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(self.timestamp))

    def total(self) -> Optional[float]:
        """The figure two runs of the same machine are compared by.

        The all-threads score: the scoring workloads, each against its
        reference. A raw sum of every measurement let the verification
        workload decide (it counts bytes per second, a hundred billion
        against a few thousand), and that one doesn't score and depends on
        each distribution's zlib. Without every scoring workload there is no
        figure, and a run cancelled halfway isn't compared.
        """
        from . import score

        return score.exact_multithread(self.scores, self.threads)

    def comparable_with(self, other: "Entry") -> bool:
        """Whether two runs can be put side by side.

        Changing the duration changes the figure (three seconds get all the
        turbo and thirty don't), so comparing against another duration would
        say the machine got slower when only the question changed.
        """
        return (self.cpu == other.cpu and self.threads == other.threads
                and same_duration(self.seconds, other.seconds)
                and self.score_version == other.score_version)


# The flags that decide which path zlib-ng takes. The 256-bit one
# (`vpclmulqdq`) is Ice Lake and Zen 3 onwards, so an older processor takes
# another and performs differently with the same library.
#
# They are the processor's, not those the library ends up using: with a
# classic zlib underneath none is used, as it carries none. Kept anyway, and
# together with the version: the pair can be interpreted, each half alone
# can't.
SIMD_FLAGS = ("vpclmulqdq", "pclmulqdq", "avx2")


def _zlib_version() -> Optional[str]:
    """Which compression library is underneath, which differs between
    distributions: CachyOS and Fedora ship zlib-ng; Debian, Ubuntu, Arch and
    openSUSE the classic one."""
    try:
        import zlib
        return zlib.ZLIB_RUNTIME_VERSION
    except Exception:                                  # noqa: BLE001
        return None


def _openssl_version() -> Optional[str]:
    """The OpenSSL it was measured with, which two workloads hang from."""
    try:
        import ssl
        return ssl.OPENSSL_VERSION
    except Exception:                                  # noqa: BLE001
        # A Python built without `ssl` still measures: `hashlib` falls back
        # on what CPython carries. There's just nothing to report then.
        return None


def _simd_flags() -> tuple[str, ...]:
    """Those of `SIMD_FLAGS` this processor has, in that order."""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(("flags", "Features")):
                    present = set(line.split(":", 1)[1].split())
                    return tuple(f for f in SIMD_FLAGS if f in present)
    except OSError:
        pass
    return ()


def from_result(result: Result, cpu: str, seconds: float) -> Entry:
    # `rate` rather than `operations / seconds`: where an operation's size
    # varies between machines, bytes per second are what compare.
    scores = {f"{m.load}/{m.threads}": m.rate
              for m in result.measures if m.seconds}
    conditions = result.conditions
    threads = max((m.threads for m in result.measures), default=1)
    from . import score

    return Entry(
        score_version=score.VERSION,
        zlib_version=_zlib_version(),
        zlib_simd=_simd_flags(),
        openssl_version=_openssl_version(),
        timestamp=time.time(),
        cpu=cpu,
        threads=threads,
        seconds=seconds,
        scores=scores,
        governor=conditions.governor,
        temperature_peak_c=conditions.temperature_peak_c,
        frequency_avg_hz=conditions.frequency_avg_hz,
        background_load=conditions.background_load,
        background_peak=conditions.background_peak,
    )


def _is_number(value) -> bool:
    # `bool` is an `int` to Python, and a `true` where a date goes isn't one.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _well_formed(row: dict) -> bool:
    """Whether an entry read from disk can be used without crashing later.

    The program writes the file, but it lives on someone's disk: an entry
    with a field of the wrong type was read without complaint and crashed
    later, sorting or summing while building the Benchmark page, so the
    window didn't open.
    """
    measures = row.get("scores")
    return (_is_number(row.get("timestamp"))
            and isinstance(row.get("cpu"), str)
            and _is_number(row.get("threads")) and row["threads"] > 0
            and _is_number(row.get("seconds")) and row["seconds"] > 0
            and isinstance(measures, dict)
            and all(isinstance(k, str) and _is_number(v) for k, v in measures.items())
            and isinstance(row.get("label", ""), str)
            and all(row.get(field) is None or _is_number(row[field])
                    for field in ("temperature_peak_c", "frequency_avg_hz",
                                  "background_load", "background_peak",
                                  "score_version")))


def load() -> list[Entry]:
    """The saved runs, newest first."""
    try:
        raw = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # `ValueError` covers malformed JSON and broken UTF-8 too.
        return []
    if not isinstance(raw, list):
        return []

    entries = []
    known_fields = {f.name for f in dataclasses.fields(Entry)}
    for row in raw:
        if not isinstance(row, dict) or not _well_formed(row):
            continue
        try:
            entries.append(Entry(**{k: v for k, v in row.items() if k in known_fields}))
        except TypeError:
            # An entry from a version with other fields: it alone is skipped
            # rather than dropping the whole file.
            continue
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


def save(entries: list[Entry]) -> bool:
    """Save the history. Not critical: if it fails, the run was already shown."""
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        temp_path = history_path().with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps([dataclasses.asdict(e) for e in entries[:MAX_ENTRIES]],
                       indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        temp_path.replace(history_path())
        return True
    except OSError:
        return False


def append(entry: Entry) -> list[Entry]:
    """Add a run to the history and return the resulting history."""
    entries = [entry] + load()
    save(entries)
    return entries[:MAX_ENTRIES]


def compare(latest: Entry, previous: list[Entry]) -> Optional[tuple[Entry, float]]:
    """The latest comparable run and how much it changed, in percent.

    None when there's nothing to compare with, as happens the first time and
    whenever the measurement's duration changes.
    """
    total = latest.total()
    if not total:
        return None
    for other in previous:
        if other.timestamp >= latest.timestamp or not other.comparable_with(latest):
            continue
        before = other.total()
        if before:
            return other, (total - before) / before * 100
    return None


# How alike two scores must be for their temperature difference to mean
# something. If the machine did 20 % more work, running hotter explains
# itself and there's nothing to warn about.
CLOSE_SCORE = 0.03

# The temperature rise worth mentioning. Below it is noise: the same run
# twice in a row already varies a couple of degrees with how the machine was
# before starting.
MIN_DRIFT_C = 4.0

# How many older runs make a reference. With only one, a trend can't be told
# from an odd day.
MIN_TO_COMPARE = 3


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def thermal_drift(latest: Entry, previous: list[Entry]) -> Optional[tuple[float, int]]:
    """How much hotter the machine runs doing the same work.

    Returns `(degrees of difference, how many runs back it)`, or None if
    there's nothing to compare with. It is what gives away dried paste or
    dust: the score can hold while the fan compensates, and what rises first
    is the temperature for the same work.

    Compared against the median, not the latest: a lone run started with the
    machine already warm comes out high and means nothing. And only those
    that scored alike count, since a machine that did more work running
    hotter explains itself.

    What this can't know is the room temperature, which no sensor in the
    machine measures. Eight degrees between February and August are normal
    and would look the same as eight degrees of dried paste, so the warning
    says what it sees and doesn't diagnose.
    """
    if latest.temperature_peak_c is None:
        return None
    total = latest.total()
    if not total:
        return None

    references = []
    for other in previous:
        if other.timestamp >= latest.timestamp or not other.comparable_with(latest):
            continue
        if other.temperature_peak_c is None:
            continue
        own = other.total()
        if not own:
            continue
        if abs(own - total) / total > CLOSE_SCORE:
            continue
        references.append(other.temperature_peak_c)

    if len(references) < MIN_TO_COMPARE:
        return None
    difference = latest.temperature_peak_c - _median(references)
    if abs(difference) < MIN_DRIFT_C:
        return None
    return difference, len(references)


def clear() -> bool:
    """Delete the whole history. Return whether there was anything to delete."""
    try:
        history_path().unlink()
        return True
    except OSError:
        return False


def remove(timestamp: float) -> list[Entry]:
    """Delete one run by its timestamp."""
    kept = [e for e in load() if e.timestamp != timestamp]
    save(kept)
    return kept


def remove_other_scales(version: int) -> list[Entry]:
    """Delete the runs measured on a scale other than `version`.

    Also those that don't say which: they predate numbered scales. Their
    figure can't sit next to today's.
    """
    kept = [e for e in load() if e.score_version == version]
    save(kept)
    return kept


def rename(timestamp: float, label: str) -> list[Entry]:
    """Name (or unname) a run."""
    entries = []
    for entry in load():
        if entry.timestamp == timestamp:
            entry = dataclasses.replace(entry, label=label.strip())
        entries.append(entry)
    save(entries)
    return entries
