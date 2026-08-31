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
import random
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

from . import rawcpuid
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
_CODIGO_PERSEGUIR = bytes((0x48, 0x89, 0xF8,
                           0x48, 0x8B, 0x00,
                           0x48, 0xFF, 0xCE,
                           0x75, 0xF8,
                           0xC3))

# Una línea de caché. Se salta de una a otra porque leer dos veces la misma
# línea sale de la misma lectura y no mide nada.
LINEA = 64

# Cuántos saltos se dan como mínimo, para que el coste de entrar y salir de la
# llamada —570 ns— no pese: en la L1 un acceso son 0,9 ns, así que con pocos
# saltos se estaría cronometrando ctypes otra vez.
MINIMO_SALTOS = 200_000

# Y un tope de eslabones, que es lo que cuesta tiempo de verdad: barajarlos y
# enlazarlos son bucles de Python. Con seis millones se van cuatro segundos
# antes de medir nada. Con este tope, un procesador de caché normal se prepara
# en décimas y uno con una L3 enorme se queda sin la latencia de RAM y lo dice,
# que es mejor que tener el botón parado cinco segundos.
MAXIMO_ESLABONES = 4_000_000

# Para la latencia basta con el doble de la caché: con dos, tres y cuatro veces
# salen 80,0, 83,6 y 80,8 ns, o sea lo mismo, y cada vez que se dobla el bloque
# se dobla el tiempo de preparar la cadena. Para el ancho de banda se usa el
# triple porque allí no hay cadena que construir y no cuesta nada.
VECES_FUERA_PARA_LATENCIA = 2

# Un tope al bloque con el que se mide una caché, además de su fracción. La L3
# de un Zen 3 es caché de víctimas —solo guarda lo que se expulsa de la L2—, así
# que con la mitad de sus 96 MB recorridos al azar ya casi no retiene nada: da
# 66 ns donde tiene que dar 12. Con 4, 8 y 16 MB sale 11,9, 12,0 y 13,2, así que
# el escalón está bastante por debajo de la mitad y hay que quedarse abajo.
MAXIMO_BLOQUE_DE_CACHE = 16 * 1024 * 1024

# Páginas de 2 MB en vez de 4 KB. Perseguir punteros por 288 MB toca 73728
# páginas y el TLB de datos guarda unas 2000, así que cada acceso pagaba además
# un recorrido de tablas: 94,7 ns con páginas normales contra 82,1 con grandes.
# Es un consejo, no una orden: si el sistema las tiene desactivadas no pasa nada.
MADV_HUGEPAGE = 14
PAGINA_GRANDE = 2 * 1024 * 1024

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
class Latencia:
    """Lo que tarda un acceso que no se puede adelantar, por nivel."""

    nivel: str                       # "L1", "L2", "L3", "RAM"
    bytes_: int
    nanoseconds: float


@dataclass(frozen=True)
class Resultado:
    medidas: tuple[Medida, ...] = ()
    latencias: tuple[Latencia, ...] = ()
    # Por qué faltan latencias, que no es lo mismo que por qué falta el ancho
    # de banda: se puede tener una cosa y no la otra.
    motivo_latencias: Optional[str] = None
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


def _reservar(tam: int):
    """Un bloque alineado a 2 MB y con páginas grandes pedidas.

    Se pide con `mmap` y no con un búfer de ctypes porque la alineación es lo
    que el kernel exige para poder juntar las páginas, y un búfer normal cae
    donde caiga.
    """
    try:
        mapa = mmap.mmap(-1, tam + PAGINA_GRANDE,
                         prot=mmap.PROT_READ | mmap.PROT_WRITE)
    except (OSError, ValueError):
        return None
    cruda = ctypes.addressof(ctypes.c_char.from_buffer(mapa))
    base = (cruda + PAGINA_GRANDE - 1) & ~(PAGINA_GRANDE - 1)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.madvise.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.madvise(ctypes.c_void_p(base), tam, MADV_HUGEPAGE)
    return mapa, base


def _cadena(base: int, lineas: int) -> int:
    """Enlaza `lineas` líneas del bloque en un ciclo aleatorio.

    Devuelve la dirección del primer eslabón. El orden es aleatorio a propósito:
    con un salto constante el prefetcher lo adivina y se mide lo que tarda en
    llegar un dato que ya venía de camino, no lo que tarda un acceso.
    """
    orden = list(range(lineas))
    random.shuffle(orden)
    vista = (ctypes.c_uint64 * (lineas * LINEA // 8)).from_address(base)
    siguientes = orden[1:]
    siguientes.append(orden[0])
    for actual, siguiente in zip(orden, siguientes):
        vista[actual * (LINEA // 8)] = base + siguiente * LINEA
    return base + orden[0] * LINEA


def _latencia(perseguir, primero: int, saltos: int) -> float:
    """Nanosegundos por acceso, del mejor intento."""
    perseguir(primero, min(saltos, 100_000))          # calentar
    mejor = None
    for _ in range(3):
        arranque = time.perf_counter()
        perseguir(primero, saltos)
        tardanza = time.perf_counter() - arranque
        mejor = tardanza if mejor is None else min(mejor, tardanza)
    return (mejor or 0.0) / saltos * 1e9


def latencias(niveles: "list[tuple[str, int]]") -> tuple:
    """Mide un nivel por cada caché, y la RAM detrás.

    `niveles` son pares de nombre y tamaño, del más pequeño al más grande. De
    cada uno se recorre la mitad, para que la cadena quepa de sobra dentro; de
    la RAM, el triple de la caché mayor, para que no quepa de ninguna manera.
    """
    if not rawcpuid.is_supported():
        return (), "no_x86"
    try:
        mm, direccion = rawcpuid.pagina_ejecutable(_CODIGO_PERSEGUIR)
    except Exception:                                          # noqa: BLE001
        # Un entorno que prohíbe ejecutar memoria anónima. Sin latencias, pero
        # el resto de la medida sigue valiendo.
        return (), "sin_ejecutable"

    perseguir = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_size_t)(direccion)
    salidas = []
    motivo = None
    try:
        mayor = max((tam for _, tam in niveles), default=0)
        tramos = [(nombre, min(tam // 2, MAXIMO_BLOQUE_DE_CACHE))
                  for nombre, tam in niveles if tam // 2 >= LINEA * 8]
        tramos.append(("RAM", max(MINIMO_FIABLE * 64,
                                  mayor * VECES_FUERA_PARA_LATENCIA)))
        disponible = _memoria_disponible()
        for nombre, tam in tramos:
            lineas = tam // LINEA
            if lineas > MAXIMO_ESLABONES:
                # Preparar la cadena son bucles de Python: seis millones de
                # eslabones se llevan cuatro segundos antes de medir nada.
                motivo = motivo or "cadena_enorme"
                continue
            if disponible is not None and tam + MARGEN_LIBRE > disponible:
                motivo = motivo or "sin_memoria"
                continue
            bloque = _reservar(tam)
            if bloque is None:
                motivo = motivo or "sin_memoria"
                continue
            mapa, base = bloque
            primero = _cadena(base, lineas)
            # Al menos dos vueltas al ciclo entero: con menos saltos que líneas,
            # lo recorrido cabe en la caché y se mide la caché creyendo que se
            # mide la RAM. Salían 28 ns donde hay 76.
            saltos = max(MINIMO_SALTOS, lineas * 2)
            salidas.append(Latencia(nombre, tam, round(
                _latencia(perseguir, primero, saltos), 1)))
            mapa.close()
    finally:
        mm.close()
    return tuple(salidas), motivo


def en_este_proceso(cache_bytes: Optional[int],
                    niveles: "Optional[list]" = None) -> Resultado:
    """Mide de verdad.

    `cache_bytes` es la caché más grande, y decide los bloques del ancho de
    banda. `niveles` son los pares de nombre y tamaño de cada caché, que es lo
    que hace falta para las latencias; sin ellos se mide solo el ancho de banda.
    """
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
    if n > MAXIMO_BLOQUE or (disponible is not None
                             and n + MARGEN_LIBRE > disponible):
        tiempos, porque = latencias(niveles or [])
        return Resultado(tuple(medidas),
                         tiempos, porque,
                         motivo=("cache_enorme" if n > MAXIMO_BLOQUE
                                 else "sin_memoria"))
    bloque = ctypes.create_string_buffer(n)
    segundos = _leer(libc, ctypes.addressof(bloque), n)
    if segundos > 0:
        medidas.append(Medida(n, int(n / segundos), "ram"))
    del bloque
    tiempos, porque = latencias(niveles or [])
    return Resultado(tuple(medidas), tiempos, porque)


def consultar(cache_bytes: Optional[int],
              niveles: "Optional[list]" = None) -> Resultado:
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
            [sys.executable, "-m", "silux.membench", str(cache_bytes or 0),
             json.dumps(niveles or [])],
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
            tuple(Latencia(**l) for l in leido.get("latencias", ())),
            leido.get("motivo_latencias"),
            leido.get("motivo"),
        )
    except (ValueError, TypeError):
        return Resultado(motivo="no_arranco")


def main() -> int:
    # La salida tiene que ser JSON limpio: cualquier otra cosa impresa aquí
    # rompería al padre.
    cache = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    niveles = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
    json.dump(asdict(en_este_proceso(cache or None, niveles)), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
