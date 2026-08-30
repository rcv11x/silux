#!/usr/bin/env python3
"""Vuelve a medir la escala con la que se puntúan las pruebas.

    python3 tools/medir_referencia.py            # mide y enseña
    python3 tools/medir_referencia.py --write    # y la guarda

Las cinco cargas del benchmark dan cifras de magnitudes muy distintas —en un
5800X3D, 28 000 operaciones por segundo la compresión pesada y 480 la memoria—,
así que sumarlas en crudo deja la puntuación en manos de una sola. La escala
las pone a todas en la misma unidad: cada una vale lo que da en el equipo que
sirve de patrón.

Rehacerla cambia la puntuación de todo el mundo a la vez, así que no es algo
que se haga a menudo. Cuando se haga, tiene que subir `score.VERSION`: una
cifra medida con una escala y otra medida con la siguiente no se pueden poner
juntas, y nada en pantalla avisaría de eso.

**La máquina tiene que estar en reposo.** El propio benchmark avisa cuando hay
carga de fondo, y una escala tomada con el navegador abierto arrastra ese error
a las puntuaciones de todos los demás. Aquí se comprueba y se para.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from silux import benchmark, render, score  # noqa: E402
from silux.collector import Collector  # noqa: E402

# Por encima de esto, la medida no vale como escala. El benchmark ya lo avisa
# por su cuenta; aquí se convierte en un corte, porque una cosa es informar de
# que una prueba salió sucia y otra publicarla como referencia de las demás.
CARGA_MAXIMA = 3.0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="guarda la escala en silux/db/scores.json")
    parser.add_argument("--igualmente", action="store_true",
                        help="mide aunque la máquina no esté en reposo (la "
                             "escala queda marcada como provisional)")
    args = parser.parse_args(argv)

    foto = Collector().sample()
    cpu = (render.cpu_short_name(foto.cpu.types[0].brand)
           if foto.cpu.types else "?")
    print(f"  midiendo en {cpu}, {os.cpu_count() or 1} hilos, "
          f"{score.SEGUNDOS_CANONICOS:.0f} s por carga")
    print("  (unos dos minutos y medio; conviene no tocar el equipo)\n")

    resultado = benchmark.run(seconds=score.SEGUNDOS_CANONICOS)
    for aviso in resultado.warnings:
        print(f"  aviso: {aviso}", file=sys.stderr)

    carga = resultado.conditions.background_load
    sucia = carga is not None and carga > CARGA_MAXIMA
    if sucia and not args.igualmente:
        print(f"\n  Había un {carga:.0f} % de carga de fondo y la escala se "
              f"toma en reposo.\n  Cierra lo que esté corriendo y repite, o "
              f"usa --igualmente si sabes lo que haces.", file=sys.stderr)
        return 1

    hilos = max((m.threads for m in resultado.measures), default=1)
    op = {f"{m.load}/{m.threads}": m.operations / m.seconds
          for m in resultado.measures if m.seconds}
    cargas = sorted({k.split("/")[0] for k in op})

    tabla = {
        "schema": 1,
        "version_formula": score.VERSION,
        "about": _leer_about(),
        "patron": {
            "cpu": cpu,
            "hilos": hilos,
            "segundos": score.SEGUNDOS_CANONICOS,
            "gobernador": resultado.conditions.governor,
            "carga_de_fondo": carga,
            "temperatura_pico_c": resultado.conditions.temperature_peak_c,
            "provisional": bool(sucia),
        },
        "un_hilo": {c: round(op[f"{c}/1"], 2) for c in cargas},
        "multihilo": {c: round(op[f"{c}/{hilos}"], 2) for c in cargas},
    }
    # Lo que han medido otros equipos no lo produce esta herramienta y no se
    # puede volver a tomar: se conserva salvo que cambie la versión.
    if piezas := _piezas_que_siguen_valiendo():
        tabla["piezas"] = piezas

    print(f"\n  {'carga':<18} {'1 hilo':>10} {str(hilos) + ' hilos':>12}")
    for c in cargas:
        print(f"  {c:<18} {tabla['un_hilo'][c]:>10} {tabla['multihilo'][c]:>12}")

    if not args.write:
        print("\n  (con --write se guarda; acuérdate de subir score.VERSION)")
        return 0

    destino = RAIZ / "silux" / "db" / "scores.json"
    destino.write_text(json.dumps(tabla, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    print(f"\n  guardada en {destino.relative_to(RAIZ)}")
    print("  sube score.VERSION: las puntuaciones anteriores ya no valen")
    return 0


def _tabla_anterior() -> dict:
    """Lo que hay guardado ahora mismo, o vacío si no hay nada legible."""
    try:
        with (RAIZ / "silux" / "db" / "scores.json").open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _leer_about() -> str:
    """Conserva la explicación que ya tenga el archivo, si la tiene."""
    return _tabla_anterior().get("about", "")


def _piezas_que_siguen_valiendo() -> dict:
    """Las medidas de otros equipos, si la escala nueva es la misma versión.

    `anadir_puntuacion.py` las va acumulando en «piezas», y esta herramienta
    reescribía el archivo entero sin ellas: remedir la escala las borraba
    todas. No se notó porque todavía no había ninguna, que es la única razón
    por la que esto no ha costado ya un disgusto.

    Cuando cambia la versión de la fórmula sí se descartan, y entonces es lo
    correcto: una puntuación medida con la escala anterior no significa lo
    mismo que una de ahora, y guardarlas juntas es justo lo que
    `score.VERSION` existe para impedir.
    """
    anterior = _tabla_anterior()
    if not anterior.get("piezas"):
        return {}
    if anterior.get("version_formula") != score.VERSION:
        cuantas = len(anterior["piezas"])
        print(f"  se descartan las medidas de {cuantas} "
              f"{'pieza' if cuantas == 1 else 'piezas'}: eran de la escala "
              f"v{anterior.get('version_formula')} y esta es la "
              f"v{score.VERSION}", file=sys.stderr)
        return {}
    return anterior["piezas"]


if __name__ == "__main__":
    sys.exit(main())
