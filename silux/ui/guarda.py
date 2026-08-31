"""Que un Qt demasiado nuevo no se lleve el programa por delante sin decir nada.

El AppImage ya tiene su guarda, escrita en shell dentro del AppRun, y ahí es
exacta: el empaquetador lee el desensamblado de las bibliotecas que acaba de
meter y le pasa las banderas que encontró. Desde el código fuente no hay nada
que leer —el Qt es el que tenga puesto quien ejecuta, y mirar su ELF en cada
arranque costaría más que arrancar—, así que se va por la regla que Qt
publica: de 6.10 en adelante pide x86-64-v2.

Sin esto, en un Core 2 o en un Phenom II el programa se cae con «Instrucción
ilegal» y un volcado antes de pintar nada. Qt trae un aviso para ese caso
—«Incompatible processor»— y no llega a salir, porque revienta antes de
imprimirlo. Quien lo ve no tiene forma de saber que la culpa es de la versión
de una dependencia.

La regla es una regla y no una medida, así que puede equivocarse: una
distribución es libre de compilar su Qt 6.10 para x86-64 a secas y entonces
esto estorbaría. Por eso `SILUX_SIN_GUARDA` la desactiva. Equivocarse aquí
tiene que costar una variable de entorno, no un programa que no abre.
"""

from __future__ import annotations

import os
from typing import Optional

# Desde qué serie de Qt hace falta x86-64-v2. Está en el comentario de
# `RANGO_PYSIDE`, en el empaquetador, con el detalle de en qué funciones
# aparece: `QString`, `QUtf8::convertToUnicode`, `QPainterPath::quadTo`. No son
# rutas que se eligen mirando la CPU, son funciones normales, así que no hay
# forma de esquivarlas usando el programa con cuidado.
TECHO_QT = (6, 10)

# Las instrucciones de x86-64-v2, con el nombre que les da `/proc/cpuinfo`,
# que es de donde se leen. Es la misma lista que la guarda del AppImage, y hay
# un test que no las deja separarse: si el empaquetador aprende a detectar una
# más, esta se entera.
#
# Son cinco y no siete: `cx16` y `lahf_lm` también son de x86-64-v2, pero el
# empaquetador no puede reconocerlas leyendo el desensamblado y no están en su
# tabla. Pedir aquí una que allí no se comprueba solo añadiría formas de
# equivocarse en máquinas raras.
JUEGOS_V2 = ("pni", "ssse3", "sse4_1", "sse4_2", "popcnt")

# La puerta para cuando la regla se equivoque.
ESCAPE = "SILUX_SIN_GUARDA"

# Aparte para que las pruebas puedan darle otro, como ya hace el ayudante
# privilegiado con su tabla DMI.
CPUINFO = "/proc/cpuinfo"


def banderas_de(texto: str) -> set[str]:
    """Las banderas de la primera línea `flags` de un `/proc/cpuinfo`.

    Vacío si no hay ninguna, y quien llama tiene que distinguir eso de «no
    tiene ninguna de las que busco»: son la misma respuesta con el signo
    cambiado, y confundirlas deja sin arrancar a un equipo del que solo se
    sabe que no contestó.
    """
    for linea in texto.splitlines():
        if linea.startswith("flags"):
            _clave, _sep, valor = linea.partition(":")
            return set(valor.split())
    return set()


def banderas_que_faltan() -> tuple[str, ...]:
    """De x86-64-v2, las que este procesador no publica.

    Vacío también cuando no hay nada que decidir: fuera de x86-64 la pregunta
    no aplica, sin `/proc/cpuinfo` no se sabe y sin línea `flags` tampoco.
    Ninguno de los tres es motivo para no dejar arrancar a nadie.
    """
    if os.uname().machine not in ("x86_64", "amd64"):
        return ()
    try:
        with open(CPUINFO, encoding="utf-8", errors="replace") as archivo:
            texto = archivo.read()
    except OSError:
        return ()
    banderas = banderas_de(texto)
    if not banderas:
        return ()
    return tuple(j for j in JUEGOS_V2 if j not in banderas)


def version_de_pyside() -> Optional[tuple[int, int]]:
    """La serie de PySide6 instalada, sin importarlo.

    Importarlo es justo lo que no se puede hacer todavía: cargar QtCore es lo
    que revienta. Los metadatos del paquete se leen del disco y no ejecutan
    nada suyo.

    `None` cuando no se sabe, que dentro del AppImage es lo normal —viaja
    copiado, no instalado— y da igual, porque ahí la guarda de verdad es la
    del AppRun y ya ha corrido antes que Python.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        crudo = version("PySide6")
    except (PackageNotFoundError, ValueError):
        return None
    piezas = crudo.split(".")
    try:
        return int(piezas[0]), int(piezas[1])
    except (IndexError, ValueError):
        return None


def diagnostico() -> Optional[str]:
    """El texto que hay que enseñar antes de rendirse, o `None` si se puede tirar.

    Aparte para poder probarlo: quien decide es esta función y `comprobar` solo
    la imprime y se va.
    """
    if os.environ.get(ESCAPE):
        return None

    faltan = banderas_que_faltan()
    if not faltan:
        return None

    serie = version_de_pyside()
    if serie is None or serie < TECHO_QT:
        return None

    # A partir de aquí ya no se arranca, así que lo que cueste da igual: se
    # carga el idioma que el usuario tenga guardado para que el aviso salga en
    # el suyo. Es lo último que va a leer del programa.
    from .. import i18n, settings as prefs_module

    i18n.set_language(prefs_module.load().language)
    _ = i18n._

    return "\n".join((
        _("guard.cpu.missing").format(banderas=" ".join(faltan)),
        "",
        _("guard.cpu.why").format(mayor=TECHO_QT[0], menor=TECHO_QT[1]),
        "",
        _("guard.cpu.fix"),
        "",
        "    pip install 'PySide6<6.10'",
        "",
        _("guard.cpu.meanwhile"),
        "",
        "    python3 -m silux.cli --report informe.md",
        "",
        _("guard.cpu.override").format(variable=ESCAPE),
    ))


def comprobar() -> None:
    """Se llama antes de importar Qt. Si no hay nada que decir, no hace nada."""
    aviso = diagnostico()
    if aviso is None:
        return
    import sys

    print(aviso, file=sys.stderr)
    raise SystemExit(1)
