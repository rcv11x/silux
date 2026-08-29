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

La fórmula lleva versión. Cambiar las referencias o las cargas cambia la
escala de todas las puntuaciones a la vez, y una cifra vieja junto a una nueva
diría una diferencia que no existe.
"""

from __future__ import annotations

import functools
import json
import pathlib
from typing import Optional

# Sube cuando cambien las referencias, las cargas o la forma de combinarlas.
# Una puntuación de otra versión no se compara con esta.
VERSION = 1

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
# obligar a tocar código. Su único papel es poner las cinco cargas en la misma
# escala; cambiarlas mueve todas las puntuaciones a la vez, y por eso el
# archivo declara para qué versión de la fórmula vale.
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

def puntuar(scores: dict[str, float], hilos: int,
            segundos: float) -> Optional[tuple[int, int]]:
    """La puntuación de un hilo y la de todos, o None si no es comparable.

    `scores` es lo que guarda el historial: «compresion/1» y «compresion/16»
    con sus operaciones por segundo.
    """
    if not comparable(segundos):
        return None
    tabla = referencias()
    un_hilo = _combinar(scores, 1, tabla.get("un_hilo", {}))
    multi = _combinar(scores, hilos, tabla.get("multihilo", {}))
    if un_hilo is None or multi is None:
        return None
    return un_hilo, multi


def comparable(segundos: float) -> bool:
    """Si una prueba se hizo con la duración que hace comparables las cifras."""
    return abs(segundos - SEGUNDOS_CANONICOS) <= TOLERANCIA_SEGUNDOS


def _combinar(scores: dict[str, float], hilos: int,
              referencia: dict[str, float]) -> Optional[int]:
    """La media de las cargas, cada una medida contra su referencia.

    Hace falta que estén las cinco: con cuatro, la que falta se llevaría por
    delante la comparación con cualquier prueba completa, y la cifra parecería
    igual de válida.
    """
    if not referencia:
        return None
    fracciones = []
    for carga, del_patron in referencia.items():
        medido = scores.get(f"{carga}/{hilos}")
        if medido is None or not del_patron:
            return None
        fracciones.append(medido / del_patron)
    return round(sum(fracciones) / len(fracciones) * ESCALA)
