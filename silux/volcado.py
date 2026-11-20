"""Vuelca lo que leen los proveedores de este equipo, para la suite.

Lo lanza `tools/volcar_equipo.py NOMBRE`, que lo deja en
`tests/fixtures/equipos/NOMBRE/`: una copia de lo que el Collector lee
de `/sys`, `/proc` y `/etc` —y nada más—, y en `grabado.json` lo que no sale
de un archivo: la CPUID de cada tipo de núcleo, los ioctl de la gráfica, lo que
contestan OpenGL y Vulkan, el espacio de cada montaje, las direcciones. Con
`SILUX_SYSROOT` apuntando ahí, el Collector da este equipo en cualquier otro.

Solo lee. No pide permisos ni usa el ayudante: el volcado es el de un equipo
sin permisos, que es como lo abre la mayoría de la gente.

**Qué se copia lo decide el propio Collector**, no una lista escrita aquí: se
ejecuta de verdad mientras se apunta cada archivo que abre, cada directorio
que recorre, cada `stat` y cada enlace. Una lista a mano se quedaría vieja el
día que un proveedor leyera un archivo nuevo, y el volcado diría que el equipo
no lo tiene.

**Lo que identifica a alguien se sustituye** por lo mismo que pone
`privacidad.anonimizar` —el nombre del equipo, las direcciones, los números de
serie, las interfaces con nombre puesto a mano, los puntos de montaje que no
son del sistema, el usuario—, y antes de dar el volcado por bueno se
comprueban dos cosas: que `privacidad.anonimizar` no encuentra nada más que
tapar en la foto que sale de él, y que ninguno de los identificadores de esta
máquina que busca `tools/comprobar_privacidad.py` aparece en ningún byte. Si
algo falla, no se deja nada escrito.
"""

from __future__ import annotations

import builtins
import contextlib
import dataclasses
import errno
import getpass
import io
import json
import os
import pathlib
import re
import shutil
import tempfile
from typing import Optional

from . import privacidad, sysroot
from .providers.sysfs_cpu import FUENTES_DE_FRECUENCIA

VIGILADO = ("/sys/", "/proc/", "/etc/")
# Un archivo de sysfs o de procfs de más de esto no es lo que se lee para
# describir un equipo; copiarlo solo engordaría el repositorio.
TOPE = 512 * 1024
MANIFIESTO = "manifiesto.json"

# Archivos cuyo contenido identifica a una pieza concreta y no dice nada del
# modelo: se cambian por ceros del mismo largo.
SERIALES = {"serial", "serial_number", "wwid", "vpd_pg80", "vpd_pg83",
            "unique_id", "product_uuid", "product_serial", "board_serial",
            "chassis_serial", "uuid", "eui", "nguid", "perm_addr"}
DIRECCIONES = {"address", "perm_address"}
# De un dispositivo USB, lo que dice de quién es y qué modelo.
USB_QUE_IDENTIFICA = {"product", "manufacturer", "idVendor", "idProduct"}
# Nombres que no señalan a nadie: los de un concentrador o un controlador.
USB_GENERICO = re.compile(r"hub|host controller|usb\s*receiver", re.I)
MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
CORREO_SUSTITUTO = "usuario@example.org"
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


# -- las gráficas dormidas -------------------------------------------------------

SYS_DRM = "/sys/class/drm"
SYS_PCI = "/sys/bus/pci/devices"

# Lo que se puede leer de una gráfica dormida sin despertarla:
# - `power/runtime_status` y `power/control` son del núcleo de PM y devuelven
#   lo que el kernel ya tiene guardado (`drivers/base/power/sysfs.c`;
#   `Documentation/ABI/testing/sysfs-devices-power`).
# - `power_state` es `pdev->current_state`, guardado también
#   (`drivers/pci/pci-sysfs.c`; `Documentation/ABI/testing/sysfs-bus-pci`,
#   desde 5.11).
# - La identidad: `pci_config_attr` (`drivers/pci/pci-sysfs.c`) imprime los
#   campos de `struct pci_dev` que se leyeron al enumerar el bus, sin volver
#   al espacio de configuración. `driver` es un enlace: no se abre.
# Lo demás se da por peligroso. El enlace (`current_link_*`) llama a
# `pci_config_pm_runtime_get()` desde 6.18 y saca la tarjeta de D3cold; el
# hwmon de amdgpu la despertaba antes de `amdgpu_pm_get_access_if_active()`;
# NVML, según el README de NVIDIA (cap. 22, RTD3), la pone activa al abrirse.
IDENTIDAD = ("vendor", "device", "subsystem_vendor", "subsystem_device",
             "revision", "class")
ENERGIA = ("power/runtime_status", "power_state", "power/control")
SIN_DESPERTAR = IDENTIDAD + ENERGIA
# `runtime_status` y `power_state` cuando la tarjeta duerme.
DORMIDA = ("suspended",)
APAGADA = ("D3hot", "D3cold")

def _leer(ruta) -> str | None:
    try:
        return pathlib.Path(sysroot.ruta(str(ruta))).read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _real(ruta) -> pathlib.Path:
    """El camino sin enlaces, como lo vería el sistema."""
    return pathlib.Path(sysroot.fuera(pathlib.Path(sysroot.ruta(str(ruta))).resolve()))


def energia(dispositivo) -> dict[str, str]:
    """El estado de energía de un dispositivo PCI. No lo despierta."""
    return {nombre: valor for nombre in ENERGIA
            if (valor := _leer(f"{dispositivo}/{nombre}")) is not None}


def dormida(estado: dict[str, str]) -> bool:
    return (estado.get("power/runtime_status") in DORMIDA
            or estado.get("power_state") in APAGADA)


def graficas() -> list[str]:
    """Las gráficas del bus PCI (clase 0x03), tengan driver o no."""
    try:
        nombres = sorted(p.name for p in pathlib.Path(sysroot.ruta(SYS_PCI)).iterdir())
    except OSError:
        return []
    return [f"{SYS_PCI}/{n}" for n in nombres
            if (_leer(f"{SYS_PCI}/{n}/class") or "").startswith("0x03")]


def cadena(dispositivo) -> list[pathlib.Path]:
    """Los puentes por los que pasa el dispositivo hasta la raíz, sin él.

    La misma cuenta que `providers.drm._cadena_pcie`: se sube mientras la
    carpeta tenga forma de dirección PCI.
    """
    actual = _real(dispositivo).parent
    eslabones = []
    while re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", actual.name):
        eslabones.append(actual)
        actual = actual.parent
    return eslabones


# -- qué lee el Collector ------------------------------------------------------

def _vigilado(camino) -> str | None:
    try:
        texto = os.fspath(camino)
    except TypeError:
        return None
    if isinstance(texto, bytes):
        texto = texto.decode(errors="replace")
    # Con una raíz puesta (los tests), el camino se apunta como lo vería el
    # sistema: es el que se copia después.
    texto = sysroot.fuera(texto)
    return texto if texto.startswith(VIGILADO) else None


# Where Python 3.10's pathlib keeps its own copy of these: it took them from
# os and io when imported (`_NormalAccessor`) and, unlike 3.11, does not look
# them up again. Patching os and io alone missed everything the providers
# read, list and look at with pathlib, and let it past the sleeping card's
# guard.
_POR_PATHLIB = {"open": (io, builtins), "listdir": (os,), "scandir": (os,),
                "stat": (os,), "lstat": (os,), "readlink": (os,)}


def _con_pathlib(parches: dict) -> dict:
    """Los mismos parches, también en el `_NormalAccessor` de 3.10."""
    accesor = getattr(pathlib, "_NormalAccessor", None)
    if accesor is None:
        return parches
    todos = dict(parches)
    for nombre, modulos in _POR_PATHLIB.items():
        funcion = next((parches[(m, nombre)] for m in modulos if (m, nombre) in parches), None)
        if funcion is not None and nombre in vars(accesor):
            todos[(accesor, nombre)] = staticmethod(funcion)
    return todos


@contextlib.contextmanager
def _parcheando(parches: dict):
    """Pone cada función en su sitio y lo deja todo como estaba. De una clase
    se guarda lo que tiene de verdad (un `staticmethod`, un builtin), no lo
    que da `getattr`."""
    def original(dueno, nombre):
        return vars(dueno)[nombre] if isinstance(dueno, type) else getattr(dueno, nombre)

    parches = _con_pathlib(parches)
    originales = {clave: original(*clave) for clave in parches}
    try:
        for (dueno, nombre), funcion in parches.items():
            setattr(dueno, nombre, funcion)
        yield
    finally:
        for (dueno, nombre), funcion in originales.items():
            setattr(dueno, nombre, funcion)


@contextlib.contextmanager
def _apuntando():
    """Apunta qué toca el Collector: archivos, directorios, `stat` y enlaces."""
    leidos: set[str] = set()
    listados: set[str] = set()
    mirados: set[str] = set()

    def apuntar(conjunto, funcion):
        def envuelta(camino, *args, **kwargs):
            if (texto := _vigilado(camino)) is not None:
                conjunto.add(texto)
            return funcion(camino, *args, **kwargs)
        return envuelta

    parches = {
        (builtins, "open"): apuntar(leidos, builtins.open),
        (io, "open"): apuntar(leidos, io.open),
        (os, "listdir"): apuntar(listados, os.listdir),
        (os, "scandir"): apuntar(listados, os.scandir),
        (os, "stat"): apuntar(mirados, os.stat),
        (os, "lstat"): apuntar(mirados, os.lstat),
        (os, "readlink"): apuntar(mirados, os.readlink),
    }
    with _parcheando(parches):
        yield leidos, listados, mirados


class _Dormidas:
    """Las gráficas que el sistema tiene dormidas, y lo que no se toca de ellas.

    Volcar un portátil con la dedicada dormida no puede despertarla: se
    grabaría una tarjeta encendida solo porque la herramienta la ha
    encendido, que es justo lo que el volcado tiene que dejar ver (B-1 de
    la revisión de gráficas). De cada una dormida solo se lee
    `SIN_DESPERTAR`; lo mismo de las otras funciones de su ranura
    (el audio HDMI duerme con ella) y de los puentes de su cadena, que en
    D3cold tienen la ranura sin corriente. Tampoco se abren sus nodos de
    `/dev/dri` (los ioctl), ni NVML si es una NVIDIA, ni las API gráficas,
    que enumeran todas las tarjetas.
    """

    def __init__(self) -> None:
        self.estados: dict[str, dict[str, str]] = {}
        self.dormidas: list[str] = []
        self.nodos: list[str] = []
        self.dev: set[str] = set()
        self.nvidia = False
        for grafica in graficas():
            estado = energia(grafica)
            ranura = grafica.rsplit("/", 1)[1]
            self.estados[ranura] = estado
            if not dormida(estado):
                continue
            self.dormidas.append(ranura)
            real = _real(grafica)
            hermanas = [f"{real.parent}/{h.name}"
                        for h in pathlib.Path(sysroot.ruta(str(real.parent))).iterdir()
                        if h.name.rsplit(".", 1)[0] == ranura.rsplit(".", 1)[0]]
            self.nodos += hermanas + [str(p) for p in cadena(grafica)]
            drm = pathlib.Path(sysroot.ruta(f"{real}/drm"))
            if drm.is_dir():
                self.dev.update(f"/dev/dri/{n.name}" for n in drm.iterdir()
                                if n.name.startswith(("card", "renderD")))
            if _leer(f"{grafica}/vendor") == "0x10de":
                self.nvidia = True
        # El más largo primero: la gráfica cuelga de sus puentes.
        self.nodos = sorted(set(self.nodos), key=len, reverse=True)

    def __bool__(self) -> bool:
        return bool(self.dormidas)

    def energia(self) -> set[str]:
        """Los archivos de energía de cada gráfica, dormida o no, para el volcado."""
        return {f"{SYS_PCI}/{ranura}/{nombre}"
                for ranura, estado in self.estados.items() for nombre in estado}

    def prohibido(self, camino) -> bool:
        if not self:
            return False
        texto = os.fspath(camino)
        if isinstance(texto, bytes):
            texto = texto.decode(errors="replace")
        texto = sysroot.fuera(texto)
        if texto in self.dev:
            return True
        if not texto.startswith("/sys/"):
            return False
        real = sysroot.fuera(os.path.realpath(sysroot.ruta(texto)))
        for nodo in self.nodos:
            if real.startswith(nodo + "/"):
                return real[len(nodo) + 1:] not in SIN_DESPERTAR
        return False

    def sin_grabar(self) -> list[str]:
        if not self:
            return []
        lineas = [f"de las gráficas dormidas ({', '.join(self.dormidas)}), todo menos "
                  "su identidad y su estado de energía, y lo mismo de las otras "
                  "funciones de su ranura y de sus puentes: leerlo las despierta",
                  "lo que contestan OpenGL, Vulkan, OpenCL y VA-API: enumeran todas "
                  "las tarjetas, también la dormida"]
        if self.nvidia:
            lineas.append("NVML: abrirla despierta la NVIDIA dormida")
        return lineas


@contextlib.contextmanager
def _sin_despertar(dormidas: _Dormidas | None):
    """Que el Collector no lea lo que despierta una gráfica dormida.

    Lo que se le niega lo recibe como un archivo que no existe, que es como
    lo verá al leer el volcado.
    """
    if not dormidas:
        yield
        return
    from silux import gpuapi, nvml

    def guardar(funcion):
        def envuelta(camino, *args, **kwargs):
            if dormidas.prohibido(camino):
                raise FileNotFoundError(errno.ENOENT, "gráfica dormida: no se lee",
                                        os.fspath(camino))
            return funcion(camino, *args, **kwargs)
        return envuelta

    parches = {
        (builtins, "open"): guardar(builtins.open),
        (io, "open"): guardar(io.open),
        (os, "open"): guardar(os.open),
        (gpuapi, "consultar"): lambda *a, **k: {},
    }
    if dormidas.nvidia:
        parches[(nvml.Nvml, "open")] = lambda self: False
    with _parcheando(parches):
        yield


def _recoger(dormidas: _Dormidas | None = None):
    """Ejecuta el Collector de verdad, apuntando y grabando lo que pregunta."""
    from silux.collector import Collector

    sysroot.empezar_a_grabar()
    with _apuntando() as (leidos, listados, mirados), _sin_despertar(dormidas):
        recolector = Collector()
        try:
            recolector.snapshot()
            recolector.snapshot()
        finally:
            recolector.close()
    return leidos, listados, mirados, sysroot.lo_grabado()


def _alternativas(leidos: set[str]) -> set[str]:
    """Las otras fuentes de un dato que el proveedor leyó de la primera.

    La única excepción a que el Collector decida qué se copia: de la
    frecuencia de cada hilo se queda con la primera fuente que contesta y no
    abre las demás. Sin ellas, el volcado de un kernel que tiene
    `cpuinfo_avg_freq` no sirve para ver qué sale en uno que no la tiene. La
    lista es la del proveedor, no una escrita aquí.
    """
    return {os.path.join(os.path.dirname(camino), fuente)
            for camino in leidos if os.path.basename(camino) in FUENTES_DE_FRECUENCIA
            for fuente in FUENTES_DE_FRECUENCIA}


# Lo que se copia de cada gráfica despierta aunque el Collector no lo lea
# todavía (fase 0 de la revisión de gráficas): sin ello no se pueden
# escribir los arreglos de `xe`, de las Arc y de los contadores.
#
# - De `xe`, las frecuencias y el reposo cuelgan del nodo PCI y no del DRM
#   (`tile*/gt*/freq0/`, con su `throttle/`, y `gtidle/`), y su hwmon tiene
#   canales con nombre (`pkg`, `vram`) que no se leen hoy: el hwmon entero.
# - De cada puente de su cadena hasta la raíz, el enlace y quién es: la Arc
#   lleva un conmutador dentro y el enlace bueno es el de fuera (I1).
# - De `/sys/bus/event_source/devices`, el tipo, el formato y los eventos de
#   cada PMU: el nombre del de una Arc con i915 y los eventos de xe (I2, I9).
#   Nada de esto identifica a nadie.
EXTRAS_DE_GRAFICA = ("tile*/gt*/freq0/*", "tile*/gt*/freq0/throttle/*",
                     "tile*/gt*/gtidle/*", "hwmon/hwmon*/*")
EXTRAS_DE_PUENTE = ("vendor", "device", "class", "current_link_speed",
                    "current_link_width", "max_link_speed", "max_link_width")
EVENT_SOURCE = "/sys/bus/event_source/devices"


def _extras_de_graficas() -> set[str]:
    """Los caminos de `EXTRAS_DE_GRAFICA`, de los puentes y de event_source."""
    import glob

    def existentes(patron: str) -> set[str]:
        return {sysroot.fuera(c) for c in glob.glob(sysroot.ruta(patron))
                if os.path.isfile(c)}

    caminos: set[str] = set()
    for grafica in graficas():
        if dormida(energia(grafica)):
            continue
        real = str(_real(grafica))
        for patron in EXTRAS_DE_GRAFICA:
            caminos |= existentes(f"{real}/{patron}")
        for puente in cadena(grafica):
            for nombre in EXTRAS_DE_PUENTE:
                caminos |= existentes(f"{sysroot.fuera(str(puente))}/{nombre}")
    for patron in ("*/type", "*/format/*", "*/events/*"):
        caminos |= existentes(f"{EVENT_SOURCE}/{patron}")
    return caminos


# -- copiar ---------------------------------------------------------------------

class _Copia:
    """Reproduce caminos del sistema dentro del volcado, con sus enlaces.

    Through `sysroot`: with a dump mounted, it dumps that one. That is how the
    dumper is tested on machines that are not this one, and on the dumps of
    the suite, whose values are already the substitutes.
    """

    def __init__(self, destino: pathlib.Path):
        self.destino = destino
        self.ilegibles: set[str] = set()

    def _dentro(self, camino: str) -> pathlib.Path:
        return self.destino / camino.lstrip("/")

    def _enlace(self, camino: str) -> None:
        dentro = self._dentro(camino)
        if dentro.is_symlink() or dentro.exists():
            return
        try:
            destino = os.readlink(sysroot.ruta(camino))
        except OSError:
            # `/proc/1/exe` sin permisos: se deja fuera, y quien lo lea recibe
            # un error igual que en el equipo de verdad.
            return
        dentro.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(destino, dentro)

    def camino(self, camino: str) -> str | None:
        """Recrea cada enlace del camino y devuelve dónde está de verdad."""
        actual = "/"
        for trozo in pathlib.PurePosixPath(camino).parts[1:]:
            siguiente = os.path.join(actual, trozo)
            vueltas = 0
            while os.path.islink(sysroot.ruta(siguiente)) and vueltas < 40:
                self._enlace(siguiente)
                try:
                    destino = os.readlink(sysroot.ruta(siguiente))
                except OSError:
                    return None
                siguiente = os.path.normpath(os.path.join(os.path.dirname(siguiente), destino))
                vueltas += 1
            if not os.path.lexists(sysroot.ruta(siguiente)):
                return None
            if not siguiente.startswith(VIGILADO) and siguiente not in ("/sys", "/proc", "/etc"):
                # Un enlace que sale del sistema (`/proc/1/exe`): basta con él.
                return None
            actual = siguiente
        return actual

    def archivo(self, camino: str) -> None:
        real = self.camino(camino)
        if real is None:
            self._de_fuera(camino)
            return
        dentro = self._dentro(real)
        if os.path.isdir(sysroot.ruta(real)):
            dentro.mkdir(parents=True, exist_ok=True)
            return
        if dentro.exists():
            return
        dentro.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(sysroot.ruta(real), "rb") as origen:
                datos = origen.read(TOPE)
        except PermissionError:
            # Se deja el archivo y se apunta: al montar el volcado se le
            # quitan los permisos para que leerlo dé el mismo error que aquí.
            dentro.write_bytes(b"")
            self.ilegibles.add(real)
            return
        except OSError:
            return
        dentro.write_bytes(datos)

    def _de_fuera(self, camino: str) -> None:
        """Un enlace que sale de lo volcado y acaba en un archivo.

        `/etc/os-release` apunta a `../usr/lib/os-release`. Copiar `/usr` no
        tiene sentido, así que en el sitio del enlace va el archivo.
        """
        try:
            real = sysroot.fuera(os.path.realpath(sysroot.ruta(camino)))
        except OSError:
            # Python 3.10 deja escapar el error de leer un enlace que no se
            # deja leer (`/proc/1/exe`); los posteriores lo tragan.
            return
        if real.startswith(VIGILADO) or not os.path.isfile(sysroot.ruta(real)):
            return
        try:
            with open(sysroot.ruta(real), "rb") as origen:
                datos = origen.read(TOPE)
        except OSError:
            return
        dentro = self._dentro(camino)
        if dentro.is_symlink():
            dentro.unlink()
        dentro.parent.mkdir(parents=True, exist_ok=True)
        dentro.write_bytes(datos)

    def directorio(self, camino: str) -> None:
        real = self.camino(camino)
        if real is None or not os.path.isdir(sysroot.ruta(real)):
            return
        dentro = self._dentro(real)
        dentro.mkdir(parents=True, exist_ok=True)
        try:
            entradas = os.listdir(sysroot.ruta(real))
        except OSError:
            return
        for nombre in entradas:
            hijo = os.path.join(real, nombre)
            if os.path.islink(sysroot.ruta(hijo)):
                self._enlace(hijo)
            elif os.path.isdir(sysroot.ruta(hijo)):
                (dentro / nombre).mkdir(exist_ok=True)
            # Los archivos de un directorio recorrido y no leídos no se
            # copian: no los mira nadie, y en /proc serían miles.


# -- anonimizar -----------------------------------------------------------------

def _texto(ruta: pathlib.Path) -> str | None:
    try:
        datos = ruta.read_bytes()
    except OSError:
        return None
    if b"\x00" in datos:
        return None
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _edid_sin_serie(datos: bytes) -> bytes:
    """El EDID con el número de serie a ceros y la suma de control al día."""
    if len(datos) < 128 or datos[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return datos
    bloque = bytearray(datos[:128])
    bloque[12:16] = b"\x00\x00\x00\x00"
    for inicio in range(54, 126, 18):
        if bloque[inicio:inicio + 3] == b"\x00\x00\x00" and bloque[inicio + 3] == 0xFF:
            bloque[inicio + 5:inicio + 18] = b"0" * 13
    bloque[127] = (-sum(bloque[:127])) % 256
    return bytes(bloque) + datos[128:]


# Dónde lleva el SPD el número de serie del módulo, según el tipo de memoria
# (byte 2). Ninguna suma de control lo cubre: la de DDR4 acaba en el 253 y la
# de DDR5 en el 509. silux no lo decodifica, y por eso ni la foto ni el
# comprobador lo verían: se borra aquí, por posición.
SERIE_SPD = {0x0C: (325, 329), 0x12: (517, 521)}


def _spd_sin_serie(datos: bytes) -> tuple[bytes, bytes]:
    """El SPD con el número de serie a ceros, y el número que se quitó."""
    if len(datos) < 3 or datos[2] not in SERIE_SPD:
        return datos, b""
    inicio, fin = SERIE_SPD[datos[2]]
    if len(datos) < fin:
        return datos, b""
    return datos[:inicio] + bytes(fin - inicio) + datos[fin:], datos[inicio:fin]


# Las interfaces que una herramienta crea en serie: Docker, un puente por red
# y un `veth` por contenedor en marcha. Dicen cuánto hay montado en la máquina
# y no añaden nada al volcado: de cada familia se queda una.
EN_SERIE = (re.compile(r"br-[0-9a-f]{12}"), re.compile(r"veth[0-9a-f]+"))


# An ATA IDENTIFY's words that identify the piece: serial number, WWN and
# media serial number.
IDENTIFY_SERIE = (*range(10, 20), *range(108, 112), *range(176, 206))


def _identify_sin_serie(texto: str) -> tuple[str, str]:
    """`ata_device/*/id` with its serial words at zero, and the serial.

    The model stays: it is what says the unit of the disk's counters.
    """
    try:
        palabras = [int(p, 16) for p in texto.split()]
    except ValueError:
        return re.sub(r"[0-9a-fA-F]", "0", texto), ""
    serie = b"".join(palabras[i].to_bytes(2, "big") for i in range(10, 20)
                     if i < len(palabras)).decode("ascii", "replace").strip()
    for i in IDENTIFY_SERIE:
        if i < len(palabras):
            palabras[i] = 0
    lineas = [" ".join(f"{p:04x}" for p in palabras[i:i + 8]) for i in range(0, len(palabras), 8)]
    return "\n".join(lineas) + "\n", serie


def _tarjetas_sin_nombre(texto: str) -> str:
    """`/proc/asound/cards` sin el nombre de los aparatos de sonido USB.

    Cada tarjeta son dos renglones. De las USB se deja que lo son y por dónde
    cuelgan, y se quita cómo se llaman; las de la placa y la gráfica se quedan
    como están, que no identifican a nadie.
    """
    lineas = texto.splitlines()
    salida = []
    for primera, segunda in zip(lineas[::2], lineas[1::2]):
        if "USB-Audio" in primera:
            primera = primera.split("USB-Audio", 1)[0] + "USB-Audio - "
            segunda = re.sub(r"^(\s*).*?( at usb-)", r"\1Audio USB\2", segunda)
        salida += [primera, segunda]
    return "\n".join(salida) + "\n"


def _sobrantes(nombres) -> set[str]:
    """De cada familia de interfaces en serie, todas menos la primera."""
    nombres = list(nombres)
    sobran: set[str] = set()
    for patron in EN_SERIE:
        sobran.update(sorted(n for n in nombres if patron.fullmatch(n))[1:])
    return sobran


def _ipv4_hex(ip: str) -> str:
    """Una dirección como la escribe /proc/net/route: hexadecimal al revés."""
    return "".join(f"{int(x):02X}" for x in reversed(ip.split(".")))


# What the dumper itself writes in place of something, as it writes it: the
# router and its network in /proc/net/route, the IPv6 in if_inet6.
SUSTITUTOS_HEX = frozenset(s.lower() for s in (
    _ipv4_hex(privacidad.PUERTA), _ipv4_hex(privacidad.PUERTA.rsplit(".", 1)[0] + ".0"),
    "20010db8" + "0" * 20 + "0011", CORREO_SUSTITUTO))


# What kind of thing each looked-for value is: the annex says it in words
# (`render.annex_what`), never the value.
QUE = {
    "email": "una dirección de correo", "serial": "un número de serie",
    "disk_serial": "el número de serie de un disco",
    "monitor_serial": "el número de serie de un monitor",
    "memory_serial": "el número de serie de un módulo de memoria",
    "mac": "una dirección física de red", "usb": "el nombre de algo enchufado por USB",
    "camera": "el nombre de una cámara", "router": "la dirección del router",
    "ip": "una dirección IP de este equipo", "ipv6": "una dirección IPv6 de este equipo",
    "gpu_id": "el identificador de una gráfica", "interface": "el nombre de una conexión de red",
    "machine": "un dato de este equipo",
}


class _Anonimizador:
    def __init__(self, destino: pathlib.Path, grabado: dict):
        self.destino = destino
        self.grabado = grabado
        # Lo que se quitó, por su clase (`QUE`), para buscarlo al final.
        self.secretos: dict[str, str] = {}
        # Lo quitado de un archivo binario, que no se busca como texto.
        self.crudos: dict[bytes, str] = {}
        nombre = pathlib.Path(sysroot.ruta("/proc/sys/kernel/hostname"))
        self.equipo = nombre.read_text().strip() if nombre.is_file() else ""
        # A machine named as everyone's (the distribution, the brand): it is
        # neither replaced in the texts nor looked for.
        if privacidad.equipo_de_todos(self.equipo, privacidad.palabras_del_equipo(str(destino))):
            self.equipo = ""
        self.usuario = getpass.getuser()
        self.casa = str(pathlib.Path.home())
        self.interfaces = self._interfaces()
        # El nombre que alguien le puso a una interfaz es suyo: además de
        # sustituirlo donde se sabe que sale, se busca al final en cada byte.
        for viejo in self.interfaces:
            self._secreto(viejo, "mac" if privacidad.MAC_EN_EL_NOMBRE.fullmatch(viejo)
                          else "interface")
        self.montajes: dict[str, str] = {}

    def _secreto(self, valor: Optional[str], que: str) -> None:
        """Lo que se quitó, para buscarlo después en cada byte. Lo que es un
        sustituto no: una puerta de enlace de verdad puede ser 192.168.1.1, y
        encontrarla al final era encontrar el sustituto (el primer anexo de un
        portátil con Wi-Fi no salió por eso)."""
        valor = (valor or "").strip()
        if len(valor) >= 4 and not privacidad.es_sustituto(valor) \
                and valor.lower() not in SUSTITUTOS_HEX:
            self.secretos.setdefault(valor, que)

    def _interfaces(self) -> dict[str, str]:
        nombres = {}
        red = self.destino / "sys" / "class" / "net"
        entradas = sorted(e.name for e in red.iterdir()) if red.is_dir() else []
        for entrada in entradas:
            if not privacidad.de_sistema(entrada):
                nombres[entrada] = privacidad.INTERFAZ.format(len(nombres) + 1)
        # A USB adapter's name carries its MAC: the same substitute the report
        # gives it, in the same order.
        con_mac = [e for e in entradas if privacidad.MAC_EN_EL_NOMBRE.fullmatch(e)]
        for orden, entrada in enumerate(con_mac):
            if (nuevo := privacidad.nombre_sin_mac(entrada, orden)) != entrada:
                nombres[entrada] = nuevo
        return nombres

    def en_serie(self) -> int:
        """Quita las interfaces en serie que sobran, y dice cuántas eran.

        De todas partes: su carpeta, su enlace, sus líneas en las tablas de
        `/proc/net` y lo que se grabó de ellas.
        """
        red = self.destino / "sys" / "class" / "net"
        if not red.is_dir():
            return 0
        sobran = _sobrantes(e.name for e in red.iterdir())
        for nombre in sobran:
            enlace = red / nombre
            carpeta = enlace.resolve()
            if enlace.is_symlink():
                enlace.unlink()
            if carpeta.is_dir() and self.destino in carpeta.parents:
                shutil.rmtree(carpeta)
        for tabla in ("route", "if_inet6"):
            for ruta in (self.destino / "proc").glob(f"*/net/{tabla}"):
                if ruta.is_symlink() or not ruta.is_file():
                    continue
                lineas = ruta.read_text().splitlines()
                ruta.write_text("".join(
                    linea + "\n" for linea in lineas if not sobran.intersection(linea.split())))
        direcciones = self.grabado.get("ioctl_red")
        if isinstance(direcciones, dict):
            for clave in [c for c in direcciones if c.partition(":")[0] in sobran]:
                del direcciones[clave]
        return len(sobran)

    def _cambiar_texto(self, texto: str) -> str:
        for viejo, nuevo in self.interfaces.items():
            texto = re.sub(rf"(?<![\w.-]){re.escape(viejo)}(?![\w.-])", nuevo, texto)
        texto = privacidad._sin_el_equipo(texto, self.equipo) or texto
        texto = texto.replace(self.casa, "/home/usuario")
        if len(self.usuario) >= 3:
            texto = re.sub(rf"(?<![\w.-]){re.escape(self.usuario)}(?![\w.-])", "usuario", texto)
        texto = MAC.sub(lambda m: m.group(0) if m.group(0) in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")
                        else privacidad.MAC, texto)
        texto = UUID.sub("00000000-0000-0000-0000-000000000000", texto)
        # An address, wherever it is: /proc/version names whoever built the
        # kernel, and a kernel compiled at home names its owner. The same
        # rule as the checker that runs before publishing.
        def correo(m: re.Match) -> str:
            if privacidad.CORREOS_PERMITIDOS.search(m.group()):
                return m.group()
            self._secreto(m.group(), "email")
            return CORREO_SUSTITUTO
        return privacidad.CORREO.sub(correo, texto)

    def _montaje(self, punto: str) -> str:
        if punto in privacidad._MONTAJES_DEL_SISTEMA:
            return punto
        return self.montajes.setdefault(punto, privacidad.MONTAJE.format(len(self.montajes) + 1))

    def contenidos(self) -> None:
        modelos = {(_texto(m) or "").strip().lower() for m in self.destino.rglob("model")
                   if m.is_file() and not m.is_symlink()}
        for ruta in sorted(self.destino.rglob("*")):
            if ruta.is_symlink() or not ruta.is_file():
                continue
            nombre = ruta.name
            relativo = "/" + str(ruta.relative_to(self.destino))
            datos = ruta.read_bytes()
            if nombre in SERIALES and datos.strip():
                self._secreto(datos.strip().decode(errors="replace"), "serial")
                ruta.write_bytes(re.sub(rb"[^\n\x00]", b"0", datos))
                continue
            if nombre == "id" and "/ata_device/" in relativo:
                limpio, serie = _identify_sin_serie(datos.decode(errors="replace"))
                if serie:
                    self._secreto(serie, "disk_serial")
                ruta.write_text(limpio)
                continue
            if nombre == "edid":
                if len(datos) >= 16 and any(datos[12:16]):
                    self.crudos[datos[12:16]] = "monitor_serial"
                ruta.write_bytes(_edid_sin_serie(datos))
                continue
            if nombre == "eeprom":
                limpio, serie = _spd_sin_serie(datos)
                if any(serie):
                    self.crudos[serie] = "memory_serial"
                ruta.write_bytes(limpio)
                continue
            if nombre in DIRECCIONES and "/net/" in relativo:
                if datos.strip() and datos.strip() not in (b"00:00:00:00:00:00",):
                    self._secreto(datos.strip().decode(errors="replace"), "mac")
                    ruta.write_text(privacidad.MAC + "\n")
                continue
            # Lo enchufado. El inventario de alguien también lo señala: una
            # llave de seguridad, un micrófono concreto. Del USB quedan la
            # clase, la velocidad y de qué cuelga cada cosa, que es lo que
            # los tests necesitan; la marca, el modelo y sus identificadores
            # se quitan, y con ellos el nombre del adaptador Bluetooth, que
            # sale del mismo archivo. Es lo mismo que hace
            # `privacidad.anonimizar` con la foto, y por eso el archivo se
            # borra en vez de rellenarse: el proveedor tiene que leer «nada».
            # The maker goes too, but is not looked for afterwards: it is a
            # company, and «Realtek» or «Generic» are also the sound codec,
            # the PHY or the HDA card.
            if nombre in USB_QUE_IDENTIFICA and re.search(r"/usb\d+/", relativo):
                texto_usb = datos.decode(errors="replace").strip()
                # A USB stick's name is also its disk's model, which the dump
                # keeps as any disk's (and the report shows): not looked for.
                if nombre == "product" and len(texto_usb) >= 6 \
                        and not USB_GENERICO.search(texto_usb) \
                        and texto_usb.lower() not in modelos:
                    self._secreto(texto_usb, "usb")
                ruta.unlink()
                continue
            if relativo.startswith("/sys/") and "/video4linux/" in relativo and nombre == "name":
                if len(datos.strip()) >= 6:
                    self._secreto(datos.decode(errors="replace").strip().split(":")[0], "camera")
                ruta.unlink()
                continue
            if relativo == "/proc/asound/cards":
                ruta.write_text(_tarjetas_sin_nombre(datos.decode(errors="replace")))
                continue
            if relativo == "/proc/sys/kernel/hostname":
                ruta.write_text(privacidad.EQUIPO + "\n")
                continue
            if relativo == "/proc/cmdline":
                # The disks' UUIDs, an encrypted volume, the machine's name.
                ruta.write_text(" ".join(privacidad.hide_cmdline_identifiers(
                    datos.decode(errors="replace"))) + "\n")
                continue
            # /proc/net es un enlace a self/net: el archivo de verdad acaba en
            # /proc/<pid>/net/, así que se reconoce por cómo termina.
            if relativo.startswith("/proc/") and relativo.endswith("/net/route"):
                ruta.write_text(self._cambiar_texto(self._ruta_de_red(datos.decode())))
                continue
            if relativo.startswith("/proc/") and relativo.endswith("/net/if_inet6"):
                ruta.write_text(self._cambiar_texto(self._ipv6(datos.decode())))
                continue
            if relativo.startswith("/proc/") and relativo.endswith("/mounts"):
                ruta.write_text(self._cambiar_texto(self._mounts(datos.decode())))
                continue
            texto = _texto(ruta)
            if texto is not None:
                cambiado = self._cambiar_texto(texto)
                if cambiado != texto:
                    ruta.write_text(cambiado)

    def _ruta_de_red(self, texto: str) -> str:
        lineas = texto.splitlines()
        salida = lineas[:1]
        for linea in lineas[1:]:
            campos = linea.split("\t")
            if len(campos) > 2:
                if campos[1] != "00000000":
                    campos[1] = _ipv4_hex(privacidad.PUERTA.rsplit(".", 1)[0] + ".0")
                if campos[2] != "00000000":
                    self._secreto(campos[2], "router")
                    campos[2] = _ipv4_hex(privacidad.PUERTA)
            salida.append("\t".join(campos))
        return "\n".join(salida) + "\n"

    def _ipv6(self, texto: str) -> str:
        # privacidad.IPV6, 2001:db8::11, en los 32 dígitos de /proc/net/if_inet6.
        sustituta = "20010db8" + "0" * 20 + "0011"
        salida = []
        for linea in texto.splitlines():
            campos = linea.split()
            if campos and campos[0] != "0" * 31 + "1":
                self._secreto(campos[0], "ipv6")
                linea = linea.replace(campos[0], sustituta, 1)
            salida.append(linea)
        return "\n".join(salida) + "\n"

    def _mounts(self, texto: str) -> str:
        """Los montajes de los discos, con los puntos que puso alguien tapados.

        Solo se quedan las líneas de un dispositivo, que son las que lee el
        proveedor. Las demás no describen el equipo sino la sesión: el
        AppImage abierto, los contenedores, la carpeta del usuario.
        """
        salida = []
        for linea in texto.splitlines():
            campos = linea.split(" ")
            if not campos[0].startswith("/dev/"):
                continue
            if len(campos) > 1:
                punto = campos[1].replace("\\040", " ")
                nuevo = self._montaje(punto)
                if nuevo != punto:
                    campos[1] = nuevo
            salida.append(" ".join(campos))
        return "\n".join(salida) + "\n"

    def nombres(self) -> None:
        """Las interfaces con nombre propio, también en carpetas y enlaces."""
        if not self.interfaces:
            return
        for ruta in sorted(self.destino.rglob("*"), key=lambda r: -len(r.parts)):
            if ruta.is_symlink():
                destino = os.readlink(ruta)
                nuevo = self._cambiar_texto(destino)
                if nuevo != destino:
                    ruta.unlink()
                    os.symlink(nuevo, ruta)
            if ruta.name in self.interfaces:
                ruta.rename(ruta.with_name(self.interfaces[ruta.name]))

    def grabado_limpio(self) -> dict:
        # NVML's UUID («GPU-» and a UUID) names the card. The rule for UUIDs
        # zeroed its UUID and left «GPU-», which anonimizar still covered: a
        # laptop with an awake NVIDIA had no annex. It goes as anonimizar
        # leaves it, and the real one is looked for in every byte.
        for tarjeta in (self.grabado.get("nvml") or {}).get("tarjetas") or ():
            if isinstance(tarjeta, dict) and tarjeta.get("uuid"):
                self._secreto(tarjeta["uuid"], "gpu_id")
                self._secreto(tarjeta["uuid"].removeprefix("GPU-"), "gpu_id")
        limpio = json.loads(self._cambiar_texto(json.dumps(self.grabado, ensure_ascii=False)))
        for tarjeta in (limpio.get("nvml") or {}).get("tarjetas") or ():
            if isinstance(tarjeta, dict) and tarjeta.get("uuid"):
                tarjeta["uuid"] = privacidad._tapar(tarjeta["uuid"])
        for clave in list(limpio.get("ioctl_red", {})):
            valor = limpio["ioctl_red"][clave]
            nombre, _sep, codigo = clave.partition(":")
            if valor and codigo == "0x8915" and not valor.startswith("127."):
                self._secreto(valor, "ip")
                limpio["ioctl_red"][clave] = privacidad.IPV4
        if "statvfs" in limpio:
            limpio["statvfs"] = {self._montaje(p): v for p, v in limpio["statvfs"].items()}
        entorno = limpio.get("plataforma", {}).get("uname")
        if isinstance(entorno, dict) and entorno.get("node"):
            entorno["node"] = privacidad.EQUIPO
        return limpio


# -- comprobar ------------------------------------------------------------------

# Looked for as a word and not inside another: a machine's or a
# connection's name is part of driver names (a «thinkpad» in thinkpad_hwmon
# blocked an annex), and an IP is the start of a longer one. A serial number
# is looked for anywhere.
COMO_PALABRA = frozenset({"machine_name", "interface", "usb", "ip"})
_ALREDEDOR = rb"[A-Za-z0-9_.-]"


def _clase_propia(descripcion: str) -> str:
    """The kind of one of `privacidad.de_esta_maquina`'s identifiers."""
    if descripcion == "el nombre de este equipo":
        return "machine_name"
    if "interfaz" in descripcion:
        return "interface"
    if "IPv4" in descripcion:
        return "ip"
    return "machine"


def encontrados(destino: pathlib.Path, secretos, crudos=(),
                propios: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Where something of this machine is in the dump: (path, kind), the
    kinds of `QUE`. Empty if nothing.

    `secretos` and `crudos`, what the dumper took away (a dict by kind, or
    any collection); `propios`, what identifies this machine, without which
    `privacidad.de_esta_maquina`'s. A substitute is never looked for.
    """
    if propios is None:
        propios = privacidad.de_esta_maquina()
    por_clase = lambda grupo, clase: (grupo.items() if isinstance(grupo, dict)
                                      else ((g, clase) for g in grupo))
    buscados: list[tuple[bytes, str]] = []
    for valor, clase in [*((d, _clase_propia(q)) for d, q in propios.items()),
                         *por_clase(secretos, "machine")]:
        if valor and len(valor) >= 4 and not privacidad.es_sustituto(valor):
            buscados.append((valor.encode(), clase))
    buscados += [(c, clase) for c, clase in por_clase(crudos, "serial") if any(c)]
    patrones = [(re.compile(rb"(?<!" + _ALREDEDOR + rb")" + re.escape(b) + rb"(?!" + _ALREDEDOR + rb")")
                 if clase in COMO_PALABRA else None, b, clase) for b, clase in buscados]
    hallazgos = []
    for ruta in sorted(destino.rglob("*")):
        if ruta.is_symlink():
            contenido = os.readlink(ruta).encode()
        elif ruta.is_file():
            contenido = ruta.read_bytes()
        else:
            contenido = b""
        relativa = str(ruta.relative_to(destino))
        for patron, crudo, clase in patrones:
            for donde in (contenido, relativa.encode()):
                if (patron.search(donde) if patron is not None else crudo in donde):
                    hallazgos.append((relativa, clase, patron or crudo))
                    break
    return hallazgos


def comprobar(destino: pathlib.Path, secretos, crudos=(),
              propios: dict[str, str] | None = None) -> list[str]:
    """Lo que delata a esta máquina dentro del volcado, en palabras. Vacío si nada."""
    return [f"{ruta}: {QUE.get(clase, clase)}"
            for ruta, clase, _buscado in encontrados(destino, secretos, crudos, propios)]


class Rechazo(SystemExit):
    """Nothing is written: anonimizar would still cover these fields of the
    photo. They are named by position («gpus[1].unique_id»), never by value."""

    def __init__(self, campos: list[str]):
        self.campos = list(campos)
        super().__init__("anonimizar todavía encuentra qué tapar: "
                         + "; ".join(self.campos[:10]) + ". No se escribe nada.")


def _esta(buscado, texto: str) -> bool:
    datos = texto.encode()
    return bool(buscado.search(datos)) if isinstance(buscado, re.Pattern) else buscado in datos


def _json_sin(dato, buscado, ruta: str = "") -> tuple[object, list[str]]:
    """The JSON without what holds `buscado`: a string goes to None, a key or
    a list item goes. And where it was, as a path of keys."""
    if isinstance(dato, dict):
        salida, quitados = {}, []
        for clave, valor in dato.items():
            camino = f"{ruta}.{clave}" if ruta else str(clave)
            if _esta(buscado, str(clave)):
                quitados.append(camino)
                continue
            salida[clave], dentro = _json_sin(valor, buscado, camino)
            quitados += dentro
        return salida, quitados
    if isinstance(dato, list):
        salida, quitados = [], []
        for i, valor in enumerate(dato):
            if isinstance(valor, str) and _esta(buscado, valor):
                quitados.append(f"{ruta}[{i}]")
                continue
            limpio, dentro = _json_sin(valor, buscado, f"{ruta}[{i}]")
            salida.append(limpio)
            quitados += dentro
        return salida, quitados
    if isinstance(dato, str) and _esta(buscado, dato):
        return None, [ruta]
    return dato, []


def _sin_lo_encontrado(trabajo: pathlib.Path, hallazgos) -> list[dict]:
    """Takes away what could not be covered safely, instead of writing
    nothing: the file, or in the two JSON files the answer that holds it.
    Says what each was, by kind."""
    quitados: list[dict] = []
    for relativa, clase, buscado in hallazgos:
        ruta = trabajo / relativa
        if relativa in (sysroot.GRABADO, MANIFIESTO) and ruta.is_file():
            limpio, caminos = _json_sin(json.loads(ruta.read_text()), buscado)
            ruta.write_text(json.dumps(limpio, ensure_ascii=False, indent=1,
                                       sort_keys=relativa == sysroot.GRABADO) + "\n")
            quitados += [{"ruta": f"{relativa}: {c}", "dato": clase} for c in caminos]
            continue
        if ruta.is_symlink() or ruta.is_file():
            ruta.unlink()
        elif ruta.is_dir():
            shutil.rmtree(ruta)
        else:
            continue
        quitados.append({"ruta": "/" + relativa, "dato": clase})
    return quitados


@contextlib.contextmanager
def montado(carpeta: pathlib.Path):
    """El volcado listo para leer: una copia con los ilegibles sin permiso."""
    with tempfile.TemporaryDirectory(prefix="silux-equipo-") as tmp:
        copia = pathlib.Path(tmp) / "raiz"
        shutil.copytree(carpeta, copia, symlinks=True)
        manifiesto = json.loads((copia / MANIFIESTO).read_text())
        for vacio in manifiesto.get("vacios", []):
            (copia / vacio.lstrip("/")).mkdir(parents=True, exist_ok=True)
        for ilegible in manifiesto.get("ilegibles", []):
            camino = copia / ilegible.lstrip("/")
            if camino.exists():
                camino.chmod(0)
        anterior = os.environ.get(sysroot.VARIABLE)
        os.environ[sysroot.VARIABLE] = str(copia)
        sysroot.olvidar()
        try:
            yield copia
        finally:
            for ilegible in manifiesto.get("ilegibles", []):
                camino = copia / ilegible.lstrip("/")
                if camino.exists():
                    camino.chmod(0o600)
            if anterior is None:
                os.environ.pop(sysroot.VARIABLE, None)
            else:
                os.environ[sysroot.VARIABLE] = anterior
            sysroot.olvidar()


def foto_de(carpeta: pathlib.Path):
    """La foto que da el Collector leyendo el volcado."""
    from silux.collector import Collector

    with montado(carpeta):
        recolector = Collector()
        try:
            recolector.snapshot()
            return recolector.snapshot()
        finally:
            recolector.close()


# -- principal ------------------------------------------------------------------

def volcar(nombre: str, destino_base: pathlib.Path,
           propios: dict[str, str] | None = None) -> pathlib.Path:
    destino = destino_base / nombre
    if destino.exists():
        raise SystemExit(f"ya existe {destino}: bórralo antes para volcar otra vez")

    # Lo primero, antes de que nada la despierte: cómo está cada gráfica.
    dormidas = _Dormidas()
    leidos, listados, mirados, grabado = _recoger(dormidas)
    leidos |= _alternativas(leidos) | dormidas.energia() | _extras_de_graficas()
    # Copiar también es leer: lo de una gráfica dormida no pasa ni por aquí.
    leidos = {c for c in leidos if not dormidas.prohibido(c)}
    mirados = {c for c in mirados if not dormidas.prohibido(c)}
    with tempfile.TemporaryDirectory(prefix="silux-volcado-") as tmp:
        trabajo = pathlib.Path(tmp) / nombre
        trabajo.mkdir()
        copia = _Copia(trabajo)
        for camino in sorted(listados):
            copia.directorio(camino)
        for camino in sorted(leidos):
            copia.archivo(camino)
        for camino in sorted(mirados - leidos - listados):
            # Un `exists()` o un `is_dir()` que salió que sí: que siga saliendo.
            if os.path.lexists(sysroot.ruta(camino)):
                (copia.directorio(camino) if os.path.isdir(sysroot.ruta(camino))
                 else copia.archivo(camino))

        limpio = _Anonimizador(trabajo, grabado)
        quitadas = limpio.en_serie()
        limpio.contenidos()
        limpio.nombres()
        (trabajo / sysroot.GRABADO).write_text(
            json.dumps(limpio.grabado_limpio(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")

        # Git no guarda directorios vacíos, y algunos cuentan: los procesos de
        # /proc, o un /sys/firmware/efi que solo se mira si existe. Se apuntan
        # y se recrean al montar.
        vacios = sorted("/" + str(d.relative_to(trabajo)) for d in trabajo.rglob("*")
                        if d.is_dir() and not d.is_symlink() and not any(d.iterdir()))
        (trabajo / MANIFIESTO).write_text(json.dumps({
            "herramienta": 1,
            "vacios": vacios,
            "ilegibles": sorted(limpio._cambiar_texto(c) for c in copia.ilegibles),
            # Cómo estaba cada gráfica antes de leer nada, por su ranura.
            "energia_de_las_graficas": dormidas.estados,
            "sin_grabar": [
                "de NVML, el número de serie de cada tarjeta",
                "todo lo que lee el ayudante privilegiado",
                "el uso de cada hilo: sale de restar dos lecturas de /proc/stat, "
                "y el volcado guarda una",
                "el consumo (RAPL): sale de restar dos lecturas del contador de "
                "energía, y el volcado guarda una",
                "la residencia en los estados de reposo (C-states): sale de restar "
                "dos lecturas de cpuidle, y el volcado guarda una",
                "de lo enchufado por USB: la marca, el modelo y sus identificadores; "
                "y el nombre de las cámaras y de las tarjetas de sonido USB. "
                "Quedan la clase, la velocidad y de qué cuelga cada cosa",
                "las variables del cargador de arranque que no se leen "
                "(LoaderDevicePartUUID, LoaderSystemToken)",
            ] + dormidas.sin_grabar() + ([f"{quitadas} interfaces de red en serie (puentes de Docker y "
                  "veth): queda una de cada"] if quitadas else []),
        }, ensure_ascii=False, indent=1) + "\n")

        # What was not covered goes, file by file, and the annex says so: a
        # dump with a file less is still a dump, and with nothing written
        # three of three testers had no annex.
        quitados = _sin_lo_encontrado(
            trabajo, encontrados(trabajo, limpio.secretos, limpio.crudos, propios))
        if quitados:
            manifiesto = json.loads((trabajo / MANIFIESTO).read_text())
            manifiesto["quitados"] = quitados
            (trabajo / MANIFIESTO).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n")
        foto = foto_de(trabajo)
        if quedan := _lo_que_anonimizar_taparia(foto):
            raise Rechazo(quedan)
        if hallazgos := comprobar(trabajo, limpio.secretos, limpio.crudos, propios):
            raise SystemExit("El volcado delata a esta máquina; no se escribe nada:\n  "
                             + "\n  ".join(hallazgos[:20]))

        manifiesto = json.loads((trabajo / MANIFIESTO).read_text())
        cpu = foto.cpu.types[0].brand if foto.cpu.types else None
        manifiesto.update(cpu=cpu, kernel=foto.system.kernel if foto.system else None,
                          gpus=[g.name for g in foto.gpus], fuentes=sorted(foto.capabilities))
        (trabajo / MANIFIESTO).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n")
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(trabajo, destino, symlinks=True)
    return destino


# Lo que `anonimizar` sustituye aunque no identifique a nadie: el bucle local
# y una MAC a ceros. Que lo cambie no significa que el volcado se lo dejara.
INOFENSIVOS = {"127.0.0.1", "::1", "00:00:00:00:00:00", None, ()}
YA_SUSTITUIDO = re.compile(re.escape(privacidad.MONTAJE).replace(r"\{\}", r"\d+"))


def _sin_numerar(discos):
    """Los discos con los montajes ya sustituidos sin su número.

    `anonimizar` numera por el orden de los discos y el volcado por el de
    `/proc/mounts`: un `/media/unidad3` que pasa a `/media/unidad1` no es un
    dato que quedara por tapar.
    """
    return tuple(
        dataclasses.replace(d, partitions=tuple(
            dataclasses.replace(p, mountpoint=privacidad.MONTAJE.format(""))
            if p.mountpoint and YA_SUSTITUIDO.fullmatch(p.mountpoint) else p
            for p in d.partitions))
        for d in discos)


def _diferencias(antes, despues, ruta: str) -> list[str]:
    """Where two values differ, as field paths («gpus[1].unique_id»): what
    the refusal says, without the value, which is what it protects."""
    if antes == despues:
        return []
    if (dataclasses.is_dataclass(antes) and type(antes) is type(despues)):
        return [d for campo in dataclasses.fields(antes)
                for d in _diferencias(getattr(antes, campo.name), getattr(despues, campo.name),
                                      f"{ruta}.{campo.name}")]
    if isinstance(antes, tuple) and isinstance(despues, tuple) and len(antes) == len(despues):
        return [d for i, (a, b) in enumerate(zip(antes, despues))
                for d in _diferencias(a, b, f"{ruta}[{i}]")]
    return [ruta]


def _lo_que_anonimizar_taparia(foto) -> list[str]:
    """Lo que `privacidad.anonimizar` cambiaría en la foto del volcado.

    Si cambia algo, es que el volcado dejó un dato que identifica a alguien.
    Lo único que se acepta es lo que anonimizar tapa por sistema sin que sea
    de nadie, como `127.0.0.1`.
    """
    tapada = privacidad.anonimizar(foto)
    quedan = []
    for campo in dataclasses.fields(foto):
        antes, despues = getattr(foto, campo.name), getattr(tapada, campo.name)
        if antes == despues:
            continue
        if campo.name == "network":
            for i, j in zip(antes, despues):
                for sub in dataclasses.fields(i):
                    a, b = getattr(i, sub.name), getattr(j, sub.name)
                    restos = [x for x in (a if isinstance(a, tuple) else (a,))
                              if x not in INOFENSIVOS and x not in privacidad.SUSTITUTOS_ANTERIORES]
                    if a != b and restos:
                        # By position: the name may be what is protected.
                        quedan.append(f"network[{antes.index(i)}].{sub.name}")
            continue
        if campo.name == "disks" and _sin_numerar(antes) == _sin_numerar(despues):
            continue
        if (campo.name == "system" and antes.hostname in privacidad.SUSTITUTOS_ANTERIORES
                and dataclasses.replace(antes, hostname=despues.hostname) == despues):
            continue
        quedan += _diferencias(antes, despues, campo.name)
    return quedan
