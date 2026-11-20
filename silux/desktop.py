"""El icono y la entrada de menú en el escritorio del usuario.

Sin esto la aplicación no aparece en el lanzador y la barra de tareas le pone
un icono genérico. Todo va a `~/.local/share`, así que no hace falta root y no
toca nada del sistema.

Vive dentro del paquete, y no en `tools/`, porque lo usan dos sitios: la
herramienta `tools/install_desktop.py` y el botón de Ajustes, que también
tiene que funcionar desde el AppImage, donde `tools/` no viaja.

La entrada apunta a lo que se está ejecutando, y cada forma de ejecutarlo
tiene la suya (`current_launcher`):

- desde el AppImage, `silux.desktop` abre el archivo `.AppImage`, no la
  carpeta temporal donde se monta, que desaparece al cerrar;
- desde el código, `silux-dev.desktop`, «Silux (desarrollo)», con su propio
  icono e identificador: la del AppImage y la del repositorio conviven y
  quitar una no deja a la otra sin icono;
- desde un paquete instalado, `silux.desktop` con `silux-gui`.

Los PNG se generan desde el SVG con Qt, que ya es dependencia de la interfaz:
así no hace falta tener rsvg-convert ni Inkscape. Con `QImageReader` y no con
`QtSvg`, que no va dentro del AppImage; el complemento `qsvg`, sí.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Mapping, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
SVG = pathlib.Path(__file__).resolve().parent / "ui" / "assets" / "silux.svg"

APP_ID = "silux"
DEV_APP_ID = "silux-dev"
# Los tamaños que pide la especificación de iconos de freedesktop, más los que
# usan en la práctica Plasma y GNOME para la barra de tareas.
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)

# El nombre que tuvo el proyecto antes de llamarse silux. Su instalador dejó
# `cpuz.desktop` y su juego de iconos, y nada los quitaba: en la oficina seguía
# en el menú una entrada que lanza un módulo que ya no existe desde una carpeta
# que tampoco. Solo se quita si es nuestra; un CPU-Z bajo Wine es otra cosa.
LEGACY_ID = "cpuz"
LEGACY_MODULE = "cpuz.ui.app"
MODULE = "silux.ui.app"

# Las palabras con las que alguien buscaría esto en el lanzador. Van sin tildes
# además de con ellas porque nadie teclea «caché» con acento al buscar, y sin
# marcas registradas: el nombre se cambió justamente para no rozarlas.
KEYWORDS = (
    "hardware;cpu;procesador;processor;gpu;grafica;gráfica;graphics;tarjeta;"
    "radeon;geforce;vram;memoria;memory;ram;dimm;cache;caché;placa;motherboard;"
    "bios;uefi;red;network;ethernet;wifi;ip;monitor;pantalla;display;edid;"
    "sensor;sensores;temperatura;temperature;ventilador;fan;rpm;voltaje;"
    "voltage;vatios;watts;frecuencia;frequency;mhz;ghz;reloj;clock;"
    "monitorizacion;monitorización;monitoring;diagnostico;diagnóstico;info;"
    "sistema;system;"
)

# El identificador va en tres sitios y tienen que coincidir: el nombre del
# archivo (que es el `app_id` de la ventana en Wayland), `Icon=` y
# `StartupWMClass=`, que en X11 se compara con la clase de la ventana.
DESKTOP_TEMPLATE = f"""[Desktop Entry]
Type=Application
Version=1.5
Name=@NAME@
Name[en]=@NAME_EN@
GenericName=Información y sensores del equipo
GenericName[en]=Hardware information and sensors
Comment=Qué hardware tienes y qué está haciendo ahora mismo
Comment[en]=What hardware you have and what it is doing right now
Exec=@EXEC@
TryExec=@TRYEXEC@
Path=@PATH@
Icon=@ID@
Terminal=false
Categories=System;Monitor;
Keywords={KEYWORDS}
StartupNotify=true
StartupWMClass=@ID@
"""


class DesktopError(RuntimeError):
    """Lo que impide instalar, dicho para quien lo lee."""


@dataclass(frozen=True)
class Launcher:
    """Cómo se abre esta copia de silux desde el menú."""

    mode: str                       # "appimage", "development" o "package"
    app_id: str
    name: str
    name_en: str
    # La orden, argumento a argumento. Vacía si no se sabe: un AppImage
    # montado sin `$APPIMAGE` no dice dónde está su archivo.
    command: tuple[str, ...]
    working_dir: str = ""


def source_checkout() -> Optional[pathlib.Path]:
    """La carpeta del repositorio, si este silux se ejecuta desde su código."""
    if (ROOT / "pyproject.toml").is_file() and (ROOT / "tools" / "install_desktop.py").is_file():
        return ROOT
    return None


def current_launcher(environ: Optional[Mapping[str, str]] = None) -> Launcher:
    env = os.environ if environ is None else environ
    if env.get("APPIMAGE"):
        return Launcher("appimage", APP_ID, "Silux", "Silux", (env["APPIMAGE"],))
    if "/.mount_" in sys.executable:
        return Launcher("appimage", APP_ID, "Silux", "Silux", ())
    if (root := source_checkout()) is not None:
        return Launcher("development", DEV_APP_ID, "Silux (desarrollo)",
                        "Silux (development)", (sys.executable, "-m", MODULE), str(root))
    if (script := shutil.which("silux-gui")):
        return Launcher("package", APP_ID, "Silux", "Silux", (script,))
    return Launcher("package", APP_ID, "Silux", "Silux", (sys.executable, "-m", MODULE))


def data_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_DATA_HOME") or (pathlib.Path.home() / ".local" / "share"))


def hicolor() -> pathlib.Path:
    return data_home() / "icons" / "hicolor"


def icon_path(size: int, app_id: str = APP_ID) -> pathlib.Path:
    return hicolor() / f"{size}x{size}" / "apps" / f"{app_id}.png"


def scalable_path(app_id: str = APP_ID) -> pathlib.Path:
    return hicolor() / "scalable" / "apps" / f"{app_id}.svg"


def desktop_path(app_id: str = APP_ID) -> pathlib.Path:
    return data_home() / "applications" / f"{app_id}.desktop"


def icon_files(app_id: str) -> list[pathlib.Path]:
    """Todos los iconos con ese nombre en el tema, de cualquier tamaño.

    No solo los de `SIZES`: un tamaño que una versión anterior generaba y
    esta ya no se quedaría para siempre con el logo de entonces, y el
    escritorio lo elige cuando es el que mejor le encaja.
    """
    if not hicolor().is_dir():
        return []
    return sorted(p for p in hicolor().glob(f"*/apps/{app_id}.*")
                  if p.suffix in (".png", ".svg"))


def _read(path: pathlib.Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def legacy_files(launcher: Launcher) -> list[pathlib.Path]:
    """Lo que dejó una versión vieja y esta ya no escribe.

    La entrada de cuando el proyecto se llamaba cpuz; y, si esta copia es la
    del repositorio, la `silux.desktop` que el instalador escribía antes para
    el código, que ahora es de quien lo ejecute empaquetado.
    """
    viejos: list[pathlib.Path] = []
    texto = _read(desktop_path(LEGACY_ID))
    if texto is not None and LEGACY_MODULE in texto:
        viejos += [desktop_path(LEGACY_ID), *icon_files(LEGACY_ID)]
    if launcher.mode == "development":
        texto = _read(desktop_path(APP_ID))
        if texto is not None and MODULE in texto:
            viejos += [desktop_path(APP_ID), *icon_files(APP_ID)]
    return viejos


# -- la orden -----------------------------------------------------------------

# Lo que obliga a entrecomillar un argumento según la especificación de las
# entradas de escritorio. Dentro de las comillas, estos cuatro van con barra.
_RESERVADOS = set(" \t\n\"'\\><~|&;$*?#()`")
_CON_BARRA = re.compile(r'(["`$\\])')


def _quote(argument: str) -> str:
    if argument and not (_RESERVADOS & set(argument)):
        citado = argument
    else:
        citado = '"' + _CON_BARRA.sub(r"\\\1", argument) + '"'
    # `%` abre un código de campo (`%f`, `%U`); el literal se escribe doble.
    return citado.replace("%", "%%")


def exec_line(command: tuple[str, ...]) -> str:
    """La orden como va en `Exec=`.

    Lleva dos capas: la de las comillas, y encima la del valor de texto del
    archivo, donde una barra se escribe doble.
    """
    return " ".join(_quote(a) for a in command).replace("\\", "\\\\")


def _split(value: str) -> list[str]:
    """Parte la orden con las reglas de la especificación, no las de la shell:
    entre comillas, la barra solo escapa a `"`, `` ` ``, `$` y a sí misma."""
    partes: list[str] = []
    actual: Optional[str] = None
    i = 0
    while i < len(value):
        c = value[i]
        if c in " \t":
            if actual is not None:
                partes.append(actual)
                actual = None
        elif c == '"':
            actual = actual or ""
            i += 1
            while i < len(value) and value[i] != '"':
                if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in '"`$\\':
                    i += 1
                actual += value[i]
                i += 1
        else:
            actual = (actual or "") + c
        i += 1
    if actual is not None:
        partes.append(actual)
    return partes


def _string_value(value: str) -> str:
    """A path as a string value of the file: backslashes and control
    characters escaped, and a leading space kept."""
    escrito = (value.replace("\\", "\\\\").replace("\n", "\\n")
               .replace("\t", "\\t").replace("\r", "\\r"))
    return "\\s" + escrito[1:] if escrito.startswith(" ") else escrito


def parse_exec(value: str) -> tuple[str, ...]:
    """Lo contrario de `exec_line`, sin los códigos de campo."""
    sin_texto = re.sub(r"\\(.)", lambda m: "\\" if m.group(1) == "\\" else m.group(0), value)
    return tuple(p.replace("%%", "%") for p in _split(sin_texto)
                 if not re.fullmatch(r"%[a-zA-Z]", p))


def entry_text(launcher: Launcher) -> str:
    texto = (DESKTOP_TEMPLATE
             .replace("@NAME@", launcher.name)
             .replace("@NAME_EN@", launcher.name_en)
             .replace("@EXEC@", exec_line(launcher.command))
             .replace("@TRYEXEC@", _string_value(launcher.command[0] if launcher.command else ""))
             .replace("@PATH@", launcher.working_dir)
             .replace("@ID@", launcher.app_id))
    if not launcher.working_dir:
        texto = "\n".join(line for line in texto.splitlines() if line != "Path=") + "\n"
    return texto


# -- escribir -----------------------------------------------------------------


def render_icons(app_id: str = APP_ID) -> list[pathlib.Path]:
    """Rasteriza el SVG a los tamaños de la especificación."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication, QImageReader

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])

    # Fuera lo anterior antes de escribir: archivos nuevos y no reescritos
    # encima, y ninguno de un tamaño que esta versión ya no genera.
    for viejo in icon_files(app_id):
        viejo.unlink()

    written = []
    for size in SIZES:
        reader = QImageReader(str(SVG))
        reader.setScaledSize(QSize(size, size))
        image = reader.read()
        if image.isNull():
            raise DesktopError(f"no se pudo dibujar {SVG}: {reader.errorString()}")

        target = icon_path(size, app_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target), "PNG"):
            raise DesktopError(f"no se pudo escribir {target}")
        written.append(target)

    scalable = scalable_path(app_id)
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SVG, scalable)
    written.append(scalable)
    del app
    return written


def write_desktop(launcher: Launcher) -> pathlib.Path:
    if not launcher.command:
        raise DesktopError("no se sabe dónde está el archivo de este AppImage")
    target = desktop_path(launcher.app_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(entry_text(launcher), encoding="utf-8")
    target.chmod(0o755)
    return target


def refresh_caches() -> None:
    """Avisa al escritorio de que hay iconos y entrada nuevos.

    Todas las órdenes son opcionales: si no están, el escritorio acaba
    enterándose igual, solo que más tarde. Pero en Plasma «más tarde» puede
    ser «al reiniciar la sesión»: `plasmashell` guarda en memoria los iconos
    que ya pintó, y cambiar el archivo no le basta. Escucha una señal de
    D-Bus para volver a leerlos, la misma que manda Plasma al cambiar de tema
    de iconos.
    """
    # Que la carpeta del tema parezca cambiada a quien compare fechas.
    if hicolor().is_dir():
        os.utime(hicolor())
    for command in (
        ["update-desktop-database", str(desktop_path().parent)],
        ["gtk-update-icon-cache", "-f", "-t", str(hicolor())],
        # Las entradas de menú de Plasma salen de su caché, no de la carpeta.
        ["kbuildsycoca6"],
        ["dbus-send", "--session", "--type=signal", "/KIconLoader",
         "org.kde.KIconLoader.iconChanged", "int32:0"],
    ):
        if shutil.which(command[0]):
            try:
                subprocess.run(command, check=False, capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass


def desktop_dir() -> pathlib.Path:
    """La carpeta del escritorio del usuario («Escritorio» en español).

    Se lee de `user-dirs.dirs`, que es lo que hace `xdg-user-dir`, sin lanzar
    nada: esto se pregunta desde la interfaz.
    """
    casa = pathlib.Path.home()
    config = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or casa / ".config")
    try:
        for linea in (config / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if linea.startswith("XDG_DESKTOP_DIR="):
                valor = linea.split("=", 1)[1].strip().strip('"')
                return pathlib.Path(valor.replace("$HOME", str(casa)))
    except OSError:
        pass
    return casa / "Desktop"


def shortcut_path(app_id: str = APP_ID) -> pathlib.Path:
    return desktop_dir() / f"{app_id}.desktop"


def _write_shortcut(launcher: Launcher) -> pathlib.Path:
    """La misma entrada, en el escritorio. Ejecutable, que es lo que piden
    Plasma y GNOME para lanzarla; GNOME además quiere que se marque como de
    confianza, y `gio` lo hace si está."""
    destino = shortcut_path(launcher.app_id)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(entry_text(launcher), encoding="utf-8")
    destino.chmod(0o755)
    if shutil.which("gio"):
        try:
            subprocess.run(["gio", "set", str(destino), "metadata::trusted", "true"],
                           check=False, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return destino


# -- el estado ----------------------------------------------------------------

@dataclass(frozen=True)
class DesktopStatus:
    """Cómo está la entrada de menú de esta copia de silux.

    `state`: «unsupported» (no se puede instalar: un AppImage que no dice
    dónde está su archivo), «missing», «current», «elsewhere» (abre otra
    copia que existe), «broken» (abre algo que ya no existe) u «outdated»
    (abre esta, pero la entrada, los iconos o lo que dejó una versión vieja
    no son los de ahora).
    """

    state: str
    launcher: Launcher
    # A qué apunta la entrada instalada, para decirlo: la orden, o la carpeta
    # si es la del repositorio.
    target: str = ""
    on_desktop: bool = False


def _instalado(texto: str) -> tuple[tuple[str, ...], str]:
    """La orden y la carpeta de una entrada instalada."""
    orden, carpeta = (), ""
    for linea in texto.splitlines():
        if linea.startswith("Exec="):
            orden = parse_exec(linea[len("Exec="):])
        elif linea.startswith("Path="):
            carpeta = linea[len("Path="):]
    return orden, carpeta


def _existe(orden: tuple[str, ...], carpeta: str) -> bool:
    if not orden:
        return False
    programa = orden[0]
    encontrado = (os.path.isfile(programa) and os.access(programa, os.X_OK)) \
        if os.sep in programa else shutil.which(programa) is not None
    return encontrado and (not carpeta or os.path.isdir(carpeta))


def _iconos_al_dia(app_id: str) -> bool:
    try:
        if scalable_path(app_id).read_bytes() != SVG.read_bytes():
            return False
    except OSError:
        return False
    return all(icon_path(tamano, app_id).is_file() for tamano in SIZES)


def status(launcher: Optional[Launcher] = None) -> DesktopStatus:
    """Lo que hay instalado comparado con lo que se instalaría ahora.

    Se compara el contenido —la entrada entera y el SVG—, no un número de
    versión que alguien tendría que acordarse de subir.
    """
    launcher = launcher or current_launcher()
    en_escritorio = on_desktop(launcher.app_id)
    if not launcher.command:
        return DesktopStatus("unsupported", launcher, on_desktop=en_escritorio)
    texto = _read(desktop_path(launcher.app_id))
    if texto is None or not in_menu(launcher.app_id):
        return DesktopStatus("missing", launcher, on_desktop=en_escritorio)
    orden, carpeta = _instalado(texto)
    destino = carpeta or (orden[0] if orden else "")
    if (orden, carpeta) != (launcher.command, launcher.working_dir):
        estado = "elsewhere" if _existe(orden, carpeta) else "broken"
        return DesktopStatus(estado, launcher, destino, en_escritorio)
    al_dia = (texto == entry_text(launcher) and _iconos_al_dia(launcher.app_id)
              and not legacy_files(launcher))
    if en_escritorio and _read(shortcut_path(launcher.app_id)) != entry_text(launcher):
        al_dia = False
    return DesktopStatus("current" if al_dia else "outdated", launcher, destino, en_escritorio)


# -- instalar y quitar -------------------------------------------------------


def set_shortcuts(menu: bool, on_desktop: bool,
                  launcher: Optional[Launcher] = None) -> None:
    """Each shortcut on its own: the menu entry and the one on the desktop.

    The icons stay while either needs them. What an older version left is
    removed whenever something is written.
    """
    launcher = launcher or current_launcher()
    if (menu or on_desktop) and not launcher.command:
        raise DesktopError("no se sabe dónde está el archivo de este AppImage")
    for viejo in legacy_files(launcher):
        viejo.unlink()
    if menu or on_desktop:
        render_icons(launcher.app_id)
    else:
        for icono in icon_files(launcher.app_id):
            if icono.exists():
                icono.unlink()
    entrada, acceso = desktop_path(launcher.app_id), shortcut_path(launcher.app_id)
    if menu:
        write_desktop(launcher)
        _drop_kde_exclusion(launcher.app_id)
    elif in_menu(launcher.app_id):
        # Only a visible one: a file the user hid is theirs, and removing it
        # could uncover a system entry it was hiding.
        entrada.unlink()
    if on_desktop:
        _write_shortcut(launcher)
    elif acceso.exists():
        acceso.unlink()
    refresh_caches()


def uninstall(launcher: Optional[Launcher] = None) -> int:
    """Quita la entrada, los iconos y el acceso del escritorio; devuelve
    cuántos archivos quitó."""
    launcher = launcher or current_launcher()
    removed = 0
    for path in [desktop_path(launcher.app_id), *icon_files(launcher.app_id),
                 *legacy_files(launcher), shortcut_path(launcher.app_id)]:
        if path.exists():
            path.unlink()
            removed += 1
    refresh_caches()
    return removed


def install(launcher: Optional[Launcher] = None,
            on_desktop: Optional[bool] = None) -> tuple[list[pathlib.Path], pathlib.Path]:
    """Instala los iconos y la entrada; devuelve los dos.

    Reinstalar deja lo mismo que instalar en limpio: quita antes lo que dejó
    una versión vieja. `on_desktop` pone o quita el acceso del escritorio;
    con None se deja como esté, al día si existe.
    """
    launcher = launcher or current_launcher()
    if on_desktop is None:
        on_desktop = shortcut_path(launcher.app_id).is_file()
    set_shortcuts(True, on_desktop, launcher)
    return icon_files(launcher.app_id), desktop_path(launcher.app_id)


# -- what the user deleted or hid ---------------------------------------------

def _hidden(texto: str) -> bool:
    """`Hidden=true` (deleted, says the specification) or `NoDisplay=true`
    (kept out of the menus), in the entry's own group."""
    grupo = ""
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("["):
            grupo = linea
        elif grupo == "[Desktop Entry]" and "=" in linea:
            clave, valor = (parte.strip() for parte in linea.split("=", 1))
            if clave in ("Hidden", "NoDisplay") and valor == "true":
                return True
    return False


def kde_menu_file() -> pathlib.Path:
    """Where Plasma's menu editor keeps its changes. Deleting an entry there
    leaves the file and adds an `<Exclude>` with its name."""
    config = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
    return config / "menus" / "applications-kmenuedit.menu"


_EXCLUDE = re.compile(r"(?P<pre>[ \t]*)<Exclude>(?P<body>.*?)</Exclude>(?P<post>\n?)", re.S)


def _kde_excluded(app_id: str) -> bool:
    texto = _read(kde_menu_file())
    if not texto:
        return False
    nombre = f"<Filename>{app_id}.desktop</Filename>"
    fuera = any(nombre in m.group("body") for m in _EXCLUDE.finditer(texto))
    # Moved to another submenu is an Exclude in one and an Include in another.
    dentro = any(nombre in bloque for bloque in re.findall(r"<Include>.*?</Include>", texto, re.S))
    return fuera and not dentro


def _drop_kde_exclusion(app_id: str) -> None:
    """Turning the menu shortcut on again undoes a delete from Plasma's menu
    editor; otherwise the switch would say «in the menu» and it would not be."""
    ruta = kde_menu_file()
    texto = _read(ruta)
    nombre = f"<Filename>{app_id}.desktop</Filename>"
    if not texto or nombre not in texto:
        return

    def limpiar(m: re.Match) -> str:
        cuerpo = re.sub(r"\s*" + re.escape(nombre), "", m.group("body"))
        if cuerpo == m.group("body"):
            return m.group(0)
        return "" if not cuerpo.strip() else f"{m.group('pre')}<Exclude>{cuerpo}</Exclude>{m.group('post')}"

    nuevo = _EXCLUDE.sub(limpiar, texto)
    if nuevo == texto:
        return
    import tempfile
    modo = ruta.stat().st_mode & 0o777
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".silux-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(nuevo)
        os.chmod(temporal, modo)
        os.replace(temporal, ruta)
    except OSError:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def in_menu(app_id: str = APP_ID) -> bool:
    """Whether the menu shows this entry: the file is there, not hidden and
    not deleted from Plasma's menu editor. Deleted by hand it is simply not
    there: no notice, no error."""
    texto = _read(desktop_path(app_id))
    return texto is not None and not _hidden(texto) and not _kde_excluded(app_id)


def on_desktop(app_id: str = APP_ID) -> bool:
    texto = _read(shortcut_path(app_id))
    return texto is not None and not _hidden(texto)


# -- where the AppImage lives -------------------------------------------------

def appimages_dir() -> pathlib.Path:
    """~/AppImages: where a shortcut can point without breaking, because
    nobody empties it the way Downloads or a temporary folder get emptied."""
    return pathlib.Path.home() / "AppImages"


def in_appimages(path) -> bool:
    """Whether the file is in ~/AppImages, as a link or not: the folder is
    resolved, the file itself is not followed."""
    return pathlib.Path(os.path.abspath(path)).parent.resolve() == appimages_dir().resolve()


def points_here(launcher: Optional[Launcher] = None) -> bool:
    """Whether a shortcut the user sees opens this copy."""
    launcher = launcher or current_launcher()
    app_id = launcher.app_id
    for visible, ruta in ((in_menu(app_id), desktop_path(app_id)),
                          (on_desktop(app_id), shortcut_path(app_id))):
        texto = _read(ruta) if visible else None
        if texto is not None and _instalado(texto) == (launcher.command, launcher.working_dir):
            return True
    return False


@dataclass(frozen=True)
class Moved:
    """Where the AppImage is now, and whether the old one is still there
    (it could not be moved, only copied)."""

    path: pathlib.Path
    copied: bool


def _free_name(carpeta: pathlib.Path, nombre: str) -> pathlib.Path:
    """The name, or the name with -2, -3… if one with it is already there."""
    destino = carpeta / nombre
    raiz, extension = os.path.splitext(nombre)
    n = 2
    while destino.exists():
        destino = carpeta / f"{raiz}-{n}{extension}"
        n += 1
    return destino


def move_to_appimages(path) -> Moved:
    """Moves the AppImage into ~/AppImages without overwriting anything.

    A hard link and then removing the old name: the link fails if the name is
    taken, so another file can never be overwritten, and it is a move when
    both are on the same file system. Across file systems or without
    permission to remove the old one, it is copied, and the old one stays.
    """
    origen = pathlib.Path(path)
    carpeta = appimages_dir()
    carpeta.mkdir(parents=True, exist_ok=True)
    while True:
        destino = _free_name(carpeta, origen.name)
        try:
            os.link(origen, destino)
        except FileExistsError:
            continue
        except OSError:
            break
        try:
            origen.unlink()
        except OSError:
            return Moved(destino, copied=True)
        return Moved(destino, copied=False)
    while True:
        destino = _free_name(carpeta, origen.name)
        try:
            with open(origen, "rb") as fuente, open(destino, "xb") as copia:
                shutil.copyfileobj(fuente, copia, 1 << 20)
        except FileExistsError:
            continue
        except OSError:
            try:
                destino.unlink()
            except OSError:
                pass
            raise
        destino.chmod(0o755)
        return Moved(destino, copied=True)


# What the AppImage's AppRun adds to the environment, pointing inside its
# mount. Opening the moved copy without them: it sets its own.
_DEL_MONTAJE = ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH",
                "QT_QPA_PLATFORM_PLUGIN_PATH")
_DEL_RUNTIME = ("APPIMAGE", "APPDIR", "ARGV0", "OWD")


def relaunch_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The environment to open another AppImage from this one: what this
    mount added, taken out again; the rest, as the user had it."""
    montaje = environ.get("APPDIR") or ""
    entorno = {k: v for k, v in environ.items() if k not in _DEL_RUNTIME}
    for variable in _DEL_MONTAJE:
        if variable not in entorno or not montaje:
            continue
        quedan = [parte for parte in entorno[variable].split(os.pathsep)
                  if parte and not parte.startswith(montaje)]
        if quedan:
            entorno[variable] = os.pathsep.join(quedan)
        else:
            del entorno[variable]
    return entorno
