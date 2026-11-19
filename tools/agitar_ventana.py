#!/usr/bin/env python3
"""La ventana de verdad cambiando de forma sin parar, para cazar cierres de Qt.

    python3 tools/agitar_ventana.py                    # diez minutos, una ventana
    python3 tools/agitar_ventana.py --minutos 2 --ventanas 6

Monta la ventana como `main()`, con su bucle de eventos, y cada 300 ms le da
la foto de un equipo distinto (los volcados de `tests/fixtures/equipos`, con
y sin contadores avanzando), mientras cambia de página cada 70 ms. Es lo que
en la app pasa al dar permisos o al conectar un disco o un USB, en bucle.

Así se vio que PySide6 6.11.3 en Python 3.10 libera dos veces la llamada
encolada de un `QScrollBar`: tres ventanas de seis reventaron en diez
minutos. Con 6.9.3 en 3.10 y con 6.12.0 en 3.14, ninguna. Cambiando de
página con las fotos de un solo equipo no revienta: hace falta que la
ventana cambie de forma (docs/empaquetado.md).

Cada ventana va en su proceso, sin pantalla. Sale con 1 si alguna revienta,
y dice la versión de Python y de PySide6 con que se probó.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def agitar(minutos: float, semilla: int) -> int:
    """Una ventana, en este proceso. Sale con 0 si llega viva al final."""
    import faulthandler
    import random
    import time

    faulthandler.enable()
    sys.path.insert(0, str(RAIZ))
    from PySide6.QtCore import QTimer

    from silux.ui import app as appmod
    from tests.test_equipos import volcados
    from tests.test_nada_se_mueve import con_contadores_avanzando, dos_fotos

    aplicacion, ventana, _args = appmod.build_app([])
    fotos = []
    for carpeta in volcados():
        fotos += [*dos_fotos(carpeta), *con_contadores_avanzando(carpeta)]
    ventana.show()
    ventana._on_sample(fotos[0])
    secciones = [clave for clave, activa in appmod.SECTIONS if activa]
    azar = random.Random(semilla)
    fin = time.monotonic() + minutos * 60
    cuenta = {"fotos": 0, "páginas": 0}

    def foto() -> None:
        if time.monotonic() > fin:
            print(f"viva: {cuenta['fotos']} fotos, {cuenta['páginas']} páginas",
                  flush=True)
            aplicacion.quit()
            return
        ventana._on_sample(azar.choice(fotos))
        cuenta["fotos"] += 1

    def pagina() -> None:
        ventana.select_section(azar.choice(secciones))
        cuenta["páginas"] += 1

    reloj_fotos = QTimer()
    reloj_fotos.timeout.connect(foto)
    reloj_fotos.start(300)
    reloj_paginas = QTimer()
    reloj_paginas.timeout.connect(pagina)
    reloj_paginas.start(70)
    return aplicacion.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutos", type=float, default=10.0)
    parser.add_argument("--ventanas", type=int, default=1)
    parser.add_argument("--una", type=int, metavar="SEMILLA",
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.una is not None:
        return agitar(args.minutos, args.una)

    import PySide6

    print(f"Python {sys.version.split()[0]} · PySide6 {PySide6.__version__} · "
          f"{args.ventanas} ventanas, {args.minutos:g} minutos", flush=True)
    with tempfile.TemporaryDirectory() as carpeta:
        entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       XDG_CONFIG_HOME=carpeta, PYTHONFAULTHANDLER="1")
        procesos = [subprocess.Popen(
            [sys.executable, __file__, "--minutos", str(args.minutos),
             "--una", str(semilla)],
            env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True) for semilla in range(args.ventanas)]
        caidas = 0
        for semilla, proceso in enumerate(procesos):
            salida, _ = proceso.communicate()
            if proceso.returncode != 0:
                caidas += 1
                print(f"ventana {semilla}: revienta (código {proceso.returncode})")
                print("    " + "\n    ".join(
                    l for l in salida.splitlines() if "Fatal" in l or "File" in l))
            else:
                print(f"ventana {semilla}: {salida.strip().splitlines()[-1]}")
    print(f"{caidas} de {args.ventanas} reventaron")
    return 1 if caidas else 0


if __name__ == "__main__":
    raise SystemExit(main())
