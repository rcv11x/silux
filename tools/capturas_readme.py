#!/usr/bin/env python3
"""Las capturas del README: la ventana de verdad, anonimizada y con permisos.

    python3 tools/capturas_readme.py              # a ~/Imágenes/silux-test/readme/
    python3 tools/capturas_readme.py --segundos 60

Monta la ventana sin pantalla, pide los permisos una vez (la contraseña la
pide el sistema en su ventana), deja que se llenen las gráficas y guarda
Inicio, CPU, Gráficos, Memoria y Sensores. Cada imagen va anonimizada, como
con `--anonymous`, y lo lleva escrito dentro (`silux-anonimo`), que es lo
que mira `tools/comprobar_privacidad.py`. Se guardan fuera del repositorio:
se miran antes de copiarlas a `capturas/es/` o `capturas/en/`, según el idioma.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PAGINAS = (("nav.home", "inicio"), ("nav.cpu", "cpu"), ("nav.graphics", "graficos"),
           ("nav.memory", "memoria"), ("nav.sensors", "sensores"))


def carpeta_de_imagenes() -> pathlib.Path:
    try:
        base = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        base = str(pathlib.Path.home() / "Pictures")
    return pathlib.Path(base) / "silux-test" / "readme"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--segundos", type=int, default=30,
                        help="cuánto se dejan llenar las gráficas antes de capturar")
    parser.add_argument("--destino", type=pathlib.Path, default=None)
    parser.add_argument("--tamano", default="1100x720")
    parser.add_argument("--sin-permisos", action="store_true")
    args = parser.parse_args()

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(RAIZ))
    from PySide6.QtWidgets import QApplication

    from silux.collector import Collector
    from silux.privacidad import anonymize
    from silux.ui import app as appmod

    destino = args.destino or carpeta_de_imagenes()
    destino.mkdir(parents=True, exist_ok=True)
    aplicacion, ventana, _opciones = appmod.build_app(["--dark", "--size", args.tamano])
    ventana.show()
    recolector = Collector()
    if not args.sin_permisos:
        print("Pidiendo permisos: la contraseña la pide el sistema en su ventana.",
              flush=True)
        recolector.request_elevation()
    for _vuelta in range(max(2, args.segundos)):
        ventana._on_sample(anonymize(recolector.snapshot()))
        aplicacion.processEvents()
        time.sleep(1.0)
    privilegios = ventana._last_snapshot.privileged
    print("Con permisos:", "sí" if privilegios.connected else "no", flush=True)
    for clave, nombre in PAGINAS:
        if not ventana.select_section(clave):
            continue
        for _vez in range(5):
            aplicacion.processEvents()
            time.sleep(0.08)
        imagen = ventana.grab().toImage()
        imagen.setText("silux-anonimo", "anonima")
        ruta = destino / f"{nombre}.png"
        imagen.save(str(ruta))
        print(ruta, flush=True)
    recolector.close()
    QApplication.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
