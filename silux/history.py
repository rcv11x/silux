"""El historial de pruebas de rendimiento de este equipo.

Una puntuación suelta no dice nada: 610 op/s solo significa algo comparado
con otra cosa. Lo de fuera —la tabla de internet— casi nunca sirve, porque
está medido con otro gobernador, otra temperatura ambiente y otro programa.
Lo que sí compara bien es el mismo equipo consigo mismo: antes y después de
cambiar la pasta térmica, en invierno y en agosto, con el portátil enchufado
y con batería.

Se guarda en el disco del usuario, no se envía a ninguna parte, y cada
entrada lleva las condiciones en las que se midió: sin ellas, dos cifras
distintas del mismo equipo no se pueden interpretar.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import time
from typing import Any, Optional

from .benchmark import Result

# Cuántas pruebas se conservan. Suficiente para ver una tendencia a lo largo
# de meses, y poco para que el archivo siga siendo un JSON que se lee de una
# vez y se puede abrir con un editor.
MAXIMO = 60


def data_dir() -> pathlib.Path:
    base = os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "silux"


def history_path() -> pathlib.Path:
    return data_dir() / "benchmarks.json"


@dataclasses.dataclass(frozen=True, slots=True)
class Entry:
    """Una prueba guardada, con lo justo para volver a interpretarla."""

    timestamp: float
    cpu: str                       # para no comparar contra otro equipo
    threads: int
    seconds: float                 # cuánto duró cada medida
    scores: dict[str, float]       # «compresion/1», «compresion/16» → op/s
    # Un nombre que le pone el usuario: «con la pasta nueva», «verano», «tras
    # subir el PBO». Sin él, una lista de fechas no dice qué cambió entre una
    # y otra, que es justo lo que se quiere saber al comparar.
    label: str = ""
    governor: Optional[str] = None
    temperature_peak_c: Optional[float] = None
    frequency_avg_hz: Optional[int] = None
    background_load: Optional[float] = None
    # Lo más que llegó a robarle otro programa mientras se medía. El de arriba
    # se toma antes de empezar y no ve lo que pase después.
    background_peak: Optional[float] = None
    # Con qué escala se calculó su puntuación. Sin esto, dos pruebas medidas
    # con escalas distintas salen en la misma tabla como si se pudieran
    # comparar, y la diferencia que se lee no existe: al rehacer la escala la
    # cifra de un hilo se movió un 68 % sin que el equipo cambiara.
    score_version: Optional[int] = None
    # Con qué bibliotecas se midió, y con qué extensiones del procesador. Ya
    # no deciden la puntuación —desde la v6 las tres cargas que dependen del
    # sistema no puntúan—, pero siguen guardándose, porque son lo que permite
    # leer sus cifras: la misma pieza da 14,9 GB/s en la carga de verificación
    # con zlib-ng y 1,5 con la zlib de Ubuntu 22.04, que es la que va dentro
    # del AppImage.
    #
    # Las extensiones van al lado de la versión y no sueltas porque por sí
    # solas no dicen nada: una zlib clásica no trae ni una instrucción
    # `pclmulqdq` ni un solo `cpuid`, así que ejecuta el mismo camino en un
    # Nehalem de 2009 que en un Zen 5 y las banderas dan igual. Solo importan
    # cuando debajo hay zlib-ng, que sí despacha mirando la CPU.
    zlib_version: Optional[str] = None
    zlib_simd: tuple[str, ...] = ()
    # Y con qué OpenSSL, que es la otra biblioteca de la que cuelgan cargas.
    # Aquí el reparto es curioso y por eso se guarda: el resumen
    # criptográfico da lo mismo en todas partes (190,05 · 190,13 · 190,17 op/s
    # en tres distribuciones con dos versiones mayores), y la derivación de
    # clave se lleva un ×1,38 entre la 3.0 y la 3.5, porque lo que cambió no
    # es el algoritmo sino lo que cuesta cada una de sus doce mil vueltas.
    openssl_version: Optional[str] = None

    @property
    def when(self) -> str:
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(self.timestamp))

    def total(self) -> Optional[float]:
        """La suma de las medidas a todos los hilos, como cifra única.

        No es una puntuación con unidades: es lo que permite ordenar dos
        pruebas del mismo equipo. Compararla contra otro equipo no significa
        nada y por eso no se enseña sola en ninguna parte.
        """
        multihilo = [v for k, v in self.scores.items() if not k.endswith("/1")]
        return sum(multihilo) if multihilo else None

    def comparable_con(self, otra: "Entry") -> bool:
        """Si dos pruebas se pueden poner una al lado de otra.

        Cambiar la duración cambia la cifra —una medida de tres segundos coge
        el turbo entero y una de treinta no—, así que comparar contra una de
        otra duración diría que el equipo se ha vuelto más lento cuando lo
        único que cambió fue la pregunta.
        """
        return (self.cpu == otra.cpu and self.threads == otra.threads
                and abs(self.seconds - otra.seconds) < 0.01
                and self.score_version == otra.score_version)


# Las banderas que deciden qué ruta usa zlib-ng. No es una lista de curiosidades:
# la de 256 bits (`vpclmulqdq`) es de Ice Lake y Zen 3 en adelante, así que un
# procesador anterior usa otra y rinde distinto con la misma biblioteca.
#
# Son las del procesador y no las que la biblioteca llegue a usar, que no es lo
# mismo y conviene no leerlo mal: con una zlib clásica debajo no se usa
# ninguna, porque no lleva ninguna dentro. Se guardan igualmente, y juntas con
# la versión: la pareja se interpreta, cada mitad por su cuenta no.
EXTENSIONES = ("vpclmulqdq", "pclmulqdq", "avx2")


def _zlib_version() -> Optional[str]:
    """Qué biblioteca de compresión hay debajo, que no es la misma en todas
    las distribuciones: CachyOS y Fedora traen zlib-ng, y Debian, Ubuntu,
    Arch y openSUSE la clásica."""
    try:
        import zlib
        return zlib.ZLIB_RUNTIME_VERSION
    except Exception:                                  # noqa: BLE001
        return None


def _openssl_version() -> Optional[str]:
    """Con qué OpenSSL se midió, de la que cuelgan dos de las cargas."""
    try:
        import ssl
        return ssl.OPENSSL_VERSION
    except Exception:                                  # noqa: BLE001
        # Un Python compilado sin `ssl` sigue midiendo: `hashlib` cae a lo que
        # trae CPython dentro. Lo que no hay entonces es de qué informar.
        return None


def _extensiones() -> tuple[str, ...]:
    """Las de `EXTENSIONES` que tenga este procesador, en ese orden."""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for linea in fh:
                if linea.startswith(("flags", "Features")):
                    tiene = set(linea.split(":", 1)[1].split())
                    return tuple(f for f in EXTENSIONES if f in tiene)
    except OSError:
        pass
    return ()


def from_result(resultado: Result, cpu: str, seconds: float) -> Entry:
    # `rate` y no `operations / seconds`: donde el tamaño de una operación
    # cambia de una máquina a otra, lo comparable son los bytes por segundo.
    scores = {f"{m.load}/{m.threads}": m.rate
              for m in resultado.measures if m.seconds}
    condiciones = resultado.conditions
    hilos = max((m.threads for m in resultado.measures), default=1)
    from . import score

    return Entry(
        score_version=score.VERSION,
        zlib_version=_zlib_version(),
        zlib_simd=_extensiones(),
        openssl_version=_openssl_version(),
        timestamp=time.time(),
        cpu=cpu,
        threads=hilos,
        seconds=seconds,
        scores=scores,
        governor=condiciones.governor,
        temperature_peak_c=condiciones.temperature_peak_c,
        frequency_avg_hz=condiciones.frequency_avg_hz,
        background_load=condiciones.background_load,
        background_peak=condiciones.background_peak,
    )


def load() -> list[Entry]:
    """Las pruebas guardadas, de la más reciente a la más antigua."""
    try:
        crudo = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(crudo, list):
        return []

    entradas = []
    validos = {f.name for f in dataclasses.fields(Entry)}
    for fila in crudo:
        if not isinstance(fila, dict):
            continue
        try:
            entradas.append(Entry(**{k: v for k, v in fila.items() if k in validos}))
        except TypeError:
            # Una entrada de una versión con otros campos: se salta ella sola
            # en vez de tirar el archivo entero.
            continue
    entradas.sort(key=lambda e: e.timestamp, reverse=True)
    return entradas


def save(entradas: list[Entry]) -> bool:
    """Guarda el historial. No es crítico: si falla, la prueba ya se enseñó."""
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        temporal = history_path().with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps([dataclasses.asdict(e) for e in entradas[:MAXIMO]],
                       indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        temporal.replace(history_path())
        return True
    except OSError:
        return False


def append(entrada: Entry) -> list[Entry]:
    """Añade una prueba al historial y devuelve el historial resultante."""
    entradas = [entrada] + load()
    save(entradas)
    return entradas[:MAXIMO]


def comparar(actual: Entry, anteriores: list[Entry]) -> Optional[tuple[Entry, float]]:
    """La prueba comparable más reciente y cuánto ha cambiado, en tanto por ciento.

    Devuelve None cuando no hay con qué comparar, que es lo que pasa la
    primera vez y cada vez que se cambia la duración de la medida.
    """
    total = actual.total()
    if not total:
        return None
    for otra in anteriores:
        if otra.timestamp >= actual.timestamp or not otra.comparable_con(actual):
            continue
        anterior = otra.total()
        if anterior:
            return otra, (total - anterior) / anterior * 100
    return None


# Cuánto tienen que parecerse dos puntuaciones para que su diferencia de
# temperatura signifique algo. Si el equipo rindió un 20 % más, que esté más
# caliente se explica solo y no hay nada que avisar.
CERCA_EN_PUNTUACION = 0.03

# El salto térmico a partir del cual se dice algo. Por debajo es ruido: la
# misma prueba dos veces seguidas ya varía un par de grados según cómo estuviera
# el equipo antes de empezar.
DERIVA_MINIMA_C = 4.0

# Cuántas pruebas viejas hacen falta para tener una referencia. Con una sola no
# se distingue una tendencia de un día raro.
MINIMO_PARA_COMPARAR = 3


def _mediana(valores: list[float]) -> float:
    ordenados = sorted(valores)
    mitad = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[mitad]
    return (ordenados[mitad - 1] + ordenados[mitad]) / 2


def deriva_termica(actual: Entry, anteriores: list[Entry]) -> Optional[tuple[float, int]]:
    """Cuánto más caliente está el equipo haciendo el mismo trabajo.

    Devuelve `(grados de diferencia, cuántas pruebas hay detrás)`, o None si
    no hay con qué comparar. Es el dato que delata pasta seca o polvo: la
    puntuación puede aguantar mientras el ventilador compensa, y lo que sube
    antes es la temperatura para el mismo trabajo.

    Se compara contra la mediana y no contra la última: una prueba suelta
    lanzada con el equipo ya caliente sale alta y no significa nada. Y solo
    entran las que puntuaron parecido, porque si el equipo rindió más, que
    esté más caliente se explica solo.

    Lo que esto no puede saber es la temperatura ambiente, que no la mide
    ningún sensor de la máquina. Ocho grados entre febrero y agosto son
    normales y aquí saldrían igual que ocho grados de pasta seca; por eso el
    aviso dice lo que ve y no lo diagnostica.
    """
    if actual.temperature_peak_c is None:
        return None
    total = actual.total()
    if not total:
        return None

    referencias = []
    for otra in anteriores:
        if otra.timestamp >= actual.timestamp or not otra.comparable_con(actual):
            continue
        if otra.temperature_peak_c is None:
            continue
        suya = otra.total()
        if not suya:
            continue
        if abs(suya - total) / total > CERCA_EN_PUNTUACION:
            continue
        referencias.append(otra.temperature_peak_c)

    if len(referencias) < MINIMO_PARA_COMPARAR:
        return None
    diferencia = actual.temperature_peak_c - _mediana(referencias)
    if abs(diferencia) < DERIVA_MINIMA_C:
        return None
    return diferencia, len(referencias)


def clear() -> bool:
    """Borra el historial entero. Devuelve si había algo que borrar."""
    try:
        history_path().unlink()
        return True
    except OSError:
        return False


def remove(timestamp: float) -> list[Entry]:
    """Borra una prueba concreta por su marca de tiempo."""
    quedan = [e for e in load() if e.timestamp != timestamp]
    save(quedan)
    return quedan


def rename(timestamp: float, label: str) -> list[Entry]:
    """Le pone (o le quita) el nombre a una prueba."""
    entradas = []
    for entrada in load():
        if entrada.timestamp == timestamp:
            entrada = dataclasses.replace(entrada, label=label.strip())
        entradas.append(entrada)
    save(entradas)
    return entradas
