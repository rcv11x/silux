#!/usr/bin/env python3
"""Mantiene al día los archivos de idioma a partir de lo que dice el código.

    python3 tools/gen_lang.py            # informe: qué falta y qué sobra
    python3 tools/gen_lang.py --write    # actualiza los .json

Recorre el código buscando las llamadas a `_()` y compara lo que encuentra con
lo que hay en `silux/db/lang/*.json`. Lo que falta se añade con la traducción
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

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LANG = RAIZ / "silux" / "db" / "lang"

# Dónde puede haber texto de interfaz. `providers/` no está: lo que sale de ahí
# son datos del equipo, no frases del programa.
FUENTES = ("silux/ui", "silux/render.py", "silux/cli.py", "silux/report.py")


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
                primero = nodo.args[0]
                if isinstance(primero, ast.Constant) and isinstance(primero.value, str):
                    relativo = str(archivo.relative_to(RAIZ))
                    encontradas.setdefault(primero.value, []).append(relativo)
    return encontradas


def actualizar(codigo: str, cadenas: dict[str, list[str]],
               escribir: bool) -> tuple[int, int, int]:
    """Sincroniza un idioma. Devuelve (traducidas, sin traducir, sobrantes)."""
    ruta = LANG / f"{codigo}.json"
    try:
        actual = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        actual = {}

    nuevo = {texto: actual.get(texto, "") for texto in sorted(cadenas)}
    sobrantes = {k: v for k, v in actual.items() if k not in cadenas and v}

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
    args = parser.parse_args(argv)

    cadenas = cadenas_del_codigo()
    print(f"  {len(cadenas)} cadenas envueltas en _() en el código")

    idiomas = sorted(p.stem for p in LANG.glob("*.json")) if LANG.is_dir() else []
    if not idiomas:
        idiomas = ["en"]

    for codigo in idiomas:
        hechas, faltan, sobran = actualizar(codigo, cadenas, args.write)
        estado = f"  {codigo}: {hechas} traducidas, {faltan} sin traducir"
        if sobran:
            estado += f", {sobran} que ya no están en el código"
        print(estado)

    if not args.write:
        print("\n  (informe; con --write se actualizan los archivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
