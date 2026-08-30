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

**Lo que no se mide aquí, y por qué.** La latencia en nanosegundos no se puede
sacar sin código nativo propio, y se probaron dos caminos antes de descartarla:

- Con muchos accesos aleatorios sueltos sale plana —9.7 ns en 16 KB y 11.2 en
  256 MB— porque no dependen unos de otros y el procesador los solapa. La
  latencia real de esa máquina va de un nanosegundo a ochenta.
- Con búsqueda binaria, que sí encadena cada salto con el anterior, hay señal
  (22 ns por salto dentro de la caché y 42 fuera), pero para convertirlo en un
  número hay que suponer cuántos niveles del árbol están cacheados y descontar
  el coste de la llamada. Serían tres suposiciones sosteniendo una cifra.

Y tampoco se miden la L1 ni la L2: una llamada cuesta 570 ns, y en un bloque
de 32 KB eso es casi todo el tiempo. Desde un mega baja del 2 %, así que se
mide de ahí hacia arriba y lo demás se deja sin medir en vez de inventarlo.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

# Por debajo de esto la llamada pesa más que la memoria y la cifra deja de
# hablar del equipo para hablar de ctypes.
MINIMO_FIABLE = 1024 * 1024

# Cuánto hay que pasarse del tamaño de la caché para estar seguro de que se
# está midiendo la RAM. Con el doble todavía cabe media tirada en la caché;
# con el triple, lo que se lee viene de fuera.
VECES_FUERA_DE_LA_CACHE = 3

# Un tope, porque hay Threadripper con 256 MB de caché y el triple de eso no
# lo debe pedir un programa que enseña fichas. Si no se llega a este tamaño la
# medida de RAM se salta y se dice.
MAXIMO_BLOQUE = 512 * 1024 * 1024

# Lo que se deja libre en el equipo pase lo que pase. Medir no puede ser el
# motivo de que algo se vaya a la swap.
MARGEN_LIBRE = 512 * 1024 * 1024

# Cuánto tiempo se le dedica a cada bloque. Iba por número de vueltas y salían
# tres para el bloque de RAM: con tan pocas basta que una tanda pille el equipo
# ocupado para que la cifra salga un 15 % baja, y quien pulsa el botón ve un
# número distinto cada vez sin que su memoria haya cambiado. Repartiendo por
# tiempo, un bloque pequeño da cientos de vueltas y uno grande las que quepan,
# y en los dos casos hay de dónde sacar un mínimo que signifique algo.
PRESUPUESTO = 0.15
MINIMO_VUELTAS = 5
MAXIMO_VUELTAS = 500

TIEMPO_MAXIMO = 60


@dataclass(frozen=True)
class Medida:
    """Una lectura de un bloque de un tamaño concreto."""

    bytes_: int
    bandwidth_bytes: int
    # "ram" es el dato; "techo" es el control: un bloque que cabe en la caché,
    # que no mide la caché sino lo más rápido que puede ir esta herramienta.
    donde: str                       # "techo" | "ram"


@dataclass(frozen=True)
class Resultado:
    medidas: tuple[Medida, ...] = ()
    # Por qué no se pudo medir algo, para poder decirlo en vez de callar.
    motivo: Optional[str] = None


def _libc():
    libc = ctypes.CDLL(None)
    libc.memchr.restype = ctypes.c_void_p
    libc.memchr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
    return libc


def _leer(libc, puntero: int, n: int) -> float:
    """El mejor tiempo de recorrer el bloque, en segundos.

    El mejor y no la media: lo que se busca es lo que da el equipo cuando nadie
    le estorba, y cualquier interrupción solo puede empeorar una vuelta. Por eso
    hacen falta unas cuantas: con el mínimo de tres que había antes, una tanda
    entera podía caer dentro de la interferencia y no había ninguna vuelta
    limpia de la que fiarse.
    """
    libc.memchr(puntero, 0xFF, n)                 # calentar
    mejor = None
    gastado = 0.0
    vueltas = 0
    while vueltas < MINIMO_VUELTAS or (gastado < PRESUPUESTO
                                       and vueltas < MAXIMO_VUELTAS):
        arranque = time.perf_counter()
        libc.memchr(puntero, 0xFF, n)
        tardanza = time.perf_counter() - arranque
        gastado += tardanza
        vueltas += 1
        mejor = tardanza if mejor is None else min(mejor, tardanza)
    return mejor or 0.0


def _memoria_disponible() -> Optional[int]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as archivo:
            for linea in archivo:
                if linea.startswith("MemAvailable:"):
                    return int(linea.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def en_este_proceso(cache_bytes: Optional[int]) -> Resultado:
    """Mide de verdad. `cache_bytes` es la caché más grande del procesador."""
    libc = _libc()
    medidas: list[Medida] = []
    disponible = _memoria_disponible()

    # El techo: un bloque que cabe de sobra en la caché, así que lo que limita
    # ahí no es la memoria. La mitad de la caché, para que quepa con holgura
    # aunque el sistema esté usando una parte.
    if cache_bytes and cache_bytes // 2 >= MINIMO_FIABLE:
        n = cache_bytes // 2
        bloque = ctypes.create_string_buffer(n)
        segundos = _leer(libc, ctypes.addressof(bloque), n)
        if segundos > 0:
            medidas.append(Medida(n, int(n / segundos), "techo"))
        del bloque

    # Fuera de toda caché, que es el ancho de banda de la RAM.
    n = max(MINIMO_FIABLE * 64,
            (cache_bytes or 0) * VECES_FUERA_DE_LA_CACHE)
    if n > MAXIMO_BLOQUE:
        return Resultado(tuple(medidas), "cache_enorme")
    if disponible is not None and n + MARGEN_LIBRE > disponible:
        return Resultado(tuple(medidas), "sin_memoria")
    bloque = ctypes.create_string_buffer(n)
    segundos = _leer(libc, ctypes.addressof(bloque), n)
    if segundos > 0:
        medidas.append(Medida(n, int(n / segundos), "ram"))
    return Resultado(tuple(medidas))


def consultar(cache_bytes: Optional[int]) -> Resultado:
    """Mide en otro proceso, que es donde puede pedir cientos de megas.

    Para salirse de una caché de 96 MB hace falta un bloque de casi trescientos,
    y el programa entero tiene un presupuesto de 300. Aquí se pide, se mide y
    se muere; lo que queda en esta memoria es una cifra.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = os.pathsep.join(
        [raiz] + ([entorno["PYTHONPATH"]] if entorno.get("PYTHONPATH") else [])
    )
    try:
        completado = subprocess.run(
            [sys.executable, "-m", "silux.membench", str(cache_bytes or 0)],
            capture_output=True, timeout=TIEMPO_MAXIMO, env=entorno, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return Resultado(motivo="no_arranco")
    if completado.returncode != 0 or not completado.stdout:
        return Resultado(motivo="no_arranco")
    try:
        leido = json.loads(completado.stdout)
        return Resultado(
            tuple(Medida(**m) for m in leido.get("medidas", ())),
            leido.get("motivo"),
        )
    except (ValueError, TypeError):
        return Resultado(motivo="no_arranco")


def main() -> int:
    # La salida tiene que ser JSON limpio: cualquier otra cosa impresa aquí
    # rompería al padre.
    cache = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    json.dump(asdict(en_este_proceso(cache or None)), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
