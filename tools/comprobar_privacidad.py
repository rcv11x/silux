#!/usr/bin/env python3
"""Busca en lo que se va a publicar datos de la máquina donde se trabaja.

Se escribió después de encontrar el nombre del equipo, la dirección física de
la tarjeta de red y el número de serie de la gráfica dentro de los archivos de
prueba, puestos ahí sin pensar al montar un caso. Uno de esos archivos era,
precisamente, el que comprueba que el informe de fallos no publica nada de eso.

    python3 tools/comprobar_privacidad.py

Devuelve 1 si encuentra algo, para poder engancharlo a un hook de git.
"""

from __future__ import annotations

import pathlib
import re
import socket
import subprocess
import sys

RANGOS_DE_DOCUMENTACION = (
    re.compile(r"^192\.0\.2\."), re.compile(r"^198\.51\.100\."),
    re.compile(r"^203\.0\.113\."), re.compile(r"^2001:db8"),
    re.compile(r"^00:00:5e:00:53:", re.I),
)


def _versionados() -> list[pathlib.Path]:
    salida = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return [pathlib.Path(l) for l in salida.stdout.splitlines() if l]


def _de_esta_maquina() -> dict[str, str]:
    """Lo que identifica al equipo donde se está trabajando ahora mismo."""
    datos = {socket.gethostname(): "el nombre de este equipo"}
    for ruta in pathlib.Path("/sys/class/net").glob("*/address"):
        try:
            mac = ruta.read_text().strip()
        except OSError:
            continue
        if mac and not mac.startswith("00:00:00"):
            datos[mac] = f"la dirección física de {ruta.parent.name}"
    for ruta in pathlib.Path("/sys/class/drm").glob("card*/device/unique_id"):
        try:
            serie = ruta.read_text().strip()
        except OSError:
            continue
        if serie:
            datos[serie] = "el número de serie de la gráfica"
    if (casa := pathlib.Path.home()).name:
        datos[str(casa)] = "la carpeta personal"
    return datos


def _direcciones_sospechosas(texto: str) -> list[str]:
    """IP privadas que no sean de los rangos reservados para documentación."""
    encontradas = re.findall(
        r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
        texto)
    return [d for d in encontradas
            if not any(r.match(d) for r in RANGOS_DE_DOCUMENTACION)]


def main() -> int:
    propios = _de_esta_maquina()
    hallazgos: list[str] = []

    for ruta in _versionados():
        try:
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for dato, que_es in propios.items():
            if dato and dato in texto:
                hallazgos.append(f"{ruta}: {que_es}")
        for direccion in _direcciones_sospechosas(texto):
            hallazgos.append(f"{ruta}: la dirección {direccion}")

    autores = subprocess.run(
        ["git", "log", "--all", "--format=%ae%n%ce"],
        capture_output=True, text=True).stdout.split()
    if len(set(autores)) > 1:
        hallazgos.append(f"el historial tiene {len(set(autores))} correos "
                         f"distintos: {', '.join(sorted(set(autores)))}")

    if not hallazgos:
        print("Nada que delate a esta máquina en lo que se va a publicar.")
        return 0

    print("Esto se publicaría:", file=sys.stderr)
    for linea in sorted(set(hallazgos)):
        print(f"  {linea}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
