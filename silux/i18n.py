"""El idioma de la interfaz.

Las claves son símbolos —`cpu.card.clocks`— y no el texto español. Así,
retocar una frase en castellano no deja su traducción inglesa colgada de la
versión vieja: la clave no se mueve, y lo que cambia es el valor en `es.json`.

Lo malo conocido de las claves simbólicas es que una traducción incompleta
enseña `cpu.card.clocks` en pantalla. Aquí no pasa, porque hay dos escalones:
si el idioma pedido no tiene la clave se mira el español, y solo si tampoco
está sale la clave. Un archivo a medio traducir enseña español entre inglés,
que se lee; y la clave suelta queda como aviso de que falta escribirla en las
dos lenguas, no en una.

Los idiomas son archivos JSON en `db/lang/`. Se eligió sobre gettext por quién
los va a escribir: un `.po` hay que compilarlo a binario antes de que sirva, y
esto se corrige desde el navegador de GitHub y se lee en el diff línea a línea.

    _("cpu.card.clocks")       → "Clocks" en inglés, "Relojes" en español

Lo que **no** se traduce es lo que sale del propio equipo: el nombre del
procesador, las etiquetas de los sensores que publica el kernel, los códigos
de los chips. Eso no es texto del programa, es el dato.
"""

from __future__ import annotations

import json
import pathlib
from typing import Callable, Optional

# Los idiomas que trae el programa. La clave es el código ISO y el valor, el
# nombre en su propia lengua: quien busca su idioma lo reconoce escrito como
# lo escribe él, no traducido al de la interfaz.
IDIOMAS: dict[str, str] = {
    "es": "Español",
    "en": "English",
}

CARPETA = pathlib.Path(__file__).resolve().parent / "db" / "lang"

_actual = "es"
_tabla: dict[str, str] = {}
# El español se tiene siempre cargado, sea cual sea el idioma elegido: es el
# escalón intermedio entre una traducción que falta y la clave pelada.
_base: dict[str, str] = {}
_oyentes: list[Callable[[], None]] = []


def disponible() -> dict[str, str]:
    """Los idiomas que tienen archivo."""
    idiomas = {}
    for ruta in sorted(CARPETA.glob("*.json")) if CARPETA.is_dir() else ():
        idiomas[ruta.stem] = IDIOMAS.get(ruta.stem, ruta.stem)
    return idiomas or {"es": IDIOMAS["es"]}


def _cargar(codigo: str) -> dict[str, str]:
    """Un archivo de idioma, o vacío si no está o está roto.

    Se descarta lo que no sea texto por texto: un archivo a medio escribir no
    tiene por qué tirar la interfaz abajo.
    """
    try:
        datos = json.loads((CARPETA / f"{codigo}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in datos.items()
            if isinstance(k, str) and isinstance(v, str) and v}


def actual() -> str:
    return _actual


def set_language(codigo: Optional[str]) -> str:
    """Carga un idioma y avisa a quien esté escuchando. Devuelve el que quedó.

    Un código que no existe no es un error que deba parar el programa: se
    vuelve al español, que siempre está.
    """
    global _actual, _tabla, _base

    if not _base:
        _base = _cargar("es")

    codigo = (codigo or "es").lower()
    if codigo == "es":
        _actual, _tabla = "es", {}
    else:
        cargado = _cargar(codigo)
        _actual, _tabla = (codigo, cargado) if cargado else ("es", {})
    _avisar()
    return _actual


def _(clave: str) -> str:
    """El texto de una clave en el idioma de ahora.

    Tres escalones, y el orden es lo que hace utilizable esto: el idioma
    pedido, el español, y por último la clave. Un `en.json` a medias enseña
    español entre inglés, que se lee; solo cuando la frase no está escrita en
    ninguna de las dos lenguas asoma la clave, y eso es lo que hace falta ver
    para ir a escribirla.
    """
    if clave in _tabla:
        return _tabla[clave]
    if not _base:
        set_language(_actual)
    return _base.get(clave, clave)


def en_español(clave: str) -> str:
    """El texto castellano de una clave, aunque la interfaz esté en otro idioma.

    Lo usa quien tiene que reconocer un nombre escrito en español venga de
    donde venga: `--page Sensores` no puede dejar de funcionar porque alguien
    se ponga la interfaz en inglés.
    """
    global _base
    if not _base:
        _base = _cargar("es")
    return _base.get(clave, clave)


def al_cambiar(callback: Callable[[], None]) -> None:
    """Registra a quien tenga que repintarse cuando cambie el idioma."""
    if callback not in _oyentes:
        _oyentes.append(callback)


def olvidar(callback: Callable[[], None]) -> None:
    if callback in _oyentes:
        _oyentes.remove(callback)


def _avisar() -> None:
    for callback in list(_oyentes):
        try:
            callback()
        except RuntimeError:
            # Un widget que Qt ya destruyó. Se descuelga y se sigue: que un
            # oyente muerto impida cambiar de idioma sería absurdo.
            olvidar(callback)


def sin_traducir(codigo: str) -> list[str]:
    """Las cadenas que el idioma pedido todavía no cubre.

    Sirve para `tools/gen_lang.py`, que es quien mantiene los archivos al día
    cuando aparece texto nuevo en el programa.
    """
    ruta = CARPETA / f"{codigo}.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(k for k, v in datos.items() if not v)
