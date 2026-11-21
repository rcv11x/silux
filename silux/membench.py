"""Cuánto se mueve de verdad la memoria de este equipo.

Los MT/s del SPD dicen a qué velocidad está catalogado el módulo, y el ancho
de banda teórico sale de una multiplicación. Ninguno de los dos dice lo que la
máquina consigue: eso hay que medirlo, y es lo que se echa de menos frente a
lo que enseña AIDA64 en Windows.

Se mide leyendo, con `memchr` buscando un byte que no está: recorre el bloque
entero a velocidad de memoria y no necesita destino, así que gasta la mitad
que copiar y la cifra sale de una lectura pura, que es la comparable. El bucle
está en la libc, ya compilado, porque dentro de un AppImage no hay compilador
con el que generar nada al vuelo.

**Y la propia herramienta tiene un techo, que hay que medir.** `memchr` no pasa
de unos 112 GB/s en el equipo donde se escribió esto, y ese número no lo pone
la memoria: bloques de 1, 4, 16 y 48 MB —que caben en cachés distintas— dan
los cuatro lo mismo, y hasta la L1 con el coste de la llamada descontado se
queda ahí. Un bloque que quepa en la caché no mide la caché: mide hasta dónde
llega esta forma de medir.

Por eso se mide igualmente, pero como control y no como dato. Si el ancho de
banda de la RAM se acerca a ese techo, la cifra está limitada por la
herramienta y la memoria puede ser más rápida de lo que se enseña; eso pasa en
un equipo con memoria muy rápida, y callarlo sería dar una cifra baja con cara
de medida.

**Lo que todavía no se mide aquí, y por qué.** La latencia en nanosegundos no
sale con lo que trae la libc, y se probaron dos caminos antes de dejarla fuera
de esta primera versión:

- Con muchos accesos aleatorios sueltos sale plana —9.7 ns en 16 KB y 11.2 en
  256 MB— porque no dependen unos de otros y el procesador los solapa. La
  latencia real de esa máquina va de un nanosegundo a ochenta.
- Con búsqueda binaria, que sí encadena cada salto con el anterior, hay señal
  (22 ns por salto dentro de la caché y 42 fuera), pero para convertirlo en un
  número hay que suponer cuántos niveles del árbol están cacheados y descontar
  el coste de la llamada. Serían tres suposiciones sosteniendo una cifra.

Sí sale escribiendo el bucle en código máquina, que es lo que hace
`rawcpuid.py` para llamar a CPUID: doce bytes persiguiendo punteros dan 0,9 ns
en L1 y 76,1 en RAM en el equipo de casa. Está probado y pendiente de integrar,
con una trampa apuntada: si se dan menos saltos que líneas tiene el array, la
cadena recorrida cabe en la caché y se mide la caché creyendo que se mide la
RAM.

Y tampoco se miden la L1 ni la L2 por este camino: una llamada cuesta 570 ns, y
en un bloque de 32 KB eso es casi todo el tiempo. Desde un mega baja del 2 %,
así que se mide de ahí hacia arriba y lo demás se deja sin medir en vez de
inventarlo.
"""

from __future__ import annotations

import ctypes
import json
import mmap
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

from . import rawcpuid

# Por debajo de esto la llamada pesa más que la memoria y la cifra deja de
# hablar del equipo para hablar de ctypes.
MIN_RELIABLE = 1024 * 1024

# Cuánto hay que pasarse del tamaño de la caché para estar seguro de que se
# está midiendo la RAM. Con el doble todavía cabe media tirada en la caché;
# con el triple, lo que se lee viene de fuera.
TIMES_PAST_CACHE = 3

# Un tope, porque hay Threadripper con 256 MB de caché y el triple de eso no
# lo debe pedir un programa que enseña fichas. Si no se llega a este tamaño la
# medida de RAM se salta y se dice.
MAX_BLOCK = 512 * 1024 * 1024

# Lo que se deja libre en el equipo pase lo que pase. Medir no puede ser el
# motivo de que algo se vaya a la swap.
FREE_MARGIN = 512 * 1024 * 1024

# Cuánto tiempo se le dedica a cada bloque. Iba por número de vueltas y salían
# tres para el bloque de RAM: con tan pocas basta que una tanda pille el equipo
# ocupado para que la cifra salga un 15 % baja, y quien pulsa el botón ve un
# número distinto cada vez sin que su memoria haya cambiado. Repartiendo por
# tiempo, un bloque pequeño da cientos de vueltas y uno grande las que quepan,
# y en los dos casos hay de dónde sacar un mínimo que signifique algo.
TIME_BUDGET_S = 0.15
MIN_PASSES = 5
MAX_PASSES = 500

# Persigue punteros: cada lectura da la dirección de la siguiente, así que el
# procesador no puede adelantarse y lo que se cronometra es lo que tarda un
# acceso. Es lo que no se puede escribir en Python, donde el intérprete cuesta
# más que el propio acceso.
#
#   mov rax, rdi        48 89 f8     rdi = primer eslabón
# bucle:
#   mov rax, [rax]      48 8b 00     <- depende del resultado anterior
#   dec rsi             48 ff ce     rsi = cuántos saltos
#   jnz bucle           75 f8
#   ret                 c3
_CHASE_CODE = bytes((0x48, 0x89, 0xF8,
                           0x48, 0x8B, 0x00,
                           0x48, 0xFF, 0xCE,
                           0x75, 0xF8,
                           0xC3))

# Una línea de caché. Se salta de una a otra porque leer dos veces la misma
# línea sale de la misma lectura y no mide nada.
LINE = 64

# Cuántos saltos se dan como mínimo, para que el coste de entrar y salir de la
# llamada —570 ns— no pese: en la L1 un acceso son 0,9 ns, así que con pocos
# saltos se estaría cronometrando ctypes otra vez.
MIN_HOPS = 200_000

# Y un tope de eslabones, que es lo que cuesta tiempo de verdad: barajarlos y
# enlazarlos son bucles de Python. Con seis millones se van cuatro segundos
# antes de medir nada. Con este tope, un procesador de caché normal se prepara
# en décimas y uno con una L3 enorme se queda sin la latencia de RAM y lo dice,
# que es mejor que tener el botón parado cinco segundos.
MAX_LINKS = 4_000_000

# Para la latencia basta con el doble de la caché: con dos, tres y cuatro veces
# salen 80,0, 83,6 y 80,8 ns, o sea lo mismo, y cada vez que se dobla el bloque
# se dobla el tiempo de preparar la cadena. Para el ancho de banda se usa el
# triple porque allí no hay cadena que construir y no cuesta nada.
TIMES_PAST_FOR_LATENCY = 2

# Un tope al bloque con el que se mide una caché, además de su fracción. La L3
# de un Zen 3 es caché de víctimas —solo guarda lo que se expulsa de la L2—, así
# que con la mitad de sus 96 MB recorridos al azar ya casi no retiene nada: da
# 66 ns donde tiene que dar 12. Con 4, 8 y 16 MB sale 11,9, 12,0 y 13,2, así que
# el escalón está bastante por debajo de la mitad y hay que quedarse abajo.
MAX_CACHE_BLOCK = 16 * 1024 * 1024

# Páginas de 2 MB en vez de 4 KB. Perseguir punteros por 288 MB toca 73728
# páginas y el TLB de datos guarda unas 2000, así que cada acceso pagaba además
# un recorrido de tablas: 94,7 ns con páginas normales contra 82,1 con grandes.
# Es un consejo, no una orden: si el sistema las tiene desactivadas no pasa nada.
MADV_HUGEPAGE = 14
HUGE_PAGE = 2 * 1024 * 1024

TIMEOUT_S = 60


@dataclass(frozen=True)
class Measurement:
    """Una lectura de un bloque de un tamaño concreto."""

    bytes_: int
    bandwidth_bytes: int
    # "ram" es el dato; "techo" es el control: un bloque que cabe en la caché,
    # que no mide la caché sino lo más rápido que puede ir esta herramienta.
    where: str                       # "techo" | "ram"


@dataclass(frozen=True)
class Latency:
    """Lo que tarda un acceso que no se puede adelantar, por nivel."""

    level: str                       # "L1", "L2", "L3", "RAM"
    bytes_: int
    nanoseconds: float


@dataclass(frozen=True)
class MemoryResult:
    measurements: tuple[Measurement, ...] = ()
    latencies: tuple[Latency, ...] = ()
    # Por qué faltan latencias, que no es lo mismo que por qué falta el ancho
    # de banda: se puede tener una cosa y no la otra.
    latency_reason: Optional[str] = None
    # Por qué no se pudo medir algo, para poder decirlo en vez de callar.
    reason: Optional[str] = None


def _libc():
    libc = ctypes.CDLL(None)
    libc.memchr.restype = ctypes.c_void_p
    libc.memchr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
    return libc


def _best_pass(libc, address: int, n: int) -> float:
    """El mejor tiempo de recorrer el bloque, en segundos.

    El mejor y no la media: lo que se busca es lo que da el equipo cuando nadie
    le estorba, y cualquier interrupción solo puede empeorar una vuelta. Por eso
    hacen falta unas cuantas: con el mínimo de tres que había antes, una tanda
    entera podía caer dentro de la interferencia y no había ninguna vuelta
    limpia de la que fiarse.
    """
    libc.memchr(address, 0xFF, n)                 # calentar
    best = None
    spent = 0.0
    passes = 0
    while passes < MIN_PASSES or (spent < TIME_BUDGET_S
                                       and passes < MAX_PASSES):
        start = time.perf_counter()
        libc.memchr(address, 0xFF, n)
        elapsed = time.perf_counter() - start
        spent += elapsed
        passes += 1
        best = elapsed if best is None else min(best, elapsed)
    return best or 0.0


def _available_memory() -> Optional[int]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _reserve(size: int):
    """Un bloque alineado a 2 MB y con páginas grandes pedidas.

    Se pide con `mmap` y no con un búfer de ctypes porque la alineación es lo
    que el kernel exige para poder juntar las páginas, y un búfer normal cae
    donde caiga.
    """
    # Private: `mmap(-1)` alone is shared anonymous memory, which only gets
    # huge pages where shmem THP is on (it is off in Fedora). Without them the
    # TLB misses went into the latency: RAM read 72 ns there instead of 62.
    try:
        mapping = mmap.mmap(-1, size + HUGE_PAGE,
                         flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                         prot=mmap.PROT_READ | mmap.PROT_WRITE)
    except (OSError, ValueError):
        return None
    raw_address = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
    base = (raw_address + HUGE_PAGE - 1) & ~(HUGE_PAGE - 1)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.madvise.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.madvise(ctypes.c_void_p(base), size, MADV_HUGEPAGE)
    return mapping, base


def _chain(base: int, lines: int) -> int:
    """Enlaza `lineas` líneas del bloque en un ciclo aleatorio.

    Devuelve la dirección del primer eslabón. El orden es aleatorio a propósito:
    con un salto constante el prefetcher lo adivina y se mide lo que tarda en
    llegar un dato que ya venía de camino, no lo que tarda un acceso.
    """
    order = list(range(lines))
    random.shuffle(order)
    view = (ctypes.c_uint64 * (lines * LINE // 8)).from_address(base)
    followers = order[1:]
    followers.append(order[0])
    for current, following in zip(order, followers):
        view[current * (LINE // 8)] = base + following * LINE
    return base + order[0] * LINE


def _latency(chase, first: int, hops: int) -> float:
    """Nanosegundos por acceso, del mejor intento."""
    chase(first, min(hops, 100_000))          # calentar
    best = None
    for _attempt in range(3):
        start = time.perf_counter()
        chase(first, hops)
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return (best or 0.0) / hops * 1e9


def measure_latencies(levels: "list[tuple[str, int]]") -> tuple:
    """Mide un nivel por cada caché, y la RAM detrás.

    `niveles` son pares de nombre y tamaño, del más pequeño al más grande. De
    cada uno se recorre la mitad, para que la cadena quepa de sobra dentro; de
    la RAM, el triple de la caché mayor, para que no quepa de ninguna manera.
    """
    if not rawcpuid.is_supported():
        return (), "no_x86"
    try:
        mm, address = rawcpuid.executable_page(_CHASE_CODE)
    except Exception:                                          # noqa: BLE001
        # Un entorno que prohíbe ejecutar memoria anónima. Sin latencias, pero
        # el resto de la medida sigue valiendo.
        return (), "sin_ejecutable"

    chase = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_size_t)(address)
    results = []
    reason = None
    try:
        largest = max((size for _name, size in levels), default=0)
        spans = [(name, min(size // 2, MAX_CACHE_BLOCK))
                  for name, size in levels if size // 2 >= LINE * 8]
        spans.append(("RAM", max(MIN_RELIABLE * 64,
                                  largest * TIMES_PAST_FOR_LATENCY)))
        available = _available_memory()
        for name, size in spans:
            lines = size // LINE
            if lines > MAX_LINKS:
                # Preparar la cadena son bucles de Python: seis millones de
                # eslabones se llevan cuatro segundos antes de medir nada.
                reason = reason or "cadena_enorme"
                continue
            if available is not None and size + FREE_MARGIN > available:
                reason = reason or "sin_memoria"
                continue
            block = _reserve(size)
            if block is None:
                reason = reason or "sin_memoria"
                continue
            mapping, base = block
            first = _chain(base, lines)
            # Al menos dos vueltas al ciclo entero: con menos saltos que líneas,
            # lo recorrido cabe en la caché y se mide la caché creyendo que se
            # mide la RAM. Salían 28 ns donde hay 76.
            hops = max(MIN_HOPS, lines * 2)
            results.append(Latency(name, size, round(
                _latency(chase, first, hops), 1)))
            mapping.close()
    finally:
        mm.close()
    return tuple(results), reason


def in_this_process(cache_bytes: Optional[int],
                    levels: "Optional[list]" = None) -> MemoryResult:
    """Mide de verdad.

    `cache_bytes` es la caché más grande, y decide los bloques del ancho de
    banda. `niveles` son los pares de nombre y tamaño de cada caché, que es lo
    que hace falta para las latencias; sin ellos se mide solo el ancho de banda.
    """
    libc = _libc()
    measurements: list[Measurement] = []
    available = _available_memory()

    # El techo: un bloque que cabe de sobra en la caché, así que lo que limita
    # ahí no es la memoria. La mitad de la caché, para que quepa con holgura
    # aunque el sistema esté usando una parte.
    if cache_bytes and cache_bytes // 2 >= MIN_RELIABLE:
        n = cache_bytes // 2
        block = ctypes.create_string_buffer(n)
        seconds = _best_pass(libc, ctypes.addressof(block), n)
        if seconds > 0:
            measurements.append(Measurement(n, int(n / seconds), "techo"))
        del block

    # Fuera de toda caché, que es el ancho de banda de la RAM.
    n = max(MIN_RELIABLE * 64,
            (cache_bytes or 0) * TIMES_PAST_CACHE)
    if n > MAX_BLOCK or (available is not None
                             and n + FREE_MARGIN > available):
        latencies, why = measure_latencies(levels or [])
        return MemoryResult(tuple(measurements),
                         latencies, why,
                         reason=("cache_enorme" if n > MAX_BLOCK
                                 else "sin_memoria"))
    block = ctypes.create_string_buffer(n)
    seconds = _best_pass(libc, ctypes.addressof(block), n)
    if seconds > 0:
        measurements.append(Measurement(n, int(n / seconds), "ram"))
    del block
    latencies, why = measure_latencies(levels or [])
    return MemoryResult(tuple(measurements), latencies, why)


def query(cache_bytes: Optional[int],
              levels: "Optional[list]" = None) -> MemoryResult:
    """Mide en otro proceso, que es donde puede pedir cientos de megas.

    Para salirse de una caché de 96 MB hace falta un bloque de casi trescientos,
    y el programa entero tiene un presupuesto de 300. Aquí se pide, se mide y
    se muere; lo que queda en esta memoria es una cifra.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "silux.membench", str(cache_bytes or 0),
             json.dumps(levels or [])],
            capture_output=True, timeout=TIMEOUT_S, env=env, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return MemoryResult(reason="no_arranco")
    if completed.returncode != 0 or not completed.stdout:
        return MemoryResult(reason="no_arranco")
    try:
        data = json.loads(completed.stdout)
        return MemoryResult(
            tuple(Measurement(**m) for m in data.get("measurements", ())),
            tuple(Latency(**l) for l in data.get("latencies", ())),
            data.get("latency_reason"),
            data.get("reason"),
        )
    except (ValueError, TypeError):
        return MemoryResult(reason="no_arranco")


def main() -> int:
    # La salida tiene que ser JSON limpio: cualquier otra cosa impresa aquí
    # rompería al padre.
    cache = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    levels = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
    json.dump(asdict(in_this_process(cache or None, levels)), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
