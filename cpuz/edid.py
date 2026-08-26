"""Decodifica el EDID, que es la chapa de identificación de un monitor.

Cada pantalla lleva 128 bytes —a veces con extensiones detrás— que el kernel
deja tal cual en `/sys/class/drm/<conector>/edid`, sin pedir permisos. Dentro
está lo que sysfs no cuenta por otra vía: quién la fabricó, qué modelo es,
cuándo se hizo, cuánto mide de verdad y a qué resolución y refresco quiere
trabajar.

El formato es de 1994 y se nota. Las tres letras del fabricante van empaquetadas
en cinco bits cada una, los tamaños se parten entre varios bytes con los cuatro
bits altos de un tercero, y el nombre del modelo puede estar en cualquiera de
cuatro descriptores o en ninguno. Es el mismo tipo de trabajo que `spd.py`.

Las tres letras se traducen a un nombre con `pnp.ids`, del mismo paquete hwdata
del que ya sale `pci.ids`.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional

CABECERA = bytes((0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00))
BLOQUE = 128

CANDIDATOS_PNP = (
    "/usr/share/hwdata/pnp.ids",
    "/usr/share/misc/pnp.ids",
    "/usr/share/pnp.ids",
)

# Los cuatro descriptores de 18 bytes que hay a partir del byte 54.
DESCRIPTORES = range(54, 126, 18)
TIPO_SERIE = 0xFF
TIPO_TEXTO = 0xFE
TIPO_RANGOS = 0xFD
TIPO_NOMBRE = 0xFC


@dataclass(frozen=True, slots=True)
class Edid:
    """Lo que una pantalla dice de sí misma."""

    manufacturer_id: Optional[str] = None      # las tres letras: GBT, GSM…
    manufacturer: Optional[str] = None         # ya traducidas
    model: Optional[str] = None
    product_code: Optional[int] = None
    serial: Optional[str] = None
    year: Optional[int] = None
    week: Optional[int] = None
    version: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    native_width: Optional[int] = None
    native_height: Optional[int] = None
    native_refresh_hz: Optional[float] = None
    # El rango que declara el monitor, que no es lo mismo que el modo
    # preferido: un OLED de 240 Hz puede pedir 60 como preferido y aun así
    # llegar a 240. Enseñar solo el preferido se queda muy corto.
    refresh_min_hz: Optional[int] = None
    refresh_max_hz: Optional[int] = None

    @property
    def diagonal_inches(self) -> Optional[float]:
        if not (self.width_mm and self.height_mm):
            return None
        diagonal = (self.width_mm ** 2 + self.height_mm ** 2) ** 0.5
        return round(diagonal / 25.4, 1)

    @property
    def refresh_range(self) -> Optional[str]:
        if not self.refresh_max_hz:
            return None
        if self.refresh_min_hz and self.refresh_min_hz != self.refresh_max_hz:
            return f"{self.refresh_min_hz}–{self.refresh_max_hz} Hz"
        return f"{self.refresh_max_hz} Hz"

    @property
    def made(self) -> Optional[str]:
        """«semana 16 de 2024», que es como lo fecha el propio estándar."""
        if not self.year:
            return None
        return f"semana {self.week} de {self.year}" if self.week else str(self.year)


def parse(raw: bytes) -> Optional[Edid]:
    """Devuelve None si esto no es un EDID; nunca revienta con basura."""
    if len(raw) < BLOQUE or not raw.startswith(CABECERA):
        return None
    # El bloque tiene que sumar cero módulo 256. Un EDID que no cuadra suele ser
    # un cable malo o un adaptador que se lo inventa, y sus datos no valen.
    if sum(raw[:BLOQUE]) % 256 != 0:
        return None

    empaquetado = int.from_bytes(raw[8:10], "big")
    letras = "".join(chr(((empaquetado >> desplazamiento) & 0x1F) + 0x40)
                     for desplazamiento in (10, 5, 0))
    if not letras.isalpha():
        return None

    nombre, serie_texto = _de_los_descriptores(raw)
    ancho, alto, refresco = _modo_preferido(raw)
    minimo, maximo = _rango_de_refresco(raw)
    serie_numero = int.from_bytes(raw[12:16], "little")

    return Edid(
        manufacturer_id=letras,
        model=nombre,
        product_code=int.from_bytes(raw[10:12], "little"),
        # El de texto es el que enseña la pegatina de detrás; el numérico es el
        # de respaldo, y un 0 o un 0x01010101 significan «sin número».
        serial=serie_texto or (str(serie_numero)
                               if serie_numero not in (0, 0x01010101) else None),
        year=raw[17] + 1990 if raw[17] else None,
        week=raw[16] if 1 <= raw[16] <= 53 else None,
        version=f"{raw[18]}.{raw[19]}",
        width_mm=raw[21] * 10 or None,
        height_mm=raw[22] * 10 or None,
        native_width=ancho,
        native_height=alto,
        native_refresh_hz=refresco,
        refresh_min_hz=minimo,
        refresh_max_hz=maximo,
    )


def read(connector: pathlib.Path | str) -> Optional[Edid]:
    """Lee y decodifica el EDID de un conector de `/sys/class/drm`."""
    try:
        crudo = pathlib.Path(connector, "edid").read_bytes()
    except OSError:
        return None
    return parse(crudo) if crudo else None


def resolve_vendors(edids: Iterable[Edid]) -> dict[str, str]:
    """Traduce las tres letras a nombres, en una sola pasada por `pnp.ids`."""
    buscados = {e.manufacturer_id for e in edids if e.manufacturer_id}
    if not buscados:
        return {}
    ruta = next((p for p in map(pathlib.Path, CANDIDATOS_PNP) if p.is_file()), None)
    if ruta is None:
        return {}

    encontrados: dict[str, str] = {}
    try:
        with ruta.open(encoding="utf-8", errors="replace") as fichero:
            for linea in fichero:
                codigo, _, nombre = linea.partition("\t")
                if codigo in buscados:
                    encontrados[codigo] = nombre.strip()
                    if len(encontrados) == len(buscados):
                        break
    except OSError:
        pass
    return encontrados


# -- interno ----------------------------------------------------------------

def _texto_del_descriptor(trozo: bytes) -> str:
    """Los descriptores de texto van rellenos con 0x0A y espacios."""
    crudo = trozo[5:18].split(b"\x0a")[0]
    return re.sub(r"\s+", " ", crudo.decode("cp437", "replace")).strip()


def _de_los_descriptores(raw: bytes) -> tuple[Optional[str], Optional[str]]:
    nombre = serie = None
    for inicio in DESCRIPTORES:
        trozo = raw[inicio:inicio + 18]
        if len(trozo) < 18 or trozo[0:2] != b"\x00\x00":
            continue                      # es un temporizador, no texto
        tipo = trozo[3]
        if tipo == TIPO_NOMBRE:
            nombre = _texto_del_descriptor(trozo) or nombre
        elif tipo == TIPO_SERIE:
            serie = _texto_del_descriptor(trozo) or serie
    return nombre, serie


def _rango_de_refresco(raw: bytes) -> tuple[Optional[int], Optional[int]]:
    """El descriptor 0xFD dice entre qué refrescos puede trabajar la pantalla.

    Los valores no caben en un byte desde que hay monitores de más de 255 Hz,
    así que el estándar añadió unos bits de acarreo en el byte anterior que hay
    que sumar antes de leerlos.
    """
    for inicio in DESCRIPTORES:
        trozo = raw[inicio:inicio + 18]
        if len(trozo) < 18 or trozo[0:2] != b"\x00\x00" or trozo[3] != TIPO_RANGOS:
            continue
        acarreo = trozo[4]
        minimo = trozo[5] + (255 if acarreo & 0x01 else 0)
        maximo = trozo[6] + (255 if acarreo & 0x02 else 0)
        if maximo:
            return minimo or None, maximo
    return None, None


def _modo_preferido(raw: bytes) -> tuple[Optional[int], Optional[int], Optional[float]]:
    """El primer temporizador detallado es el modo nativo de la pantalla."""
    trozo = raw[54:72]
    reloj = int.from_bytes(trozo[0:2], "little") * 10_000      # en hercios
    if not reloj:
        return None, None, None

    ancho = trozo[2] | ((trozo[4] & 0xF0) << 4)
    ancho_blanco = trozo[3] | ((trozo[4] & 0x0F) << 8)
    alto = trozo[5] | ((trozo[7] & 0xF0) << 4)
    alto_blanco = trozo[6] | ((trozo[7] & 0x0F) << 8)
    if not (ancho and alto):
        return None, None, None

    total = (ancho + ancho_blanco) * (alto + alto_blanco)
    refresco = round(reloj / total, 1) if total else None
    return ancho, alto, refresco
