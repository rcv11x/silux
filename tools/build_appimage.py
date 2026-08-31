#!/usr/bin/env python3
"""Empaqueta silux como AppImage: un fichero que se ejecuta sin instalar nada.

    python3 tools/build_appimage.py                 # construye dist/silux-x86_64.AppImage
    python3 tools/build_appimage.py --appdir-only   # solo el árbol, para depurar
    python3 tools/build_appimage.py --keep          # no borra el AppDir al terminar

La gracia de un AppImage es que quien lo prueba no tiene que instalar Python ni
Qt ni saber qué es PySide6: descarga, `chmod +x` y abre. El precio es meter
dentro todo lo que hace falta, y ahí está el trabajo: PySide6 completo son 51 MB
de bindings y Qt arrastra otros 100 en bibliotecas. Casi nada de eso se usa.

Lo que se hace para que quepa:

- **De PySide6, tres módulos.** silux solo usa QtCore, QtGui y QtWidgets. Los
  otros treinta (Quick, 3D, Charts, Multimedia, WebEngine) se quedan fuera.
- **Las bibliotecas se resuelven con `ldd`**, no a mano, y se copian solo las
  que hagan falta de verdad. Las que trae cualquier Linux (glibc, X11, los
  drivers gráficos) se dejan al sistema: meterlas dentro es lo que rompe un
  AppImage al abrirlo en otra distribución.
- **De la stdlib de Python se quita lo que no se usa**: los tests del propio
  Python, tkinter, idlelib y compañía suman bastante y no pintan nada aquí.
- **`strip` a todo binario** y compresión zstd del resultado.

Lo que más pesa y no se puede quitar es ICU, la tabla de internacionalización
de la que depende Qt: 38 MB en disco. Comprime a una fracción porque son datos
tabulares, así que se queda.
"""

from __future__ import annotations

import bisect
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import sysconfig
import urllib.request
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Una distribución vieja y genérica. Lo que se compila contra una glibc antigua
# funciona en las nuevas, pero no al revés; y sus paquetes van para x86-64
# básico, no para las extensiones que solo tienen los procesadores recientes.
IMAGEN_BASE = "docker.io/library/ubuntu:22.04"

# Se la pone `construir_en_contenedor` a la construcción de dentro, que si no
# no tiene forma de saber dónde está. Sin ella el aviso final recomendaba
# construir en un contenedor a quien acababa de hacerlo.
EN_CONTENEDOR = "SILUX_EN_CONTENEDOR"
DIST = ROOT / "dist"
APPDIR = DIST / "silux.AppDir"
APP_ID = "silux"

# Lo único que silux importa de Qt. Todo lo demás sobra.
QT_MODULES = ("QtCore", "QtGui", "QtWidgets")

# Plugins de Qt sin los que la ventana no abre o se ve mal.
QT_PLUGINS = (
    "platforms",         # wayland y xcb: sin esto no hay ventana
    "imageformats",      # el icono es un SVG
    "iconengines",
    "wayland-shell-integration",
    "wayland-decoration-client",
    "wayland-graphics-integration-client",
)

# `platformthemes` se queda fuera a propósito: arrastra GTK entero y los iconos
# de Breeze, unos 40 MB, para integrar el programa con el tema del escritorio.
# silux fija el estilo Fusion en `ui/theme.py` y se pinta él mismo, así que no
# lo usaría de todas formas.

# De `imageformats` solo estos. Los demás tiran de los códecs de vídeo del
# sistema (x265, aom, SVT-AV1) que suman otros 35 MB por poder abrir un HEIF o
# un AVIF que aquí no se abre nunca.
IMAGEFORMATS = ("qsvg", "qico", "qjpeg", "qgif")

# Bibliotecas que trae cualquier Linux de escritorio. Empaquetarlas es la causa
# más común de que un AppImage funcione en la máquina donde se hizo y en
# ninguna otra: la copia de dentro choca con los drivers de fuera.
# Bibliotecas que se dejan al anfitrión. Se comparan por principio de nombre,
# no por subcadena: escrito como "libxcb" a secas, el filtro también descartaba
# libxcb-cursor, libxcb-icccm y las otras nueve auxiliares que necesita el
# plugin xcb de Qt. No son parte del protocolo con el servidor X, son utilidades
# que muchas distribuciones no instalan de serie, y sin ellas el programa no
# levanta ventana: «xcb-cursor0 or libxcb-cursor0 is needed».
DEL_SISTEMA = (
    # El tiempo de ejecución de C y C++, que tiene que ser el del sistema.
    "libc.so", "libm.so", "libpthread.so", "libdl.so", "librt.so",
    "ld-linux", "libgcc_s.so", "libstdc++.so",
    # Aceleración gráfica: esto es el driver de la tarjeta que haya puesta.
    "libGL.so", "libGLX.so", "libGLdispatch.so", "libEGL.so", "libOpenGL.so",
    "libdrm.so", "libgbm.so",
    # Quien habla con el servidor gráfico y con el bus del escritorio. Estas
    # sí van por protocolo y deben ser las de la máquina.
    "libX11.so", "libX11-xcb.so", "libxcb.so", "libdbus-1.so",
    "libwayland-client.so", "libwayland-cursor.so", "libwayland-egl.so",
    "libwayland-server.so",
    # Con estado en /run y /sys.
    "libudev.so", "libselinux.so",
)

# De la biblioteca estándar de Python: lo que no se usa y ocupa.
STDLIB_FUERA = (
    # `site-packages` es lo primero de la lista y por un buen motivo: vive
    # dentro de la biblioteca estándar y contiene todo lo que el usuario haya
    # instalado con pip. Copiarla entera metía 300 MB de paquetes ajenos (el
    # PySide6 completo entre ellos, justo el que se está podando) en un
    # AppImage que solo necesita la stdlib.
    "site-packages", "dist-packages",
    "test", "tests", "idlelib", "tkinter", "turtledemo", "lib2to3",
    "ensurepip", "pydoc_data", "distutils", "unittest/test",
    "config-*", "__pycache__", "*.pyc",
)

# Módulos de extensión de la biblioteca estándar que este programa no usa y
# que arrastran media distribución detrás: `nis` se lleva Kerberos entero,
# `_curses` la terminfo, `_tkinter` medio Tcl. Se quitan para no copiar sus
# dependencias, no por lo que ocupan ellos.
DYNLOAD_FUERA = (
    "nis", "ossaudiodev", "audioop", "spwd", "_dbm", "_gdbm", "_tkinter",
    "_curses", "_curses_panel", "readline", "_sqlite3", "_ssl", "_crypt",
    "_test", "_xx", "xx",
)

# Qué PySide6 se empaqueta. Sin `--compat` la última, que es la que trae los
# arreglos de Qt —los de Wayland, sobre todo, que es donde más se mueve—. Con
# `--compat`, la última serie que sigue compilándose para x86-64 a secas.
RANGO_PYSIDE = {False: "PySide6>=6.6", True: "PySide6>=6.6,<6.10"}

# Lo pone `main` al arrancar. Lo miran el nombre del archivo y la guarda.
COMPAT = False

# Lo que sigue lo escribe `tools/build_appimage.py` cuando el Qt empaquetado
# pide más de lo que garantiza un x86-64. `%%JUEGOS%%` son los nombres tal y
# como los publica `/proc/cpuinfo`.
GUARDA = """
# --- procesador ------------------------------------------------------------
# Sin esto, un procesador al que le falte alguna de estas instrucciones se
# lleva un «Instrucción ilegal» y un volcado en cuanto Qt toca una cadena, sin
# nada que explique por qué. Qt trae un aviso para el caso y no da tiempo a
# que salga: revienta antes de imprimirlo.
FALTAN=""
if [ -r /proc/cpuinfo ]; then
    for BANDERA in %%JUEGOS%%; do
        grep -qw "$BANDERA" /proc/cpuinfo || FALTAN="$FALTAN $BANDERA"
    done
fi
if [ -n "$FALTAN" ]; then
    case "${LANG:-}" in
      es*) cat >&2 <<FIN
A este procesador le faltan instrucciones que necesita la versión normal:$FALTAN

Es lo que pide Qt 6.10 en adelante, y deja fuera a los Intel anteriores a 2008
y a los AMD anteriores a 2011. No es un fallo del equipo.

Hay una versión para estos procesadores, con el mismo programa dentro:

    %%NOMBRE%%-compat.AppImage

Mientras tanto, esto sí funciona y saca todo el hardware por la terminal:

    $0 --report informe.md
FIN
      ;;
      *) cat >&2 <<FIN
This processor is missing instructions the normal build needs:$FALTAN

Qt 6.10 and later require them, which leaves out Intel chips older than 2008
and AMD chips older than 2011. Nothing is wrong with your machine.

There is a build for these processors, with the same program inside:

    %%NOMBRE%%-compat.AppImage

In the meantime this works, and dumps all the hardware to the terminal:

    $0 --report report.md
FIN
      ;;
    esac
    exit 1
fi
# --- fin procesador --------------------------------------------------------
"""

APPRUN = """#!/bin/sh
# Punto de entrada del AppImage.
AQUI="$(dirname "$(readlink -f "$0")")"
export PYTHONHOME="$AQUI/usr"
export PYTHONPATH="$AQUI/usr/lib/python:$PYTHONPATH"
# El segundo directorio es para cuando PySide6 trae su propio Qt: el de PyPI
# lo guarda junto a sus módulos y no en el sitio de siempre.
export LD_LIBRARY_PATH="$AQUI/usr/lib:$AQUI/usr/lib/python/PySide6/Qt/lib:$LD_LIBRARY_PATH"
# Que Qt encuentre sus plugins dentro y no los del sistema, que pueden ser de
# otra versión y no cargar.
export QT_PLUGIN_PATH="$AQUI/usr/lib/qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$AQUI/usr/lib/qt/plugins/platforms"
# Con qué se arranca. La interfaz es lo normal, pero el volcado en terminal
# tiene que estar a mano: «--report» es lo primero que se le pide a quien dice
# que algo no le sale, y quien usa el AppImage no tiene otra forma de sacarlo.
# `-m` mete el directorio desde el que se llama al principio de sys.path, así
# que un `silux/` en la carpeta actual gana al que va dentro del paquete: el
# AppImage ejecutaba código ajeno sin decir nada. Se ve lanzándolo desde una
# copia del repositorio, donde enseñaba la versión del árbol de trabajo en vez
# de la suya. Python 3.11 trae PYTHONSAFEPATH para esto, pero aquí dentro va
# el 3.10 de Ubuntu 22.04, así que se quita a mano antes de importar nada.
ARRANQUE='import sys, runpy
sys.path.pop(0)
runpy.run_module(sys.argv.pop(1), run_name="__main__", alter_sys=True)'

case "${1:-}" in
    --cli) shift; exec "$AQUI/usr/bin/python3" -c "$ARRANQUE" silux.cli "$@" ;;
    --report|--json|--sensors|--watch|--db-info|--no-color|--with-identifiers|--version)
        exec "$AQUI/usr/bin/python3" -c "$ARRANQUE" silux.cli "$@" ;;
esac
exec "$AQUI/usr/bin/python3" -c "$ARRANQUE" silux.ui.app "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=silux
GenericName=Perfilador de hardware
Comment=Identificación del equipo y monitorización de sensores
Exec=silux
Icon=silux
Categories=System;Monitor;
Terminal=false
StartupWMClass=silux
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--appdir-only", action="store_true",
                        help="construye el árbol pero no lo empaqueta")
    parser.add_argument("--keep", action="store_true",
                        help="conserva el AppDir después de empaquetar")
    parser.add_argument("--compat", action="store_true",
                        help="empaqueta la última serie de Qt que se compila "
                             "para x86-64 a secas, para procesadores "
                             "anteriores a 2008 (Intel) o 2011 (AMD)")
    parser.add_argument("--container", metavar="IMAGEN", nargs="?",
                        const=IMAGEN_BASE,
                        help="construye dentro de un contenedor con una "
                             "distribución antigua, para que el resultado "
                             "funcione en procesadores y sistemas viejos")
    parser.add_argument("--pyside-range", action="store_true",
                        help="imprime qué PySide6 hace falta para lo que se "
                             "va a construir, y no hace nada más")
    args = parser.parse_args()

    # Quien construye sin `--container` se trae el PySide6 que tenga puesto,
    # así que el techo hay que ponerlo antes de instalarlo y fuera de aquí. La
    # acción de GitHub lo pregunta por esto en vez de repetir el rango: escrito
    # a mano en los dos sitios es como se le quedó un «>=6.6» sin techo, y con
    # él llegó un Qt que no arranca en los procesadores del paquete compat.
    if args.pyside_range:
        print(RANGO_PYSIDE[args.compat])
        return 0

    global COMPAT
    COMPAT = args.compat

    if args.container:
        return construir_en_contenedor(args.container, args.compat)

    if APPDIR.exists():
        shutil.rmtree(APPDIR)
    (APPDIR / "usr" / "bin").mkdir(parents=True)
    (APPDIR / "usr" / "lib").mkdir(parents=True)

    print("· intérprete de Python")
    bibliotecas = copiar_python()
    print("· silux")
    copiar_silux()
    print("· PySide6, solo", ", ".join(QT_MODULES))
    bibliotecas |= copiar_pyside()
    print("· plugins de Qt")
    bibliotecas |= copiar_plugins()
    print("· bibliotecas compartidas")
    copiar_bibliotecas(bibliotecas)
    print("· strip")
    quitar_simbolos()
    print("· comprobación")
    comprobar_autocontenido()
    # Antes de escribir el AppRun: lo que salga de aquí decide si lleva guarda
    # y qué banderas busca. Después del strip porque `.dynsym`, que es lo que
    # mira, no se toca, y así se mide lo que se reparte de verdad.
    banderas = comprobar_juego_de_instrucciones()
    print("· metadatos")
    escribir_metadatos(banderas)
    sellar_build()

    total = sum(f.stat().st_size for f in APPDIR.rglob("*") if f.is_file())
    print(f"\nAppDir listo: {total / 1024**2:.0f} MB sin comprimir")
    avisar_de_compatibilidad()

    if args.appdir_only:
        print(f"En {APPDIR}")
        return 0

    destino = empaquetar()
    if destino is None:
        return 1
    print(f"\n{destino}  ({destino.stat().st_size / 1024**2:.0f} MB)")
    if not args.keep:
        shutil.rmtree(APPDIR)
    return 0


RECETA = """set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Las libxcb-* auxiliares hacen falta *instaladas* aunque luego se empaqueten:
# `ldd` solo informa de lo que puede resolver, así que una biblioteca que no
# esté en la imagen no aparece como dependencia y se queda fuera sin ruido.
apt-get install -y -qq --no-install-recommends \
    python3 python3-pip python3-venv file binutils desktop-file-utils \
    libgl1 libegl1 libdbus-1-3 libfontconfig1 \
    libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
    libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-sync1 libxcb-util1 libxcb-xfixes0 \
    libxcb-xinerama0 libxcb-xinput0 libxcb-xkb1 libsm6 libice6 \
    libwayland-client0 libwayland-cursor0 libwayland-egl1 >/dev/null
# El PySide6 de PyPI viene compilado para manylinux: glibc antigua y x86-64
# básico. El de la distribución iría atado a la versión de Qt del sistema.
#
# La versión la elige quien llama: `--compat` pone el techo, y sin él se coge
# la última. Ver `RANGO_PYSIDE`.
#
# El techo no es capricho. Qt 6.10 pasó a compilarse con `-march=x86-64-v2`, y
# no en rutas aparte que se eligen mirando la CPU, sino en funciones normales:
# `QString`, `QUtf8::convertToUnicode`, `QPainterPath::quadTo`. En un
# procesador sin SSE4.1 el programa se cae con «Instrucción ilegal» antes de
# pintar nada, y ni siquiera llega a salir el aviso que Qt trae para eso.
# x86-64-v2 es Nehalem (2008) en Intel y Bulldozer (2011) en AMD: deja fuera
# los Core 2, los Athlon II y los Phenom II, que es justo la clase de equipo
# cuyo dueño quiere saber qué lleva dentro. 6.9 es la última serie que se
# compila para x86-64 a secas.
pip3 install --quiet --break-system-packages "$PYSIDE" 2>/dev/null || \
    pip3 install --quiet "$PYSIDE"
cd /fuente
python3 tools/build_appimage.py "$@"
"""


def _marca_de_construccion() -> str:
    """La marca de git, leída aquí fuera para pasársela al contenedor."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from silux import _preguntar_a_git

    return _preguntar_a_git()


def construir_en_contenedor(imagen: str, compat: bool = False) -> int:
    """Repite la construcción dentro de una distribución antigua.

    Un AppImage se lleva dentro los binarios de donde se construyó. Hecho en
    una distribución moderna, exige una glibc reciente y las extensiones de
    procesador que ella use, y deja fuera a quien no las tenga. Hecho en una
    antigua, funciona en las dos.
    """
    motor = next((m for m in ("podman", "docker") if shutil.which(m)), None)
    if motor is None:
        print("Hace falta podman o docker para construir en contenedor.\n"
              "  sudo pacman -S podman        (Arch, CachyOS)\n"
              "  sudo dnf install podman      (Fedora)\n"
              "  sudo apt install podman      (Debian, Ubuntu)", file=sys.stderr)
        return 1

    # `flush` porque justo detrás va un proceso que escribe directo: sin él,
    # esta línea se queda en el búfer y sale la última en cuanto la salida
    # se canaliza a un archivo, que es cuando se quiere el registro.
    print(f"· construyendo dentro de {imagen} con {motor}", flush=True)
    DIST.mkdir(parents=True, exist_ok=True)
    # El `pip` de dentro no ve los argumentos de aquí, así que la versión va
    # por entorno; la opción se repite para que el build de dentro sepa cómo
    # llamar al archivo y qué guarda escribir.
    dentro = ["--compat"] if compat else []
    orden = [
        motor, "run", "--rm",
        "-v", f"{ROOT}:/fuente:z",
        "-w", "/fuente",
        "-e", f"PYSIDE={RANGO_PYSIDE[compat]}",
        "-e", f"SILUX_BUILD={_marca_de_construccion()}",
        "-e", f"{EN_CONTENEDOR}=1",
        # Sin esto la salida sale desordenada y no se puede leer: dentro del
        # contenedor la stdout de Python no es un terminal, así que va por
        # bloques y se vuelca entera al final, mientras appimagetool y pip
        # escriben directos. Los pasos aparecían después de empaquetar, que
        # ocurre al revés. Hoy solo confunde; el día que falle un paso, el
        # registro no dirá en cuál.
        "-e", "PYTHONUNBUFFERED=1",
        imagen, "bash", "-c", RECETA, "--", *dentro,
    ]
    resultado = subprocess.run(orden, check=False)
    if resultado.returncode != 0:
        print("La construcción en contenedor falló.", file=sys.stderr)
    return resultado.returncode


def avisar_de_compatibilidad() -> None:
    """Dice en qué máquinas NO va a funcionar lo que se acaba de construir.

    Un AppImage se lleva dentro los binarios de la distribución donde se
    construyó, con sus exigencias. Dos de ellas dejan fuera a mucha gente y no
    se ven hasta que alguien lo ejecuta:

    * **El nivel de ISA.** Algunas distribuciones compilan para `x86-64-v3`,
      que pide AVX2 y compañía: procesadores de 2013 en adelante. En una CPU
      anterior el enlazador se niega a arrancar con un escueto «CPU ISA level
      is lower than required», que no dice de quién es la culpa. CachyOS lo
      hace por omisión, y es justo donde se está desarrollando esto.
    * **La versión de glibc.** Un binario compilado contra una glibc nueva no
      arranca en un sistema con una más vieja, aunque al revés sí funcione.

    Las dos se arreglan igual: construyendo dentro de un contenedor con una
    distribución antigua y genérica. Mientras tanto, al menos que quien
    construye sepa a quién está dejando fuera.
    """
    nivel = _nivel_isa()
    glibc = _glibc_minima()
    if not (nivel or glibc):
        return

    dentro = bool(os.environ.get(EN_CONTENEDOR))
    print("\nCompatibilidad de lo construido:")

    # Cuántos de los avisos son cosas que quien construye puede arreglar. La
    # línea del final se contaba sola —decía «las dos cosas» hubiera salido una
    # o dos— y encima recomendaba lo que se acababa de hacer.
    pendientes = 0

    if nivel and nivel != "x86-64-baseline":
        pendientes += 1
        print(f"  ⚠ Exige {nivel}: no arrancará en procesadores anteriores a "
              f"{'2013 (Haswell / Zen)' if nivel.endswith('v3') else '2009'}.")
        print("    El error que verán es «CPU ISA level is lower than required».")

    if glibc and dentro:
        # Construido en la imagen base, ese suelo es el que se buscaba y no un
        # problema. Marcarlo con un aviso hace dudar de un paquete que está
        # bien, que es justo lo contrario de para lo que existe este bloque.
        print(f"  · Exige glibc {glibc}, la de la imagen base: es el suelo que")
        print("    se buscaba construyendo aquí dentro. Para bajarlo hace falta")
        print("    una base más antigua, no una opción.")
    elif glibc:
        pendientes += 1
        print(f"  ⚠ Exige glibc {glibc} o superior.")

    if not pendientes:
        return
    if dentro:
        # Que quede algo pendiente construyendo ya en la imagen antigua es la
        # sorpresa que hay que contar: no lo arregla el contenedor.
        print("  Y eso construyendo ya dentro del contenedor, así que no lo")
        print("  arregla la imagen: lo pide algo de lo que se está empaquetando.")
    else:
        arreglo = "Se resuelve" if pendientes == 1 else "Las dos se resuelven"
        print(f"  {arreglo} construyendo en un contenedor con una distribución")
        print("  antigua; ver la sección «Compatibilidad» del README.")


def _nivel_isa() -> Optional[str]:
    """El nivel de instrucciones más alto que exige el intérprete empaquetado."""
    binario = APPDIR / "usr" / "bin" / "python3"
    if not binario.exists() or not shutil.which("readelf"):
        return None
    try:
        salida = subprocess.run(["readelf", "-n", str(binario)],
                                capture_output=True, text=True, check=False).stdout
    except OSError:
        return None
    for linea in salida.splitlines():
        if "ISA needed" in linea:
            niveles = [t.strip() for t in linea.split(":", 1)[1].split(",")]
            return niveles[-1] if niveles else None
    return None


def objetos_del_appdir() -> list[pathlib.Path]:
    """Todo lo que dentro del AppDir puede pedirle algo al sistema.

    Es una sola lista y la comparten las dos comprobaciones a propósito. Cuando
    cada una recorría lo suyo, la del juego de instrucciones miraba el AppDir
    entero y la de glibc solo `usr/lib/*.so*`, y las sesenta primeras: el
    intérprete cuelga de `usr/bin` y los módulos de extensión de la biblioteca
    estándar viven en `lib-dynload`, así que la de glibc no veía ni a
    `python3`, que es justo quien pide el símbolo más alto.

    El criterio de qué es un binario es el mismo que ya usaba la de
    instrucciones: o lleva `.so` en el nombre, o tiene el bit de ejecución.
    """
    objetos = []
    for objeto in sorted(APPDIR.resolve().rglob("*")):
        if not objeto.is_file() or objeto.is_symlink():
            continue
        if ".so" not in objeto.name and not objeto.stat().st_mode & 0o111:
            continue
        objetos.append(objeto)
    return objetos


def _glibc_minima() -> Optional[str]:
    """La versión de glibc más alta que pide cualquier objeto del AppDir.

    Sin tope de cuántos se miran y sin quedarse en un directorio. Equivocarse
    aquí solo puede salir en una dirección —decir que hace falta menos glibc de
    la que hace falta—, y esa es la que manda a alguien a descargar un paquete
    que no le va a arrancar. Estuvo diciendo 2.34 cuando eran 2.35, que es la
    diferencia entre que RHEL 9 valga o no valga.
    """
    if not shutil.which("objdump"):
        return None
    mayor = (0, 0)
    for binario in objetos_del_appdir():
        try:
            salida = subprocess.run(["objdump", "-T", str(binario)],
                                    capture_output=True, text=True, check=False).stdout
        except OSError:
            continue
        for pieza in re.findall(r"GLIBC_(\d+)\.(\d+)", salida):
            version = (int(pieza[0]), int(pieza[1]))
            mayor = max(mayor, version)
    return f"{mayor[0]}.{mayor[1]}" if mayor > (0, 0) else None


# -- piezas ------------------------------------------------------------------

def copiar_python() -> set[str]:
    """El intérprete y su biblioteca estándar, sin lo que no se usa.

    Se empaqueta Python entero y no se usa el del sistema porque los bindings
    de PySide6 se compilan contra una versión concreta: los de aquí no cargarían
    en una máquina con otra.
    """
    destino_bin = APPDIR / "usr" / "bin" / "python3"
    shutil.copy2(sys.executable, destino_bin)
    destino_bin.chmod(0o755)

    origen = pathlib.Path(sysconfig.get_paths()["stdlib"])
    destino = APPDIR / "usr" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"

    def ignorar(directorio, nombres):
        return {n for n in nombres
                if any(pathlib.PurePath(n).match(patron) for patron in STDLIB_FUERA)}

    shutil.copytree(origen, destino, ignore=ignorar, symlinks=True,
                    ignore_dangling_symlinks=True)

    # Los módulos de extensión de la biblioteca estándar tienen sus propias
    # dependencias, y hasta ahora solo se miraban las del ejecutable. Por eso
    # `_hashlib` se quedaba sin `libcrypto` y `_lzma` sin `liblzma`: dos de las
    # cinco cargas del benchmark reventaban en cualquier máquina que no las
    # trajera puestas, y en las distribuciones con OpenSSL 1.1 eso es siempre.
    # Desde la escala v4 la compresión pesada usa `_bz2`, así que `libbz2` está
    # en la misma situación: sale sola por aquí mientras nadie meta `_bz2` en
    # `DYNLOAD_FUERA`, y si alguien lo mete, la carga revienta fuera de casa.
    dynload = destino / "lib-dynload"
    bibliotecas = set(dependencias(destino_bin))
    for modulo in sorted(dynload.glob("*.so")) if dynload.is_dir() else ():
        if modulo.name.startswith(DYNLOAD_FUERA):
            modulo.unlink()
            continue
        bibliotecas |= set(dependencias(modulo))
    return bibliotecas


def copiar_silux() -> None:
    destino = APPDIR / "usr" / "lib" / "python" / "silux"
    shutil.copytree(ROOT / "silux", destino,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def qt_propio() -> list[pathlib.Path]:
    """Dónde busca `ldd` las bibliotecas de Qt además de las del sistema.

    El PySide6 de PyPI trae su propio Qt dentro del paquete; el de una
    distribución usa el del sistema. Sin mirar en los dos sitios, los módulos
    y los plugins aparecen como si no dependieran de nada y el AppImage sale
    sin Qt: arranca con `offscreen`, que apenas necesita nada, y revienta en
    cuanto hay una pantalla de verdad delante.
    """
    import PySide6
    origen = pathlib.Path(PySide6.__file__).parent
    return [origen / "Qt" / "lib", origen]


def copiar_pyside() -> set[str]:
    """Solo los módulos que se usan, y sus bibliotecas."""
    import PySide6
    import shiboken6

    origen = pathlib.Path(PySide6.__file__).parent
    destino = APPDIR / "usr" / "lib" / "python" / "PySide6"
    destino.mkdir(parents=True)


    bibliotecas: set[str] = set()
    (destino / "__init__.py").write_bytes((origen / "__init__.py").read_bytes())
    for modulo in QT_MODULES:
        for fichero in origen.glob(f"{modulo}.*.so"):
            copia = destino / fichero.name
            shutil.copy2(fichero, copia)
            bibliotecas |= set(dependencias(copia, extra=qt_propio()))
        for pyi in origen.glob(f"{modulo}.pyi"):
            pass                          # las anotaciones no hacen falta en tiempo de ejecución

    # shiboken es el puente entre Python y C++; sin él no carga ningún módulo.
    origen_shiboken = pathlib.Path(shiboken6.__file__).parent
    destino_shiboken = APPDIR / "usr" / "lib" / "python" / "shiboken6"
    shutil.copytree(origen_shiboken, destino_shiboken,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyi", "docs"))
    for so in destino_shiboken.rglob("*.so*"):
        bibliotecas |= set(dependencias(so, extra=qt_propio() + [origen_shiboken]))
    return bibliotecas


def copiar_plugins() -> set[str]:
    raiz = plugins_de_qt()
    if raiz is None:
        print("  aviso: no se encontraron los plugins de Qt", file=sys.stderr)
        return set()

    destino_raiz = APPDIR / "usr" / "lib" / "qt" / "plugins"
    bibliotecas: set[str] = set()
    for nombre in QT_PLUGINS:
        origen = raiz / nombre
        if not origen.is_dir():
            continue
        destino = destino_raiz / nombre
        if nombre == "imageformats":
            destino.mkdir(parents=True)
            for base in IMAGEFORMATS:
                for so in origen.glob(f"{base}.so"):
                    shutil.copy2(so, destino / so.name)
        else:
            shutil.copytree(origen, destino)
        for so in destino.rglob("*.so"):
            bibliotecas |= set(dependencias(so, extra=qt_propio()))
    return bibliotecas


def copiar_bibliotecas(rutas: set[str]) -> None:
    """Resuelve el cierre de dependencias y copia lo que no trae el sistema."""
    destino = APPDIR / "usr" / "lib"
    pendientes = [r for r in rutas if r]
    vistas: set[str] = set()

    # Los directorios de donde salieron las primeras, para que las siguientes
    # se resuelvan igual: las de Qt dependen unas de otras y viven juntas.
    origenes = {pathlib.Path(r).parent for r in pendientes if r}

    while pendientes:
        ruta = pendientes.pop()
        if ruta in vistas:
            continue
        vistas.add(ruta)
        nombre = os.path.basename(ruta)
        if nombre.startswith(DEL_SISTEMA):
            continue
        copia = destino / nombre
        if not copia.exists():
            try:
                shutil.copy2(ruta, copia, follow_symlinks=True)
            except OSError:
                continue
        pendientes.extend(dependencias(copia, extra=sorted(origenes)))


# Instrucciones que un x86-64 de 2003 no tiene. Están todas por encima de
# SSE2, que es lo único que la arquitectura garantiza; el nivel «x86-64-v2»
# las agrupa y equivale a un Intel de 2008 o un AMD de 2011.
# Cada juego con el nombre que le da `/proc/cpuinfo`, que es donde lo va a
# buscar la guarda del AppRun. El orden importa: se prueba de arriba abajo y
# gana el primero que casa, así que lo específico va antes que lo general.
#
# Solo están las de x86-64-v2, que es el escalón que decide si un equipo de
# antes de 2008 arranca o no. AVX y BMI se probaron y hubo que quitarlas: un
# compilador no las mete sin que se las pidan, así que donde aparecen es casi
# siempre detrás de una pregunta a la CPU hecha dentro de la propia función
# —Qt lo hace así en `QUtf8::convertToUnicode`, zstd en sus bloques—, y eso no
# se ve leyendo el desensamblado. Con ellas dentro, la comprobación marcaba
# igual el paquete bueno y el malo, que es no comprobar nada.
JUEGOS = (
    ("sse4_2", re.compile(r"\b(crc32|pcmpistr\w|pcmpestr\w)\b")),
    ("popcnt", re.compile(r"\bpopcnt\b")),
    ("sse4_1", re.compile(r"\b(pblendw|blendvp[sd]|roundp?[sd]|pmovzx\w+|"
                          r"pmovsx\w+|ptest|pminu[dw]|pmaxu[dw]|pmulld|"
                          r"packusdw|insertps|extractps|mpsadbw|phminposuw)\b")),
    ("ssse3", re.compile(r"\b(pshufb|palignr|phadd\w*|phsub\w*|pmaddubsw|"
                         r"pmulhrsw|psign[bwd]|pabs[bwd])\b")),
    ("pni", re.compile(r"\b(addsubp[sd]|haddp[sd]|hsubp[sd]|lddqu|movddup|"
                       r"movshdup|movsldup)\b")),
)

# Bibliotecas que eligen su camino dentro de la propia función, preguntando a
# la CPU en tiempo de ejecución. Se sabe porque son las de siempre —compresión
# y criptografía, donde media docena de instrucciones deciden el rendimiento— y
# porque llevan décadas corriendo en cualquier procesador. Su `deflate` usa
# CRC32 si lo hay y una tabla si no. Se anotan aparte en vez de esconderlas.
DESPACHO_INTERNO = frozenset({
    "libz.so.1", "libzstd.so.1", "liblz4.so.1", "liblzma.so.5",
    "libcrypto.so.3", "libssl.so.3", "libgcrypt.so.20", "libpng16.so.16",
    "libicuuc.so.73", "libicui18n.so.73", "libicudata.so.73", "libbsd.so.0",
    "libk5crypto.so.3",
})

SOBRE_LA_BASE = re.compile(
    "|".join(patron.pattern for _juego, patron in JUEGOS))

# Cómo se llama una función que el propio código elige después de preguntarle
# a la CPU qué sabe hacer. Esas pueden llevar lo que quieran: no se ejecutan
# si no toca. El resto no tiene escapatoria.
CON_DESPACHO = re.compile(r"(sse\d|ssse3|avx\d*|fma|bmi\d?|neon|sve|_v[234]$"
                          r"|dispatch|resolver)", re.IGNORECASE)


def comprobar_juego_de_instrucciones() -> set[str]:
    """Avisa si algo del AppDir exige más de lo que garantiza un x86-64.

    Esto se aprendió por el camino largo: alguien con un Athlon II X2 de 2009
    ejecutó el AppImage y le salió «Instrucción ilegal» y un volcado. La causa
    era Qt 6.10, que pasó a compilarse con `-march=x86-64-v2` sin que aquí lo
    notara nadie, porque el `pip install` no tenía techo de versión y las dos
    máquinas donde se probaba son modernas.

    Lo que hace falta comprobar no es si la instrucción aparece —libcrypto y
    zlib llevan AVX-512 y funcionan en cualquier sitio—, sino si aparece en
    una función a la que se llega siempre. Las rutas que el código elige
    mirando antes qué CPU hay se reconocen por el nombre, que lleva dentro el
    juego que usan: `qt_convert_rgb888_to_rgb32_ssse3` no se ejecuta en un
    procesador sin SSSE3. Los símbolos siguen ahí después del `strip` porque
    `.dynsym` no se toca.
    """
    faltan = [t for t in ("objdump", "readelf") if shutil.which(t) is None]
    if faltan:
        # Decir «arranca en cualquier sitio» sin haber podido mirar es peor
        # que no decir nada: es justo la frase que hace que nadie lo revise.
        print(f"  sin {' ni '.join(faltan)}: no se pudo comprobar qué "
              "procesador exige el paquete", file=sys.stderr)
        return set()

    sospechosos: dict[str, list[str]] = {}
    conocidas: set[str] = set()
    banderas: set[str] = set()
    for objeto in objetos_del_appdir():
        malos, juegos = _simbolos_sin_escapatoria(objeto)
        if not malos:
            continue
        if objeto.name in DESPACHO_INTERNO:
            conocidas.add(objeto.name)
            continue
        sospechosos[objeto.name] = malos
        banderas |= juegos

    if not sospechosos:
        print("  x86-64 sin extras: arranca en cualquier procesador de 64 bits")
        if conocidas:
            print(f"    ({len(conocidas)} bibliotecas eligen su camino "
                  "mirando la CPU: " + ", ".join(sorted(conocidas)[:4]) + "…)")
        return set()

    print(f"  exige {' '.join(sorted(banderas))}: no arranca en un procesador "
          "anterior a 2008 (Intel) o 2011 (AMD)")
    for nombre, malos in sorted(sospechosos.items(),
                                key=lambda x: (-len(x[1]), x[0]))[:6]:
        print(f"    {nombre}  ({len(malos)} símbolos, p. ej. {malos[0][:56]})")
    if not COMPAT:
        print("    → la guarda del AppRun lo dirá con palabras; el paquete "
              "para esos equipos sale con --compat")
    return banderas


def _simbolos_sin_escapatoria(
        objeto: pathlib.Path) -> tuple[list[str], set[str]]:
    """Los símbolos exportados que usan instrucciones de más sin comprobar.

    Devuelve además qué juegos hacen falta, con el nombre que les da
    `/proc/cpuinfo`: es lo que la guarda del AppRun va a buscar allí.
    """
    try:
        tabla = subprocess.run(["readelf", "-sW", "--dyn-syms", str(objeto)],
                               capture_output=True, text=True,
                               timeout=300).stdout
        codigo = subprocess.run(["objdump", "-d", "--no-show-raw-insn",
                                 str(objeto)], capture_output=True, text=True,
                                timeout=600).stdout
    except (OSError, subprocess.SubprocessError):
        return [], set()

    funciones = []
    for linea in tabla.splitlines():
        campos = linea.split()
        if len(campos) >= 8 and campos[3] == "FUNC":
            try:
                funciones.append((int(campos[1], 16), int(campos[2]), campos[7]))
            except ValueError:
                pass
    if not funciones:
        return [], set()
    funciones.sort()
    inicios = [f[0] for f in funciones]

    encontrados: set[str] = set()
    juegos: set[str] = set()
    for linea in codigo.splitlines():
        if not SOBRE_LA_BASE.search(linea):
            continue
        try:
            direccion = int(linea.split(":", 1)[0].strip(), 16)
        except (ValueError, IndexError):
            continue
        indice = bisect.bisect_right(inicios, direccion) - 1
        if indice < 0:
            continue
        inicio, tam, nombre = funciones[indice]
        if direccion < inicio + tam and not CON_DESPACHO.search(nombre):
            encontrados.add(nombre)
            for juego, patron in JUEGOS:
                if patron.search(linea):
                    juegos.add(juego)
                    break
    return sorted(encontrados), juegos


def comprobar_autocontenido() -> None:
    """Avisa si algo del AppDir depende de una biblioteca que no lleva dentro.

    Vale la pena aunque parezca redundante: en la máquina donde se construye
    casi todo se resuelve solo, porque el sistema tiene puesto lo mismo que se
    está empaquetando. El agujero solo se ve en la máquina ajena, y para
    entonces ya se ha repartido. Aquí se mira una a una: si la resuelve algo de
    fuera del AppDir y no está en la lista de las que se dejan al anfitrión,
    falta por copiar.
    """
    raiz = APPDIR.resolve()
    dentro = sorted({p.parent for p in raiz.rglob("*.so*") if p.is_file()})
    faltan: dict[str, set[str]] = {}
    for so in sorted(raiz.rglob("*.so*")):
        if not so.is_file():
            continue
        resueltas, sin_resolver = dependencias(so, extra=dentro, ausentes=True)
        for nombre in sin_resolver:
            # Ni dentro ni en el sistema donde se construye. Esta es la peor
            # de las dos: al no resolverla, `ldd` tampoco la propone para
            # copiar, así que se cae del AppImage sin decir nada.
            if not nombre.startswith(DEL_SISTEMA):
                faltan.setdefault(nombre, set()).add(so.name)
        for resuelta in resueltas:
            nombre = os.path.basename(resuelta)
            if nombre.startswith(DEL_SISTEMA):
                continue
            if pathlib.Path(resuelta).resolve().is_relative_to(raiz):
                continue
            faltan.setdefault(nombre, set()).add(so.name)

    if not faltan:
        print("  todo resuelve dentro")
        return
    print(f"  aviso: {len(faltan)} bibliotecas se cogen del sistema y "
          f"pueden no estar en otra máquina:", file=sys.stderr)
    for nombre, quienes in sorted(faltan.items()):
        pide = ", ".join(sorted(quienes)[:3])
        print(f"    {nombre}  ({pide})", file=sys.stderr)


def sellar_build() -> None:
    """Deja dentro del paquete de qué copia salió.

    El AppImage viaja sin repositorio, así que `silux.build()` no tiene a quién
    preguntar una vez empaquetado. Se escribe aquí, donde git todavía está a
    mano, y a partir de ese momento el dato viaja con el programa: sale en la
    barra lateral, en `--version` y en la cabecera del informe.
    """
    # Dentro del contenedor no hay git —y si lo hubiera se quejaría de que el
    # repositorio es de otro usuario—, así que la marca la calcula quien lanza
    # la construcción y viaja por entorno. Ejecutando este archivo a mano,
    # quien está en el path es `tools/` y no la raíz, de ahí el apaño.
    marca = os.environ.get("SILUX_BUILD", "")
    if not marca:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from silux import _preguntar_a_git

        marca = _preguntar_a_git()
    if not marca:
        print("  sin git: el paquete sale sin marca de construcción",
              file=sys.stderr)
        return
    # Los dos paquetes salen del mismo commit, así que sin esto llevarían la
    # misma marca y una captura no diría cuál de los dos se estaba ejecutando,
    # que es justo para lo que sirve la marca.
    if COMPAT:
        marca += "-compat"
    (APPDIR / "usr" / "lib" / "python" / "silux" / "_build.txt").write_text(
        marca + "\n", encoding="utf-8")
    print(f"  {marca}")


def escribir_metadatos(banderas: set[str] = frozenset()) -> None:
    apprun = APPDIR / "AppRun"
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    guion = APPRUN
    if banderas:
        # Detrás de la línea del intérprete y delante de todo lo demás: si el
        # procesador no da, no hay nada más que preparar.
        cabecera, resto = guion.split("\n", 1)
        relleno = (GUARDA.replace("%%JUEGOS%%", " ".join(sorted(banderas)))
                         .replace("%%NOMBRE%%", f"{APP_ID}-x86_64"))
        guion = f"{cabecera}\n{relleno}{resto}"
    apprun.write_text(guion, encoding="utf-8")
    apprun.chmod(0o755)

    # El AppRun apunta a lib/python; la stdlib está en lib/pythonX.Y. Un enlace
    # deja las dos rutas donde el intérprete las busca.
    (APPDIR / "usr" / "lib" / "python").mkdir(exist_ok=True)

    (APPDIR / f"{APP_ID}.desktop").write_text(DESKTOP, encoding="utf-8")
    icono = ROOT / "silux" / "ui" / "assets" / "silux.svg"
    if icono.exists():
        shutil.copy2(icono, APPDIR / f"{APP_ID}.svg")
        destino_icono = APPDIR / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        destino_icono.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icono, destino_icono / f"{APP_ID}.svg")


def quitar_simbolos() -> None:
    """Los símbolos de depuración son la mitad del tamaño de algunas libs."""
    if shutil.which("strip") is None:
        print("  sin strip: el paquete sale más grande de lo necesario",
              file=sys.stderr)
        return
    for binario in list((APPDIR / "usr" / "lib").rglob("*.so*")):
        if binario.is_file() and not binario.is_symlink():
            subprocess.run(["strip", "--strip-unneeded", str(binario)],
                           capture_output=True, check=False)


def empaquetar() -> pathlib.Path | None:
    herramienta = conseguir_appimagetool()
    if herramienta is None:
        print("Falta appimagetool y no se pudo descargar. Con --appdir-only se\n"
              "construye igualmente el árbol para empaquetarlo a mano.", file=sys.stderr)
        return None

    sufijo = "-compat" if COMPAT else ""
    destino = DIST / f"{APP_ID}-x86_64{sufijo}.AppImage"
    # appimagetool es a su vez un AppImage, así que necesita FUSE para
    # montarse a sí mismo. Dentro de un contenedor no lo hay, y en muchas
    # distribuciones modernas tampoco: ya solo traen FUSE 3 y estos piden el 2.
    # Con esta variable se descomprime en /tmp y se ejecuta desde ahí, que
    # funciona siempre y cuesta un segundo más.
    entorno = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    resultado = subprocess.run(
        [str(herramienta), "--comp", "zstd", str(APPDIR), str(destino)],
        env=entorno, check=False,
    )
    if resultado.returncode != 0 or not destino.exists():
        print("appimagetool falló.", file=sys.stderr)
        return None
    return destino


def conseguir_appimagetool() -> pathlib.Path | None:
    if (ruta := shutil.which("appimagetool")):
        return pathlib.Path(ruta)
    cache = DIST / "appimagetool"
    if cache.exists():
        return cache

    url = ("https://github.com/AppImage/appimagetool/releases/download/"
           "continuous/appimagetool-x86_64.AppImage")
    print(f"· descargando appimagetool de {url}")
    try:
        DIST.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, cache)
        cache.chmod(0o755)
    except (OSError, urllib.error.URLError) as error:
        print(f"  no se pudo: {error}", file=sys.stderr)
        return None
    return cache


# -- utilidades --------------------------------------------------------------

def dependencias(binario: pathlib.Path,
                 extra: Optional[list[pathlib.Path]] = None,
                 ausentes: bool = False):
    """Las bibliotecas de las que depende un binario, según `ldd`.

    `extra` son directorios donde buscar además de los del sistema. Hacen falta
    para el PySide6 de PyPI, que no usa el Qt de la distribución sino que trae
    el suyo dentro del propio paquete: sin decírselo a `ldd`, sus módulos
    aparecen como si no dependieran de nada y el AppImage sale sin Qt.
    """
    entorno = dict(os.environ)
    if extra:
        rutas = [str(d) for d in extra if d.is_dir()]
        if rutas:
            entorno["LD_LIBRARY_PATH"] = os.pathsep.join(
                rutas + ([entorno["LD_LIBRARY_PATH"]] if entorno.get("LD_LIBRARY_PATH") else []))
    try:
        salida = subprocess.run(["ldd", str(binario)], capture_output=True,
                                text=True, check=False, env=entorno).stdout
    except OSError:
        return ([], []) if ausentes else []
    encontradas, sin_resolver = [], []
    for linea in salida.splitlines():
        if "=>" not in linea:
            continue
        izquierda, derecha = linea.split("=>", 1)
        ruta = derecha.strip().split(" ")[0]
        if ruta.startswith("/") and os.path.exists(ruta):
            encontradas.append(ruta)
        elif "not found" in derecha:
            sin_resolver.append(izquierda.strip())
    return (encontradas, sin_resolver) if ausentes else encontradas


def plugins_de_qt() -> pathlib.Path | None:
    """Dónde guarda esta distribución los plugins de Qt6."""
    candidatos = []
    try:
        import PySide6
        candidatos.append(pathlib.Path(PySide6.__file__).parent / "Qt" / "plugins")
        candidatos.append(pathlib.Path(PySide6.__file__).parent / "plugins")
    except ImportError:
        pass
    candidatos += [pathlib.Path(p) for p in
                   ("/usr/lib/qt6/plugins", "/usr/lib/qt/plugins",
                    "/usr/lib64/qt6/plugins", "/usr/lib/x86_64-linux-gnu/qt6/plugins")]
    return next((c for c in candidatos if c.is_dir()), None)


if __name__ == "__main__":
    raise SystemExit(main())
