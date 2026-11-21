"""Una prueba de rendimiento que dice en qué condiciones se hizo.

La cifra de un benchmark no vale nada por sí sola. El mismo procesador da
resultados muy distintos según el gobernador de energía, según lo caliente que
esté, según si otro programa le está robando la mitad de los núcleos. Quien
compara su número con el de internet y no cuadra se queda sin saber por qué.

Silux ya sabe leer todo eso mientras trabaja, así que aquí la prueba no
devuelve un número: devuelve un número **y las condiciones en las que salió**.
Si el gobernador estaba en ahorro, lo dice. Si la CPU bajó de frecuencia a
mitad de prueba, lo dice. Si había carga de fondo, avisa de que el resultado no
es comparable. Eso es lo que convierte una cifra en un diagnóstico.

Sobre las cargas: son de la biblioteca estándar, y no por comodidad. Compilar
un núcleo en C daría lo mismo (se probó: la misma estabilidad), pero dentro de
un AppImage no hay compilador, y una prueba que solo funciona desde el código
fuente no le sirve a quien descarga el programa. `zlib`, `bz2` y `hashlib`
tienen su bucle en C igualmente, ya compilado, y liberan el intérprete mientras
trabajan, así que reparten de verdad entre núcleos.

`SHA-512` y no `SHA-256` a propósito: la instrucción `sha_ni` acelera la
segunda y no la primera, así que con SHA-256 un procesador que la tenga saldría
inflado y dejaría de poder compararse con uno que no. Vale para las dos cargas
que usan hash, la del resumen y la de derivación de clave: en esta última el
efecto sería incluso mayor, porque son miles de rondas encadenadas.
"""

from __future__ import annotations

import bz2
import hashlib
import os
import pathlib
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

SYS_CPU = "/sys/devices/system/cpu"

# 4 MB con entropía media: ni tan repetido que la compresión sea trivial ni tan
# aleatorio que no haya nada que comprimir.
PATTERN = bytes(range(256)) * 16384
# Un trozo del anterior: la compresión pesada es tan lenta que con los 4 MB
# enteros cada operación tardaría más que la medida entera.
MEDIUM = PATTERN[:65536]

# Cuánto dura cada medida. Por debajo de tres segundos el resultado depende de
# si al turbo le dio tiempo a subir; por encima de diez, la prueba entera se
# hace larga sin cambiar la cifra.
SECONDS = 5.0
QUICK_SECONDS = 2.0
# Los extremos de lo que se puede pedir. Por debajo de uno la cifra depende de
# si al turbo le dio tiempo a subir; por encima de sesenta, la prueba se hace
# eterna para medir lo mismo que a los treinta.
MIN_SECONDS = 1.0
# Media hora por medida. Con seis medidas eso son tres horas de prueba, que es
# más de lo que nadie necesita, pero quien quiera dejar el equipo cociéndose
# toda la tarde para ver si aguanta tiene derecho a pedirlo.
MAX_SECONDS = 1800.0

# A partir de aquí, la carga de fondo estropea la medida.
ACCEPTABLE_LOAD = 10.0
# Y a partir de aquí, la frecuencia cayó lo bastante como para decirlo.
NOTABLE_DROP = 0.90


@dataclass(frozen=True, slots=True)
class Workload:
    """Una de las cosas que se le pide hacer al procesador."""

    key: str
    name: str
    explanation: str
    work: Callable[[], object]
    # Cuántos bytes recorre una operación. Solo lo declara la carga cuyo
    # bloque no mide lo mismo en todas las máquinas: contar «operaciones por
    # segundo» de un bloque que se dimensiona con la caché de cada equipo
    # premiaba a los procesadores con poca caché en un 42,8 %, porque una
    # operación sobre 64 MB no es la misma que sobre 192. Es una función y no
    # un número porque ese tamaño se decide al arrancar la prueba.
    bytes_per_op: Optional[Callable[[], int]] = None


# El bloque tiene que no caber en la caché, y cuánto es eso depende del
# procesador: un 5800X3D lleva 96 MB de L3 y se traga entero un bloque de 64,
# así que ahí la prueba mediría la caché y no la memoria. Se dimensiona al
# doble de la L3 que haya, con un suelo para las CPU pequeñas y un techo para
# no pedir media RAM prestada.
MIN_BLOCK_MB = 64
MAX_BLOCK_MB = 192
_big: Optional[bytes] = None


def _block_size_mb() -> int:
    """En megas: el doble de la caché de último nivel, entre 64 y 192."""
    largest = 0
    for index in range(5):
        raw = _read(f"{SYS_CPU}/cpu0/cache/index{index}/size")
        if not raw:
            continue
        try:
            value = int(raw.rstrip("KMG"))
        except ValueError:
            continue
        if raw.endswith("M"):
            value *= 1024
        elif raw.endswith("G"):
            value *= 1024 * 1024
        largest = max(largest, value // 1024)          # a megas
    return max(MIN_BLOCK_MB, min(MAX_BLOCK_MB, largest * 2 or MIN_BLOCK_MB))


def _big_block() -> bytes:
    global _big
    if _big is None:
        megabytes = _block_size_mb()
        _big = PATTERN * (megabytes * 1024 * 1024 // len(PATTERN))
    return _big


def _release_block() -> None:
    """Devuelve los megas del bloque al terminar la prueba.

    Son hasta 192 MB, y el programa entero se mueve en 130: dejarlos vivos
    después de medir dispararía el consumo el resto de la sesión por una
    prueba que dura medio minuto.
    """
    global _big
    _big = None


WORKLOADS: tuple[Workload, ...] = (
    Workload("compresion", "Compresión",
             "Comprimir es enteros y acceso a memoria, que es lo que hace el "
             "equipo al instalar un juego o abrir un proyecto grande.",
             lambda: zlib.compress(PATTERN, 9)),
    Workload("hash", "Resumen criptográfico",
             "Enteros puros y sin instrucciones especializadas: mide el núcleo, "
             "no una aceleración concreta.",
             lambda: hashlib.sha512(PATTERN).digest()),
    # bzip2 y no LZMA, y no es indiferente: ver `POR QUÉ NO LZMA` más abajo.
    Workload("compresion_dura", "Compresión pesada",
             "Lo mismo pero apretando de verdad: bzip2 ordena el bloque entero "
             "antes de comprimirlo, así que hace mucho más trabajo por byte y "
             "separa a un núcleo rápido de uno que solo tiene muchos hermanos.",
             lambda: bz2.compress(MEDIUM, 9)),
    Workload("derivacion", "Derivación de clave",
             "Miles de rondas encadenadas sin poder adelantar trabajo: es lo que "
             "hace un gestor de contraseñas al abrirse, y no lo acelera ninguna "
             "instrucción especial.",
             lambda: hashlib.pbkdf2_hmac("sha512", b"silux", b"benchmark", 12_000)),
    # Se llamaba «Memoria» y prometía medir el camino hasta la RAM. No lo
    # mide: con un bloque de 4 MB, que cabe de sobra en la caché, da lo mismo
    # que con 384 —21 GB/s en los dos—, porque el cuello lo pone el cálculo
    # del CRC y no la memoria (la RAM de esa misma máquina da 48,5 GB/s
    # medidos con `membench`). Lo que sí es cierto es que de las cinco es la
    # que menos gana con los hilos.
    Workload("verificacion", "Suma de verificación",
             "Recorre un bloque grande calculando una suma de comprobación. El "
             "cuello lo pone el propio cálculo y no la RAM, así que mide enteros "
             "y no el camino hasta la memoria: de eso se encarga la página de "
             "Memoria, que sí lo mide.",
             lambda: zlib.crc32(_big_block()),
             bytes_per_op=lambda: len(_big_block())),
)

# POR QUÉ NO LZMA. La compresión pesada fue `lzma.compress(MEDIO, preset=0)`
# hasta que se midió de qué venía la dispersión de la puntuación multihilo.
# LZMA alterna entre dos velocidades —25 800 y 32 500 operaciones por segundo
# en un 5800X3D, un 26 % de diferencia— según le llueva o no una tormenta de
# fallos de página: 280 000 por segundo contra ninguno, de los búferes que
# pide en cada llamada. El estado se decide por proceso, tarda entre cero y
# más de veinticinco segundos en asentarse, y a veces no se asienta; dentro de
# una misma medida es plano, así que alargarla no lo promedia, lo hereda. Con
# eso, la puntuación entera dispersaba un 4,7 % entre repeticiones del mismo
# equipo, y quitando esta carga, un 0,3 %: era ella sola.
#
# Se probó a domarla y no se pudo. Rodar más no basta porque a veces no se
# calma nunca. `mallopt` con el umbral de `mmap` fijo lo empeora —a 256 KB
# baja a 4 787 op/s— porque fijarlo apaga el ajuste dinámico de glibc, que es
# justo lo que llevaba al estado bueno. Bajar el diccionario lo hunde a un
# tercio y subirlo a 1 MB, a un octavo. Y no es el asignador y ya: con
# `preset=1` los fallos casi desaparecen y sigue dispersando un 18 %, o sea
# que LZMA tiene además otra fuente de inestabilidad que no se aisló.
#
# bzip2 no tiene ninguna de las dos: dispersa un 2,1 % en vez de un 20,6 % y
# reparte igual de bien (×9.9 con dieciséis hilos, contra ×10.9). Es más lenta
# en operaciones por segundo, y da igual: lo que se compara es contra el
# patrón, no contra otra carga.

# No hay carga de coma flotante, y no es un olvido. Todo lo que la haría en
# Python sin dependencias —sumar, multiplicar listas— tiene el bucle en C pero
# manejando objetos del intérprete, así que no suelta el GIL: medido aquí,
# escala ×1.0 con dieciséis hilos. Una prueba multihilo que no reparte no mide
# el procesador, mide el candado.

# QUÉ SE PERDIÓ AL QUITAR ZLIB DE LA PUNTUACIÓN. Desde la v6 puntúan dos de
# las cinco —el resumen y la compresión pesada—, que son las únicas cuya
# implementación no cambia con la distribución. El porqué, con las cifras,
# está en `score.PUNTUABLES`; aquí está lo que costó, que es lo que hay que
# recuperar y no se ha recuperado.
#
# No se fueron «tres cargas»: se fue un perfil. De las cinco, las dos únicas
# donde tener más hilos por núcleo *resta* estaban entre las que salieron.
# Medido en un i5-10400, doce hilos contra sus seis núcleos físicos:
#
#     compresión           +0,5 %
#     resumen              +4,0 %
#     compresión pesada   +15,0 %
#     derivación           −5,3 %
#     verificación        −13,1 %
#
# Con las cinco, el SMT sale a +0,2 % neto y la puntuación dice que doce hilos
# rinden como seis núcleos (481 contra 483). Con las dos que quedan sale a
# +9,5 %. La cifra no deja de distinguir piezas por esto —las distancias
# medidas entre cuatro configuraciones se mantienen o crecen—, pero premia el
# SMT más de lo que el equipo da en un abanico de trabajos.
#
# La carga que taparía el hueco tiene que ser código máquina propio, como el
# que `membench` ya usa: es lo único que no cambia de un entorno a otro. El
# mismo kernel da 12,95 y 13,02 millones de saltos por segundo en Python 3.14
# y en 3.10 (±0,7 %), donde el sha512 que CPython trae dentro se va al doble
# entre esas dos versiones y zlib a un ×9,7 entre distribuciones.
#
# Y tiene dos condiciones más, las dos medidas y ninguna evidente:
#
# 1. **De lectura secuencial, no de latencia.** El kernel de persecución de
#    punteros que ya existe no sirve para esto: escala ×12,24 con doce hilos,
#    o sea premia el SMT todavía más que las dos que quedan, porque la
#    latencia es justo lo que el SMT tapa. Lo que hace falta es saturar el
#    bus: leyendo, un i5-10400 da 21-27 GB/s con un hilo, 32 con seis y 29 con
#    doce, o sea ×0,89 al pasar de seis a doce. Más hilos estorban, que es el
#    perfil que falta.
#
# 2. **Un bloque propio por hilo.** Con el bloque compartido —que es lo que
#    hace la verificación con su `_bloque_grande()` global— los hilos recorren
#    en fila el mismo camino y se sirven unos a otros desde la caché: doce
#    hilos «miden» 131 GB/s en un equipo cuya RAM da 32. Ese es el fallo que
#    no hay que repetir, y explica de paso por qué el ×5,96 de escalado de esa
#    carga nunca fue el camino hasta la memoria.


@dataclass(frozen=True, slots=True)
class Measure:
    """El resultado de una carga con un número de hilos."""

    load: str
    threads: int
    operations: int
    seconds: float
    # Los bytes que recorrió cada operación, si la carga lo declara.
    bytes_: Optional[int] = None

    @property
    def per_second(self) -> float:
        return self.operations / self.seconds if self.seconds else 0.0

    @property
    def rate(self) -> float:
        """Lo que se puntúa: bytes por segundo donde el tamaño varía.

        Es la cifra que no depende de cómo de grande sea el bloque en esta
        máquina. Donde la carga tiene una entrada fija —las otras cuatro— las
        dos formas son proporcionales y da lo mismo, así que se sigue contando
        por operaciones y no hace falta declarar nada.
        """
        if not self.seconds:
            return 0.0
        if self.bytes_ is None:
            return self.operations / self.seconds
        return self.operations * self.bytes_ / self.seconds


@dataclass(frozen=True, slots=True)
class Conditions:
    """En qué estado estaba la máquina mientras se medía."""

    # Lo que ocupaba otro programa mientras se medía, no antes de empezar. Son
    # dos preguntas distintas y la segunda es la que importa: una prueba de
    # quince segundos por carga dura dos minutos y medio, y `background_load`
    # se tomaba en tres décimas antes del primer paso. Con eso, alguien que
    # abriera el navegador a mitad salía con «0 % de carga de fondo» y una
    # cifra baja sin explicación.
    background_peak: Optional[float] = None
    frequency_avg_hz: Optional[int] = None
    frequency_peak_hz: Optional[int] = None
    frequency_end_hz: Optional[int] = None
    temperature_start_c: Optional[float] = None
    temperature_peak_c: Optional[float] = None
    governor: Optional[str] = None
    energy_preference: Optional[str] = None
    background_load: Optional[float] = None

    @property
    def throttled(self) -> bool:
        """Si la frecuencia cayó de forma apreciable durante la prueba."""
        if not (self.frequency_peak_hz and self.frequency_end_hz):
            return False
        return self.frequency_end_hz < self.frequency_peak_hz * NOTABLE_DROP


@dataclass(frozen=True, slots=True)
class Result:
    """Las medidas y el contexto que dice si valen."""

    measures: tuple[Measure, ...] = ()
    conditions: Conditions = field(default_factory=Conditions)
    warnings: tuple[str, ...] = ()

    def find(self, load: str, threads: int) -> Optional[Measure]:
        return next((m for m in self.measures
                     if m.load == load and m.threads == threads), None)

    def scaling(self, load: str, threads: int) -> Optional[float]:
        """Cuánto multiplica el rendimiento al usar todos los hilos."""
        one = self.find(load, 1)
        many = self.find(load, threads)
        if not (one and many and one.per_second):
            return None
        return round(many.per_second / one.per_second, 1)


def run(quick: bool = False, on_progress: Optional[Callable[[str, float], None]] = None,
        stop: Optional[threading.Event] = None,
        seconds: Optional[float] = None,
        loads: Optional[Sequence[str]] = None) -> Result:
    """Ejecuta la prueba entera. Bloquea: llámese desde un hilo aparte.

    `on_progress` recibe qué se está midiendo y cuánto se lleva, de 0 a 1.
    `stop` permite cancelar entre medidas.
    `seconds` fija cuánto dura cada medida; sin él manda `quick`.
    `loads` son las claves de las cargas que se miden; sin él, todas. Van en
    el orden de la prueba, no en el que se pidan. Un resultado con menos
    cargas de las que puntúan no da puntuación: es para medir una cosa suelta.

    Alargar la prueba no cambia la cifra, cambia en qué condiciones se toma:
    a los cinco segundos el turbo ya subió y el disipador aún no se ha
    calentado, mientras que a los treinta se mide con el equipo asentado, que
    es lo que de verdad va a pasar mientras se juega o se compila.
    """
    duration = (max(MIN_SECONDS, min(MAX_SECONDS, float(seconds)))
                if seconds else (QUICK_SECONDS if quick else SECONDS))
    threads = os.cpu_count() or 1
    workloads = WORKLOADS
    if loads is not None:
        if unknown := set(loads) - {workload.key for workload in WORKLOADS}:
            raise ValueError(f"no hay ninguna carga llamada {sorted(unknown)}")
        workloads = tuple(workload for workload in WORKLOADS if workload.key in loads)
    watcher = _Watcher()

    background = _background_load()
    start_temperature = _temperature()

    steps = [(workload, n) for workload in workloads for n in (1, threads)]
    measures: list[Measure] = []
    watcher.start()
    try:
        for index, (workload, n) in enumerate(steps):
            if stop is not None and stop.is_set():
                break
            if on_progress:
                label = f"{workload.name}, {n} {'hilo' if n == 1 else 'hilos'}"
                on_progress(label, index / len(steps))
            measures.append(_measure(workload, n, duration))
    finally:
        watcher.stop()
        _release_block()

    if on_progress:
        on_progress("listo", 1.0)

    conditions = Conditions(
        frequency_avg_hz=watcher.average(),
        frequency_peak_hz=watcher.peak(),
        frequency_end_hz=watcher.final(),
        temperature_start_c=start_temperature,
        temperature_peak_c=watcher.temperature_peak(),
        governor=_read(f"{SYS_CPU}/cpu0/cpufreq/scaling_governor"),
        energy_preference=_read(f"{SYS_CPU}/cpu0/cpufreq/energy_performance_preference"),
        background_load=background,
        background_peak=watcher.stolen_peak(),
    )
    return Result(tuple(measures), conditions, _warnings(conditions))


# -- ejecución ---------------------------------------------------------------

# Unas vueltas que no se cuentan, antes de cada medida. La primera vez que una
# carga corre en un proceso da una cifra distinta de todas las siguientes, y lo
# que se paga ahí no es del procesador sino del asignador, que sirve con `mmap`
# los búferes holgados hasta que glibc sube su umbral por su cuenta.
#
# Con la compresión pesada de entonces —LZMA— la diferencia era del 65 %:
# 1 780 operaciones por segundo la primera vez y 2 950 a partir de la segunda.
# Con bzip2 es del 2,7 % a un hilo (151,7 la primera y 156,0 después), porque
# no pide en cada llamada un búfer que cruce el umbral. Sigue mereciendo la
# pena: cuesta unas centésimas y quita un sesgo que caía siempre en la misma
# cifra, la de un hilo, por medirse antes que las demás.
#
# Con unas ochenta vueltas ya está en régimen; se dejan ciento veinte de
# margen. Lo que el rodaje no arregla es la inestabilidad de LZMA que la sacó
# de aquí: esa no se calma en ningún número de vueltas.
IDLE_ROUNDS = 120

# Tope por si la carga es lentísima en un equipo modesto: más vale medir con
# el arranque a medio pagar que dejar la prueba colgada un minuto por carga.
IDLE_CAP_S = 2.0


def _warm_up(workload: "Workload", threads: int) -> None:
    """Deja la carga en régimen para que la medida no pague su arranque.

    Como el orden es un hilo primero y todos después, ese arranque lo pagaba
    siempre la medida de un hilo: la escala entre uno y todos salía en catorce
    veces con un procesador de ocho núcleos.
    """
    # Se cuentan vueltas y no segundos. Lo que hay que dejar atrás es el
    # arranque de la carga, que son unas ochenta llamadas, y eso no dura lo
    # mismo en un Ryzen que en un portátil de hace diez años: medio segundo
    # aquí son cientos de vueltas y allí puede que ninguna.
    end = time.perf_counter() + IDLE_CAP_S

    def loop() -> None:
        work = workload.work
        for _round in range(IDLE_ROUNDS):
            if time.perf_counter() > end:
                break
            work()

    workers = [threading.Thread(target=loop, daemon=True)
               for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=IDLE_CAP_S + 5)


def _measure(workload: Workload, threads: int, duration: float) -> Measure:
    """Cuenta cuántas veces cabe la carga en el tiempo dado.

    Se mide por tiempo y no por trabajo fijo porque una cantidad que en un
    Ryzen tarda un segundo, en un portátil de hace diez años tarda treinta.
    """
    _warm_up(workload, threads)
    stop = threading.Event()
    count = [0] * threads

    def loop(index: int) -> None:
        rounds = 0
        work = workload.work
        while not stop.is_set():
            work()
            rounds += 1
        count[index] = rounds

    workers = [threading.Thread(target=loop, args=(i,), daemon=True)
               for i in range(threads)]
    start = time.perf_counter()
    for worker in workers:
        worker.start()
    time.sleep(duration)
    stop.set()
    for worker in workers:
        worker.join(timeout=10)
    elapsed = time.perf_counter() - start

    return Measure(load=workload.key, threads=threads,
                  operations=sum(count), seconds=elapsed,
                  bytes_=workload.bytes_per_op() if workload.bytes_per_op else None)


# Aquí vivían `_fijar_afinidad` y `_nucleo_preferido`, que ataban el hilo de
# la medida de un núcleo al que el firmware señala como mejor. La idea era
# quitar ruido —un hilo que salta de núcleo tira la caché— y hacía justo lo
# contrario: medida contra medida, atarlo cuesta un 40 % en la compresión
# pesada y un 11 % en la derivación de clave, y la dispersión entre
# repeticiones sale igual o peor que dejándolo suelto.
#
# Y como la afinidad solo se fijaba al medir con un hilo, esa penalización
# caía siempre en la misma cifra. La prueba entera daba 1 771 operaciones por
# segundo a un hilo y 24 842 a dieciséis: una escala de catorce veces en un
# procesador de ocho núcleos, que no es posible. Sin atar nada sale 3 004 y
# 24 099, ocho veces, que es lo que dan las otras cuatro cargas.
#
# Si algún día vuelve a hacer falta, que sea con una medición delante: la
# dispersión sin atar, en este equipo y con el gobernador en «performance»,
# fue del 1,3 % al 3,3 % según la carga.


# -- contexto ----------------------------------------------------------------

class _Watcher:
    """Sigue la frecuencia y la temperatura mientras se mide."""

    def __init__(self) -> None:
        self._frequencies: list[int] = []
        self._temperatures: list[float] = []
        self._stolen: list[float] = []
        self._cpu_before = _jiffies()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Solo cuenta la frecuencia más alta del momento: la media de todos
            # los núcleos, con la mitad dormidos, no dice a qué fue el trabajo.
            current = [_read_int(f"{SYS_CPU}/cpu{i}/cpufreq/scaling_cur_freq")
                     for i in range(os.cpu_count() or 1)]
            valid = [p for p in current if p]
            if valid:
                self._frequencies.append(max(valid) * 1000)
            if (degrees := _temperature()) is not None:
                self._temperatures.append(degrees)
            if (stolen := self._stolen_now()) is not None:
                self._stolen.append(stolen)
            self._stop_event.wait(0.25)

    def _stolen_now(self) -> Optional[float]:
        """Qué parte de la máquina se lleva otro programa, ahora mismo.

        No vale mirar `/proc/stat` a secas mientras la prueba corre: la prueba
        ocupa el equipo entero y todo saldría al cien por cien. Lo que se busca
        es la resta, lo ocupado menos lo que consume este mismo proceso, que es
        justo lo que le está quitando sitio a la medida.
        """
        now = _jiffies()
        before, self._cpu_before = self._cpu_before, now
        if now is None or before is None:
            return None
        total, idle, own = now
        total_before, idle_before, own_before = before
        elapsed = total - total_before
        if elapsed <= 0:
            return None
        busy = elapsed - (idle - idle_before)
        stolen = busy - (own - own_before)
        # Puede salir negativo por unas centésimas: los dos ficheros no se leen
        # en el mismo instante. Cero es la respuesta, no un error.
        return max(0.0, stolen / elapsed * 100)

    def average(self) -> Optional[int]:
        return int(sum(self._frequencies) / len(self._frequencies)) if self._frequencies else None

    def peak(self) -> Optional[int]:
        return max(self._frequencies) if self._frequencies else None

    def final(self) -> Optional[int]:
        """La media del último tramo, para ver si acabó más baja que empezó."""
        if len(self._frequencies) < 8:
            return self._frequencies[-1] if self._frequencies else None
        tail = self._frequencies[-len(self._frequencies) // 4:]
        return int(sum(tail) / len(tail))

    def temperature_peak(self) -> Optional[float]:
        return max(self._temperatures) if self._temperatures else None

    def stolen_peak(self) -> Optional[float]:
        """Lo más que llegó a robarle otro programa durante la prueba.

        El pico y no la media: lo que estropea una medida es que algo se
        despierte a mitad, y promediado entre dos minutos y medio eso se diluye
        hasta parecer nada.
        """
        return round(max(self._stolen), 1) if self._stolen else None


def _warnings(conditions: Conditions) -> tuple[str, ...]:
    """Lo que hay que saber antes de comparar esta cifra con otra."""
    warnings = []
    if conditions.background_load and conditions.background_load > ACCEPTABLE_LOAD:
        warnings.append(
            f"Había un {conditions.background_load:.0f} % de carga de fondo al "
            "empezar. El resultado no es comparable con el de una máquina en "
            "reposo."
        )
    # Lo de arriba mira cómo estaba el equipo antes de empezar; esto, lo que
    # pasó mientras se medía. Son preguntas distintas y la segunda es la que
    # estropea una prueba: quien la lanza y se va a hacer otra cosa, o quien
    # tiene una actualización en marcha sin saberlo, salía con «0 % de carga de
    # fondo» y una cifra baja que no tenía explicación en ninguna parte.
    if (conditions.background_peak
            and conditions.background_peak > ACCEPTABLE_LOAD):
        warnings.append(
            f"Otro programa llegó a llevarse el "
            f"{conditions.background_peak:.0f} % de la máquina mientras se "
            "medía. La cifra sale más baja de lo que da este equipo en reposo."
        )
    if conditions.governor and conditions.governor not in ("performance",):
        warnings.append(
            f"El gobernador de energía estaba en «{conditions.governor}». "
            "En «performance» la cifra sería más alta."
        )
    if conditions.throttled:
        peak = conditions.frequency_peak_hz or 0
        final = conditions.frequency_end_hz or 0
        warnings.append(
            f"La frecuencia bajó de {peak / 1e9:.2f} a {final / 1e9:.2f} GHz "
            "durante la prueba: el procesador no pudo sostener su máximo."
        )
    return tuple(warnings)


def _jiffies() -> Optional[tuple[int, int, int]]:
    """Del sistema: totales e inactivos; y lo que lleva gastado este proceso.

    Los tres a la vez y del mismo instante, porque lo que se busca es la resta
    entre ellos.
    """
    try:
        with open("/proc/stat", encoding="utf-8") as handle:
            numbers = [int(x) for x in handle.readline().split()[1:8]]
        with open(f"/proc/{os.getpid()}/stat", encoding="utf-8") as handle:
            fields = handle.read().rsplit(")", 1)[1].split()
        # utime + stime, que es lo que este proceso ha consumido de CPU.
        own = int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None
    if len(numbers) < 5:
        return None
    return sum(numbers), numbers[3] + numbers[4], own


def _background_load() -> Optional[float]:
    """Qué porcentaje de la máquina está ocupado antes de empezar."""
    def snapshot() -> Optional[tuple[int, int]]:
        try:
            with open("/proc/stat", encoding="utf-8") as handle:
                fields = handle.readline().split()
        except OSError:
            return None
        if len(fields) < 5:
            return None
        numbers = [int(c) for c in fields[1:8] if c.isdigit()]
        return sum(numbers), numbers[3]        # total, inactivo

    before = snapshot()
    if before is None:
        return None
    time.sleep(0.3)
    after = snapshot()
    if after is None or after[0] == before[0]:
        return None
    busy = (after[0] - before[0]) - (after[1] - before[1])
    return round(busy / (after[0] - before[0]) * 100, 1)


def _temperature() -> Optional[float]:
    """La del procesador, del primer chip que la publique."""
    for index in range(16):
        name = _read(f"/sys/class/hwmon/hwmon{index}/name")
        if name in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
            millidegrees = _read_int(f"/sys/class/hwmon/hwmon{index}/temp1_input")
            if millidegrees:
                return round(millidegrees / 1000, 1)
    return None


def _read(path: str) -> Optional[str]:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    raw = _read(path)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None
