"""Leer el sistema desde otra raíz: la de un equipo volcado.

Con `SILUX_SYSROOT` apuntando a un volcado de `tools/volcar_equipo.py`, los
proveedores leen `/sys`, `/proc` y `/etc` de ahí en vez de del equipo que
ejecuta el programa. Es lo que permite comprobar que un arreglo sale bien en
un Intel y en un AMD sin tener los dos delante: el volcado de cada uno va en
`tests/fixtures/equipos/` y la suite monta el Collector contra todos.

Lo que no sale de un archivo —la instrucción CPUID, los ioctl de DRM, lo que
contestan OpenGL y Vulkan, el espacio libre de un disco, las direcciones IP—
se graba al volcar y se repite al leer, con `a_traves`. Un volcado del
5800X3D tiene que dar un 5800X3D aunque la suite corra en un i5-10400: si la
CPUID se preguntara al procesador de verdad, el test mezclaría dos equipos y
diría que todo cuadra.

Sin la variable no cambia nada: `ruta` devuelve lo mismo que recibe y
`a_traves` llama a la función.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from typing import Any, Callable, Optional, TypeVar

VARIABLE = "SILUX_SYSROOT"
# Lo grabado va en un archivo del propio volcado, al lado de `sys/` y `proc/`.
GRABADO = "grabado.json"

# Los prefijos que se redirigen. `/dev` no: lo que se lee de `/dev` son
# ioctl, y esos van grabados.
PREFIJOS = ("/sys/", "/proc/", "/etc/")

T = TypeVar("T")

# Mientras se vuelca, lo que pasa por `a_traves` se apunta aquí.
_grabacion: Optional[dict[str, dict[str, Any]]] = None
_cache: dict[pathlib.Path, dict] = {}


def raiz() -> Optional[pathlib.Path]:
    valor = os.environ.get(VARIABLE)
    return pathlib.Path(valor) if valor else None


def activo() -> bool:
    return raiz() is not None


def ruta(camino):
    """El camino dentro de la raíz activa, del mismo tipo que se recibe.

    Idempotente: un camino que ya está dentro de la raíz se devuelve igual,
    porque los proveedores pasan caminos de una función a otra y no todos
    saben si el que reciben ya se tradujo.
    """
    base = raiz()
    if base is None:
        return camino
    texto = os.fspath(camino)
    if texto.startswith(str(base) + os.sep) or texto == str(base):
        return camino
    if not (texto.startswith(PREFIJOS) or texto in ("/sys", "/proc", "/etc")):
        return camino
    nuevo = str(base) + texto
    return pathlib.Path(nuevo) if isinstance(camino, pathlib.PurePath) else nuevo


def fuera(camino) -> str:
    """El camino como lo vería el sistema: sin la raíz delante.

    Para lo que se compara con un camino del sistema escrito en el código, o
    se enseña, o acaba en el modelo: dentro del modelo no puede quedar la
    carpeta donde vive un volcado.
    """
    base = raiz()
    texto = os.fspath(camino)
    if base is not None and texto.startswith(str(base) + os.sep):
        return texto[len(str(base)):]
    return texto


def _grabado() -> dict:
    base = raiz()
    if base is None:
        return {}
    if base not in _cache:
        try:
            _cache[base] = json.loads((base / GRABADO).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache[base] = {}
    return _cache[base]


def grabo(espacio: str) -> bool:
    """Si el volcado activo llegó a grabar algo de ese espacio.

    Para lo que se empezó a grabar después de hechos los primeros volcados:
    en uno que no lo tiene, quien pregunta sigue como antes de grabarse.
    """
    return espacio in _grabado()


def a_traves(espacio: str, clave: Any, funcion: Callable[..., T], *args,
             tipo: Optional[type] = None, **kwargs) -> Optional[T]:
    """Llama a `funcion`, o devuelve lo que contestó cuando se volcó el equipo.

    `espacio` y `clave` identifican la pregunta: `("cpuid", "0:7:0")`,
    `("amdgpu", "/dev/dri/renderD128")`. Con la raíz activa no se llama a
    nada; lo que no se grabó devuelve `None`, que es lo mismo que contesta
    el programa cuando una fuente no está. `tipo` reconstruye una dataclass a
    partir del diccionario grabado.
    """
    clave = str(clave)
    if activo():
        crudo = _grabado().get(espacio, {}).get(clave)
        if crudo is None:
            return None
        # Dumping a mounted dump records what it answered, as from a machine.
        if _grabacion is not None:
            _grabacion.setdefault(espacio, {})[clave] = crudo
        if tipo is not None and dataclasses.is_dataclass(tipo):
            return tipo(**crudo)
        if isinstance(crudo, list):
            return tuple(crudo)
        return crudo
    valor = funcion(*args, **kwargs)
    if _grabacion is not None:
        guardable = dataclasses.asdict(valor) if dataclasses.is_dataclass(valor) else valor
        _grabacion.setdefault(espacio, {})[clave] = guardable
    return valor


def empezar_a_grabar() -> None:
    global _grabacion
    _grabacion = {}


def lo_grabado() -> dict:
    global _grabacion
    hecho, _grabacion = _grabacion or {}, None
    return hecho


def olvidar() -> None:
    """Para los tests que cambian de volcado dentro del mismo proceso."""
    _cache.clear()
