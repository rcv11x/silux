"""La tabla de telemetría que el firmware de una Radeon publica cada momento.

`gpu_metrics` es un binario que el driver deja en sysfs con lo que le cuenta el
microcontrolador de la tarjeta. Trae cosas que no están en ningún otro sitio:

- **Por qué la tarjeta se está frenando**, si es que lo hace. Es la pregunta que
  se hace cualquiera cuando un juego va a menos de lo que debería, y hasta ahora
  solo se podía responder a ojo mirando la temperatura.
- **Las temperaturas de los reguladores de voltaje**, que hwmon no expone.
- **El reloj efectivo de la memoria**, que es el que se anuncia en las fichas:
  una GDDR6 a 1258 MHz de reloj de comando trabaja a 2505 efectivos.

El formato lleva versión en la cabecera y ha cambiado varias veces, no siempre
añadiendo al final. Por eso cada versión tiene aquí su tabla de posiciones
explícita: leer una v1.4 con las posiciones de una v1.3 no da error, da números
creíbles y equivocados, que es peor. Una versión que no esté en la tabla se
deja pasar con una nota en vez de adivinar.
"""

from __future__ import annotations

import pathlib
import struct
from dataclasses import dataclass, field
from typing import Optional

CABECERA = "<HBB"          # tamaño, revisión de formato, revisión de contenido

# Por qué se frena la tarjeta. Son los bits de `indep_throttle_status`, que AMD
# definió justamente para que no dependieran del modelo de chip.
MOTIVOS = {
    0: "límite de potencia (PPT0)",
    1: "límite de potencia (PPT1)",
    2: "límite de potencia (PPT2)",
    3: "límite de potencia (PPT3)",
    4: "corriente del núcleo gráfico",
    5: "corriente del SoC",
    6: "corriente de la memoria",
    7: "temperatura de la GPU",
    8: "temperatura de la memoria",
    9: "temperatura del borde",
    10: "temperatura del punto caliente",
    11: "temperatura del SoC",
    12: "temperatura del regulador gráfico",
    13: "temperatura del regulador del SoC",
    14: "temperatura del regulador de memoria",
    15: "temperatura del regulador de memoria",
    16: "aviso de la fuente de alimentación (APCC)",
    17: "gestión de potencia de la plataforma",
    18: "fiabilidad del silicio (FIT)",
    19: "regulador de voltaje caliente",
    20: "regulador de voltaje caliente",
}

# Las posiciones dentro de cada versión de la tabla. Las v1.0 a v1.3 comparten
# toda la primera mitad (cada una añadió campos detrás) así que se construyen
# una a partir de la anterior; las v1.4 en adelante reordenaron y no valen.
_V1_0 = {
    "temp_edge": ("H", 4), "temp_hotspot": ("H", 6), "temp_mem": ("H", 8),
    "temp_vr_gfx": ("H", 10), "temp_vr_soc": ("H", 12), "temp_vr_mem": ("H", 14),
    "gfx_activity": ("H", 16), "memory_activity": ("H", 18), "video_activity": ("H", 20),
    "socket_power": ("H", 22),
    "gfx_clock_average": ("H", 40), "soc_clock_average": ("H", 42),
    "memory_clock_average": ("H", 44),
    "gfx_clock": ("H", 54), "soc_clock": ("H", 56), "memory_clock": ("H", 58),
    "throttle_status": ("I", 68),
    "fan_rpm": ("H", 72), "link_width": ("H", 74), "link_speed": ("H", 76),
}
_V1_3 = _V1_0 | {
    "voltage_soc": ("H", 104), "voltage_gfx": ("H", 106), "voltage_mem": ("H", 108),
    "throttle_independent": ("Q", 112),
}

VERSIONES = {
    (1, 0): _V1_0,
    (1, 1): _V1_0,
    (1, 2): _V1_0,
    (1, 3): _V1_3,
}

# Un campo a todo unos es «este chip no lo mide». Hay que descartarlo antes de
# enseñar 65 535 grados o un reloj de cuatro mil millones.
SIN_DATO = {"H": 0xFFFF, "I": 0xFFFFFFFF, "Q": 0xFFFFFFFFFFFFFFFF}


@dataclass(frozen=True, slots=True)
class Metrics:
    """Una foto de la telemetría, ya en unidades del modelo."""

    version: str = ""
    temp_edge_c: Optional[float] = None
    temp_hotspot_c: Optional[float] = None
    temp_memory_c: Optional[float] = None
    temp_vr_gfx_c: Optional[float] = None
    temp_vr_soc_c: Optional[float] = None
    temp_vr_mem_c: Optional[float] = None
    gfx_activity_percent: Optional[float] = None
    memory_activity_percent: Optional[float] = None
    video_activity_percent: Optional[float] = None
    socket_power_w: Optional[float] = None
    gfx_clock_hz: Optional[int] = None
    gfx_clock_average_hz: Optional[int] = None
    soc_clock_hz: Optional[int] = None
    memory_clock_hz: Optional[int] = None
    # El reloj efectivo de la memoria: el que sale en las fichas técnicas.
    memory_clock_effective_hz: Optional[int] = None
    fan_rpm: Optional[int] = None
    link_width: Optional[int] = None
    link_speed_gts: Optional[float] = None
    voltage_gfx_v: Optional[float] = None
    voltage_soc_v: Optional[float] = None
    voltage_memory_v: Optional[float] = None
    throttle_reasons: tuple[str, ...] = ()
    throttled: Optional[bool] = None


def parse(raw: bytes) -> Optional[Metrics]:
    """Devuelve None si la tabla está vacía o es de una versión desconocida."""
    if len(raw) < 4:
        return None
    tamano, formato, contenido = struct.unpack_from(CABECERA, raw, 0)
    tabla = VERSIONES.get((formato, contenido))
    if tabla is None:
        return None
    # El propio firmware dice cuánto ocupa: si lo leído no llega, la tabla está
    # cortada y no hay forma de saber qué campos son buenos.
    util = min(tamano, len(raw))

    def leer(nombre: str) -> Optional[int]:
        if nombre not in tabla:
            return None
        formato_campo, sitio = tabla[nombre]
        if sitio + struct.calcsize(formato_campo) > util:
            return None
        valor = struct.unpack_from("<" + formato_campo, raw, sitio)[0]
        return None if valor == SIN_DATO[formato_campo] else valor

    mhz = lambda nombre: (lambda v: v * 1_000_000 if v else None)(leer(nombre))
    grados = lambda nombre: (lambda v: float(v) if v is not None else None)(leer(nombre))
    voltios = lambda nombre: (lambda v: round(v / 1000, 3) if v else None)(leer(nombre))
    porcentaje = lambda nombre: (lambda v: float(v) if v is not None and v <= 100 else None)(leer(nombre))

    # El independiente del modelo de chip va primero; el otro solo se entiende
    # sabiendo qué ASIC hay debajo, y ahí sí que no se puede nombrar el motivo.
    banderas = leer("throttle_independent")
    motivos = _motivos(banderas) if banderas is not None else ()
    if banderas is None:
        crudo = leer("throttle_status")
        frenada = None if crudo is None else bool(crudo)
    else:
        frenada = bool(banderas)

    ancho = leer("link_width")
    velocidad = leer("link_speed")
    return Metrics(
        version=f"{formato}.{contenido}",
        temp_edge_c=grados("temp_edge"),
        temp_hotspot_c=grados("temp_hotspot"),
        temp_memory_c=grados("temp_mem"),
        temp_vr_gfx_c=grados("temp_vr_gfx"),
        temp_vr_soc_c=grados("temp_vr_soc"),
        temp_vr_mem_c=grados("temp_vr_mem"),
        gfx_activity_percent=porcentaje("gfx_activity"),
        memory_activity_percent=porcentaje("memory_activity"),
        video_activity_percent=porcentaje("video_activity"),
        socket_power_w=(lambda v: float(v) if v is not None else None)(leer("socket_power")),
        gfx_clock_hz=mhz("gfx_clock"),
        gfx_clock_average_hz=mhz("gfx_clock_average"),
        soc_clock_hz=mhz("soc_clock"),
        memory_clock_hz=mhz("memory_clock"),
        memory_clock_effective_hz=mhz("memory_clock_average"),
        fan_rpm=leer("fan_rpm"),
        link_width=ancho or None,
        # Viene en décimas de gigatransferencia: 160 son 16,0 GT/s.
        link_speed_gts=round(velocidad / 10, 1) if velocidad else None,
        voltage_gfx_v=voltios("voltage_gfx"),
        voltage_soc_v=voltios("voltage_soc"),
        voltage_memory_v=voltios("voltage_mem"),
        throttle_reasons=motivos,
        throttled=frenada,
    )


def read(device: pathlib.Path | str) -> Optional[Metrics]:
    """Lee la tabla del nodo PCI de una tarjeta."""
    try:
        crudo = pathlib.Path(device, "gpu_metrics").read_bytes()
    except OSError:
        return None
    return parse(crudo) if crudo else None


def version_of(raw: bytes) -> Optional[str]:
    """La versión de una tabla, aunque no se sepa interpretar su contenido."""
    if len(raw) < 4:
        return None
    _, formato, contenido = struct.unpack_from(CABECERA, raw, 0)
    return f"{formato}.{contenido}"


def _motivos(banderas: int) -> tuple[str, ...]:
    """Los motivos encendidos, sin repetir: varios bits nombran lo mismo."""
    vistos: list[str] = []
    for bit, motivo in MOTIVOS.items():
        if banderas & (1 << bit) and motivo not in vistos:
            vistos.append(motivo)
    return tuple(vistos)
