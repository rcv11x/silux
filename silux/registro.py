"""Guardar en un CSV lo que va midiendo la sesión.

Un monitor abierto durante una partida ve cosas que el usuario no: en qué
minuto empezó a subir la temperatura, si el ventilador reaccionó tarde, cuánto
duró de verdad el pico. Todo eso vive en la memoria del programa y se pierde
al cerrarlo.

Se escribe sobre la marcha y no al final, por dos motivos. Una sesión que se
quiere registrar es larga —eso es lo que la hace interesante— y acumularla
entera en memoria para volcarla al cerrar contradice el presupuesto que tiene
este programa. Y si algo se cuelga a mitad, que es justo cuando más falta hace
el registro, lo escrito hasta ese momento sigue ahí.

El formato es CSV a propósito: se abre en cualquier hoja de cálculo sin
explicar nada a nadie. Una fila por muestreo y una columna por sensor, que es
la forma en la que una hoja de cálculo sabe dibujar una gráfica sola.
"""

from __future__ import annotations

import csv
import os
import pathlib
import time
from typing import Optional, TextIO

from .model import UNITS, Snapshot

# Las columnas fijas que van delante de los sensores. El reloj de pared sirve
# para cruzar el registro con lo que uno estaba haciendo; el relativo, para
# leer la gráfica sin restar horas.
FIXED_HEADER = ("hora", "segundos")


def folder() -> pathlib.Path:
    base = os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "silux" / "registros"


def suggested_name() -> str:
    return time.strftime("silux-%Y%m%d-%H%M.csv")


class SensorLog:
    """Escribe un CSV mientras dura la sesión.

    Las columnas se fijan con el primer muestreo y no cambian: un sensor que
    aparece a mitad —al enchufar algo, al cargar un módulo— se queda fuera en
    vez de descolocar todas las filas anteriores. Y uno que desaparece deja su
    columna vacía, que es la diferencia entre «no había dato» y «valía cero».
    """

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self._file: Optional[TextIO] = None
        self._csv = None
        self._keys: tuple[str, ...] = ()
        self._start_ns: Optional[int] = None
        self._rows = 0

    # -- ciclo de vida ------------------------------------------------------

    def open(self, snapshot: Snapshot) -> None:
        """Crea el archivo y escribe la cabecera a partir de esta foto."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # `newline=""` es lo que pide el módulo csv para no doblar los saltos
        # de línea en los sistemas que los escriben con dos caracteres.
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._file)
        self._keys = tuple(s.key for s in snapshot.sensors)
        self._start_ns = snapshot.monotonic_ns

        # La cabecera lleva el nombre legible y la unidad, no la clave interna:
        # quien abre esto en una hoja de cálculo no sabe qué es
        # «hwmon/nct6798/temp3_input».
        labels = []
        for sensor in snapshot.sensors:
            name = f"{sensor.device} · {sensor.label}"
            unit = UNITS.get(sensor.kind, "")
            labels.append(f"{name} ({unit})" if unit else name)
        self._csv.writerow([*FIXED_HEADER, *labels])
        self._file.flush()

    def write(self, snapshot: Snapshot) -> None:
        """Una fila. Se ignora si el registro no está abierto."""
        if self._csv is None or self._file is None:
            return
        values = {s.key: s.value for s in snapshot.sensors}
        elapsed = (snapshot.monotonic_ns - (self._start_ns or 0)) / 1e9
        self._csv.writerow([
            time.strftime("%H:%M:%S"),
            f"{elapsed:.1f}",
            # Un sensor que ha desaparecido deja la celda vacía y no un cero:
            # una hoja de cálculo dibuja el cero y salta el hueco, que es
            # exactamente la diferencia que hay que ver.
            *[_cell(values.get(key)) for key in self._keys],
        ])
        self._rows += 1
        # Se vacía el buffer en cada fila. Cuesta poco a un muestreo por
        # segundo y es lo que hace que el archivo sirva si el equipo se cuelga,
        # que es justo el caso para el que se enciende un registro.
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
        self._file = None
        self._csv = None

    # -- estado -------------------------------------------------------------

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
    # Punto decimal y sin separador de miles: es lo que toda hoja de cálculo
    # entiende como número sin tener que elegir región al importar.
    return f"{value:g}"
