"""El idioma de la interfaz.

El original es el español y no una lista de claves simbólicas. La diferencia
importa cuando falta una traducción: con claves, la pantalla enseña
`settings.fluid.desc`; con el español de original, enseña el español, que es
lo que el programa decía antes de que existiera esto.

Los idiomas son archivos JSON en `db/lang/`, un diccionario del español a la
otra lengua. Se eligió JSON sobre gettext por quién los va a escribir: un
`.po` hay que compilarlo a binario antes de que sirva, y esto se corrige desde
el navegador de GitHub y se lee en el diff línea a línea.

    _("Frecuencia")            → "Clock" en inglés, "Frecuencia" en español

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
_oyentes: list[Callable[[], None]] = []


def disponible() -> dict[str, str]:
    """Los idiomas con archivo, más el español, que es el original."""
    idiomas = {"es": IDIOMAS["es"]}
    for ruta in sorted(CARPETA.glob("*.json")) if CARPETA.is_dir() else ():
        codigo = ruta.stem
        if codigo != "es":
            idiomas[codigo] = IDIOMAS.get(codigo, codigo)
    return idiomas


def actual() -> str:
    return _actual


def set_language(codigo: Optional[str]) -> str:
    """Carga un idioma y avisa a quien esté escuchando. Devuelve el que quedó.

    Un código que no existe no es un error que deba parar el programa: se
    vuelve al español, que siempre está.
    """
    global _actual, _tabla

    codigo = (codigo or "es").lower()
    if codigo == "es":
        _actual, _tabla = "es", {}
        _avisar()
        return _actual

    ruta = CARPETA / f"{codigo}.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _actual, _tabla = "es", {}
        _avisar()
        return _actual

    # Se descarta lo que no sea texto por texto: un archivo a medio escribir no
    # tiene por qué tirar la interfaz abajo.
    _tabla = {k: v for k, v in datos.items()
              if isinstance(k, str) and isinstance(v, str) and v}
    _actual = codigo
    _avisar()
    return _actual


def _(texto: str) -> str:
    """El texto en el idioma de ahora, o tal cual si no está traducido."""
    return _tabla.get(texto, texto)


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
