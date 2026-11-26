"""Run a test in a child process of this same Python and read what it says.

A test that takes memory or writes to a disk runs apart: what it takes is
freed when the child goes, and a crash in native code takes the child and
not the window. The child says how far it has got on its standard output,
one JSON object per line, the last one with its `result`; killing it is how
a test is cancelled.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import threading
import time
from typing import Callable, Optional


@dataclasses.dataclass(frozen=True)
class Outcome:
    # What the child gave as its result; None if it gave none.
    answer: Optional[dict] = None
    cancelled: bool = False
    # Why it gave none: it couldn't be started, or what it left on its
    # standard error and how it ended.
    not_started: Optional[str] = None
    detail: str = ""


def run(module: str, argument: str,
        on_message: Optional[Callable[[dict], None]] = None,
        stop: Optional[threading.Event] = None, timeout_s: float = 180) -> Outcome:
    """Run `python -m module argument` and wait for it. Call from a thread.

    `on_message` gets every message that isn't the result; setting `stop`,
    or `timeout_s` going by, kills the child.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", module, argument],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    except OSError as error:
        return Outcome(not_started=str(error))

    finished = threading.Event()

    def watch() -> None:
        deadline = time.monotonic() + timeout_s
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
            if not isinstance(message, dict):
                continue
            if "result" in message:
                answer = message["result"]
            elif on_message is not None:
                on_message(message)
        errors = child.stderr.read()
        child.wait()
    finally:
        finished.set()
        watcher.join(timeout=2)
        child.stdout.close()
        child.stderr.close()
    if stop is not None and stop.is_set():
        return Outcome(cancelled=True)
    if answer is None:
        return Outcome(detail=errors.strip()[-2000:] or f"exit {child.returncode}")
    return Outcome(answer=answer)


def die_with_parent() -> None:
    """In the child: ask the kernel to kill this process when the one that
    started it ends, whatever the window died of."""
    import ctypes
    import signal

    parent = os.getppid()
    try:
        ctypes.CDLL(None, use_errno=True).prctl(1, int(signal.SIGKILL), 0, 0, 0)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        return
    if os.getppid() != parent:
        # It ended before the kernel was asked.
        os._exit(0)
