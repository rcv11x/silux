"""Write what the session measures to a CSV file.

A monitor left open during a game sees what the user doesn't: the minute
the temperature started to climb, whether the fan reacted late, how long
the peak really lasted. All of that lives in memory and is lost on exit.

It is written as it goes, not at the end. A session worth recording is
long, and holding it all in memory to write it on exit would break the
program's memory budget. And if something hangs halfway, which is exactly
when the log is needed, what was written so far is still there.

CSV on purpose: any spreadsheet opens it as is. One row per sample and one
column per sensor is the shape a spreadsheet charts on its own.
"""

from __future__ import annotations

import csv
import os
import pathlib
import time
from typing import Optional, TextIO

from .model import UNITS, Snapshot

# The wall clock lines the log up with what the user was doing; the
# relative one lets the chart be read without subtracting times.
FIXED_HEADER = ("hora", "segundos")


def folder() -> pathlib.Path:
    base = os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "silux" / "registros"


def suggested_name() -> str:
    return time.strftime("silux-%Y%m%d-%H%M.csv")


class SensorLog:
    """Writes a CSV for as long as the session lasts.

    The columns are fixed by the first sample: a sensor that appears halfway
    (something plugged in, a module loaded) is left out rather than shifting
    every earlier row. One that disappears leaves its column empty, which
    tells «no reading» apart from «it was zero».
    """

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self._file: Optional[TextIO] = None
        self._csv = None
        self._keys: tuple[str, ...] = ()
        self._start_ns: Optional[int] = None
        self._rows = 0

    # -- lifecycle ----------------------------------------------------------

    def open(self, snapshot: Snapshot) -> None:
        """Create the file and write the header from this snapshot."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # `newline=""` is what the csv module asks for, so line breaks aren't
        # doubled on systems that write them as two characters.
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._file)
        self._keys = tuple(s.key for s in snapshot.sensors)
        self._start_ns = snapshot.monotonic_ns

        # The header has the readable name and the unit, not the internal key:
        # whoever opens this in a spreadsheet doesn't know what
        # «hwmon/nct6798/temp3_input» is.
        labels = []
        for sensor in snapshot.sensors:
            name = f"{sensor.device} · {sensor.label}"
            unit = UNITS.get(sensor.kind, "")
            labels.append(f"{name} ({unit})" if unit else name)
        self._csv.writerow([*FIXED_HEADER, *labels])
        self._file.flush()

    def write(self, snapshot: Snapshot) -> None:
        """One row. Ignored if the log isn't open."""
        if self._csv is None or self._file is None:
            return
        values = {s.key: s.value for s in snapshot.sensors}
        elapsed = (snapshot.monotonic_ns - (self._start_ns or 0)) / 1e9
        self._csv.writerow([
            time.strftime("%H:%M:%S"),
            f"{elapsed:.1f}",
            # A sensor that disappeared leaves the cell empty, not a zero: a
            # spreadsheet plots the zero and skips the gap, which is exactly
            # the difference to see.
            *[_cell(values.get(key)) for key in self._keys],
        ])
        self._rows += 1
        # Flushed on every row. At one sample a second it costs little, and it
        # keeps the file useful if the machine hangs, which is the very case a
        # log is started for.
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
        self._file = None
        self._csv = None

    # -- state --------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._file is not None

    @property
    def rows(self) -> int:
        return self._rows

    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


def _cell(value: Optional[float]) -> str:
    if value is None:
        return ""
    # A decimal point and no thousands separator: every spreadsheet reads
    # that as a number without picking a region on import.
    return f"{value:g}"
