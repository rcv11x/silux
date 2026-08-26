"""Acumulación de mínimos, máximos y medias por sensor.

Es la función que define a un monitor de hardware: el valor actual lo da
cualquiera, pero saber a cuánto llegó la temperatura mientras jugabas (o si
un ventilador se paró un instante) exige recordar. Se guarda aparte del
modelo a propósito: el snapshot es una foto, y esto es la película.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class Extremes:
    minimum: float
    maximum: float
    total: float = 0.0
    samples: int = 0
    last: float = 0.0

    @property
    def average(self) -> float:
        return self.total / self.samples if self.samples else self.last


@dataclass
class Tracker:
    """Sigue una colección de valores identificados por clave."""

    _values: dict[str, Extremes] = field(default_factory=dict)

    def update(self, key: str, value: Optional[float]) -> None:
        if value is None:
            return
        entry = self._values.get(key)
        if entry is None:
            self._values[key] = Extremes(minimum=value, maximum=value,
                                         total=value, samples=1, last=value)
            return
        entry.minimum = min(entry.minimum, value)
        entry.maximum = max(entry.maximum, value)
        entry.total += value
        entry.samples += 1
        entry.last = value

    def update_many(self, items: Iterable[tuple[str, Optional[float]]]) -> None:
        for key, value in items:
            self.update(key, value)

    def get(self, key: str) -> Optional[Extremes]:
        return self._values.get(key)

    def reset(self, key: Optional[str] = None) -> None:
        """Pone a cero un sensor, o todos. Equivale al botón de reiniciar
        mínimos y máximos que trae cualquier monitor de hardware."""
        if key is None:
            self._values.clear()
        else:
            self._values.pop(key, None)

    def __len__(self) -> int:
        return len(self._values)
