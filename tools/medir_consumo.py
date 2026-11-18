#!/usr/bin/env python3
"""Lo que gasta silux por página, contra sus objetivos de CLAUDE.md.

    python3 tools/medir_consumo.py               # todas las páginas, ~6 min
    python3 tools/medir_consumo.py --paginas Inicio,Gráficos --segundos 6
    python3 tools/medir_consumo.py --json consumo.json

Abre la ventana sin pantalla (`QT_QPA_PLATFORM=offscreen`) con unas
preferencias aisladas en una carpeta temporal —no toca las de quien lo
ejecuta— y lee este equipo de verdad, con el muestreo a un segundo. Para
cada página mide, en % de un núcleo y con todos los hilos del proceso:

- a la vista, sin movimiento fluido y con él;
- escondida (la ventana se esconde, que es lo que hace el compositor con una
  minimizada o en otro escritorio).

Y la memoria (RSS) al acabar. Sale con código 1 si algo pasa de su objetivo.

Sin pantalla Qt pinta igual, en memoria; lo que no cuenta es lo que le
cuesta al compositor. Para eso, y para los estados de verdad (minimizada, en
otro escritorio), está la medida con la ventana en la pantalla de
`docs/rendimiento.md`. Las cifras dependen del equipo: los objetivos son del
5800X3D, y en uno más lento conviene mirar la tabla más que el código de
salida. No va en la suite: medir CPU en un runner compartido es ruido.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Los objetivos, en % de un núcleo, para la página que más gasta de cada
# estado. Son los de CLAUDE.md (regla 7); si se cambian aquí, se cambian
# allí. Medido el 18 de noviembre de 2026 en el 5800X3D (CachyOS) con esta
# herramienta: 5,7 sin fluido (Gráficos), 7,2 con él (Gráficos), 4,5
# escondida; antes de la pasada de rendimiento, 9,4, 22,8 y 8,2. El margen es
# para el ruido de la medida, que ronda el medio punto.
OBJETIVOS = {
    ("vista", False): 7.0,      # a la vista, sin movimiento fluido
    ("vista", True): 9.0,       # a la vista, con él
    ("escondida", False): 5.5,  # minimizada o en otro escritorio
    ("escondida", True): 5.5,
}
MEMORIA_MB = 300                # el presupuesto de siempre (regla 7)
ASENTAR_S = 3.0


def medir(fluido: bool, paginas: list[str], segundos: float) -> list[dict]:
    """Una ventana nueva por ajuste, en un proceso aparte: así el arranque y
    lo que deja una medida no se cuelan en la otra."""
    with tempfile.TemporaryDirectory(prefix="silux-consumo-") as conf:
        os.makedirs(os.path.join(conf, "silux"))
        with open(os.path.join(conf, "silux", "settings.json"), "w") as f:
            json.dump({"interval_s": 1.0, "fluid_charts": fluido, "theme": "dark",
                       "font_scale": "normal", "language": "es",
                       "window_width": 1440, "window_height": 900}, f)
        entorno = dict(os.environ, XDG_CONFIG_HOME=conf, QT_QPA_PLATFORM="offscreen")
        salida = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--hijo", json.dumps(paginas),
             str(segundos)], env=entorno, capture_output=True, text=True, cwd=RAIZ)
    if salida.returncode != 0:
        raise SystemExit(f"la medida falló:\n{salida.stderr[-2000:]}")
    filas = json.loads(salida.stdout.strip().splitlines()[-1])
    for fila in filas:
        fila["fluido"] = fluido
    return filas


def hijo(paginas: list[str], segundos: float) -> None:
    """Dentro del proceso medido: monta la ventana y recorre las páginas."""
    sys.path.insert(0, RAIZ)
    from PySide6.QtCore import QTimer

    from silux.ui import app as appmod

    app, ventana, _args = appmod.build_app([])
    if not paginas:
        paginas = [n for n in ventana.section_names() if ventana.select_section(n)]
    plan = [("vista", p) for p in paginas] + [("escondida", p) for p in paginas[:2]]
    filas: list[dict] = []

    def rss_mb() -> float:
        for linea in open("/proc/self/status"):
            if linea.startswith("VmRSS:"):
                return int(linea.split()[1]) / 1024
        return 0.0

    def siguiente() -> None:
        if not plan:
            print(json.dumps(filas, ensure_ascii=False), flush=True)
            app.quit()
            return
        estado, pagina = plan.pop(0)
        if estado == "escondida" and ventana.isVisible():
            ventana.hide()
        ventana.select_section(pagina)
        QTimer.singleShot(int(ASENTAR_S * 1000), lambda: empezar(estado, pagina))

    def empezar(estado: str, pagina: str) -> None:
        inicio = (time.monotonic(), time.process_time())
        QTimer.singleShot(int(segundos * 1000), lambda: acabar(estado, pagina, inicio))

    def acabar(estado: str, pagina: str, inicio: tuple) -> None:
        t0, c0 = inicio
        filas.append({"estado": estado, "pagina": pagina,
                      "cpu": round(100 * (time.process_time() - c0) / (time.monotonic() - t0), 2),
                      "rss_mb": round(rss_mb(), 1)})
        siguiente()

    ventana.resize(1440, 900)
    ventana.show()
    ventana.start()
    QTimer.singleShot(4000, siguiente)        # el primer muestreo y lo estático
    app.exec()
    ventana.sampler.stop()
    os._exit(0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--paginas", default="", help="separadas por comas; todas si no")
    parser.add_argument("--segundos", type=float, default=8.0, help="por medida (8)")
    parser.add_argument("--json", metavar="FICHERO", help="guarda las medidas")
    parser.add_argument("--hijo", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.hijo:
        hijo(json.loads(args.hijo[0]), float(args.hijo[1]))
        return 0

    paginas = [p for p in args.paginas.split(",") if p]
    filas = medir(False, paginas, args.segundos) + medir(True, paginas, args.segundos)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(filas, f, ensure_ascii=False, indent=1)

    print(f"{'estado':10} {'página':15} {'sin fluido':>10} {'con fluido':>10}")
    por = {(f["estado"], f["pagina"], f["fluido"]): f for f in filas}
    for estado, pagina in dict.fromkeys((f["estado"], f["pagina"]) for f in filas):
        sin, con = por.get((estado, pagina, False)), por.get((estado, pagina, True))
        print(f"{estado:10} {pagina:15} {sin['cpu'] if sin else '—':>9} % {con['cpu'] if con else '—':>9} %")

    fallos = []
    for (estado, fluido), objetivo in OBJETIVOS.items():
        peor = max((f for f in filas if f["estado"] == estado and f["fluido"] == fluido),
                   key=lambda f: f["cpu"], default=None)
        if peor and peor["cpu"] > objetivo:
            fallos.append(f"{estado}, {'con' if fluido else 'sin'} fluido: {peor['pagina']} "
                          f"gasta {peor['cpu']} % de un núcleo; el objetivo es {objetivo} %")
    memoria = max(f["rss_mb"] for f in filas)
    if memoria > MEMORIA_MB:
        fallos.append(f"memoria: {memoria} MB; el presupuesto es {MEMORIA_MB} MB")
    print(f"\nmemoria máxima: {memoria} MB (presupuesto {MEMORIA_MB} MB)")
    for fallo in fallos:
        print(f"PASA DEL OBJETIVO: {fallo}")
    if not fallos:
        print("dentro de los objetivos")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
