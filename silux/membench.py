"""How fast this machine's memory really moves.

The SPD's MT/s say what the module is rated for, and the theoretical
bandwidth is a multiplication. Neither says what the machine achieves: that
has to be measured, and it is what's missed next to what AIDA64 shows on
Windows.

Bandwidth is measured by reading, with `memchr` looking for a byte that
isn't there: it walks the whole block at memory speed and needs no
destination, so it costs half of copying and the figure comes from a pure
read, the comparable one. The loop is libc's, already compiled, since an
AppImage carries no compiler to generate anything on the fly.

**The tool itself has a ceiling, which has to be measured.** `memchr`
tops out around 112 GB/s on a fast machine, and memory doesn't set that
number: blocks of 1, 4, 16 and 48 MB, which fit different caches, all give
the same, and even L1 with the call's cost taken off stays there. A block
that fits in the cache doesn't measure the cache: it measures how far this
way of measuring goes. So it is measured anyway, as a control rather than
data: if the RAM's bandwidth nears that ceiling, the figure is limited by
the tool and the memory may be faster than shown.

**Latency** can't come from libc. Many scattered random accesses come out
flat, since they don't depend on each other and the processor overlaps
them; a binary search chains them, but turning it into a number takes three
guesses. So the loop is written in machine code, as `rawcpuid.py` does for
CPUID: twelve bytes chasing pointers, each read giving the next address.
"""

from __future__ import annotations

import ctypes
import json
import mmap
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

from . import rawcpuid

# Below this the call weighs more than the memory, and the figure stops
# speaking about the machine and speaks about ctypes.
MIN_RELIABLE = 1024 * 1024

# How far past the cache's size to go to be sure the RAM is measured. At
# twice the size half a pass still fits in the cache; at three times, what
# is read comes from outside.
TIMES_PAST_CACHE = 3

# A cap, since some Threadrippers have 256 MB of cache and three times that
# shouldn't be asked by a program that shows spec sheets. When the block
# can't reach this size, the RAM measurement is skipped and that is said.
MAX_BLOCK = 512 * 1024 * 1024

# What is left free on the machine whatever happens. Measuring must never
# push something into swap.
FREE_MARGIN = 512 * 1024 * 1024

# How much time each block gets. By a pass count, the RAM block got three:
# with so few, one batch catching the machine busy made the figure 15 % low,
# and whoever pressed the button saw a different number each time. Shared by
# time, a small block gets hundreds of passes and a big one those that fit,
# and both have enough to take a meaningful minimum from.
TIME_BUDGET_S = 0.15
MIN_PASSES = 5
MAX_PASSES = 500

# Chases pointers: each read gives the address of the next, so the processor
# can't run ahead and what's timed is how long one access takes. It can't be
# written in Python, where the interpreter costs more than the access.
#
#   mov rax, rdi        48 89 f8     rdi = first link
# loop:
#   mov rax, [rax]      48 8b 00     <- depends on the previous result
#   dec rsi             48 ff ce     rsi = how many hops
#   jnz loop            75 f8
#   ret                 c3
_CHASE_CODE = bytes((0x48, 0x89, 0xF8,
                           0x48, 0x8B, 0x00,
                           0x48, 0xFF, 0xCE,
                           0x75, 0xF8,
                           0xC3))

# A cache line. Hops go from one line to another because reading the same
# line twice comes from the same fetch and measures nothing.
LINE = 64

# The minimum hops, so the cost of entering and leaving the call (570 ns)
# doesn't weigh: an L1 access is 0.9 ns, so with few hops it would be timing
# ctypes again.
MIN_HOPS = 200_000

# And a cap on links, which is what really costs time: shuffling and linking
# them are Python loops. Six million take four seconds before anything is
# measured. With this cap, a processor with a normal cache gets ready in
# tenths of a second, and one with a huge L3 goes without the RAM latency
# and says so, which beats a button frozen for five seconds.
MAX_LINKS = 4_000_000

# For latency, twice the cache is enough: two, three and four times give
# 80.0, 83.6 and 80.8 ns, the same, and each doubling of the block doubles
# the time to build the chain. Bandwidth uses three times, as there's no
# chain to build there and it costs nothing.
TIMES_PAST_FOR_LATENCY = 2

# A cap on the block a cache is measured with, besides its fraction. A Zen 3's
# L3 is a victim cache (it only keeps what L2 evicts), so with half of its
# 96 MB walked at random it holds almost nothing: 66 ns where it should be
# 12. With 4, 8 and 16 MB it gives 11.9, 12.0 and 13.2, so the step is well
# below half and it has to stay low.
MAX_CACHE_BLOCK = 16 * 1024 * 1024

# 2 MB pages instead of 4 KB. Chasing pointers through 288 MB touches 73728
# pages and the data TLB holds about 2000, so every access also paid for a
# page walk: 94.7 ns with normal pages against 82.1 with huge ones. Advice,
# not an order: if the system has them off, nothing breaks.
MADV_HUGEPAGE = 14
HUGE_PAGE = 2 * 1024 * 1024

TIMEOUT_S = 60


@dataclass(frozen=True)
class Measurement:
    """One reading of a block of a given size."""

    bytes_: int
    bandwidth_bytes: int
    # "ram" is the datum; "techo" is the control: a block that fits in the
    # cache, measuring not the cache but the fastest this tool can go.
    where: str                       # "techo" | "ram"


@dataclass(frozen=True)
class Latency:
    """How long an access that can't be anticipated takes, per level."""

    level: str                       # "L1", "L2", "L3", "RAM"
    bytes_: int
    nanoseconds: float


@dataclass(frozen=True)
class MemoryResult:
    measurements: tuple[Measurement, ...] = ()
    latencies: tuple[Latency, ...] = ()
    # Why latencies are missing, which isn't why bandwidth is: one can be had
    # without the other.
    latency_reason: Optional[str] = None
    # Why something couldn't be measured, to say it instead of staying silent.
    reason: Optional[str] = None


def _libc():
    libc = ctypes.CDLL(None)
    libc.memchr.restype = ctypes.c_void_p
    libc.memchr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
    return libc


def _best_pass(libc, address: int, n: int) -> float:
    """The best time to walk the block, in seconds.

    The best and not the mean: what's sought is what the machine gives when
    nothing gets in its way, and any interruption can only make a pass
    worse. Hence several passes: with only three, a whole batch could fall
    inside the interference with no clean pass to trust.
    """
    libc.memchr(address, 0xFF, n)                 # warm up
    best = None
    spent = 0.0
    passes = 0
    while passes < MIN_PASSES or (spent < TIME_BUDGET_S
                                       and passes < MAX_PASSES):
        start = time.perf_counter()
        libc.memchr(address, 0xFF, n)
        elapsed = time.perf_counter() - start
        spent += elapsed
        passes += 1
        best = elapsed if best is None else min(best, elapsed)
    return best or 0.0


def _available_memory() -> Optional[int]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _reserve(size: int):
    """A block aligned to 2 MB, with huge pages requested.

    With `mmap` rather than a ctypes buffer because the alignment is what the
    kernel needs to merge the pages, and a normal buffer lands wherever.
    """
    # Private: `mmap(-1)` alone is shared anonymous memory, which only gets
    # huge pages where shmem THP is on (it is off in Fedora). Without them the
    # TLB misses went into the latency: RAM read 72 ns there instead of 62.
    try:
        mapping = mmap.mmap(-1, size + HUGE_PAGE,
                         flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                         prot=mmap.PROT_READ | mmap.PROT_WRITE)
    except (OSError, ValueError):
        return None
    raw_address = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
    base = (raw_address + HUGE_PAGE - 1) & ~(HUGE_PAGE - 1)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.madvise.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.madvise(ctypes.c_void_p(base), size, MADV_HUGEPAGE)
    return mapping, base


def _chain(base: int, lines: int) -> int:
    """Link `lines` lines of the block into a random cycle.

    Returns the first link's address. Random on purpose: with a constant
    stride the prefetcher guesses it, and what's measured is how long data
    already on its way takes to arrive, not an access.
    """
    order = list(range(lines))
    random.shuffle(order)
    view = (ctypes.c_uint64 * (lines * LINE // 8)).from_address(base)
    followers = order[1:]
    followers.append(order[0])
    for current, following in zip(order, followers):
        view[current * (LINE // 8)] = base + following * LINE
    return base + order[0] * LINE


def _latency(chase, first: int, hops: int) -> float:
    """Nanoseconds per access, from the best attempt."""
    chase(first, min(hops, 100_000))          # warm up
    best = None
    for _attempt in range(3):
        start = time.perf_counter()
        chase(first, hops)
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return (best or 0.0) / hops * 1e9


def measure_latencies(levels: "list[tuple[str, int]]") -> tuple:
    """Measure one level per cache, and the RAM behind them.

    `levels` are pairs of name and size, smallest first. Half of each is
    walked, so the chain fits well inside; for the RAM, three times the
    largest cache, so it can't fit at all.
    """
    if not rawcpuid.is_supported():
        return (), "no_x86"
    try:
        mm, address = rawcpuid.executable_page(_CHASE_CODE)
    except Exception:                                          # noqa: BLE001
        # An environment that forbids executing anonymous memory. No
        # latencies, but the rest of the measurement still stands.
        return (), "sin_ejecutable"

    chase = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_size_t)(address)
    results = []
    reason = None
    try:
        largest = max((size for _name, size in levels), default=0)
        spans = [(name, min(size // 2, MAX_CACHE_BLOCK))
                  for name, size in levels if size // 2 >= LINE * 8]
        spans.append(("RAM", max(MIN_RELIABLE * 64,
                                  largest * TIMES_PAST_FOR_LATENCY)))
        available = _available_memory()
        for name, size in spans:
            lines = size // LINE
            if lines > MAX_LINKS:
                # Building the chain is Python loops: six million links take
                # four seconds before anything is measured.
                reason = reason or "cadena_enorme"
                continue
            if available is not None and size + FREE_MARGIN > available:
                reason = reason or "sin_memoria"
                continue
            block = _reserve(size)
            if block is None:
                reason = reason or "sin_memoria"
                continue
            mapping, base = block
            first = _chain(base, lines)
            # At least two rounds of the whole cycle: with fewer hops than
            # lines, what's walked fits in the cache and the cache gets
            # measured as if it were the RAM. It read 28 ns where there are 76.
            hops = max(MIN_HOPS, lines * 2)
            results.append(Latency(name, size, round(
                _latency(chase, first, hops), 1)))
            mapping.close()
    finally:
        mm.close()
    return tuple(results), reason


def in_this_process(cache_bytes: Optional[int],
                    levels: "Optional[list]" = None) -> MemoryResult:
    """Measure for real.

    `cache_bytes` is the largest cache and sets the bandwidth's blocks.
    `levels` are each cache's name and size, which the latencies need;
    without them only bandwidth is measured.
    """
    libc = _libc()
    measurements: list[Measurement] = []
    available = _available_memory()

    # The ceiling: a block that fits easily in the cache, so memory isn't what
    # limits it. Half the cache, to fit with room even if the system uses some.
    if cache_bytes and cache_bytes // 2 >= MIN_RELIABLE:
        n = cache_bytes // 2
        block = ctypes.create_string_buffer(n)
        seconds = _best_pass(libc, ctypes.addressof(block), n)
        if seconds > 0:
            measurements.append(Measurement(n, int(n / seconds), "techo"))
        del block

    # Past every cache: the RAM's bandwidth.
    n = max(MIN_RELIABLE * 64,
            (cache_bytes or 0) * TIMES_PAST_CACHE)
    if n > MAX_BLOCK or (available is not None
                             and n + FREE_MARGIN > available):
        latencies, why = measure_latencies(levels or [])
        return MemoryResult(tuple(measurements),
                         latencies, why,
                         reason=("cache_enorme" if n > MAX_BLOCK
                                 else "sin_memoria"))
    block = ctypes.create_string_buffer(n)
    seconds = _best_pass(libc, ctypes.addressof(block), n)
    if seconds > 0:
        measurements.append(Measurement(n, int(n / seconds), "ram"))
    del block
    latencies, why = measure_latencies(levels or [])
    return MemoryResult(tuple(measurements), latencies, why)


def query(cache_bytes: Optional[int],
              levels: "Optional[list]" = None) -> MemoryResult:
    """Measure in another process, where it can ask for hundreds of megabytes.

    Getting out of a 96 MB cache takes a block of almost three hundred, and
    the whole program's budget is 300. It is asked for, measured and dies
    there; what stays in this process's memory is a number.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "silux.membench", str(cache_bytes or 0),
             json.dumps(levels or [])],
            capture_output=True, timeout=TIMEOUT_S, env=env, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return MemoryResult(reason="no_arranco")
    if completed.returncode != 0 or not completed.stdout:
        return MemoryResult(reason="no_arranco")
    try:
        data = json.loads(completed.stdout)
        return MemoryResult(
            tuple(Measurement(**m) for m in data.get("measurements", ())),
            tuple(Latency(**l) for l in data.get("latencies", ())),
            data.get("latency_reason"),
            data.get("reason"),
        )
    except (ValueError, TypeError):
        return MemoryResult(reason="no_arranco")


def main() -> int:
    # The output must be clean JSON: anything else printed here would break
    # the parent.
    cache = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    levels = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
    json.dump(asdict(in_this_process(cache or None, levels)), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
