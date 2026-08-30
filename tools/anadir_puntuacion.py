#!/usr/bin/env python3
"""Convierte los informes que manda la gente en muestras de la tabla.

    python3 tools/anadir_puntuacion.py informes/*.md          # qué añadiría
    python3 tools/anadir_puntuacion.py --write informes/*.md  # las añade

La barra que sitúa una puntuación necesita saber qué sacan los demás con la
misma pieza, y eso no se puede medir aquí: sale de los informes ajenos. Cada
uno trae su sección de rendimiento con la cifra y las condiciones, y esta
herramienta las junta en `silux/db/scores.json`.

Es de quien mantiene el programa, no de quien lo usa. Quien tiene la pieza no
necesita nada: hace su prueba y manda el informe.

**Lo que no cuadra se rechaza y se dice por qué.** El cliente es código
abierto: cualquiera puede mandar un informe con la cifra que le apetezca, y no
hay forma de impedirlo. Lo que sí se puede es que una entrada inventada no
mueva la tabla, y para eso están las condiciones que el informe trae al lado:
una puntuación imposible para ese número de hilos, o medida con el equipo
ocupado, o con una escala que ya no es la vigente, se queda fuera.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from silux import score  # noqa: E402

TABLA = RAIZ / "silux" / "db" / "scores.json"

# El nombre de la pieza va en negrita bajo su encabezado.
_CPU = re.compile(r"^## Procesador\s*\n+\*\*(.+?)\*\*", re.MULTILINE)
_FILA = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", re.MULTILINE)

# Por encima de esto, la prueba se hizo con el equipo haciendo otras cosas y su
# cifra no describe la pieza sino el momento.
CARGA_MAXIMA = 5.0

# Ninguna carga escala por encima del número de hilos, así que una puntuación
# de todos los hilos que multiplique la de uno por más que eso viene de un
# informe tocado o de una medida rota. Se deja un margen porque el turbo de un
# solo núcleo es más alto que el de todos y eso ya recorta la escala real.
MARGEN_DE_ESCALA = 1.05


def leer(ruta: pathlib.Path) -> tuple[dict, str]:
    """Lo que trae un informe, o el motivo por el que no sirve."""
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return {}, f"no se puede leer: {error}"

    cpu = _CPU.search(texto)
    if not cpu:
        return {}, "no se encuentra el procesador"

    trozo = texto.partition("## Rendimiento")[2].partition("\n## ")[0]
    if not trozo:
        return {}, "no trae prueba de rendimiento"
    campos = {clave: valor for clave, valor in _FILA.findall(trozo)}

    def numero(clave, entero=True):
        crudo = campos.get(clave, "").split()[0].replace(",", ".") if campos.get(clave) else ""
        try:
            return int(float(crudo)) if entero else float(crudo)
        except ValueError:
            return None

    datos = {
        "cpu": cpu.group(1).strip(),
        "multihilo": numero("Puntuación (todos los hilos)"),
        "un_hilo": numero("Puntuación (un hilo)"),
        "hilos": numero("Hilos"),
        "escala": campos.get("Escala", ""),
        "gobernador": campos.get("Gobernador", ""),
        "carga": numero("Carga de fondo", entero=False),
        "origen": ruta.name,
    }
    return datos, ""


def revisar(datos: dict) -> str:
    """Por qué esta muestra no entra, o cadena vacía si entra."""
    if datos["multihilo"] is None or datos["un_hilo"] is None:
        return "sin puntuación"
    if datos["escala"] != f"v{score.VERSION}":
        return f"otra escala ({datos['escala'] or 'sin declarar'})"
    if not datos["hilos"]:
        return "no dice cuántos hilos"
    if datos["carga"] is not None and datos["carga"] > CARGA_MAXIMA:
        return f"medida con {datos['carga']:.0f} % de carga de fondo"
    escala = datos["multihilo"] / max(datos["un_hilo"], 1)
    if escala > datos["hilos"] * MARGEN_DE_ESCALA:
        return (f"escala imposible: {escala:.1f}× con {datos['hilos']} hilos")
    return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("informes", nargs="+", help="los .md que manda la gente")
    parser.add_argument("--write", action="store_true",
                        help="añade las muestras a silux/db/scores.json")
    args = parser.parse_args(argv)

    tabla = json.loads(TABLA.read_text(encoding="utf-8"))
    piezas = tabla.setdefault("piezas", {})
    admitidas = []

    for nombre in args.informes:
        ruta = pathlib.Path(nombre)
        datos, fallo = leer(ruta)
        motivo = fallo or revisar(datos)
        if motivo:
            print(f"  ✗ {ruta.name}: {motivo}", file=sys.stderr)
            continue
        admitidas.append(datos)
        print(f"  ✓ {ruta.name}: {datos['cpu']} · {datos['multihilo']} "
              f"({datos['un_hilo']} a un hilo)")

    if not admitidas:
        print("\n  nada que añadir")
        return 1

    for datos in admitidas:
        pieza = piezas.setdefault(datos["cpu"], {"hilos": datos["hilos"],
                                                 "un_hilo": [], "multihilo": []})
        pieza["un_hilo"].append(datos["un_hilo"])
        pieza["multihilo"].append(datos["multihilo"])

    print()
    for nombre, pieza in sorted(piezas.items()):
        cuantas = len(pieza["multihilo"])
        falta = score.MINIMO_MUESTRAS - cuantas
        estado = ("se compara" if falta <= 0
                  else f"faltan {falta} para poder comparar")
        print(f"  {nombre:<38} {cuantas:>2} medidas · {estado}")

    if not args.write:
        print("\n  (con --write se guardan)")
        return 0

    TABLA.write_text(json.dumps(tabla, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print(f"\n  guardadas en {TABLA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
