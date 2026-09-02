"""Una puntuación que sí se puede comparar entre dos equipos.

El historial ya guardaba una cifra por prueba, pero su propio comentario decía
que solo servía para ordenar pruebas del mismo equipo. Y era verdad por dos
motivos, los dos de fondo:

**Sumaba operaciones por segundo de cinco cargas con magnitudes distintas.**
En un 5800X3D la compresión pesada daba 28 494 op/s y la memoria 533, así que
la primera pesaba el 82 % del total y las otras cuatro eran decoración. La
«puntuación» era, en la práctica, la compresión pesada; un procesador bueno en
lo demás y flojo en eso salía mal sin que se pudiera ver por qué.

**Y dependía de cuánto durase cada medida.** Tres segundos cogen el turbo
entero y treinta lo pierden a mitad, así que la misma pieza da dos cifras muy
distintas según lo que se le pida. Eso está bien para preguntar «¿cuánto
aguanta este equipo?», que es para lo que se dejan elegir duraciones, y hace
imposible poner dos pruebas cualesquiera una al lado de otra.

Aquí se arreglan las dos cosas. Cada carga se divide por lo que da en una
pieza tomada como patrón, así que todas entran valiendo lo mismo, y solo se
puntúan las pruebas hechas con la duración canónica. Lo que no cumple esas dos
condiciones no recibe puntuación: es preferible a dar una cifra que parece
comparable y no lo es.

Y hay una tercera condición, que llegó después y por el mismo motivo: **no
toda carga puede puntuar**. Tres de las cinco se apoyan en una biblioteca que
cada distribución compila a su manera, y ahí la cifra deja de ser del
procesador —hasta un ×9,7 en la misma pieza según qué zlib traiga el sistema—.
Se siguen midiendo y se enseñan, porque son buen diagnóstico; lo que no hacen
es entrar en la puntuación. Cuáles y por qué, en `PUNTUABLES`.

La fórmula lleva versión. Cambiar las referencias o las cargas cambia la
escala de todas las puntuaciones a la vez, y una cifra vieja junto a una nueva
diría una diferencia que no existe.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import pathlib
from typing import Optional

# Sube cuando cambien las referencias, las cargas o la forma de combinarlas.
# Una puntuación de otra versión no se compara con esta.
#
# La 4 cambió la compresión pesada de LZMA a bzip2. No fue por gusto: LZMA
# saltaba entre dos velocidades separadas un 26 % y ella sola metía un 4,7 %
# de dispersión en la puntuación de un equipo consigo mismo, con lo que dos
# piezas que se llevaran menos de eso salían indistinguibles. El motivo largo,
# con las cifras y lo que se probó antes de rendirse, está en `benchmark.py`.
#
# La 5 dejó de contar operaciones en la carga que recorre un bloque grande.
# Ese bloque se dimensiona con la caché de cada equipo —entre 64 y 192 MB—,
# así que una «operación» no era la misma cosa en dos máquinas: con el mismo
# ancho de banda real, un procesador con poca caché sacaba un 42,8 % más solo
# por recorrer un bloque más pequeño. Ahora esa carga se cuenta en bytes por
# segundo, que no depende del tamaño (queda un 1 % residual, por debajo del
# ruido de la propia medida, que ronda el 1,3 %). En el mismo paso, la carga
# pasó a llamarse «verificación», porque no medía lo que su nombre decía.
#
# La 6 dejó fuera de la cifra las tres cargas que dependen de una biblioteca
# del sistema. No llegó a haber una v5 publicada: se vio antes de fusionarla,
# midiendo la misma pieza —un i5-10400— con lo que trae cada distribución, el
# mismo día y en el mismo equipo:
#
#     crc32 de 64 MiB   zlib-ng 1.3.1 (Fedora)    14,9 GB/s
#                       zlib 1.3.1 (Debian)        3,9
#                       zlib 1.3.2 (Arch)          2,0
#                       zlib 1.2.11 (Ubuntu)       1,5   ← la del AppImage
#
# Un ×9,7 que no es del procesador. La compresión se lleva un ×2,75 por lo
# mismo y la derivación un ×1,38 entre OpenSSL 3.0 y 3.5. Sumado: el mismo
# equipo puntuaba 716 con la zlib de Fedora y 504 con la del AppImage, un
# 30 % que decidía la distribución y no la pieza. Y no había forma de
# arreglarlo fijando el entorno, porque el programa se reparte también en
# paquetes de distribución, donde cada usuario se lleva la suya.
VERSION = 6

# Las cargas que entran en la puntuación. No son las mejores ni las más
# bonitas: son las que miden el procesador y no la distribución.
#
# El criterio está medido, no supuesto. La misma pieza, tres distribuciones y
# dos versiones mayores de OpenSSL:
#
#     resumen criptográfico   190,05 · 190,13 · 190,17 op/s   ±0,1 %
#     compresión pesada        99,54 · 100,96 · 102,84        ±3 %
#     derivación de clave      123,53 · 152,12 · 170,00       ×1,38
#     compresión                 (zlib, arriba)               ×2,75
#     verificación               (zlib, arriba)               ×9,7
#
# Las tres de fuera se siguen midiendo y enseñando, con la biblioteca que las
# midió al lado: son buen diagnóstico, y son justamente las que delatan qué
# hay debajo. Lo que no pueden es entrar en una cifra que se compara entre
# equipos.
#
# Se probó a acercarlas usando lo que CPython trae dentro, y sale peor: su
# sha512 interno da 55 op/s en 3.14 y 109 en 3.10 —cambió la implementación, y
# hasta el nombre del módulo—, o sea el doble de dispersión que OpenSSL, que
# es una sola upstream con su ensamblador y su despacho por CPUID. Y
# `pbkdf2_hmac` ni siquiera tiene versión interna: sin OpenSSL desaparece de
# `hashlib`, así que esa carga no se puede desatar del sistema.
#
# Lo que esto cuesta está escrito donde se paga: en `benchmark.py`, al lado de
# la carga que se quedó sin sustituta.
PUNTUABLES = ("hash", "compresion_dura")

# Cuánto tiene que durar cada medida para que la prueba puntúe. Quince segundos
# es el punto en el que la mayoría de los procesadores ya han dejado atrás el
# turbo de arranque y todavía no llevan tanto rato como para que el resultado
# lo decida la refrigeración de la caja. Por debajo se mide el turbo; por
# encima, el disipador.
SEGUNDOS_CANONICOS = 15.0

# Cuánto puede desviarse la duración real y seguir contando. El bucle no corta
# en mitad de una operación, así que quince segundos pedidos salen quince y
# pico.
TOLERANCIA_SEGUNDOS = 1.5

# Lo que saca el patrón, por definición. Una cifra redonda se lee mejor que un
# tanto por ciento y deja sitio a las piezas que rinden más de mil.
ESCALA = 1000

# Las operaciones por segundo del patrón viven en un archivo de datos y no
# aquí: son medidas, no elegidas, y rehacerlas en otro equipo no debería
# obligar a tocar código. Guarda las cinco, porque describe al patrón entero;
# su papel es poner en la misma escala a las que puntúan. Cambiarlas mueve
# todas las puntuaciones a la vez, y por eso el archivo declara para qué
# versión de la fórmula vale.
_TABLA = pathlib.Path(__file__).parent / "db" / "scores.json"


@functools.lru_cache(maxsize=1)
def referencias() -> dict:
    """La tabla del patrón, o vacía si no está.

    Sin ella no hay puntuación: es la escala. Y sin escala es preferible no
    enseñar cifra a enseñar una que no significa lo mismo en dos equipos.
    """
    try:
        with _TABLA.open(encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, ValueError):
        return {}
    return datos if datos.get("version_formula") == VERSION else {}


def patron() -> dict:
    """Con qué equipo y en qué condiciones se tomó la escala."""
    return referencias().get("patron", {})

def puntuar(scores: dict[str, float], hilos: int) -> Optional[tuple[int, int]]:
    """La puntuación de un hilo y la de todos.

    `scores` es lo que guarda el historial: «compresion/1» y «compresion/16»
    con sus operaciones por segundo.

    No mira la duración a propósito. Poner las cinco cargas en la misma escala
    vale para cualquier prueba, y es mejor cifra que la suma en crudo también
    dentro de un mismo equipo. Lo que la duración decide es otra cosa: si esta
    cifra se puede poner al lado de la de otra máquina, y eso lo contesta
    `comparable`. Antes se mezclaban las dos preguntas y en la misma pantalla
    salían dos puntuaciones distintas de la misma prueba.
    """
    tabla = referencias()
    un_hilo = _combinar(scores, 1, tabla.get("un_hilo", {}))
    multi = _combinar(scores, hilos, tabla.get("multihilo", {}))
    if un_hilo is None or multi is None:
        return None
    return un_hilo, multi


def comparable(segundos: float) -> bool:
    """Si esta puntuación se puede poner al lado de la de otro equipo.

    Tres segundos cogen el turbo entero y treinta lo pierden a mitad, así que
    la misma pieza da cifras distintas según lo que se le pida. Dentro de un
    mismo equipo eso no molesta —el historial ya exige la misma duración para
    comparar—, pero entre dos equipos sí.
    """
    return abs(segundos - SEGUNDOS_CANONICOS) <= TOLERANCIA_SEGUNDOS


def puntua(carga: str) -> bool:
    """Si esta carga entra en la puntuación.

    Vive aquí y no en `benchmark.CARGAS` porque es una decisión de la escala y
    no de la carga: la misma prueba, medida igual, entra o no entra según lo
    que la fórmula sepa comparar. Poner la marca en cada carga la dejaría en
    dos sitios, y el día que se separen no lo diría nadie.
    """
    return carga in PUNTUABLES


def _combinar(scores: dict[str, float], hilos: int,
              referencia: dict[str, float]) -> Optional[int]:
    """La media de las cargas puntuables, cada una contra su referencia.

    Recorre `PUNTUABLES` y no la tabla entera: la referencia guarda las cinco
    cargas porque describe al patrón entero, y quién puntúa lo decide la
    fórmula. Con la tabla mandando, añadir una medida al patrón cambiaría la
    escala sin que nadie tocara la versión.

    Hacen falta todas: con una menos, la que falta se llevaría por delante la
    comparación con cualquier prueba completa, y la cifra parecería igual de
    válida.
    """
    if not referencia:
        return None
    fracciones = []
    for carga in PUNTUABLES:
        del_patron = referencia.get(carga)
        medido = scores.get(f"{carga}/{hilos}")
        if medido is None or not del_patron:
            return None
        fracciones.append(medido / del_patron)
    return round(sum(fracciones) / len(fracciones) * ESCALA)


# Cuántas medidas hacen falta para hablar de un rango. Con dos, los extremos
# son las dos que hay y la barra diría que cualquier cosa es normal o que nada
# lo es, según la suerte. Tres es poco y ya permite una mediana.
MINIMO_MUESTRAS = 3

# Cuánto se puede alejar la puntuación de la mediana de su pieza antes de que
# merezca comentarse. Un 8 % arriba o abajo entra dentro de lo que separa a dos
# equipos con la misma CPU: la placa, la memoria, el disipador y el gobernador.
MARGEN_NORMAL = 0.08


@dataclasses.dataclass(frozen=True, slots=True)
class Comparacion:
    """Dónde cae una puntuación entre las de su misma pieza."""

    puntuacion: int
    minimo: int
    maximo: int
    mediana: int
    muestras: int

    @property
    def fraccion(self) -> float:
        """Dónde ponerla en la barra, de 0 a 1.

        Se recorta a los extremos: una pieza que rinda por encima de todo lo
        registrado tiene que verse al final de la barra, no fuera de ella.
        """
        if self.maximo <= self.minimo:
            return 0.5
        cruda = (self.puntuacion - self.minimo) / (self.maximo - self.minimo)
        return max(0.0, min(1.0, cruda))

    @property
    def desvio(self) -> float:
        """Cuánto se aparta de la mediana, en tanto por uno."""
        return (self.puntuacion - self.mediana) / self.mediana if self.mediana else 0.0

    @property
    def normal(self) -> bool:
        return abs(self.desvio) <= MARGEN_NORMAL


def comparar(cpu: str, puntuacion: int,
             multihilo: bool = True) -> Optional[Comparacion]:
    """Dónde cae esta puntuación entre las conocidas de la misma pieza.

    Devuelve `None` cuando no se sabe nada de esa CPU, que hoy es casi
    siempre: la tabla arranca con lo poco que se ha medido y se llena con lo
    que vaya llegando. Es mejor no decir nada que situar a alguien respecto de
    dos medidas sueltas.
    """
    pieza = referencias().get("piezas", {}).get(cpu)
    if not pieza:
        return None
    muestras = sorted(pieza.get("multihilo" if multihilo else "un_hilo", []))
    if len(muestras) < MINIMO_MUESTRAS:
        return None
    mitad = len(muestras) // 2
    mediana = (muestras[mitad] if len(muestras) % 2
               else (muestras[mitad - 1] + muestras[mitad]) / 2)
    return Comparacion(
        puntuacion=puntuacion,
        minimo=int(muestras[0]),
        maximo=int(muestras[-1]),
        mediana=int(round(mediana)),
        muestras=len(muestras),
    )


def piezas_conocidas() -> int:
    """Cuántas piezas tienen medidas suficientes para comparar."""
    return sum(1 for p in referencias().get("piezas", {}).values()
               if len(p.get("multihilo", [])) >= MINIMO_MUESTRAS)
