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
    return pathlib.Path(base) / "silux"


def config_path() -> pathlib.Path:
    return config_dir() / "settings.json"


# Los nombres válidos de acento. Se repiten aquí en vez de importarlos de
# `ui.theme` porque los ajustes no deben depender de que haya interfaz: el CLI
# los lee igual y no carga Qt.
ACCENT_NAMES = ("naranja", "azul", "verde", "morado", "rojo", "cian")


@dataclass(frozen=True)
class Preferences:
    interval_s: float = 1.0
    theme: str = "system"                 # system | light | dark
    temperature_unit: str = "c"           # c | f
    density: str = "normal"               # spacious | normal | compact
    # «grande» de salida: en un monitor de 27" a 1440p el tamaño base se
    # lee pequeño, y quien lo quiera más apretado lo baja en dos clics.
    font_scale: str = "grande"            # normal | grande | mayor | máximo
    accent: str = "azul"                  # ver ui/theme.ACCENTS
    # En bytes por segundo o en bits por segundo. Los fabricantes miden los
    # enlaces en bits y los programas de descarga en bytes, y son ocho veces
    # distintos: quien compara con un test de velocidad quiere bits.
    network_unit: str = "bytes"           # bytes | bits
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
            font_scale=(self.font_scale
                        if self.font_scale in ("normal", "grande", "mayor", "máximo")
                        else "grande"),
            accent=self.accent if self.accent in ACCENT_NAMES else "azul",
            network_unit="bits" if self.network_unit == "bits" else "bytes",
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
