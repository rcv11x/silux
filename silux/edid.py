"""Decodifica el EDID, que es la chapa de identificación de un monitor.

Cada pantalla lleva 128 bytes (a veces con extensiones detrás) que el kernel
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

HEADER = bytes((0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00))
BLOCK = 128

PNP_CANDIDATES = (
    "/usr/share/hwdata/pnp.ids",
    "/usr/share/misc/pnp.ids",
    "/usr/share/pnp.ids",
)

# Los cuatro descriptores de 18 bytes que hay a partir del byte 54.
DESCRIPTORS = range(54, 126, 18)
TYPE_SERIAL = 0xFF
TYPE_TEXT = 0xFE
TYPE_RANGES = 0xFD
TYPE_NAME = 0xFC


@dataclass(frozen=True, slots=True)
class VideoMode:
    """Un modo de vídeo de los que el monitor declara admitir."""

    width: int
    height: int
    refresh_hz: float
    interlaced: bool = False
    native: bool = False

    @property
    def label(self) -> str:
        suffix = "i" if self.interlaced else ""
        return f"{self.width} × {self.height}{suffix} @ {self.refresh_hz:g} Hz"


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
    # Si esas dos medidas vienen al milímetro. El bloque base del EDID las da
    # en centímetros enteros, y de ahí salía «26.6"» para un monitor de 27:
    # medio centímetro por lado mueve la diagonal un cuarto de pulgada. El
    # temporizador del modo nativo las trae en milímetros; cuando no las trae
    # o no cuadran con las otras, quedan las de centímetros y la diagonal se
    # enseña como lo que es, aproximada.
    size_exact: bool = False
    native_width: Optional[int] = None
    native_height: Optional[int] = None
    native_refresh_hz: Optional[float] = None
    # El rango que declara el monitor, que no es lo mismo que el modo
    # preferido: un OLED de 240 Hz puede pedir 60 como preferido y aun así
    # llegar a 240. Enseñar solo el preferido se queda muy corto.
    refresh_min_hz: Optional[int] = None
    refresh_max_hz: Optional[int] = None
    # De las extensiones CTA-861. El bloque base solo tiene sitio para el modo
    # preferido y unos pocos estándar, así que sin mirarlas un monitor que
    # admite 4K a 120 aparece como si solo hiciera 1080p a 60.
    modes: tuple[VideoMode, ...] = ()
    hdr: tuple[str, ...] = ()
    color_spaces: tuple[str, ...] = ()
    audio: tuple[str, ...] = ()

    @property
    def best_mode(self) -> Optional[VideoMode]:
        """El modo más exigente de los declarados.

        Ordena por píxeles y luego por refresco: entre 4K a 60 y 1080p a 240
        gana el 4K, que es lo que define de lo que es capaz el panel.
        """
        if not self.modes:
            return None
        return max(self.modes, key=lambda m: (m.width * m.height, m.refresh_hz))

    @property
    def diagonal_inches(self) -> Optional[float]:
        """La diagonal del panel. Con un decimal si las medidas son al
        milímetro; redondeada a la pulgada si solo hay centímetros."""
        if not (self.width_mm and self.height_mm):
            return None
        diagonal = (self.width_mm ** 2 + self.height_mm ** 2) ** 0.5 / 25.4
        return round(diagonal, 1) if self.size_exact else float(round(diagonal))

    @property
    def refresh_range(self) -> Optional[str]:
        if not self.refresh_max_hz:
            return None
        if self.refresh_min_hz and self.refresh_min_hz != self.refresh_max_hz:
            return f"{self.refresh_min_hz}–{self.refresh_max_hz} Hz"
        return f"{self.refresh_max_hz} Hz"

    @property
    def refresh_summary(self) -> Optional[str]:
        """El refresco que se enseña, venga de donde venga.

        El rango del descriptor 0xFD es el bueno y manda: un OLED de 240 Hz
        declara 60 como modo preferido, así que enseñar el preferido como si
        fuera el techo se queda corto por mucho.

        Pero ese descriptor es opcional y los paneles de portátil casi nunca
        lo traen: el eDP de un ThinkPad salía sin refresco ninguno teniendo el
        dato calculado desde su temporización detallada. Cuando no hay rango,
        el modo nativo es lo único que hay y decirlo es mejor que callarse —
        con la reserva de que es el preferido y no necesariamente el máximo,
        que es lo que aclara el rótulo de al lado.
        """
        if self.refresh_range:
            return self.refresh_range
        if self.native_refresh_hz:
            return f"{self.native_refresh_hz:g} Hz"
        return None

    @property
    def refresh_is_native_only(self) -> bool:
        """Si lo que se enseña es el modo preferido y no un rango declarado."""
        return not self.refresh_range and bool(self.native_refresh_hz)


def parse(raw: bytes) -> Optional[Edid]:
    """Devuelve None si esto no es un EDID; nunca revienta con basura."""
    if len(raw) < BLOCK or not raw.startswith(HEADER):
        return None
    # El bloque tiene que sumar cero módulo 256. Un EDID que no cuadra suele ser
    # un cable malo o un adaptador que se lo inventa, y sus datos no valen.
    if sum(raw[:BLOCK]) % 256 != 0:
        return None

    packed = int.from_bytes(raw[8:10], "big")
    letters = "".join(chr(((packed >> shift) & 0x1F) + 0x40)
                     for shift in (10, 5, 0))
    if not letters.isalpha():
        return None

    model_name, serial_text = _from_descriptors(raw)
    width_mm, height_mm, exact = _panel_size(raw)
    width, height, refresh = _preferred_mode(raw)
    refresh_min, refresh_max = _refresh_range(raw)
    serial_number = int.from_bytes(raw[12:16], "little")

    return Edid(
        manufacturer_id=letters,
        model=model_name,
        product_code=int.from_bytes(raw[10:12], "little"),
        # El de texto es el que enseña la pegatina de detrás; el numérico es el
        # de respaldo, y un 0 o un 0x01010101 significan «sin número».
        serial=serial_text or (str(serial_number)
                               if serial_number not in (0, 0x01010101) else None),
        year=raw[17] + 1990 if raw[17] else None,
        week=raw[16] if 1 <= raw[16] <= 53 else None,
        version=f"{raw[18]}.{raw[19]}",
        width_mm=width_mm,
        height_mm=height_mm,
        size_exact=exact,
        native_width=width,
        native_height=height,
        native_refresh_hz=refresh,
        refresh_min_hz=refresh_min,
        refresh_max_hz=refresh_max,
        **_extensions(raw),
    )


def read(connector: pathlib.Path | str) -> Optional[Edid]:
    """Lee y decodifica el EDID de un conector de `/sys/class/drm`."""
    try:
        raw = pathlib.Path(connector, "edid").read_bytes()
    except OSError:
        return None
    return parse(raw) if raw else None


def resolve_vendors(edids: Iterable[Edid]) -> dict[str, str]:
    """Traduce las tres letras a nombres, en una sola pasada por `pnp.ids`."""
    wanted = {e.manufacturer_id for e in edids if e.manufacturer_id}
    if not wanted:
        return {}
    path = next((p for p in map(pathlib.Path, PNP_CANDIDATES) if p.is_file()), None)
    if path is None:
        return {}

    found: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                code, _tab, name = line.partition("\t")
                if code in wanted:
                    found[code] = name.strip()
                    if len(found) == len(wanted):
                        break
    except OSError:
        pass
    return found


# -- interno ----------------------------------------------------------------

def _descriptor_text(chunk: bytes) -> str:
    """Los descriptores de texto van rellenos con 0x0A y espacios."""
    text_bytes = chunk[5:18].split(b"\x0a")[0]
    return re.sub(r"\s+", " ", text_bytes.decode("cp437", "replace")).strip()


def _from_descriptors(raw: bytes) -> tuple[Optional[str], Optional[str]]:
    name = serial = None
    for start in DESCRIPTORS:
        chunk = raw[start:start + 18]
        if len(chunk) < 18 or chunk[0:2] != b"\x00\x00":
            continue                      # es un temporizador, no texto
        kind = chunk[3]
        if kind == TYPE_NAME:
            name = _descriptor_text(chunk) or name
        elif kind == TYPE_SERIAL:
            serial = _descriptor_text(chunk) or serial
    return name, serial


def _refresh_range(raw: bytes) -> tuple[Optional[int], Optional[int]]:
    """El descriptor 0xFD dice entre qué refrescos puede trabajar la pantalla.

    Los valores no caben en un byte desde que hay monitores de más de 255 Hz,
    así que el estándar añadió unos bits de acarreo en el byte anterior que hay
    que sumar antes de leerlos.
    """
    for start in DESCRIPTORS:
        chunk = raw[start:start + 18]
        if len(chunk) < 18 or chunk[0:2] != b"\x00\x00" or chunk[3] != TYPE_RANGES:
            continue
        carry = chunk[4]
        low = chunk[5] + (255 if carry & 0x01 else 0)
        high = chunk[6] + (255 if carry & 0x02 else 0)
        if high:
            return low or None, high
    return None, None


def _panel_size(raw: bytes) -> tuple[Optional[int], Optional[int], bool]:
    """Ancho y alto de la imagen en milímetros, y si son al milímetro.

    El bloque base los da en centímetros (bytes 21 y 22). El primer
    temporizador detallado, el del modo nativo, los repite en milímetros. Se
    toman esos cuando cuadran con los centímetros: hay pantallas que ponen ahí
    la proporción («16 × 9») o un cero, y un proyector no tiene medida.
    """
    width_cm, height_cm = raw[21], raw[22]
    chunk = raw[54:72]
    if int.from_bytes(chunk[0:2], "little"):            # es un temporizador
        width = chunk[12] | ((chunk[14] >> 4) << 8)
        height = chunk[13] | ((chunk[14] & 0x0F) << 8)
        matches = (abs(width - width_cm * 10) <= 10 and abs(height - height_cm * 10) <= 10
                  if width_cm and height_cm else False)
        if width and height and matches:
            return width, height, True
    return width_cm * 10 or None, height_cm * 10 or None, False


def _preferred_mode(raw: bytes) -> tuple[Optional[int], Optional[int], Optional[float]]:
    """El primer temporizador detallado es el modo nativo de la pantalla."""
    chunk = raw[54:72]
    pixel_clock = int.from_bytes(chunk[0:2], "little") * 10_000      # en hercios
    if not pixel_clock:
        return None, None, None

    width = chunk[2] | ((chunk[4] & 0xF0) << 4)
    width_blank = chunk[3] | ((chunk[4] & 0x0F) << 8)
    height = chunk[5] | ((chunk[7] & 0xF0) << 4)
    height_blank = chunk[6] | ((chunk[7] & 0x0F) << 8)
    if not (width and height):
        return None, None, None

    total = (width + width_blank) * (height + height_blank)
    refresh = round(pixel_clock / total, 1) if total else None
    return width, height, refresh


# --------------------------------------------------------------------------
# Extensiones CTA-861
# --------------------------------------------------------------------------

CTA_TAG = 0x02
# Los códigos de la tabla 3 de CTA-861: (ancho, alto, refresco, entrelazado).
# Están los de uso corriente, no los 219 que existen; un código que no esté
# aquí se salta en vez de inventarle una resolución.
VIC = {
    1: (640, 480, 59.94, False),
    2: (720, 480, 59.94, False), 3: (720, 480, 59.94, False),
    4: (1280, 720, 60.0, False),
    5: (1920, 1080, 60.0, True),
    6: (720, 480, 59.94, True), 7: (720, 480, 59.94, True),
    16: (1920, 1080, 60.0, False),
    17: (720, 576, 50.0, False), 18: (720, 576, 50.0, False),
    19: (1280, 720, 50.0, False),
    20: (1920, 1080, 50.0, True),
    31: (1920, 1080, 50.0, False),
    32: (1920, 1080, 24.0, False), 33: (1920, 1080, 25.0, False),
    34: (1920, 1080, 30.0, False),
    60: (1280, 720, 24.0, False), 61: (1280, 720, 25.0, False),
    62: (1280, 720, 30.0, False),
    63: (1920, 1080, 120.0, False), 64: (1920, 1080, 100.0, False),
    65: (1280, 720, 24.0, False), 68: (1280, 720, 50.0, False),
    69: (1280, 720, 60.0, False), 70: (1280, 720, 100.0, False),
    71: (1280, 720, 120.0, False),
    72: (1920, 1080, 24.0, False), 75: (1920, 1080, 50.0, False),
    76: (1920, 1080, 60.0, False), 77: (1920, 1080, 100.0, False),
    78: (1920, 1080, 120.0, False),
    93: (3840, 2160, 24.0, False), 94: (3840, 2160, 25.0, False),
    95: (3840, 2160, 30.0, False), 96: (3840, 2160, 50.0, False),
    97: (3840, 2160, 60.0, False),
    98: (4096, 2160, 24.0, False), 99: (4096, 2160, 25.0, False),
    100: (4096, 2160, 30.0, False), 101: (4096, 2160, 50.0, False),
    102: (4096, 2160, 60.0, False),
    103: (3840, 2160, 24.0, False), 104: (3840, 2160, 25.0, False),
    105: (3840, 2160, 30.0, False), 106: (3840, 2160, 50.0, False),
    107: (3840, 2160, 60.0, False),
    108: (3840, 2160, 100.0, False), 109: (3840, 2160, 120.0, False),
    114: (3840, 2160, 60.0, False),
    117: (3840, 2160, 100.0, False), 118: (3840, 2160, 120.0, False),
    120: (5120, 2160, 60.0, False),
    124: (7680, 4320, 24.0, False), 125: (7680, 4320, 25.0, False),
    126: (7680, 4320, 30.0, False),
    193: (5120, 2160, 100.0, False), 194: (5120, 2160, 120.0, False),
    218: (5120, 2880, 60.0, False), 219: (5120, 2880, 120.0, False),
}

# Los tipos de bloque dentro de la colección de datos.
BLOCK_AUDIO, BLOCK_VIDEO, BLOCK_VENDOR = 1, 2, 3
BLOCK_SPEAKERS, BLOCK_EXTENDED = 4, 7

# Y los subtipos de los extendidos, que es donde vive lo moderno.
EXT_COLORIMETRY, EXT_HDR = 5, 6

AUDIO_FORMATS = {
    1: "LPCM", 2: "AC-3", 3: "MPEG-1", 4: "MP3", 5: "MPEG-2", 6: "AAC",
    7: "DTS", 8: "ATRAC", 9: "DSD", 10: "E-AC-3", 11: "DTS-HD",
    12: "Dolby TrueHD", 13: "DST", 14: "WMA Pro",
}

# Las curvas de transferencia del bloque de HDR estático. La primera es la
# de siempre, así que solo se enseñan las otras: decir que un monitor admite
# gamma tradicional no es noticia.
HDR_CURVES = {1: "HDR gamma", 2: "HDR10 (PQ)", 3: "HLG"}

COLOR_SPACES = {
    0: "xvYCC601", 1: "xvYCC709", 2: "sYCC601", 3: "opYCC601",
    4: "opRGB", 5: "BT.2020 cYCC", 6: "BT.2020 YCC", 7: "BT.2020 RGB",
}


def _cta_modes(data: bytes) -> list[VideoMode]:
    """Los modos del bloque de vídeo: un byte por código, el bit 7 marca nativo."""
    modes = []
    for byte in data:
        code, native = byte & 0x7F, bool(byte & 0x80)
        if (dims := VIC.get(code)) is None:
            continue
        width, height, hz, interlaced = dims
        modes.append(VideoMode(width, height, hz, interlaced, native))
    return modes


def _cta_extension(block: bytes) -> dict:
    """Lo que dice una extensión CTA-861: modos, HDR, color y audio.

    La colección de bloques de datos ocupa desde el byte 4 hasta donde diga el
    byte 2, y cada bloque lleva su tipo y su longitud en la cabecera. Se
    recorre con cuidado de no salirse: un EDID mal grabado es de las cosas más
    fáciles de encontrar, y aquí no puede tumbar la lectura de nada más.
    """
    found: dict = {"modes": [], "hdr": [], "color_spaces": [], "audio": []}
    if len(block) < 4 or block[0] != CTA_TAG:
        return found

    end = block[2]
    if not 4 <= end <= len(block):
        return found

    i = 4
    while i < end:
        header = block[i]
        tag, length = header >> 5, header & 0x1F
        data = block[i + 1:i + 1 + length]
        if len(data) < length:
            break

        if tag == BLOCK_VIDEO:
            found["modes"].extend(_cta_modes(data))
        elif tag == BLOCK_AUDIO:
            # Tríos de bytes: los cinco bits altos del primero son el formato.
            for j in range(0, len(data) - 2, 3):
                name = AUDIO_FORMATS.get((data[j] >> 3) & 0x0F)
                if name and name not in found["audio"]:
                    found["audio"].append(name)
        elif tag == BLOCK_EXTENDED and data:
            if data[0] == EXT_HDR and len(data) >= 2:
                found["hdr"] = [name for bit, name in HDR_CURVES.items()
                                 if data[1] & (1 << bit)]
            elif data[0] == EXT_COLORIMETRY and len(data) >= 2:
                found["color_spaces"] = [
                    name for bit, name in COLOR_SPACES.items()
                    if data[1] & (1 << bit)]
        i += length + 1
    return found


def _extensions(raw: bytes) -> dict:
    """Recorre los bloques que van detrás del principal y junta lo que traen."""
    merged: dict = {"modes": [], "hdr": [], "color_spaces": [], "audio": []}
    for start in range(BLOCK, len(raw) - BLOCK + 1, BLOCK):
        chunk = raw[start:start + BLOCK]
        if len(chunk) < BLOCK or chunk[0] != CTA_TAG:
            continue
        for key, values in _cta_extension(chunk).items():
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)
    # Tuplas: el Snapshot es inmutable de arriba abajo, y una lista dentro de
    # un dataclass congelado es una promesa que no se cumple.
    return {key: tuple(values) for key, values in merged.items()}
