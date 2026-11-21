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
from typing import Optional

from .benchmark import Result

# Cuántas pruebas se conservan. Suficiente para ver una tendencia a lo largo
# de meses, y poco para que el archivo siga siendo un JSON que se lee de una
# vez y se puede abrir con un editor.
MAX_ENTRIES = 60


def data_dir() -> pathlib.Path:
    base = os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "silux"


def history_path() -> pathlib.Path:
    return data_dir() / "benchmarks.json"


def same_duration(a: float, b: float) -> bool:
    """Si dos pruebas pidieron la misma duración por medida.

    Lo guardado es lo que tardó la medida más larga: lo pedido más lo que
    tarde en acabar la operación que estaba en vuelo, que va de unos
    milisegundos a 128 con la zlib del AppImage. El margen cubre ese exceso y
    se queda por debajo del segundo que separa las dos duraciones más
    cercanas que se ofrecen, la rápida de 2 s y la de 3. No es el de
    `score.comparable` a propósito: aquel, de 1,5 s, juntaría esas dos.
    """
    return abs(a - b) <= max(0.25, 0.02 * max(a, b))


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
        """La cifra con que se comparan dos pruebas del mismo equipo.

        Es la puntuación a todos los hilos, o sea, las cargas que puntúan, cada
        una contra su referencia. Era la suma en crudo de todas las medidas, y
        la de verificación va en bytes por segundo —cien mil millones contra
        unos miles—, así que la comparación la decidía la carga que no puntúa
        y que depende de la zlib de cada distribución. Sin todas las que
        puntúan no hay cifra, y una prueba cancelada a medias no se compara.
        """
        from . import score

        return score.exact_multithread(self.scores, self.threads)

    def comparable_with(self, other: "Entry") -> bool:
        """Si dos pruebas se pueden poner una al lado de otra.

        Cambiar la duración cambia la cifra —una medida de tres segundos coge
        el turbo entero y una de treinta no—, así que comparar contra una de
        otra duración diría que el equipo se ha vuelto más lento cuando lo
        único que cambió fue la pregunta.
        """
        return (self.cpu == other.cpu and self.threads == other.threads
                and same_duration(self.seconds, other.seconds)
                and self.score_version == other.score_version)


# Las banderas que deciden qué ruta usa zlib-ng. No es una lista de curiosidades:
# la de 256 bits (`vpclmulqdq`) es de Ice Lake y Zen 3 en adelante, así que un
# procesador anterior usa otra y rinde distinto con la misma biblioteca.
#
# Son las del procesador y no las que la biblioteca llegue a usar, que no es lo
# mismo y conviene no leerlo mal: con una zlib clásica debajo no se usa
# ninguna, porque no lleva ninguna dentro. Se guardan igualmente, y juntas con
# la versión: la pareja se interpreta, cada mitad por su cuenta no.
SIMD_FLAGS = ("vpclmulqdq", "pclmulqdq", "avx2")


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


def _simd_flags() -> tuple[str, ...]:
    """Las de `EXTENSIONES` que tenga este procesador, en ese orden."""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(("flags", "Features")):
                    present = set(line.split(":", 1)[1].split())
                    return tuple(f for f in SIMD_FLAGS if f in present)
    except OSError:
        pass
    return ()


def from_result(result: Result, cpu: str, seconds: float) -> Entry:
    # `rate` y no `operations / seconds`: donde el tamaño de una operación
    # cambia de una máquina a otra, lo comparable son los bytes por segundo.
    scores = {f"{m.load}/{m.threads}": m.rate
              for m in result.measures if m.seconds}
    conditions = result.conditions
    threads = max((m.threads for m in result.measures), default=1)
    from . import score

    return Entry(
        score_version=score.VERSION,
        zlib_version=_zlib_version(),
        zlib_simd=_simd_flags(),
        openssl_version=_openssl_version(),
        timestamp=time.time(),
        cpu=cpu,
        threads=threads,
        seconds=seconds,
        scores=scores,
        governor=conditions.governor,
        temperature_peak_c=conditions.temperature_peak_c,
        frequency_avg_hz=conditions.frequency_avg_hz,
        background_load=conditions.background_load,
        background_peak=conditions.background_peak,
    )


def _is_number(value) -> bool:
    # `bool` es un `int` para Python, y un `true` donde va una fecha no lo es.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _well_formed(row: dict) -> bool:
    """Si una entrada leída del disco se puede usar sin que reviente después.

    El archivo lo escribe el programa, pero vive en el disco de alguien: una
    entrada con un campo del tipo equivocado se leía sin rechistar y
    reventaba más tarde, al ordenar o al sumar, montando la página de
    Rendimiento. O sea, la ventana no abría.
    """
    measures = row.get("scores")
    return (_is_number(row.get("timestamp"))
            and isinstance(row.get("cpu"), str)
            and _is_number(row.get("threads")) and row["threads"] > 0
            and _is_number(row.get("seconds")) and row["seconds"] > 0
            and isinstance(measures, dict)
            and all(isinstance(k, str) and _is_number(v) for k, v in measures.items())
            and isinstance(row.get("label", ""), str)
            and all(row.get(field) is None or _is_number(row[field])
                    for field in ("temperature_peak_c", "frequency_avg_hz",
                                  "background_load", "background_peak",
                                  "score_version")))


def load() -> list[Entry]:
    """Las pruebas guardadas, de la más reciente a la más antigua."""
    try:
        raw = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # `ValueError` cubre el JSON mal formado y también un UTF-8 roto.
        return []
    if not isinstance(raw, list):
        return []

    entries = []
    known_fields = {f.name for f in dataclasses.fields(Entry)}
    for row in raw:
        if not isinstance(row, dict) or not _well_formed(row):
            continue
        try:
            entries.append(Entry(**{k: v for k, v in row.items() if k in known_fields}))
        except TypeError:
            # Una entrada de una versión con otros campos: se salta ella sola
            # en vez de tirar el archivo entero.
            continue
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


def save(entries: list[Entry]) -> bool:
    """Guarda el historial. No es crítico: si falla, la prueba ya se enseñó."""
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        temp_path = history_path().with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps([dataclasses.asdict(e) for e in entries[:MAX_ENTRIES]],
                       indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        temp_path.replace(history_path())
        return True
    except OSError:
        return False


def append(entry: Entry) -> list[Entry]:
    """Añade una prueba al historial y devuelve el historial resultante."""
    entries = [entry] + load()
    save(entries)
    return entries[:MAX_ENTRIES]


def compare(latest: Entry, previous: list[Entry]) -> Optional[tuple[Entry, float]]:
    """La prueba comparable más reciente y cuánto ha cambiado, en tanto por ciento.

    Devuelve None cuando no hay con qué comparar, que es lo que pasa la
    primera vez y cada vez que se cambia la duración de la medida.
    """
    total = latest.total()
    if not total:
        return None
    for other in previous:
        if other.timestamp >= latest.timestamp or not other.comparable_with(latest):
            continue
        before = other.total()
        if before:
            return other, (total - before) / before * 100
    return None


# Cuánto tienen que parecerse dos puntuaciones para que su diferencia de
# temperatura signifique algo. Si el equipo rindió un 20 % más, que esté más
# caliente se explica solo y no hay nada que avisar.
CLOSE_SCORE = 0.03

# El salto térmico a partir del cual se dice algo. Por debajo es ruido: la
# misma prueba dos veces seguidas ya varía un par de grados según cómo estuviera
# el equipo antes de empezar.
MIN_DRIFT_C = 4.0

# Cuántas pruebas viejas hacen falta para tener una referencia. Con una sola no
# se distingue una tendencia de un día raro.
MIN_TO_COMPARE = 3


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def thermal_drift(latest: Entry, previous: list[Entry]) -> Optional[tuple[float, int]]:
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
    if latest.temperature_peak_c is None:
        return None
    total = latest.total()
    if not total:
        return None

    references = []
    for other in previous:
        if other.timestamp >= latest.timestamp or not other.comparable_with(latest):
            continue
        if other.temperature_peak_c is None:
            continue
        own = other.total()
        if not own:
            continue
        if abs(own - total) / total > CLOSE_SCORE:
            continue
        references.append(other.temperature_peak_c)

    if len(references) < MIN_TO_COMPARE:
        return None
    difference = latest.temperature_peak_c - _median(references)
    if abs(difference) < MIN_DRIFT_C:
        return None
    return difference, len(references)


def clear() -> bool:
    """Borra el historial entero. Devuelve si había algo que borrar."""
    try:
        history_path().unlink()
        return True
    except OSError:
        return False


def remove(timestamp: float) -> list[Entry]:
    """Borra una prueba concreta por su marca de tiempo."""
    kept = [e for e in load() if e.timestamp != timestamp]
    save(kept)
    return kept


def remove_other_scales(version: int) -> list[Entry]:
    """Borra las pruebas medidas con otra escala que `version`.

    También las que no dicen con cuál se midieron: son de antes de que la
    escala tuviera número. Su cifra no se puede poner al lado de las de ahora.
    """
    kept = [e for e in load() if e.score_version == version]
    save(kept)
    return kept


def rename(timestamp: float, label: str) -> list[Entry]:
    """Le pone (o le quita) el nombre a una prueba."""
    entries = []
    for entry in load():
        if entry.timestamp == timestamp:
            entry = dataclasses.replace(entry, label=label.strip())
        entries.append(entry)
    save(entries)
    return entries
