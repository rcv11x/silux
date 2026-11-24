"""Silux's native benchmarks: memory latency and bandwidth, and disk speed.
Linux only."""

from os import PathLike
from typing import Optional, TypedDict, Union

class SiluxBenchError(Exception):
    """`args` is `(key, message)`; the key is what code matches on, and
    `details` holds the error's figures by name (`errno`, `needed`, `free`,
    `call`, `bytes`…), those it has."""

    details: dict[str, Union[int, str]]

class Cancelled(SiluxBenchError): ...

class Control:
    """Stop a measurement from another thread, and see how far it went."""

    def __init__(self) -> None: ...
    def cancel(self) -> None: ...
    @property
    def cancelled(self) -> bool: ...
    def progress(self) -> tuple[int, int]: ...

class Point(TypedDict):
    bytes: int
    median_ns: float
    min_ns: float
    max_ns: float
    spread: float
    noisy: bool
    repetitions: int
    mhz: Optional[float]
    mhz_min: Optional[float]
    hops: int
    retries: int

class Curve(TypedDict):
    points: list[Point]
    pages: str
    rss_bytes: Optional[int]
    huge_bytes: Optional[int]
    cpu: Optional[int]
    frequency_source: Optional[str]
    clock_resolution_ns: float
    clock_read_ns: float

def latency_curve(
    sizes: list[int],
    *,
    huge_pages: bool = True,
    cpu: Optional[int] = None,
    repetitions: int = 7,
    seed: int = ...,
    control: Optional[Control] = None,
) -> Curve: ...
class Bandwidth(TypedDict):
    isa: str
    threads: int
    passes: int
    median_gbps: float
    min_gbps: float
    max_gbps: float
    spread: float
    noisy: bool
    repetitions: int
    mhz: Optional[float]
    mhz_min: Optional[float]
    frequency_source: Optional[str]
    retries: int

def memory_bandwidth(
    operation: str,
    *,
    bytes: int,
    cpus: list[int],
    isa: Optional[str] = None,
    non_temporal: bool = False,
    huge_pages: bool = True,
    repetitions: int = 7,
    control: Optional[Control] = None,
) -> Bandwidth: ...
def instruction_sets() -> list[str]: ...
def allowed_cpus() -> list[int]: ...

class Lap(TypedDict):
    engine: str
    threads: int
    bytes: int
    requests: int
    elapsed_ns: int
    bytes_per_second: float
    requests_per_second: float
    latency_mean_ns: Optional[float]
    latency_min_ns: Optional[int]
    latency_max_ns: Optional[int]
    latency_p50_ns: Optional[int]
    latency_p99_ns: Optional[int]
    latency_p999_ns: Optional[int]
    # How much had moved in all, and how far into the lap: `(ns, bytes)`.
    samples: list[tuple[int, int]]

class DiskFile:
    """The file a disk test reads and writes: made in `folder` without a
    name, so that it is gone when this object is, whatever happens to the
    process. Its contents are still to be written (`fill`)."""

    def __init__(self, folder: Union[str, PathLike[str]], *, bytes: int) -> None: ...
    def fill(self, *, seed: int = ..., control: Optional[Control] = None) -> None: ...
    def lap(
        self,
        pattern: str,
        direction: str,
        *,
        block: int,
        depth: int,
        seconds: float,
        engine: str = "uring",
        seed: int = 1,
        control: Optional[Control] = None,
    ) -> Lap: ...
    def cached_bytes(self) -> int: ...
    def fileno(self) -> int: ...
    def close(self) -> None: ...
    @property
    def bytes(self) -> int: ...
    @property
    def creation(self) -> str: ...
    @property
    def no_cow(self) -> Optional[bool]: ...
    @property
    def filesystem(self) -> int: ...
    @property
    def align(self) -> tuple[int, int, bool]: ...

def uring_error() -> Optional[int]:
    """The errno the kernel answers to making an io_uring ring, or None
    where there is one."""
