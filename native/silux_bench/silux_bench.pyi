"""Silux's native memory benchmark: latency by block size and bandwidth.
Linux only."""

from typing import Optional, TypedDict

class SiluxBenchError(Exception):
    """`args` is `(key, message)`; the key is what code matches on."""

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
    hops: int
    retries: int

class Curve(TypedDict):
    points: list[Point]
    pages: str
    rss_bytes: Optional[int]
    huge_bytes: Optional[int]
    cpu: Optional[int]
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
