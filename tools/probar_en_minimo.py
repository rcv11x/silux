#!/usr/bin/env python3
"""Ejecuta la suite en el Python más viejo que el proyecto dice soportar.

Que los tests pasen aquí no dice nada de si pasan en el mínimo. Esto se
descubrió empujando: `self.enterContext` es de 3.11 y se llevó once tests por
delante en el CI mientras en la máquina del autor —que va con 3.14— estaban
todos en verde. Y no es un problema que se resuelva leyendo el código: el otro
fallo de aquel día fue un traceback que perdía el texto de la línea porque
hasta 3.12 quien pinta las excepciones no atrapadas es el escritor en C, y ese
busca el código abriendo el archivo por su nombre. Eso no lo ve ningún
analizador; se probó `vermin -t=3.10` y ni siquiera cazaba el `enterContext`,
porque no sabe a qué clase pertenece un método llamado sobre `self`.

Así que la única comprobación que vale es ejecutarlo, y el CI ya lo hace. Esto
es para enterarse antes de empujar, que es más barato.

    python3 tools/probar_en_minimo.py --container

Es el mismo trato que `build_appimage.py --container`: dentro de una Ubuntu
22.04, que es donde vive el Python del suelo y donde se construye el AppImage.
Sin `--container` se busca un intérprete del mínimo en esta máquina, que sirve
si alguien tiene pyenv, pero no reproduce el resto del entorno.

El suelo no está escrito aquí: sale de `requires-python` del `pyproject.toml`,
para que subirlo no deje esta herramienta comprobando otra cosa.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# La que trae el Python del suelo, y la misma en la que se construye el
# AppImage y en la que corre el CI. Si el suelo sube, esta imagen deja de
# valer y la receta lo dice en vez de probar contra otra versión en silencio.
IMAGEN_BASE = "docker.io/library/ubuntu:22.04"

# Con el que sale la receta cuando la imagen no trae el Python declarado. Va
# aparte de un fallo de los tests: son dos cosas distintas y el mensaje final
# lo dice, porque «no pasa» manda a buscar un fallo que no existe.
SUELO_QUE_NO_CUADRA = 2


def suelo_declarado() -> str:
    """El «3.10» de `requires-python = ">=3.10"`."""
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    casa = re.search(r'requires-python\s*=\s*"[^"]*?(\d+\.\d+)"', texto)
    if casa is None:
        raise SystemExit("No encuentro requires-python en pyproject.toml")
    return casa.group(1)


# Lo que corre dentro. Instala lo mismo que el CI —ni más ni menos, para que
# verde aquí signifique verde allí— y copia el árbol fuera del punto de
# montaje: va en solo lectura a propósito, así los `__pycache__` que escribe
# root no acaban en el repositorio de quien lo lanza.
RECETA = """set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    python3 python3-pip \
    libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 \
    libfontconfig1 libfreetype6 libglib2.0-0 hwdata >/dev/null

TIENE="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$TIENE" != "$SUELO" ]; then
    echo "Esta imagen trae Python $TIENE y el proyecto declara $SUELO." >&2
    echo "O se cambia IMAGEN_BASE por una que traiga $SUELO, o se cambia" >&2
    echo "requires-python. Probar contra otra versión no comprueba nada." >&2
    exit 2
fi

pip install -q "$PYSIDE"

mkdir -p /trabajo
cp -a /fuente/. /trabajo/
rm -rf /trabajo/.git /trabajo/dist /trabajo/build
find /trabajo -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
cd /trabajo

echo
python3 -V
python3 -c 'import PySide6; print("PySide6", PySide6.__version__)'
echo
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
"""


def motor_de_contenedores() -> str:
    motor = next((m for m in ("podman", "docker") if shutil.which(m)), None)
    if motor is None:
        raise SystemExit(
            "Hace falta podman o docker para probar en contenedor.\n"
            "  sudo pacman -S podman        (Arch, CachyOS)\n"
            "  sudo dnf install podman      (Fedora)\n"
            "  sudo apt install podman      (Debian, Ubuntu)")
    return motor


def rango_de_pyside() -> str:
    """El mismo que usan el CI y el empaquetador, preguntándoselo a él.

    Repetirlo aquí sería tener dos sitios donde dice qué Qt se prueba, y el que
    nadie mira se queda atrás. Ya pasó con el paso del CI, que decía
    «PySide6>=6.6» a secas.
    """
    hecho = subprocess.run(
        [sys.executable, str(RAIZ / "tools" / "build_appimage.py"), "--pyside-range"],
        capture_output=True, text=True, check=True)
    return hecho.stdout.strip()


def en_contenedor(imagen: str) -> int:
    motor = motor_de_contenedores()
    suelo = suelo_declarado()
    print(f"· la suite en Python {suelo}, dentro de {imagen} con {motor}")
    orden = [
        motor, "run", "--rm",
        "-v", f"{RAIZ}:/fuente:ro,z",
        "-e", f"SUELO={suelo}",
        "-e", f"PYSIDE={rango_de_pyside()}",
        imagen, "sh", "-c", RECETA,
    ]
    return subprocess.run(orden, check=False).returncode


def aqui_mismo() -> int:
    """Con un intérprete del mínimo de esta máquina, si lo hay.

    Sirve para el que tenga pyenv y no quiera esperar al contenedor, pero no
    reproduce el resto: ni la distribución, ni las bibliotecas de Qt, ni el
    hecho de que allí se corre como root. Lo que vale para decir «esto pasa en
    el mínimo» es `--container`.
    """
    suelo = suelo_declarado()
    interprete = shutil.which(f"python{suelo}")
    if interprete is None:
        raise SystemExit(
            f"No hay ningún python{suelo} en esta máquina.\n"
            "  python3 tools/probar_en_minimo.py --container")
    print(f"· la suite con {interprete} (sin contenedor: solo el intérprete)")
    return subprocess.run(
        [interprete, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=RAIZ, env={**__import__("os").environ,
                       "QT_QPA_PLATFORM": "offscreen"},
        check=False).returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--container", metavar="IMAGEN", nargs="?",
                        const=IMAGEN_BASE,
                        help="dentro de esa imagen; por omisión "
                             f"{IMAGEN_BASE}. Es la forma que reproduce el CI")
    args = parser.parse_args(argv)

    codigo = en_contenedor(args.container) if args.container else aqui_mismo()
    if codigo == 0:
        print(f"\nLa suite pasa en Python {suelo_declarado()}.")
    elif codigo == SUELO_QUE_NO_CUADRA:
        # No es que fallen los tests: es que no llegaron a ejecutarse en la
        # versión que interesa. Decir «no pasa» aquí mandaría a buscar un fallo
        # que no existe.
        print("\nNo se ha probado nada: la imagen no trae el Python del suelo.",
              file=sys.stderr)
    else:
        print(f"\nLa suite NO pasa en Python {suelo_declarado()}, "
              "que es el suelo que declara el proyecto.", file=sys.stderr)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
