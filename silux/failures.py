"""Failures of Silux's own code, kept with their traceback for the report.

A provider that breaks gets a note on its page; a failure no page can show
(a reading between samples) is not swallowed either. Each collector keeps
its own, so what one test breaks does not show up in another's report.
"""

from __future__ import annotations

import sys
import threading
import traceback

from .model import Failure

# The newest ones. The same failure again only counts: one that repeats every
# second does not grow the memory.
LIMIT = 20


class Failures:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[tuple[str, str], Failure] = {}

    def record(self, where: str, exc: BaseException) -> Failure:
        error = f"{type(exc).__name__}: {exc}"
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
        with self._lock:
            before = self._by_key.pop((where, error), None)
            failure = Failure(where=where, error=error, trace=trace,
                              count=before.count + 1 if before else 1)
            self._by_key[(where, error)] = failure
            while len(self._by_key) > LIMIT:
                del self._by_key[next(iter(self._by_key))]
        return failure

    def recent(self) -> tuple[Failure, ...]:
        with self._lock:
            return tuple(self._by_key.values())


def _where(trace, prefix: str) -> str:
    """«ui.<function>»: where it broke, the innermost of Silux's own frames,
    or the innermost one if none is Silux's."""
    ours = last = None
    while trace is not None:
        code = trace.tb_frame.f_code
        last = code.co_name
        if "/silux/" in code.co_filename.replace("\\", "/"):
            ours = code.co_name
        trace = trace.tb_next
    name = ours or last
    return f"{prefix}.{name}" if name else prefix


def install_hooks(failures: Failures) -> None:
    """What breaks in the interface or in a thread of ours goes to `failures`
    for the report, and still to the terminal.

    A slot, a paint or a timer that raises doesn't stop Qt: PySide hands the
    exception to `sys.excepthook` and goes on, and threads to
    `threading.excepthook`. An interrupt is not a failure.
    """
    previous, previous_thread = sys.excepthook, threading.excepthook

    def hook(kind, value, trace) -> None:
        if isinstance(value, Exception):
            failures.record(_where(trace, "ui"), value)
        previous(kind, value, trace)

    def thread_hook(args) -> None:
        if isinstance(args.exc_value, Exception):
            name = args.thread.name if args.thread is not None else "?"
            failures.record(f"thread {name}", args.exc_value)
        previous_thread(args)

    sys.excepthook = hook
    threading.excepthook = thread_hook
