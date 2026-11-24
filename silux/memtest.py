"""The memory test: latency by block size and bandwidth, with their context.

The native module (`silux_bench`) measures; this decides what to ask it for,
runs it in a child process and reads what came back: each cache level's
latency off the curve, whether the curve steps where the processor says its
caches end, and how much of what the memory could move is being moved.

In a child process because the test maps a gigabyte, and the whole program's
budget is 300 MB: it is asked for, measured and freed there, and a crash in
native code takes the child and not the window. The child says how far it
has got on its standard output, one JSON object per line, and killing it is
how the test is cancelled.

Without the native module the simple measure of `membench` answers instead,
and the result says so: no curve, no pinned threads, one thread reading.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import json
import os
import pathlib
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from . import membench

KIB = 1024
MIB = 1024 * KIB
GIB = 1024 * MIB

# The RAM's latency is always measured the same way, so two machines can be
# compared: at random over this block, or over four times the largest cache
# where that is more, with huge pages.
RAM_BLOCK = GIB
TIMES_PAST_CACHE = 4
# Under this a block doesn't leave a large cache behind, and what it times
# isn't the RAM: the level is left out and the reason given.
SMALLEST_RAM_BLOCK = 64 * MIB
FIRST_BLOCK = 4 * KIB

# One thread moves this much per array; with every thread, each its share of
# MULTI_TOTAL, which a copy takes twice. Both grow to this many times the
# largest cache: a block only five times a 96 MiB L3 still read about a tenth
# faster than one ten times it, part of it served from the cache, and by how
# much changed from one run to the next.
SINGLE_BYTES = GIB
MULTI_TOTAL = GIB
TIMES_PAST_CACHE_MOVED = 8
MULTI_SMALLEST = 16 * MIB

# A level's plateau is the blocks that fit in its cache with room: up to
# this fraction of it. A block the size of the cache already shares it with
# whatever else the core is running.
FITS_WITHIN = 0.5
# A step is where the curve crosses the geometric mean of two plateaus, and it
# matches the cache when it falls within this factor of its size.
STEP_TOLERANCE = 2.0
# Two plateaus closer than this can't be told apart, and their step isn't
# looked for.
DISTINCT = 1.3

# What each bandwidth kernel is called in a result.
OPERATIONS = (("read", False), ("write", False), ("copy", False),
              ("write", True), ("copy", True))

TIMEOUT_S = 180
HISTORY_VERSION = 1
MAX_ENTRIES = 60


@dataclass(frozen=True)
class Point:
    """Latency at one block size."""

    bytes_: int
    nanoseconds: float
    spread: float = 0.0
    noisy: bool = False
    frequency_hz: Optional[int] = None


@dataclass(frozen=True)
class Level:
    """A cache level's latency, or the RAM's."""

    level: str                       # "L1", "L2", "L3", "RAM"
    nanoseconds: float
    bytes_: int                      # the largest block that went into it
    frequency_hz: Optional[int] = None


@dataclass(frozen=True)
class Rate:
    """How fast memory moved in one kind of pass."""

    operation: str                   # "read" | "write" | "copy"
    threads: int
    bytes_per_second: int
    non_temporal: bool = False
    isa: Optional[str] = None
    noisy: bool = False
    frequency_hz: Optional[int] = None
    # Where its block fits: "L1", "L2", "L3" or "RAM".
    level: str = "RAM"


@dataclass(frozen=True)
class Plan:
    """What the child is asked to measure."""

    cpu: Optional[int]
    cpus: tuple[int, ...]
    sizes: tuple[int, ...]
    # The block the RAM's latency comes from; None when none large enough fits.
    ram_block: Optional[int]
    # Whether free memory, and not the method, set that block.
    ram_block_limited: bool
    single_bytes: int
    multi_bytes: Optional[int]
    caches: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Result:
    engine: str                      # "native" | "simple"
    timestamp: float = 0.0
    cpu: Optional[int] = None
    points: tuple[Point, ...] = ()
    levels: tuple[Level, ...] = ()
    rates: tuple[Rate, ...] = ()
    # The part of the largest block the kernel backed with 2 MiB pages.
    huge_fraction: Optional[float] = None
    frequency_source: Optional[str] = None   # "cycles" | "cpufreq"
    ram_block: Optional[int] = None
    ram_block_limited: bool = False
    caches: tuple[tuple[str, int], ...] = ()
    governor: Optional[str] = None
    energy_preference: Optional[str] = None
    # What the memory could move, from its channels and its speed when it was
    # measured: a percentage against today's modules would lie after a change.
    theoretical_bytes_per_second: Optional[int] = None
    channels: Optional[int] = None
    speed_mts: Optional[int] = None
    seconds: float = 0.0
    # Why there is nothing, or less than asked: a key the interface translates.
    reason: Optional[str] = None
    detail: str = ""
    # A name the user gives it, as in the processor's history.
    label: str = ""

    def level(self, name: str) -> Optional[Level]:
        return next((l for l in self.levels if l.level == name), None)

    def rate(self, operation: str, threads: Optional[int] = None,
             non_temporal: bool = False, level: str = "RAM") -> Optional[Rate]:
        """That operation's rate over a block of that level with `threads`,
        or its fastest without."""
        found = [r for r in self.rates
                 if r.operation == operation and r.non_temporal == non_temporal
                 and r.level == level and threads in (None, r.threads)]
        return max(found, key=lambda r: r.bytes_per_second, default=None)

    @property
    def measured(self) -> bool:
        return bool(self.levels or self.rates)


@dataclass(frozen=True)
class Memory:
    """What the memory could move when it was measured, and from what."""

    theoretical_bytes_per_second: Optional[int] = None
    channels: Optional[int] = None
    speed_mts: Optional[int] = None


@dataclass(frozen=True)
class Step:
    """Where the curve rises past a cache, against that cache's size."""

    level: str
    declared_bytes: int
    # The first block past the rise, and the last before it.
    rises_by: int
    flat_until: int
    matches: bool


# -- what to ask for ---------------------------------------------------------

def curve_sizes(largest: int) -> tuple[int, ...]:
    """Two blocks per power of two, from 4 KiB up to and including `largest`."""
    sizes = []
    size = FIRST_BLOCK
    while size <= largest:
        sizes.append(size)
        if size + size // 2 <= largest:
            sizes.append(size + size // 2)
        size *= 2
    if largest >= FIRST_BLOCK and largest not in sizes:
        sizes.append(largest - largest % 64)
    return tuple(sorted(set(sizes)))


def make_plan(caches: Sequence[tuple[str, int]], cpus: Sequence[int],
              cpu: Optional[int] = None,
              available: Optional[int] = None) -> Plan:
    """The blocks and the CPUs, for these caches and this much free memory.

    `caches` are the data caches of the core that will be measured, smallest
    first; `cpus`, where the all-thread bandwidth runs.
    """
    caches = tuple(sorted(((str(n), int(s)) for n, s in caches if s), key=lambda c: c[1]))
    cpus = tuple(cpus)
    if available is None:
        available = membench._available_memory()
    room = None if available is None else max(0, available - membench.FREE_MARGIN)
    largest_cache = max((s for _n, s in caches), default=0)

    wanted = max(RAM_BLOCK, TIMES_PAST_CACHE * largest_cache)
    block = wanted if room is None else min(wanted, room - room % (2 * MIB))
    limited = block < wanted
    past_cache = block >= max(SMALLEST_RAM_BLOCK, 2 * largest_cache)
    ram_block = block if past_cache else None
    # Without a RAM block the curve still walks the caches.
    top = ram_block or min(block, max(largest_cache, FIRST_BLOCK))
    sizes = curve_sizes(top) if top >= FIRST_BLOCK else ()

    moved = max(SINGLE_BYTES, TIMES_PAST_CACHE_MOVED * largest_cache)
    single = moved - moved % (2 * MIB)
    if room is not None:
        # A copy maps two arrays.
        single = min(single, room // 2 - (room // 2) % (2 * MIB))
    multi = None
    if len(cpus) > 1:
        total = max(MULTI_TOTAL, TIMES_PAST_CACHE_MOVED * largest_cache)
        if room is not None:
            total = min(total, room // 2)
        share = total // len(cpus)
        share -= share % (2 * MIB)
        # All of them together have to leave the largest cache behind.
        if share >= MULTI_SMALLEST and share * len(cpus) >= 2 * largest_cache:
            multi = share
    return Plan(cpu=cpu, cpus=cpus, sizes=sizes, ram_block=ram_block,
                ram_block_limited=limited and ram_block is not None,
                single_bytes=max(single, 0), multi_bytes=multi, caches=caches)


def pick_cpu(types, allowed: Sequence[int]) -> tuple[Optional[int], tuple[tuple[str, int], ...]]:
    """The CPU to measure latency on, and its data caches.

    A CPU of the first core type, which is the fast one where there are two,
    and not the first of them: CPU 0 is where the kernel sends most of what
    interrupts. `types` are the model's `cpu.types`.
    """
    allowed = list(allowed)
    for core_type in types or ():
        own = [c for c in core_type.cpus if not allowed or c in allowed]
        if not own:
            continue
        caches = sorted({(f"L{c.level}", c.size_bytes) for c in core_type.caches
                         if c.kind in ("data", "unified") and c.size_bytes},
                        key=lambda c: c[1])
        return (own[1] if len(own) > 1 else own[0]), tuple(caches)
    if allowed:
        return (allowed[1] if len(allowed) > 1 else allowed[0]), ()
    return None, ()


# -- reading the curve -------------------------------------------------------

def levels_from_curve(points: Sequence[Point], caches: Sequence[tuple[str, int]],
                      ram_block: Optional[int]) -> tuple[Level, ...]:
    """Each level's latency: the median of the blocks that fit in its cache
    and not in the one before, and the RAM block's own point."""
    levels = []
    floor = 0
    for name, size in caches:
        fits = [p for p in points if floor < p.bytes_ <= size * FITS_WITHIN]
        floor = size
        if not fits:
            continue
        hertz = [p.frequency_hz for p in fits if p.frequency_hz]
        levels.append(Level(
            name, statistics.median(p.nanoseconds for p in fits),
            max(p.bytes_ for p in fits),
            int(statistics.median(hertz)) if len(hertz) == len(fits) else None))
    ram = next((p for p in points if ram_block and p.bytes_ == ram_block), None)
    if ram is not None:
        levels.append(Level("RAM", ram.nanoseconds, ram.bytes_, ram.frequency_hz))
    return tuple(levels)


def curve_steps(points: Sequence[Point], levels: Sequence[Level],
                caches: Sequence[tuple[str, int]]) -> tuple[Step, ...]:
    """Where the curve leaves each cache, against the size the processor
    declares for it. Only between levels the curve tells apart."""
    sizes = dict(caches)
    steps = []
    for below, above in zip(levels, levels[1:]):
        declared = sizes.get(below.level)
        if not declared or above.nanoseconds < below.nanoseconds * DISTINCT:
            continue
        threshold = (below.nanoseconds * above.nanoseconds) ** 0.5
        between = [p for p in points if below.bytes_ <= p.bytes_ <= above.bytes_]
        risen = next((p for p in between if p.nanoseconds > threshold), None)
        if risen is None:
            continue
        flat = max((p.bytes_ for p in between if p.bytes_ < risen.bytes_),
                   default=below.bytes_)
        # The rise is somewhere between the last flat block and the first
        # risen one: it matches if that stretch reaches the cache's
        # neighbourhood.
        matches = (flat <= declared * STEP_TOLERANCE
                   and risen.bytes_ >= declared / STEP_TOLERANCE)
        steps.append(Step(below.level, declared, risen.bytes_, flat, matches))
    return tuple(steps)


def share_of_theoretical(result: Result) -> Optional[float]:
    """The fastest read, in percent of what the memory could move. Above a
    hundred, one of the two figures is wrong."""
    read = result.rate("read")
    if read is None or not result.theoretical_bytes_per_second:
        return None
    return round(read.bytes_per_second / result.theoretical_bytes_per_second * 100, 1)


def with_memory(result: Result, memory: Memory, booted_at: Optional[float]) -> Result:
    """`result` with what the memory could move, when it was measured without
    knowing it and since the machine last booted: memory isn't changed with
    the machine running, so today's modules are the ones it ran on. An older
    result stays as it is."""
    if (result.theoretical_bytes_per_second or not memory.theoretical_bytes_per_second
            or booted_at is None or result.timestamp < booted_at):
        return result
    return dataclasses.replace(result, **dataclasses.asdict(memory))


# -- running it --------------------------------------------------------------

def native_module():
    """`silux_bench`, or None where it isn't installed or doesn't load."""
    try:
        import silux_bench
    except ImportError:
        return None
    return silux_bench


def run(plan: Plan, on_progress: Optional[Callable[[str, float], None]] = None,
        stop: Optional[threading.Event] = None,
        memory: Memory = Memory()) -> Result:
    """Measure in a child process and wait for it. Call from a thread.

    `on_progress` gets the phase's key and the fraction done; setting `stop`
    kills the child and the result says it was cancelled.
    """
    started = time.time()
    if native_module() is None:
        return _simple(plan, started, memory)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", "silux.memtest", json.dumps(dataclasses.asdict(plan))],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    except OSError as error:
        return Result("native", started, reason="not_started", detail=str(error))

    finished = threading.Event()

    def watch() -> None:
        deadline = time.monotonic() + TIMEOUT_S
        while not finished.wait(0.1):
            if (stop is not None and stop.is_set()) or time.monotonic() > deadline:
                child.kill()
                return

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    answer = None
    try:
        for line in child.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if "result" in message:
                answer = message["result"]
            elif on_progress is not None and "phase" in message:
                on_progress(message["phase"], float(message.get("done", 0.0)))
        errors = child.stderr.read()
        child.wait()
    finally:
        finished.set()
        watcher.join(timeout=2)
        child.stdout.close()
        child.stderr.close()
    if stop is not None and stop.is_set():
        return Result("native", started, reason="cancelled")
    if answer is None:
        return Result("native", started, reason="failed",
                      detail=errors.strip()[-2000:] or f"exit {child.returncode}")
    return _result(answer, plan, started, memory)


def _result(answer: dict, plan: Plan, started: float, memory: Memory) -> Result:
    points = tuple(Point(**p) for p in answer.get("points", ()))
    return Result(
        engine="native", timestamp=started, cpu=answer.get("cpu"), points=points,
        levels=levels_from_curve(points, plan.caches, plan.ram_block),
        rates=tuple(Rate(**r) for r in answer.get("rates", ())),
        huge_fraction=answer.get("huge_fraction"),
        frequency_source=answer.get("frequency_source"),
        ram_block=plan.ram_block, ram_block_limited=plan.ram_block_limited,
        caches=plan.caches, governor=answer.get("governor"),
        energy_preference=answer.get("energy_preference"),
        seconds=round(time.time() - started, 1),
        reason=answer.get("reason"), detail=answer.get("detail", ""),
        **dataclasses.asdict(memory))


def _simple(plan: Plan, started: float, memory: Memory) -> Result:
    """`membench`'s measure, as a result of this kind."""
    largest = max((s for _n, s in plan.caches), default=None)
    old = membench.query(largest, [list(c) for c in plan.caches])
    ram = next((m for m in old.measurements if m.where == "ram"), None)
    return Result(
        engine="simple", timestamp=started,
        levels=tuple(Level(l.level, l.nanoseconds, l.bytes_) for l in old.latencies),
        rates=(Rate("read", 1, ram.bandwidth_bytes),) if ram else (),
        caches=plan.caches, seconds=round(time.time() - started, 1),
        reason=None if (ram or old.latencies) else (old.reason or "failed"),
        **dataclasses.asdict(memory))


# -- the child ---------------------------------------------------------------

def _read(path: str) -> Optional[str]:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _hz(mhz: Optional[float]) -> Optional[int]:
    return None if mhz is None else int(mhz * 1e6)


def _measure(plan: dict, emit: Callable[[dict], None]) -> dict:
    """Everything the plan asks for, in this process."""
    import silux_bench

    cpu = plan["cpu"]
    passes = [(operation, non_temporal, threads)
              for threads in ("single", "multi")
              for operation, non_temporal in OPERATIONS
              if plan[f"{threads}_bytes"]]
    # The curve is about half the test; the rest is shared by the passes.
    curve_part = 0.5 if passes else 1.0
    answer: dict = {"cpu": cpu, "points": [], "rates": []}

    if plan["sizes"]:
        control = silux_bench.Control()
        done = threading.Event()

        def report() -> None:
            while not done.wait(0.1):
                step, of = control.progress()
                if of:
                    emit({"phase": "latency", "done": curve_part * step / of})

        reporter = threading.Thread(target=report, daemon=True)
        reporter.start()
        try:
            curve = silux_bench.latency_curve(list(plan["sizes"]), cpu=cpu, control=control)
        finally:
            done.set()
            reporter.join()
        answer["cpu"] = curve["cpu"] if cpu is None else cpu
        answer["frequency_source"] = curve["frequency_source"]
        if curve["rss_bytes"]:
            answer["huge_fraction"] = round(
                min(1.0, (curve["huge_bytes"] or 0) / curve["rss_bytes"]), 3)
        answer["points"] = [
            {"bytes_": p["bytes"], "nanoseconds": p["median_ns"], "spread": p["spread"],
             "noisy": p["noisy"], "frequency_hz": _hz(p["mhz"])}
            for p in curve["points"]]

    for index, (operation, non_temporal, threads) in enumerate(passes):
        emit({"phase": operation + ("_nt" if non_temporal else ""),
              "done": curve_part + (1 - curve_part) * index / len(passes)})
        cpus = [cpu if cpu is not None else plan["cpus"][0]] if threads == "single" \
            else list(plan["cpus"])
        try:
            rate = silux_bench.memory_bandwidth(
                operation, bytes=plan[f"{threads}_bytes"], cpus=cpus,
                non_temporal=non_temporal)
        except silux_bench.SiluxBenchError as error:
            # One pass that can't run (no memory for sixteen blocks) doesn't
            # take the others with it.
            answer.setdefault("detail", f"{operation}: {error.args[-1]}")
            continue
        answer["rates"].append({
            "operation": operation, "threads": rate["threads"],
            "bytes_per_second": int(rate["median_gbps"] * 1e9),
            "non_temporal": non_temporal, "isa": rate["isa"], "noisy": rate["noisy"],
            "frequency_hz": _hz(rate["mhz"])})

    where = f"/sys/devices/system/cpu/cpu{answer['cpu'] or 0}/cpufreq"
    answer["governor"] = _read(f"{where}/scaling_governor")
    answer["energy_preference"] = _read(f"{where}/energy_performance_preference")
    return answer


def main() -> int:
    plan = json.loads(sys.argv[1])

    def emit(message: dict) -> None:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()

    try:
        answer = _measure(plan, emit)
    except Exception as error:  # whatever it was, the parent says it
        key = error.args[0] if len(error.args) == 2 else "failed"
        answer = {"reason": str(key), "detail": str(error.args[-1] if error.args else error)}
    emit({"result": answer})
    return 0


# -- this machine's earlier tests --------------------------------------------

def history_path() -> pathlib.Path:
    from . import history

    return history.data_dir() / "memory-tests.json"


# The parts of a saved test that are lists of rows of their own, and the
# fields that tell one row of each from another.
PARTS = (("points", Point, ("bytes_",)),
         ("levels", Level, ("level",)),
         ("rates", Rate, ("operation", "threads", "level", "non_temporal")))


def _known(kind, row: dict) -> dict:
    """`row` without the fields this version has no name for: a newer one
    may have saved more."""
    names = {f.name for f in dataclasses.fields(kind)}
    return {name: value for name, value in row.items() if name in names}


def _from_dict(row: dict) -> Result:
    row = _known(Result, row)
    for part, kind, _names in PARTS:
        row[part] = tuple(kind(**_known(kind, r)) for r in row.get(part, ()))
    row["caches"] = tuple((str(n), int(s)) for n, s in row.get("caches", ()))
    return Result(**row)


def _identity(kind, names: Sequence[str], row: dict) -> tuple:
    """What tells `row` from the others in its list. A field the file left
    out counts as its default, which is what reading it gives."""
    defaults = {f.name: f.default for f in dataclasses.fields(kind)}
    return tuple(row.get(name, defaults[name]) for name in names)


def _by_identity(rows, identity: Callable[[dict], object]) -> dict:
    """Each row under what identifies it, without those that share it: there
    is no telling which of them is which."""
    found, shared = {}, set()
    for row in rows if isinstance(rows, (list, tuple)) else ():
        if not isinstance(row, dict):
            continue
        try:
            key = identity(row)
            if key in found:
                shared.add(key)
            found[key] = row
        except TypeError:
            # A list or an object where a number or a name goes.
            continue
    return {key: row for key, row in found.items() if key not in shared}


def _to_dict(result: Result, saved: Optional[dict]) -> dict:
    """The row to write over `saved`, the one the file has for that test.
    What this version has no name for stays in it: going back a version and
    measuring mustn't strip what the newer one saved.

    Each point, level and rate keeps what its own saved row had, matched by
    what it is and never by its place in the list.
    """
    row = dataclasses.asdict(result)
    if saved is None:
        return row
    for part, kind, names in PARTS:
        identity = functools.partial(_identity, kind, names)
        before = _by_identity(saved.get(part), identity)
        unmistakable = _by_identity(row[part], identity)
        merged = []
        for new in row[part]:
            key = identity(new)
            old = before.get(key) if key in unmistakable else None
            merged.append(new if old is None else {**old, **new})
        row[part] = merged
    return {**saved, **row}


def _saved_file() -> Optional[dict]:
    """The history file as it is written, when there is one and it is a
    JSON object."""
    try:
        data = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _version(data: Optional[dict]) -> Optional[int]:
    """The version a history file says it is, when it says one."""
    version = None if data is None else data.get("version")
    return version if type(version) is int else None


def _saved_rows(data: Optional[dict]) -> Optional[list[dict]]:
    """The tests of a file of this version, as they are written. None for a
    file that isn't one."""
    if _version(data) != HISTORY_VERSION or not isinstance(data.get("tests"), list):
        return None
    return [row for row in data["tests"] if isinstance(row, dict)]


def _set_aside(path: pathlib.Path, data: Optional[dict]) -> None:
    """Move out of the way a history this version can't read, so that
    nothing is written over it: another version's under a name that says
    which, and one that is cut short or isn't a history as broken. Raises
    `OSError` when it can't be moved."""
    if _saved_rows(data) is not None or not os.path.lexists(path):
        return
    version = _version(data)
    kind = "broken" if version in (None, HISTORY_VERSION) else f"v{version}"
    aside = path.with_name(f"{path.name}.{kind}")
    number = 0
    while os.path.lexists(aside):
        number += 1
        aside = path.with_name(f"{path.name}.{kind}.{number}")
    path.rename(aside)


def load_history() -> list[Result]:
    """Saved tests, newest first. A row that can't be read is left out
    without taking the rest with it."""
    results = []
    for row in _saved_rows(_saved_file()) or ():
        try:
            results.append(_from_dict(row))
        except (TypeError, ValueError, AttributeError):
            continue
    return results


def save_history(results: Sequence[Result]) -> bool:
    path = history_path()
    data = _saved_file()
    saved = _by_identity(_saved_rows(data) or (), lambda row: row.get("timestamp"))
    times = collections.Counter(r.timestamp for r in results)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _set_aside(path, data)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(
            {"version": HISTORY_VERSION,
             "tests": [_to_dict(r, saved.get(r.timestamp) if times[r.timestamp] == 1 else None)
                       for r in results[:MAX_ENTRIES]]},
            indent=1), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        return False
    return True


def append_history(result: Result) -> list[Result]:
    results = [result] + load_history()
    save_history(results)
    return results[:MAX_ENTRIES]


def fill_history(memory: Memory, booted_at: Optional[float]) -> Optional[list[Result]]:
    """Give every saved test of this boot what the memory could move
    (`with_memory`). The history as it now stands, or None if nothing
    changed."""
    saved = load_history()
    results = [with_memory(r, memory, booted_at) for r in saved]
    if all(new is old for new, old in zip(results, saved)):
        return None
    save_history(results)
    return results[:MAX_ENTRIES]


def clear_history() -> None:
    try:
        history_path().unlink()
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
