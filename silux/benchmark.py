"""A benchmark that says under what conditions it ran.

A benchmark's figure means nothing alone. The same processor gives very
different results depending on the power governor, how hot it is, or
another program taking half its cores. Whoever compares their number with
one online and finds it doesn't match is left not knowing why.

Silux can already read all of that while it works, so here the benchmark
returns a number **and the conditions it came out under**. If the governor
was saving power, it says so. If the CPU dropped frequency halfway, it says
so. If there was background load, it warns the result isn't comparable.

The workloads come from the standard library: an AppImage carries no
compiler, and a benchmark that only works from source is no use to whoever
downloads the program. `zlib`, `bz2` and `hashlib` have their loops in C
already compiled, and release the interpreter while working, so they truly
spread across cores.

`SHA-512` rather than `SHA-256` on purpose: the `sha_ni` instruction speeds
up the second and not the first, so with SHA-256 a processor having it would
come out inflated and stop being comparable with one that doesn't. That goes
for both workloads using a hash, the digest and key derivation; in the
latter the effect would be even larger, being thousands of chained rounds.

Why these workloads and how they are measured, with the figures:
docs/decisiones/cargas-del-benchmark.md.
"""

from __future__ import annotations

import bz2
import hashlib
import os
import pathlib
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

SYS_CPU = "/sys/devices/system/cpu"

# 4 MB of medium entropy: neither so repetitive that compressing is trivial
# nor so random that there's nothing to compress.
PATTERN = bytes(range(256)) * 16384
# A piece of the above: heavy compression is so slow that with the whole
# 4 MB a single operation would outlast the measurement.
MEDIUM = PATTERN[:65536]

# How long each measurement lasts. Under three seconds the result depends on
# whether the turbo had time to rise; over ten, the whole run gets long
# without changing the figure.
SECONDS = 5.0
QUICK_SECONDS = 2.0
# The limits of what can be asked. Under one second the figure depends on
# whether the turbo had time to rise; past sixty, the run drags on to
# measure what it measured at thirty.
MIN_SECONDS = 1.0
# Half an hour per measurement. With six that's three hours, more than
# anyone needs, but whoever wants to leave the machine cooking all afternoon
# to see if it holds may ask for it.
MAX_SECONDS = 1800.0

# From here on, background load spoils the measurement.
ACCEPTABLE_LOAD = 10.0
# And from here on, the frequency fell enough to say so.
NOTABLE_DROP = 0.90


@dataclass(frozen=True, slots=True)
class Workload:
    """One of the things the processor is asked to do."""

    key: str
    name: str
    explanation: str
    work: Callable[[], object]
    # How many bytes one operation walks. Only declared by the workload whose
    # block isn't the same on every machine: counting «operations per
    # second» over a block sized by each machine's cache rewarded processors
    # with little cache by 42.8 %, since an operation over 64 MB isn't one
    # over 192. A function, not a number, because that size is decided when
    # the benchmark starts.
    bytes_per_op: Optional[Callable[[], int]] = None


# The block must not fit in the cache, and how much that is depends on the
# processor: a 5800X3D has 96 MB of L3 and swallows a 64 MB block whole, so
# there the benchmark would measure the cache and not memory. Sized at twice
# the L3, with a floor for small CPUs and a ceiling so as not to borrow half
# the RAM.
MIN_BLOCK_MB = 64
MAX_BLOCK_MB = 192
_big: Optional[bytes] = None


def _block_size_mb() -> int:
    """In megabytes: twice the last-level cache, between 64 and 192."""
    largest = 0
    for index in range(5):
        raw = _read(f"{SYS_CPU}/cpu0/cache/index{index}/size")
        if not raw:
            continue
        try:
            value = int(raw.rstrip("KMG"))
        except ValueError:
            continue
        if raw.endswith("M"):
            value *= 1024
        elif raw.endswith("G"):
            value *= 1024 * 1024
        largest = max(largest, value // 1024)          # to megabytes
    return max(MIN_BLOCK_MB, min(MAX_BLOCK_MB, largest * 2 or MIN_BLOCK_MB))


def _big_block() -> bytes:
    global _big
    if _big is None:
        megabytes = _block_size_mb()
        _big = PATTERN * (megabytes * 1024 * 1024 // len(PATTERN))
    return _big


def _release_block() -> None:
    """Give back the block's megabytes when the benchmark ends.

    Up to 192 MB, and the whole program lives in about 130: keeping them
    after measuring would raise its footprint for the rest of the session
    because of a benchmark lasting half a minute.
    """
    global _big
    _big = None


WORKLOADS: tuple[Workload, ...] = (
    Workload("compresion", "Compresión",
             "Comprimir es enteros y acceso a memoria, que es lo que hace el "
             "equipo al instalar un juego o abrir un proyecto grande.",
             lambda: zlib.compress(PATTERN, 9)),
    Workload("hash", "Resumen criptográfico",
             "Enteros puros y sin instrucciones especializadas: mide el núcleo, "
             "no una aceleración concreta.",
             lambda: hashlib.sha512(PATTERN).digest()),
    # bzip2 rather than LZMA, which matters: docs/decisiones/cargas-del-benchmark.md.
    Workload("compresion_dura", "Compresión pesada",
             "Lo mismo pero apretando de verdad: bzip2 ordena el bloque entero "
             "antes de comprimirlo, así que hace mucho más trabajo por byte y "
             "separa a un núcleo rápido de uno que solo tiene muchos hermanos.",
             lambda: bz2.compress(MEDIUM, 9)),
    Workload("derivacion", "Derivación de clave",
             "Miles de rondas encadenadas sin poder adelantar trabajo: es lo que "
             "hace un gestor de contraseñas al abrirse, y no lo acelera ninguna "
             "instrucción especial.",
             lambda: hashlib.pbkdf2_hmac("sha512", b"silux", b"benchmark", 12_000)),
    # Once called «Memory», promising to measure the path to RAM. It doesn't:
    # a 4 MB block that fits easily in the cache gives the same as 384 MB,
    # because the CRC computation is the bottleneck, not memory. What is true
    # is that of the five it gains least from threads.
    Workload("verificacion", "Suma de verificación",
             "Recorre un bloque grande calculando una suma de comprobación. El "
             "cuello lo pone el propio cálculo y no la RAM, así que mide enteros "
             "y no el camino hasta la memoria: de eso se encarga la página de "
             "Memoria, que sí lo mide.",
             lambda: zlib.crc32(_big_block()),
             bytes_per_op=lambda: len(_big_block())),
)

# No floating-point workload, on purpose: done in Python without
# dependencies it handles interpreter objects and doesn't release the GIL,
# so it doesn't spread across threads. Why, and what the score lost when
# zlib's workloads left it: docs/decisiones/cargas-del-benchmark.md.


@dataclass(frozen=True, slots=True)
class Measure:
    """A workload's result with a number of threads."""

    load: str
    threads: int
    operations: int
    seconds: float
    # The bytes each operation walked, if the workload declares it.
    bytes_: Optional[int] = None

    @property
    def per_second(self) -> float:
        return self.operations / self.seconds if self.seconds else 0.0

    @property
    def rate(self) -> float:
        """What's scored: bytes per second where the size varies.

        The figure that doesn't depend on how big the block is on this
        machine. Where the workload's input is fixed (the other four) both
        ways are proportional, so it keeps counting operations and declares
        nothing.
        """
        if not self.seconds:
            return 0.0
        if self.bytes_ is None:
            return self.operations / self.seconds
        return self.operations * self.bytes_ / self.seconds


@dataclass(frozen=True, slots=True)
class Conditions:
    """The machine's state while it was being measured."""

    # What another program took while measuring, not before starting. The
    # second question is the one that matters: a run of fifteen seconds per
    # workload lasts two and a half minutes, and `background_load` is taken
    # in three tenths of a second before the first step. With only that,
    # someone opening a browser halfway got «0 % background load» and a low
    # figure with no explanation.
    background_peak: Optional[float] = None
    frequency_avg_hz: Optional[int] = None
    frequency_peak_hz: Optional[int] = None
    frequency_end_hz: Optional[int] = None
    temperature_start_c: Optional[float] = None
    temperature_peak_c: Optional[float] = None
    governor: Optional[str] = None
    energy_preference: Optional[str] = None
    background_load: Optional[float] = None

    @property
    def throttled(self) -> bool:
        """Whether the frequency fell noticeably during the run."""
        if not (self.frequency_peak_hz and self.frequency_end_hz):
            return False
        return self.frequency_end_hz < self.frequency_peak_hz * NOTABLE_DROP


@dataclass(frozen=True, slots=True)
class Result:
    """The measurements, and the context that says whether they hold."""

    measures: tuple[Measure, ...] = ()
    conditions: Conditions = field(default_factory=Conditions)
    warnings: tuple[str, ...] = ()

    def find(self, load: str, threads: int) -> Optional[Measure]:
        return next((m for m in self.measures
                     if m.load == load and m.threads == threads), None)

    def scaling(self, load: str, threads: int) -> Optional[float]:
        """How much performance multiplies with every thread."""
        one = self.find(load, 1)
        many = self.find(load, threads)
        if not (one and many and one.per_second):
            return None
        return round(many.per_second / one.per_second, 1)


def run(quick: bool = False, on_progress: Optional[Callable[[str, float], None]] = None,
        stop: Optional[threading.Event] = None,
        seconds: Optional[float] = None,
        loads: Optional[Sequence[str]] = None) -> Result:
    """Run the whole benchmark. Blocks: call it from another thread.

    `on_progress` gets what is being measured and how far along, 0 to 1.
    `stop` allows cancelling between measurements.
    `seconds` sets how long each measurement lasts; without it, `quick`
    decides.
    `loads` are the keys of the workloads to measure; without it, all. They
    run in the benchmark's order, not the order asked. A result with fewer
    workloads than score gets no score: it is for measuring one thing.

    Lengthening the run doesn't change the figure, it changes the conditions
    it's taken in: at five seconds the turbo has risen and the heatsink isn't
    warm yet, while at thirty the machine has settled, which is what really
    happens while gaming or compiling.
    """
    duration = (max(MIN_SECONDS, min(MAX_SECONDS, float(seconds)))
                if seconds else (QUICK_SECONDS if quick else SECONDS))
    threads = os.cpu_count() or 1
    workloads = WORKLOADS
    if loads is not None:
        if unknown := set(loads) - {workload.key for workload in WORKLOADS}:
            raise ValueError(f"no hay ninguna carga llamada {sorted(unknown)}")
        workloads = tuple(workload for workload in WORKLOADS if workload.key in loads)
    watcher = _Watcher()

    background = _background_load()
    start_temperature = _temperature()

    steps = [(workload, n) for workload in workloads for n in (1, threads)]
    measures: list[Measure] = []
    watcher.start()
    try:
        for index, (workload, n) in enumerate(steps):
            if stop is not None and stop.is_set():
                break
            if on_progress:
                label = f"{workload.name}, {n} {'hilo' if n == 1 else 'hilos'}"
                on_progress(label, index / len(steps))
            measures.append(_measure(workload, n, duration))
    finally:
        watcher.stop()
        _release_block()

    if on_progress:
        on_progress("listo", 1.0)

    conditions = Conditions(
        frequency_avg_hz=watcher.average(),
        frequency_peak_hz=watcher.peak(),
        frequency_end_hz=watcher.final(),
        temperature_start_c=start_temperature,
        temperature_peak_c=watcher.temperature_peak(),
        governor=_read(f"{SYS_CPU}/cpu0/cpufreq/scaling_governor"),
        energy_preference=_read(f"{SYS_CPU}/cpu0/cpufreq/energy_performance_preference"),
        background_load=background,
        background_peak=watcher.stolen_peak(),
    )
    return Result(tuple(measures), conditions, _warnings(conditions))


# -- running -----------------------------------------------------------------

# Some uncounted rounds before each measurement. The first time a workload
# runs in a process gives a different figure from all the later ones, and
# what's paid there is the allocator's, not the processor's. About eighty
# rounds settle it; a hundred and twenty leave a margin.
IDLE_ROUNDS = 120

# A cap in case the workload is very slow on a modest machine: better to
# measure with the start-up half paid than leave the run hanging a minute per
# workload.
IDLE_CAP_S = 2.0


def _warm_up(workload: "Workload", threads: int) -> None:
    """Bring the workload to a steady state so the measurement doesn't pay
    for its start-up.

    With one thread measured first, that start-up always fell on the
    single-thread figure, and the scaling from one to all came out at
    fourteen times on an eight-core processor.
    """
    # Rounds, not seconds: what must be left behind is the workload's
    # start-up, about eighty calls, and that doesn't last the same on a fast
    # desktop as on a ten-year-old laptop: half a second is hundreds of rounds
    # on one and maybe none on the other.
    end = time.perf_counter() + IDLE_CAP_S

    def loop() -> None:
        work = workload.work
        for _round in range(IDLE_ROUNDS):
            if time.perf_counter() > end:
                break
            work()

    workers = [threading.Thread(target=loop, daemon=True)
               for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=IDLE_CAP_S + 5)


def _measure(workload: Workload, threads: int, duration: float) -> Measure:
    """Count how many times the workload fits in the given time.

    By time and not by a fixed amount of work, since what takes a second on
    a fast desktop takes thirty on a ten-year-old laptop.
    """
    _warm_up(workload, threads)
    stop = threading.Event()
    count = [0] * threads

    def loop(index: int) -> None:
        rounds = 0
        work = workload.work
        while not stop.is_set():
            work()
            rounds += 1
        count[index] = rounds

    workers = [threading.Thread(target=loop, args=(i,), daemon=True)
               for i in range(threads)]
    start = time.perf_counter()
    for worker in workers:
        worker.start()
    time.sleep(duration)
    stop.set()
    for worker in workers:
        worker.join(timeout=10)
    elapsed = time.perf_counter() - start

    return Measure(load=workload.key, threads=threads,
                  operations=sum(count), seconds=elapsed,
                  bytes_=workload.bytes_per_op() if workload.bytes_per_op else None)


# The measuring thread isn't pinned to any core: pinning it made the
# single-thread figure worse, not steadier. The figures:
# docs/decisiones/cargas-del-benchmark.md.


# -- context -----------------------------------------------------------------

class _Watcher:
    """Follows frequency and temperature while measuring."""

    def __init__(self) -> None:
        self._frequencies: list[int] = []
        self._temperatures: list[float] = []
        self._stolen: list[float] = []
        self._cpu_before = _jiffies()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Only the highest frequency at the moment counts: the mean of
            # every core, half of them asleep, doesn't say what the work ran at.
            current = [_read_int(f"{SYS_CPU}/cpu{i}/cpufreq/scaling_cur_freq")
                     for i in range(os.cpu_count() or 1)]
            valid = [p for p in current if p]
            if valid:
                self._frequencies.append(max(valid) * 1000)
            if (degrees := _temperature()) is not None:
                self._temperatures.append(degrees)
            if (stolen := self._stolen_now()) is not None:
                self._stolen.append(stolen)
            self._stop_event.wait(0.25)

    def _stolen_now(self) -> Optional[float]:
        """How much of the machine another program takes, right now.

        `/proc/stat` alone won't do while the run goes: the benchmark
        occupies the whole machine and everything would read a hundred
        percent. What's sought is the difference, busy minus what this very
        process uses, which is what's taking room from the measurement.
        """
        now = _jiffies()
        before, self._cpu_before = self._cpu_before, now
        if now is None or before is None:
            return None
        total, idle, own = now
        total_before, idle_before, own_before = before
        elapsed = total - total_before
        if elapsed <= 0:
            return None
        busy = elapsed - (idle - idle_before)
        stolen = busy - (own - own_before)
        # It can come out negative by a hundredth: the two files aren't read
        # at the same instant. Zero is the answer, not an error.
        return max(0.0, stolen / elapsed * 100)

    def average(self) -> Optional[int]:
        return int(sum(self._frequencies) / len(self._frequencies)) if self._frequencies else None

    def peak(self) -> Optional[int]:
        return max(self._frequencies) if self._frequencies else None

    def final(self) -> Optional[int]:
        """The last stretch's mean, to see whether it ended lower than it began."""
        if len(self._frequencies) < 8:
            return self._frequencies[-1] if self._frequencies else None
        tail = self._frequencies[-len(self._frequencies) // 4:]
        return int(sum(tail) / len(tail))

    def temperature_peak(self) -> Optional[float]:
        return max(self._temperatures) if self._temperatures else None

    def stolen_peak(self) -> Optional[float]:
        """The most another program took from it during the run.

        The peak and not the mean: what spoils a measurement is something
        waking up halfway, and averaged over two and a half minutes that
        dilutes into nothing.
        """
        return round(max(self._stolen), 1) if self._stolen else None


def _warnings(conditions: Conditions) -> tuple[str, ...]:
    """What to know before comparing this figure with another."""
    warnings = []
    if conditions.background_load and conditions.background_load > ACCEPTABLE_LOAD:
        warnings.append(
            f"Había un {conditions.background_load:.0f} % de carga de fondo al "
            "empezar. El resultado no es comparable con el de una máquina en "
            "reposo."
        )
    # The above looks at the machine before starting; this, at what happened
    # while measuring. The second is what spoils a run: whoever starts it and
    # goes off to do something else, or has an update running unknowingly,
    # got «0 % background load» and a low figure explained nowhere.
    if (conditions.background_peak
            and conditions.background_peak > ACCEPTABLE_LOAD):
        warnings.append(
            f"Otro programa llegó a llevarse el "
            f"{conditions.background_peak:.0f} % de la máquina mientras se "
            "medía. La cifra sale más baja de lo que da este equipo en reposo."
        )
    if conditions.governor and conditions.governor not in ("performance",):
        warnings.append(
            f"El gobernador de energía estaba en «{conditions.governor}». "
            "En «performance» la cifra sería más alta."
        )
    if conditions.throttled:
        peak = conditions.frequency_peak_hz or 0
        final = conditions.frequency_end_hz or 0
        warnings.append(
            f"La frecuencia bajó de {peak / 1e9:.2f} a {final / 1e9:.2f} GHz "
            "durante la prueba: el procesador no pudo sostener su máximo."
        )
    return tuple(warnings)


def _jiffies() -> Optional[tuple[int, int, int]]:
    """The system's totals and idle time, and what this process has used.

    All three at once and from the same instant, since what's sought is the
    difference between them.
    """
    try:
        with open("/proc/stat", encoding="utf-8") as handle:
            numbers = [int(x) for x in handle.readline().split()[1:8]]
        with open(f"/proc/{os.getpid()}/stat", encoding="utf-8") as handle:
            fields = handle.read().rsplit(")", 1)[1].split()
        # utime + stime: the CPU this process has used.
        own = int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None
    if len(numbers) < 5:
        return None
    return sum(numbers), numbers[3] + numbers[4], own


def _background_load() -> Optional[float]:
    """What share of the machine is busy before starting."""
    def snapshot() -> Optional[tuple[int, int]]:
        try:
            with open("/proc/stat", encoding="utf-8") as handle:
                fields = handle.readline().split()
        except OSError:
            return None
        if len(fields) < 5:
            return None
        numbers = [int(c) for c in fields[1:8] if c.isdigit()]
        return sum(numbers), numbers[3]        # total, idle

    before = snapshot()
    if before is None:
        return None
    time.sleep(0.3)
    after = snapshot()
    if after is None or after[0] == before[0]:
        return None
    busy = (after[0] - before[0]) - (after[1] - before[1])
    return round(busy / (after[0] - before[0]) * 100, 1)


def _temperature() -> Optional[float]:
    """The processor's, from the first chip that publishes it."""
    for index in range(16):
        name = _read(f"/sys/class/hwmon/hwmon{index}/name")
        if name in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
            millidegrees = _read_int(f"/sys/class/hwmon/hwmon{index}/temp1_input")
            if millidegrees:
                return round(millidegrees / 1000, 1)
    return None


def _read(path: str) -> Optional[str]:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    raw = _read(path)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None
