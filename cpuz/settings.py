"""Preferencias del usuario, guardadas en disco.

Deliberadamente pequeño: un dataclass, un fichero JSON en la ruta que manda
la especificación XDG, y nada más. Si el fichero está corrupto o es de una
versión futura, se ignora y se usan los valores por defecto en vez de
reventar al arrancar.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict, dataclass, fields, replace
from typing import Any


def config_dir() -> pathlib.Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (pathlib.Path.home() / ".config")
    return pathlib.Path(base) / "cpuz"


def config_path() -> pathlib.Path:
    return config_dir() / "settings.json"


@dataclass(frozen=True)
class Preferences:
    interval_s: float = 1.0
    theme: str = "system"                 # system | light | dark
    temperature_unit: str = "c"           # c | f
    density: str = "normal"               # spacious | normal | compact
    show_all_features: bool = False
    # Ancho de la columna «Sensor» del árbol. 0 = calcularlo del contenido.
    # Ancho de cada columna del árbol de sensores. Vacío = calcularlo.
    sensor_columns: tuple[int, ...] = ()
    window_width: int = 900
    window_height: int = 680

    # -- validación ---------------------------------------------------------

    def normalized(self) -> "Preferences":
        return replace(
            self,
            interval_s=min(10.0, max(0.2, float(self.interval_s))),
            theme=self.theme if self.theme in ("system", "light", "dark") else "system",
            temperature_unit="f" if self.temperature_unit == "f" else "c",
            density=self.density if self.density in ("spacious", "normal", "compact") else "normal",
            show_all_features=bool(self.show_all_features),
            sensor_columns=tuple(min(900, max(30, int(w))) for w in (self.sensor_columns or ())),
            # El recorte aquí es solo un saneado grueso; el suelo de verdad lo
            # pone la ventana, que sabe qué densidad está activa.
            window_width=min(3840, max(380, int(self.window_width))),
            window_height=min(2160, max(320, int(self.window_height))),
        )

    @property
    def fahrenheit(self) -> bool:
        return self.temperature_unit == "f"

    @property
    def interval_ms(self) -> int:
        return int(round(self.interval_s * 1000))


def load() -> Preferences:
    try:
        raw: dict[str, Any] = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Preferences()
    known = {f.name for f in fields(Preferences)}
    try:
        return Preferences(**{k: v for k, v in raw.items() if k in known}).normalized()
    except (TypeError, ValueError):
        return Preferences()


def save(preferences: Preferences) -> bool:
    """Guarda y devuelve si lo consiguió. No es crítico: si falla, se sigue."""
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        # Escritura atómica: un corte de luz no debe dejar un JSON a medias.
        temporary = config_path().with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(preferences.normalized()), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(config_path())
        return True
    except OSError:
        return False
