"""Uso de CPU a partir de /proc/stat.

El uso es una derivada: no hay ningún fichero que diga "35 %", solo
contadores acumulados de jiffies. Hace falta guardar la lectura anterior y
dividir la diferencia, así que este proveedor tiene estado — el único que lo
tiene, junto con el de energía.
"""

from __future__ import annotations

from typing import Optional

from ..model import Need
from .base import Draft, Provider

# user nice system idle iowait irq softirq steal …
_IDLE_FIELDS = (3, 4)          # idle, iowait


class CpuUsage(Provider):
    name = "procfs-usage"
    provides = "cpu.usage_percent"

    def __init__(self) -> None:
        self._previous: dict[str, tuple[int, int]] = {}

    def available(self) -> bool:
        try:
            with open("/proc/stat"):
                return True
        except OSError:
            return False

    def unavailable_reason(self):
        if self.available():
            return None
        return ("cpu.usage_percent", Need.PLATFORM,
                "No hay /proc/stat en este sistema.", "")

    def collect(self, draft: Draft) -> None:
        current = self._read()
        if not current:
            return

        total = self._delta("cpu", current)
        if total is not None:
            draft.cpu_extra["usage_percent"] = total

        for index, cpu in draft.logical.items():
            value = self._delta(f"cpu{index}", current)
            if value is not None:
                cpu["usage_percent"] = value

        if load := self._load_average():
            draft.cpu_extra["load_average"] = load

        self._previous = current

    @staticmethod
    def _load_average() -> tuple[float, ...]:
        """Carga media del sistema a 1, 5 y 15 minutos.

        Complementa al porcentaje de uso: este dice cuánto se está usando la
        CPU ahora, y la carga cuántos procesos había esperando de media. Con
        12 hilos, una carga de 12 significa saturación completa.
        """
        try:
            with open("/proc/loadavg", encoding="ascii") as fh:
                return tuple(float(v) for v in fh.read().split()[:3])
        except (OSError, ValueError):
            return ()

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _read() -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        try:
            with open("/proc/stat", encoding="ascii") as fh:
                for line in fh:
                    if not line.startswith("cpu"):
                        break
                    parts = line.split()
                    values = [int(v) for v in parts[1:]]
                    idle = sum(values[i] for i in _IDLE_FIELDS if i < len(values))
                    out[parts[0]] = (sum(values), idle)
        except (OSError, ValueError):
            return {}
        return out

    def _delta(self, key: str, current: dict[str, tuple[int, int]]) -> Optional[float]:
        before = self._previous.get(key)
        if before is None or key not in current:
            return None
        total_delta = current[key][0] - before[0]
        idle_delta = current[key][1] - before[1]
        if total_delta <= 0:
            return None
        return round(100.0 * (total_delta - idle_delta) / total_delta, 1)
