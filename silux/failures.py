"""Failures of Silux's own code, kept with their traceback for the report.

A provider that breaks gets a note on its page; a failure no page can show
(a reading between samples) is not swallowed either. Each collector keeps
its own, so what one test breaks does not show up in another's report.
"""

from __future__ import annotations

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
