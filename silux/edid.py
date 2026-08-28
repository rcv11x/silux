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
class VideoMode:
    """Un modo de vídeo de los que el monitor declara admitir."""

    width: int
    height: int
    refresh_hz: float
    interlaced: bool = False
    native: bool = False

    @property
    def label(self) -> str:
        entrelazado = "i" if self.interlaced else ""
        return f"{self.width} × {self.height}{entrelazado} @ {self.refresh_hz:g} Hz"


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
        **_extensiones(raw),
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


# --------------------------------------------------------------------------
# Extensiones CTA-861
# --------------------------------------------------------------------------

ETIQUETA_CTA = 0x02
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
BLOQUE_AUDIO, BLOQUE_VIDEO, BLOQUE_FABRICANTE = 1, 2, 3
BLOQUE_ALTAVOCES, BLOQUE_EXTENDIDO = 4, 7

# Y los subtipos de los extendidos, que es donde vive lo moderno.
EXT_COLORIMETRIA, EXT_HDR = 5, 6

FORMATOS_AUDIO = {
    1: "LPCM", 2: "AC-3", 3: "MPEG-1", 4: "MP3", 5: "MPEG-2", 6: "AAC",
    7: "DTS", 8: "ATRAC", 9: "DSD", 10: "E-AC-3", 11: "DTS-HD",
    12: "Dolby TrueHD", 13: "DST", 14: "WMA Pro",
}

# Las curvas de transferencia del bloque de HDR estático. La primera es la
# de siempre, así que solo se enseñan las otras: decir que un monitor admite
# gamma tradicional no es noticia.
CURVAS_HDR = {1: "HDR gamma", 2: "HDR10 (PQ)", 3: "HLG"}

ESPACIOS_COLOR = {
    0: "xvYCC601", 1: "xvYCC709", 2: "sYCC601", 3: "opYCC601",
    4: "opRGB", 5: "BT.2020 cYCC", 6: "BT.2020 YCC", 7: "BT.2020 RGB",
}


def _modos_cta(datos: bytes) -> list[VideoMode]:
    """Los modos del bloque de vídeo: un byte por código, el bit 7 marca nativo."""
    modos = []
    for octeto in datos:
        codigo, nativo = octeto & 0x7F, bool(octeto & 0x80)
        if (medidas := VIC.get(codigo)) is None:
            continue
        ancho, alto, hz, entrelazado = medidas
        modos.append(VideoMode(ancho, alto, hz, entrelazado, nativo))
    return modos


def _extension_cta(bloque: bytes) -> dict:
    """Lo que dice una extensión CTA-861: modos, HDR, color y audio.

    La colección de bloques de datos ocupa desde el byte 4 hasta donde diga el
    byte 2, y cada bloque lleva su tipo y su longitud en la cabecera. Se
    recorre con cuidado de no salirse: un EDID mal grabado es de las cosas más
    fáciles de encontrar, y aquí no puede tumbar la lectura de nada más.
    """
    salida: dict = {"modes": [], "hdr": [], "color_spaces": [], "audio": []}
    if len(bloque) < 4 or bloque[0] != ETIQUETA_CTA:
        return salida

    fin = bloque[2]
    if not 4 <= fin <= len(bloque):
        return salida

    i = 4
    while i < fin:
        cabecera = bloque[i]
        etiqueta, largo = cabecera >> 5, cabecera & 0x1F
        datos = bloque[i + 1:i + 1 + largo]
        if len(datos) < largo:
            break

        if etiqueta == BLOQUE_VIDEO:
            salida["modes"].extend(_modos_cta(datos))
        elif etiqueta == BLOQUE_AUDIO:
            # Tríos de bytes: los cinco bits altos del primero son el formato.
            for j in range(0, len(datos) - 2, 3):
                nombre = FORMATOS_AUDIO.get((datos[j] >> 3) & 0x0F)
                if nombre and nombre not in salida["audio"]:
                    salida["audio"].append(nombre)
        elif etiqueta == BLOQUE_EXTENDIDO and datos:
            if datos[0] == EXT_HDR and len(datos) >= 2:
                salida["hdr"] = [nombre for bit, nombre in CURVAS_HDR.items()
                                 if datos[1] & (1 << bit)]
            elif datos[0] == EXT_COLORIMETRIA and len(datos) >= 2:
                salida["color_spaces"] = [
                    nombre for bit, nombre in ESPACIOS_COLOR.items()
                    if datos[1] & (1 << bit)]
        i += largo + 1
    return salida


def _extensiones(raw: bytes) -> dict:
    """Recorre los bloques que van detrás del principal y junta lo que traen."""
    juntos: dict = {"modes": [], "hdr": [], "color_spaces": [], "audio": []}
    for inicio in range(BLOQUE, len(raw) - BLOQUE + 1, BLOQUE):
        trozo = raw[inicio:inicio + BLOQUE]
        if len(trozo) < BLOQUE or trozo[0] != ETIQUETA_CTA:
            continue
        for clave, valores in _extension_cta(trozo).items():
            for valor in valores:
                if valor not in juntos[clave]:
                    juntos[clave].append(valor)
    # Tuplas: el Snapshot es inmutable de arriba abajo, y una lista dentro de
    # un dataclass congelado es una promesa que no se cumple.
    return {clave: tuple(valores) for clave, valores in juntos.items()}
