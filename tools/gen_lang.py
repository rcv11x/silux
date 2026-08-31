#!/usr/bin/env python3
"""Mantiene al día los archivos de idioma a partir de lo que dice el código.

    python3 tools/gen_lang.py            # informe: qué falta y qué sobra
    python3 tools/gen_lang.py --write    # actualiza los .json

Recorre el código buscando las llamadas a `_()` y compara las claves que
encuentra con las que hay en `silux/db/lang/*.json`. El español es un archivo
más: las claves son símbolos, así que `es.json` es el que dice qué frase
castellana lleva cada una. Lo que falta se añade con la traducción
vacía; lo que sobra —texto que se cambió o se quitó del programa— se saca a un
bloque aparte al final del informe en vez de borrarse sin avisar, porque
puede ser una cadena que solo cambió de sitio.

No se extrae cualquier cadena del código, solo las que ya están envueltas en
`_()`. Adivinar cuáles son texto de interfaz y cuáles son claves internas es
justo el tipo de cosa que sale mal en silencio: un `"amdgpu"` traducido rompe
la detección de la gráfica y nadie lo relaciona con el idioma.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from typing import Iterable

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LANG = RAIZ / "silux" / "db" / "lang"

# Dónde puede haber texto de interfaz. `providers/` entra por los avisos: lo
# que sale de ahí son datos del equipo, sí, pero la frase que explica por qué
# falta un dato la escribió el autor y se lee en pantalla. Como aquí solo se
# extrae lo que ya está envuelto en `_()`, los datos no corren peligro.
FUENTES = ("silux/ui", "silux/render.py", "silux/cli.py", "silux/report.py",
           "silux/providers", "silux/collector.py", "silux/spd.py")


# Tablas de opciones cuyo texto se traduce al montar el desplegable, con
# `_(label)` sobre una variable. El extractor solo ve literales, así que estas
# se declaran aquí: sin ellas desaparecerían de los archivos en la siguiente
# pasada y los desplegables volverían al español a mitad de una interfaz en
# inglés.
TABLAS = {
    "silux/ui/pages/settings.py": ("THEMES", "UNITS", "DENSITIES",
                                   "FONT_SCALES", "ACCENTS", "NETWORK_UNITS",
                                   "AUTORIA", "CONSTRUIDO_CON", "DATOS_DE_TERCEROS"),
    "silux/ui/app.py": ("SECTIONS",),
    "silux/model.py": ("CATEGORIES", "CATEGORY_ORDER"),
    "silux/ui/pages/memory.py": ("MODULE_FIELDS", "TIMING_HEADERS"),
    "silux/ui/pages/cpu.py": ("PROCESSOR_FIELDS", "CLOCK_FIELDS"),
    "silux/ui/sensortree.py": ("COLUMNS",),
    "silux/providers/dmi.py": ("CHASSIS_TYPES", "_ALIMENTACION"),
    "silux/providers/hwmon.py": ("ETIQUETAS_GPU", "_ALIMENTACION"),
    "silux/providers/drm.py": ("DRIVERS_CIEGOS", "INTEL_AVISOS", "MOTORES_INTEL",
                              "INTEL_SIN_TEMPERATURA"),
    # Las frases de lo que no aplica a una tarjeta. El resto de claves de esa
    # página se salvan solas porque además aparecen como literal al rellenar
    # cada ficha; estas solo viven aquí y se traducen con `_(frase)`, así que
    # sin declararlas la primera poda se las llevaba.
    "silux/ui/pages/graphics.py": ("NA_SIN_VRAM", "NA_INTEGRADA"),
}


def cadenas_de_tablas() -> dict[str, list[str]]:
    """El primer elemento de cada par de las tablas de opciones."""
    encontradas: dict[str, list[str]] = {}
    for origen, nombres in TABLAS.items():
        ruta = RAIZ / origen
        if not ruta.is_file():
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Assign):
                destinos = nodo.targets
            elif isinstance(nodo, ast.AnnAssign):
                destinos = [nodo.target]
            else:
                continue
            if not any(isinstance(t, ast.Name) and t.id in nombres
                       for t in destinos) or nodo.value is None:
                continue
            for hijo in ast.walk(nodo.value):
                if not isinstance(hijo, (ast.Tuple, ast.Dict)):
                    continue
                # De un par se coge el lado que parece clave, no el primero.
                # Los dos órdenes existen y son igual de naturales: un
                # desplegable es (etiqueta, valor guardado) y la ficha de
                # créditos es (nombre propio, para-qué). Dando por hecha la
                # posición, «Acerca de» salía con `about.author` en pantalla.
                elementos = (hijo.values if isinstance(hijo, ast.Dict)
                             else hijo.elts)
                for elemento in elementos:
                    if (isinstance(elemento, ast.Constant)
                            and isinstance(elemento.value, str)
                            and "." in elemento.value
                            and " " not in elemento.value):
                        encontradas.setdefault(elemento.value, []).append(origen)
    return encontradas


def cadenas_del_codigo() -> dict[str, list[str]]:
    """Cada cadena envuelta en `_()`, con los archivos donde aparece."""
    encontradas: dict[str, list[str]] = {}
    for origen in FUENTES:
        ruta = RAIZ / origen
        archivos = sorted(ruta.rglob("*.py")) if ruta.is_dir() else [ruta]
        for archivo in archivos:
            if not archivo.is_file():
                continue
            try:
                arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for nodo in ast.walk(arbol):
                if not (isinstance(nodo, ast.Call)
                        and isinstance(nodo.func, ast.Name)
                        and nodo.func.id == "_"
                        and nodo.args):
                    continue
                # La clave puede venir elegida con un condicional:
                # `_("sensors.count.one" if n == 1 else "…many")`. De ahí
                # solo son claves las dos ramas: el literal de la
                # comparación —`kind == "wifi"`— es un valor interno, y
                # recogerlo metía «wifi» y «data» en los archivos de idioma.
                primero = nodo.args[0]
                literales = ([primero] if isinstance(primero, ast.Constant)
                             else [n for rama in (primero.body, primero.orelse)
                                   for n in ast.walk(rama)
                                   if isinstance(n, ast.Constant)]
                             if isinstance(primero, ast.IfExp) else [])
                relativo = str(archivo.relative_to(RAIZ))
                for literal in literales:
                    if isinstance(literal.value, str):
                        encontradas.setdefault(literal.value, []).append(relativo)
    return encontradas


# Cuánto se tienen que parecer dos frases para sospechar que una es la otra
# retocada. Por debajo, emparejarlas daría traducciones que dicen otra cosa:
# «Frecuencia» y «Frecuencia máxima» se parecen mucho y no significan lo mismo.
PARECIDO_MINIMO = 0.82


def emparejar(huerfanas: dict[str, str],
              sin_traducir: list[str]) -> list[tuple[str, str, str, float]]:
    """Qué traducción huérfana podría ser de qué cadena nueva.

    Cambiar una coma en el español deja la traducción colgada de la frase
    vieja, y en la interfaz en inglés sale el español nuevo. Aquí se dice cuál
    se parece a cuál para que quien mantiene el idioma lo mueva a mano; se
    sugiere y no se arrastra, porque «Frecuencia» y «Frecuencia máxima» se
    parecen mucho y no se pueden traducir igual.
    """
    import difflib

    sugerencias = []
    for nueva in sin_traducir:
        mejor, parecido = None, 0.0
        for vieja in huerfanas:
            ratio = difflib.SequenceMatcher(None, vieja, nueva).ratio()
            if ratio > parecido:
                mejor, parecido = vieja, ratio
        if mejor and parecido >= PARECIDO_MINIMO:
            sugerencias.append((nueva, mejor, huerfanas[mejor], parecido))
    return sugerencias


def sin_rastro_en_el_codigo(claves: Iterable[str]) -> list[str]:
    """De las que el extractor no ve, cuáles no están escritas en ninguna parte.

    Hay dos motivos para que una clave traducida no aparezca en la extracción,
    y son opuestos. Uno es que se use con una variable —`_(NEED_TITLES[x])`—,
    y esa hay que conservarla: borrarla dejaría un aviso en crudo en pantalla.
    El otro es que ya no la use nadie, y esas se acumulan: al renombrar
    `mem.slots.used` a `memory.slots.used` la vieja se queda con su traducción
    puesta, indistinguible de una buena.

    La diferencia se ve buscando la clave como texto en todo el paquete. Si no
    está escrita en ningún archivo, no hay forma de que llegue a `_()`.
    """
    fuente = "\n".join(archivo.read_text(encoding="utf-8")
                       for archivo in (RAIZ / "silux").rglob("*.py"))
    return sorted(clave for clave in claves if clave not in fuente)


def actualizar(codigo: str, cadenas: dict[str, list[str]], escribir: bool,
               podar: Iterable[str] = ()) -> tuple[int, int, int]:
    """Sincroniza un idioma. Devuelve (traducidas, sin traducir, sobrantes)."""
    ruta = LANG / f"{codigo}.json"
    try:
        actual = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        actual = {}

    podar = set(podar)
    nuevo = {texto: actual.get(texto, "") for texto in sorted(cadenas)}
    sobrantes = {k: v for k, v in actual.items()
                 if k not in cadenas and v and k not in podar}

    # Lo que ya está traducido no se borra aunque el extractor no lo encuentre.
    # Puede ser una cadena que cambió de sitio, o una que se traduce con una
    # variable y aquí no se ve; en cualquier caso, tirar el trabajo de alguien
    # sin preguntar es lo peor que puede hacer esta herramienta. Se queda y se
    # dice cuántas son, para que quien mire decida.
    nuevo.update(sobrantes)
    nuevo = dict(sorted(nuevo.items()))

    if escribir:
        LANG.mkdir(parents=True, exist_ok=True)
        # `ensure_ascii=False` para que las tildes se lean en el diff de
        # GitHub, que es donde se van a revisar estos archivos.
        ruta.write_text(
            json.dumps(nuevo, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    hechas = sum(1 for v in nuevo.values() if v)
    return hechas, len(nuevo) - hechas, len(sobrantes)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="escribe los cambios en los .json")
    parser.add_argument("--podar", action="store_true",
                        help="borra además las claves que ya no aparecen "
                             "escritas en ninguna parte del código")
    args = parser.parse_args(argv)

    cadenas = cadenas_del_codigo()
    tablas = cadenas_de_tablas()
    for texto, donde in tablas.items():
        cadenas.setdefault(texto, []).extend(donde)
    print(f"  {len(cadenas)} cadenas traducibles "
          f"({len(tablas)} de tablas de opciones)")

    idiomas = sorted(p.stem for p in LANG.glob("*.json")) if LANG.is_dir() else []
    if not idiomas:
        idiomas = ["es", "en"]

    # Lo que sobra, separado en dos: lo que se usa con una variable y hay que
    # conservar, y lo que ya no menciona nadie.
    de_referencia = json.loads((LANG / "es.json").read_text(encoding="utf-8"))
    muertas = sin_rastro_en_el_codigo(k for k in de_referencia
                                      if k not in cadenas)

    for codigo in idiomas:
        hechas, faltan, sobran = actualizar(
            codigo, cadenas, args.write, muertas if args.podar else ())
        estado = f"  {codigo}: {hechas} traducidas, {faltan} sin traducir"
        if sobran:
            estado += (f", {sobran} que se traducen con una variable "
                       "(se conservan)")
        print(estado)

    if muertas:
        print(f"\n  {len(muertas)} claves que ya no aparecen en el código:")
        for clave in muertas:
            print(f"    {clave}")
        if not args.podar:
            print("  (con --podar se borran)")

    if not args.write:
        print("\n  (informe; con --write se actualizan los archivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
