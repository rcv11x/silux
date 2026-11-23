"""Silux's native memory benchmark. Linux only."""

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
def allowed_cpus() -> list[int]: ...
