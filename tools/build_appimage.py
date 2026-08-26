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
DEL_SISTEMA = (
    "libc.so", "libm.so", "libpthread", "libdl.so", "librt.so", "ld-linux",
    "libgcc_s", "libstdc++", "libGL", "libEGL", "libGLX", "libGLdispatch",
    "libX11", "libxcb", "libXau", "libXdmcp", "libXext", "libXrender",
    "libXi", "libXfixes", "libXrandr", "libXcursor", "libwayland",
    "libdrm", "libgbm", "libudev", "libselinux", "libdbus-1",
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
exec "$AQUI/usr/bin/python3" -m silux.ui.app "$@"
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
    parser.add_argument("--container", metavar="IMAGEN", nargs="?",
                        const=IMAGEN_BASE,
                        help="construye dentro de un contenedor con una "
                             "distribución antigua, para que el resultado "
                             "funcione en procesadores y sistemas viejos")
    args = parser.parse_args()

    if args.container:
        return construir_en_contenedor(args.container)

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
    print("· metadatos")
    escribir_metadatos()
    print("· strip")
    quitar_simbolos()

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
apt-get install -y -qq --no-install-recommends \
    python3 python3-pip python3-venv file desktop-file-utils \
    libgl1 libegl1 libxkbcommon0 libdbus-1-3 libfontconfig1 >/dev/null
# El PySide6 de PyPI viene compilado para manylinux: glibc antigua y x86-64
# básico. El de la distribución iría atado a la versión de Qt del sistema.
pip3 install --quiet --break-system-packages 'PySide6>=6.6' 2>/dev/null || \
    pip3 install --quiet 'PySide6>=6.6'
cd /fuente
python3 tools/build_appimage.py "$@"
"""


def construir_en_contenedor(imagen: str) -> int:
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

    print(f"· construyendo dentro de {imagen} con {motor}")
    DIST.mkdir(parents=True, exist_ok=True)
    orden = [
        motor, "run", "--rm",
        "-v", f"{ROOT}:/fuente:z",
        "-w", "/fuente",
        imagen, "bash", "-c", RECETA,
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

    print("\nCompatibilidad de lo construido:")
    if nivel and nivel != "x86-64-baseline":
        print(f"  ⚠ Exige {nivel}: no arrancará en procesadores anteriores a "
              f"{'2013 (Haswell / Zen)' if nivel.endswith('v3') else '2009'}.")
        print("    El error que verán es «CPU ISA level is lower than required».")
    if glibc:
        print(f"  ⚠ Exige glibc {glibc} o superior.")
    print("  Las dos cosas se resuelven construyendo en un contenedor con una")
    print("  distribución antigua; ver la sección «Compatibilidad» del README.")


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


def _glibc_minima() -> Optional[str]:
    """La versión de glibc más alta que pide cualquiera de las bibliotecas."""
    if not shutil.which("objdump"):
        return None
    mayor = (0, 0)
    for binario in list((APPDIR / "usr" / "lib").glob("*.so*"))[:60]:
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
    return set(dependencias(destino_bin))


def copiar_silux() -> None:
    destino = APPDIR / "usr" / "lib" / "python" / "silux"
    shutil.copytree(ROOT / "silux", destino,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def copiar_pyside() -> set[str]:
    """Solo los módulos que se usan, y sus bibliotecas."""
    import PySide6
    import shiboken6

    origen = pathlib.Path(PySide6.__file__).parent
    destino = APPDIR / "usr" / "lib" / "python" / "PySide6"
    destino.mkdir(parents=True)

    # El PySide6 de PyPI trae su propio Qt aquí dentro; el de una distribución
    # usa el del sistema. Hay que mirar en los dos sitios.
    qt_propio = [origen / "Qt" / "lib", origen]

    bibliotecas: set[str] = set()
    (destino / "__init__.py").write_bytes((origen / "__init__.py").read_bytes())
    for modulo in QT_MODULES:
        for fichero in origen.glob(f"{modulo}.*.so"):
            copia = destino / fichero.name
            shutil.copy2(fichero, copia)
            bibliotecas |= set(dependencias(copia, extra=qt_propio))
        for pyi in origen.glob(f"{modulo}.pyi"):
            pass                          # las anotaciones no hacen falta en tiempo de ejecución

    # shiboken es el puente entre Python y C++; sin él no carga ningún módulo.
    origen_shiboken = pathlib.Path(shiboken6.__file__).parent
    destino_shiboken = APPDIR / "usr" / "lib" / "python" / "shiboken6"
    shutil.copytree(origen_shiboken, destino_shiboken,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyi", "docs"))
    for so in destino_shiboken.rglob("*.so*"):
        bibliotecas |= set(dependencias(so, extra=qt_propio + [origen_shiboken]))
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
            bibliotecas |= set(dependencias(so))
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
        if any(marca in nombre for marca in DEL_SISTEMA):
            continue
        copia = destino / nombre
        if not copia.exists():
            try:
                shutil.copy2(ruta, copia, follow_symlinks=True)
            except OSError:
                continue
        pendientes.extend(dependencias(copia, extra=sorted(origenes)))


def escribir_metadatos() -> None:
    apprun = APPDIR / "AppRun"
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    apprun.write_text(APPRUN.replace("python3", "python3", 1), encoding="utf-8")
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

    destino = DIST / f"{APP_ID}-x86_64.AppImage"
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
                 extra: Optional[list[pathlib.Path]] = None) -> list[str]:
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
        return []
    encontradas = []
    for linea in salida.splitlines():
        if "=>" not in linea:
            continue
        ruta = linea.split("=>")[1].strip().split(" ")[0]
        if ruta.startswith("/") and os.path.exists(ruta):
            encontradas.append(ruta)
    return encontradas


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
