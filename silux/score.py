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

import dataclasses
import functools
import json
import pathlib
from typing import Optional

# Sube cuando cambien las referencias, las cargas o la forma de combinarlas.
# Una puntuación de otra versión no se compara con esta.
VERSION = 2

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
