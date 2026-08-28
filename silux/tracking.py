"""Acumulación de mínimos, máximos y medias por sensor.

Es la función que define a un monitor de hardware: el valor actual lo da
cualquiera, pero saber a cuánto llegó la temperatura mientras jugabas (o si
un ventilador se paró un instante) exige recordar. Se guarda aparte del
modelo a propósito: el snapshot es una foto, y esto es la película.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Cuántas muestras guarda la curva de cada sensor. Sesenta a un segundo es el
# último minuto, que es el tramo en el que se ve si algo está subiendo. Cien
# sensores por sesenta muestras son unos 200 KB: dentro del presupuesto, y
# ampliarlo mucho más no añade lectura, solo aplasta la curva.
HISTORIAL = 60


@dataclass
class Extremes:
    minimum: float
    maximum: float
    total: float = 0.0
    samples: int = 0
    last: float = 0.0
    # La serie reciente. Los extremos dicen dónde estuvo el sensor; esto dice
    # hacia dónde va, que es lo que uno mira cuando algo empieza a calentarse.
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORIAL))

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
            entry = Extremes(minimum=value, maximum=value,
                             total=value, samples=1, last=value)
            entry.history.append(value)
            self._values[key] = entry
            return
        entry.minimum = min(entry.minimum, value)
        entry.maximum = max(entry.maximum, value)
        entry.total += value
        entry.samples += 1
        entry.last = value
        entry.history.append(value)

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
