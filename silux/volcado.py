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
from .providers.sysfs_cpu import FREQUENCY_SOURCES

WATCHED_TREES = ("/sys/", "/proc/", "/etc/")
# Un archivo de sysfs o de procfs de más de esto no es lo que se lee para
# describir un equipo; copiarlo solo engordaría el repositorio.
MAX_BYTES = 512 * 1024
MANIFEST = "manifiesto.json"

# Archivos cuyo contenido identifica a una pieza concreta y no dice nada del
# modelo: se cambian por ceros del mismo largo.
SERIAL_FILES = {"serial", "serial_number", "wwid", "vpd_pg80", "vpd_pg83",
            "unique_id", "product_uuid", "product_serial", "board_serial",
            "chassis_serial", "uuid", "eui", "nguid", "perm_addr"}
ADDRESS_FILES = {"address", "perm_address"}
# De un dispositivo USB, lo que dice de quién es y qué modelo.
USB_IDENTIFYING_FILES = {"product", "manufacturer", "idVendor", "idProduct"}
# Nombres que no señalan a nadie: los de un concentrador o un controlador.
USB_GENERIC = re.compile(r"hub|host controller|usb\s*receiver", re.I)
MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
EMAIL_SUBSTITUTE = "usuario@example.org"
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
IDENTITY_FILES = ("vendor", "device", "subsystem_vendor", "subsystem_device",
             "revision", "class")
POWER_FILES = ("power/runtime_status", "power_state", "power/control")
NO_WAKE_FILES = IDENTITY_FILES + POWER_FILES
# `runtime_status` y `power_state` cuando la tarjeta duerme.
SUSPENDED = ("suspended",)
POWERED_OFF = ("D3hot", "D3cold")

def _read(path) -> str | None:
    try:
        return pathlib.Path(sysroot.path(str(path))).read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _resolved(path) -> pathlib.Path:
    """El camino sin enlaces, como lo vería el sistema."""
    return pathlib.Path(sysroot.unrooted(pathlib.Path(sysroot.path(str(path))).resolve()))


def power_state(device) -> dict[str, str]:
    """El estado de energía de un dispositivo PCI. No lo despierta."""
    return {name: value for name in POWER_FILES
            if (value := _read(f"{device}/{name}")) is not None}


def is_asleep(state: dict[str, str]) -> bool:
    return (state.get("power/runtime_status") in SUSPENDED
            or state.get("power_state") in POWERED_OFF)


def gpu_devices() -> list[str]:
    """Las gráficas del bus PCI (clase 0x03), tengan driver o no."""
    try:
        names = sorted(p.name for p in pathlib.Path(sysroot.path(SYS_PCI)).iterdir())
    except OSError:
        return []
    return [f"{SYS_PCI}/{n}" for n in names
            if (_read(f"{SYS_PCI}/{n}/class") or "").startswith("0x03")]


def bridge_chain(device) -> list[pathlib.Path]:
    """Los puentes por los que pasa el dispositivo hasta la raíz, sin él.

    La misma cuenta que `providers.drm._cadena_pcie`: se sube mientras la
    carpeta tenga forma de dirección PCI.
    """
    current = _resolved(device).parent
    links = []
    while re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", current.name):
        links.append(current)
        current = current.parent
    return links


# -- qué lee el Collector ------------------------------------------------------

def _watched(path) -> str | None:
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    # Con una raíz puesta (los tests), el camino se apunta como lo vería el
    # sistema: es el que se copia después.
    text = sysroot.unrooted(text)
    return text if text.startswith(WATCHED_TREES) else None


# Where Python 3.10's pathlib keeps its own copy of these: it took them from
# os and io when imported (`_NormalAccessor`) and, unlike 3.11, does not look
# them up again. Patching os and io alone missed everything the providers
# read, list and look at with pathlib, and let it past the sleeping card's
# guard.
_VIA_PATHLIB = {"open": (io, builtins), "listdir": (os,), "scandir": (os,),
                "stat": (os,), "lstat": (os,), "readlink": (os,)}


def _with_pathlib(patches: dict) -> dict:
    """Los mismos parches, también en el `_NormalAccessor` de 3.10."""
    accessor = getattr(pathlib, "_NormalAccessor", None)
    if accessor is None:
        return patches
    every = dict(patches)
    for name, modules in _VIA_PATHLIB.items():
        function = next((patches[(m, name)] for m in modules if (m, name) in patches), None)
        if function is not None and name in vars(accessor):
            every[(accessor, name)] = staticmethod(function)
    return every


@contextlib.contextmanager
def _patching(patches: dict):
    """Pone cada función en su sitio y lo deja todo como estaba. De una clase
    se guarda lo que tiene de verdad (un `staticmethod`, un builtin), no lo
    que da `getattr`."""
    def original(owner, name):
        return vars(owner)[name] if isinstance(owner, type) else getattr(owner, name)

    patches = _with_pathlib(patches)
    originals = {key: original(*key) for key in patches}
    try:
        for (owner, name), function in patches.items():
            setattr(owner, name, function)
        yield
    finally:
        for (owner, name), function in originals.items():
            setattr(owner, name, function)


@contextlib.contextmanager
def _noting():
    """Apunta qué toca el Collector: archivos, directorios, `stat` y enlaces."""
    read_paths: set[str] = set()
    listed: set[str] = set()
    checked: set[str] = set()

    def note(bucket, function):
        def wrapped(path, *args, **kwargs):
            if (text := _watched(path)) is not None:
                bucket.add(text)
            return function(path, *args, **kwargs)
        return wrapped

    patches = {
        (builtins, "open"): note(read_paths, builtins.open),
        (io, "open"): note(read_paths, io.open),
        (os, "listdir"): note(listed, os.listdir),
        (os, "scandir"): note(listed, os.scandir),
        (os, "stat"): note(checked, os.stat),
        (os, "lstat"): note(checked, os.lstat),
        (os, "readlink"): note(checked, os.readlink),
    }
    with _patching(patches):
        yield read_paths, listed, checked


class _SleepingCards:
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
        self.states: dict[str, dict[str, str]] = {}
        self.asleep: list[str] = []
        self.nodes: list[str] = []
        self.dev: set[str] = set()
        self.nvidia = False
        for gpu in gpu_devices():
            state = power_state(gpu)
            slot = gpu.rsplit("/", 1)[1]
            self.states[slot] = state
            if not is_asleep(state):
                continue
            self.asleep.append(slot)
            real_path = _resolved(gpu)
            siblings = [f"{real_path.parent}/{h.name}"
                        for h in pathlib.Path(sysroot.path(str(real_path.parent))).iterdir()
                        if h.name.rsplit(".", 1)[0] == slot.rsplit(".", 1)[0]]
            self.nodes += siblings + [str(p) for p in bridge_chain(gpu)]
            drm = pathlib.Path(sysroot.path(f"{real_path}/drm"))
            if drm.is_dir():
                self.dev.update(f"/dev/dri/{n.name}" for n in drm.iterdir()
                                if n.name.startswith(("card", "renderD")))
            if _read(f"{gpu}/vendor") == "0x10de":
                self.nvidia = True
        # El más largo primero: la gráfica cuelga de sus puentes.
        self.nodes = sorted(set(self.nodes), key=len, reverse=True)

    def __bool__(self) -> bool:
        return bool(self.asleep)

    def power_files(self) -> set[str]:
        """Los archivos de energía de cada gráfica, dormida o no, para el volcado."""
        return {f"{SYS_PCI}/{slot}/{name}"
                for slot, state in self.states.items() for name in state}

    def forbidden(self, path) -> bool:
        if not self:
            return False
        text = os.fspath(path)
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        text = sysroot.unrooted(text)
        if text in self.dev:
            return True
        if not text.startswith("/sys/"):
            return False
        real_path = sysroot.unrooted(os.path.realpath(sysroot.path(text)))
        for node in self.nodes:
            if real_path.startswith(node + "/"):
                return real_path[len(node) + 1:] not in NO_WAKE_FILES
        return False

    def not_recorded(self) -> list[str]:
        if not self:
            return []
        lines = [f"de las gráficas dormidas ({', '.join(self.asleep)}), todo menos "
                  "su identidad y su estado de energía, y lo mismo de las otras "
                  "funciones de su ranura y de sus puentes: leerlo las despierta",
                  "lo que contestan OpenGL, Vulkan, OpenCL y VA-API: enumeran todas "
                  "las tarjetas, también la dormida"]
        if self.nvidia:
            lines.append("NVML: abrirla despierta la NVIDIA dormida")
        return lines


@contextlib.contextmanager
def _without_waking(sleeping: _SleepingCards | None):
    """Que el Collector no lea lo que despierta una gráfica dormida.

    Lo que se le niega lo recibe como un archivo que no existe, que es como
    lo verá al leer el volcado.
    """
    if not sleeping:
        yield
        return
    from silux import gpuapi, nvml

    def guard(function):
        def wrapped(path, *args, **kwargs):
            if sleeping.forbidden(path):
                raise FileNotFoundError(errno.ENOENT, "gráfica dormida: no se lee",
                                        os.fspath(path))
            return function(path, *args, **kwargs)
        return wrapped

    patches = {
        (builtins, "open"): guard(builtins.open),
        (io, "open"): guard(io.open),
        (os, "open"): guard(os.open),
        (gpuapi, "query"): lambda *a, **k: {},
    }
    if sleeping.nvidia:
        patches[(nvml.Nvml, "open")] = lambda self: False
    with _patching(patches):
        yield


def _collect(sleeping: _SleepingCards | None = None):
    """Ejecuta el Collector de verdad, apuntando y grabando lo que pregunta."""
    from silux.collector import Collector

    sysroot.start_recording()
    with _noting() as (read_paths, listed, checked), _without_waking(sleeping):
        collector = Collector()
        try:
            collector.snapshot()
            collector.snapshot()
        finally:
            collector.close()
    return read_paths, listed, checked, sysroot.recorded_data()


def _alternatives(read_paths: set[str]) -> set[str]:
    """Las otras fuentes de un dato que el proveedor leyó de la primera.

    La única excepción a que el Collector decida qué se copia: de la
    frecuencia de cada hilo se queda con la primera fuente que contesta y no
    abre las demás. Sin ellas, el volcado de un kernel que tiene
    `cpuinfo_avg_freq` no sirve para ver qué sale en uno que no la tiene. La
    lista es la del proveedor, no una escrita aquí.
    """
    return {os.path.join(os.path.dirname(path), source)
            for path in read_paths if os.path.basename(path) in FREQUENCY_SOURCES
            for source in FREQUENCY_SOURCES}


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
GPU_EXTRAS = ("tile*/gt*/freq0/*", "tile*/gt*/freq0/throttle/*",
                     "tile*/gt*/gtidle/*", "hwmon/hwmon*/*")
BRIDGE_EXTRAS = ("vendor", "device", "class", "current_link_speed",
                    "current_link_width", "max_link_speed", "max_link_width")
EVENT_SOURCE = "/sys/bus/event_source/devices"


def _gpu_extras() -> set[str]:
    """Los caminos de `EXTRAS_DE_GRAFICA`, de los puentes y de event_source."""
    import glob

    def existing(pattern: str) -> set[str]:
        return {sysroot.unrooted(c) for c in glob.glob(sysroot.path(pattern))
                if os.path.isfile(c)}

    paths: set[str] = set()
    for gpu in gpu_devices():
        if is_asleep(power_state(gpu)):
            continue
        real_path = str(_resolved(gpu))
        for pattern in GPU_EXTRAS:
            paths |= existing(f"{real_path}/{pattern}")
        for bridge in bridge_chain(gpu):
            for name in BRIDGE_EXTRAS:
                paths |= existing(f"{sysroot.unrooted(str(bridge))}/{name}")
    for pattern in ("*/type", "*/format/*", "*/events/*"):
        paths |= existing(f"{EVENT_SOURCE}/{pattern}")
    return paths


# -- copiar ---------------------------------------------------------------------

class _Copy:
    """Reproduce caminos del sistema dentro del volcado, con sus enlaces.

    Through `sysroot`: with a dump mounted, it dumps that one. That is how the
    dumper is tested on machines that are not this one, and on the dumps of
    the suite, whose values are already the substitutes.
    """

    def __init__(self, target: pathlib.Path):
        self.target = target
        self.unreadable: set[str] = set()

    def _inside(self, path: str) -> pathlib.Path:
        return self.target / path.lstrip("/")

    def _link(self, path: str) -> None:
        inside = self._inside(path)
        if inside.is_symlink() or inside.exists():
            return
        try:
            target = os.readlink(sysroot.path(path))
        except OSError:
            # `/proc/1/exe` sin permisos: se deja fuera, y quien lo lea recibe
            # un error igual que en el equipo de verdad.
            return
        inside.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, inside)

    def resolve(self, path: str) -> str | None:
        """Recrea cada enlace del camino y devuelve dónde está de verdad."""
        current = "/"
        for part in pathlib.PurePosixPath(path).parts[1:]:
            following = os.path.join(current, part)
            hops = 0
            while os.path.islink(sysroot.path(following)) and hops < 40:
                self._link(following)
                try:
                    target = os.readlink(sysroot.path(following))
                except OSError:
                    return None
                following = os.path.normpath(os.path.join(os.path.dirname(following), target))
                hops += 1
            if not os.path.lexists(sysroot.path(following)):
                return None
            if not following.startswith(WATCHED_TREES) and following not in ("/sys", "/proc", "/etc"):
                # Un enlace que sale del sistema (`/proc/1/exe`): basta con él.
                return None
            current = following
        return current

    def copy_file(self, path: str) -> None:
        real_path = self.resolve(path)
        if real_path is None:
            self._from_outside(path)
            return
        inside = self._inside(real_path)
        if os.path.isdir(sysroot.path(real_path)):
            inside.mkdir(parents=True, exist_ok=True)
            return
        if inside.exists():
            return
        inside.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(sysroot.path(real_path), "rb") as source:
                data = source.read(MAX_BYTES)
        except PermissionError:
            # Se deja el archivo y se apunta: al montar el volcado se le
            # quitan los permisos para que leerlo dé el mismo error que aquí.
            inside.write_bytes(b"")
            self.unreadable.add(real_path)
            return
        except OSError:
            return
        inside.write_bytes(data)

    def _from_outside(self, path: str) -> None:
        """Un enlace que sale de lo volcado y acaba en un archivo.

        `/etc/os-release` apunta a `../usr/lib/os-release`. Copiar `/usr` no
        tiene sentido, así que en el sitio del enlace va el archivo.
        """
        try:
            real_path = sysroot.unrooted(os.path.realpath(sysroot.path(path)))
        except OSError:
            # Python 3.10 deja escapar el error de leer un enlace que no se
            # deja leer (`/proc/1/exe`); los posteriores lo tragan.
            return
        if real_path.startswith(WATCHED_TREES) or not os.path.isfile(sysroot.path(real_path)):
            return
        try:
            with open(sysroot.path(real_path), "rb") as source:
                data = source.read(MAX_BYTES)
        except OSError:
            return
        inside = self._inside(path)
        if inside.is_symlink():
            inside.unlink()
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(data)

    def directory(self, path: str) -> None:
        real_path = self.resolve(path)
        if real_path is None or not os.path.isdir(sysroot.path(real_path)):
            return
        inside = self._inside(real_path)
        inside.mkdir(parents=True, exist_ok=True)
        try:
            entries = os.listdir(sysroot.path(real_path))
        except OSError:
            return
        for name in entries:
            child = os.path.join(real_path, name)
            if os.path.islink(sysroot.path(child)):
                self._link(child)
            elif os.path.isdir(sysroot.path(child)):
                (inside / name).mkdir(exist_ok=True)
            # Los archivos de un directorio recorrido y no leídos no se
            # copian: no los mira nadie, y en /proc serían miles.


# -- anonimizar -----------------------------------------------------------------

def _text_of(path: pathlib.Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _edid_without_serial(data: bytes) -> bytes:
    """El EDID con el número de serie a ceros y la suma de control al día."""
    if len(data) < 128 or data[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return data
    block = bytearray(data[:128])
    block[12:16] = b"\x00\x00\x00\x00"
    for start in range(54, 126, 18):
        if block[start:start + 3] == b"\x00\x00\x00" and block[start + 3] == 0xFF:
            block[start + 5:start + 18] = b"0" * 13
    block[127] = (-sum(block[:127])) % 256
    return bytes(block) + data[128:]


# Dónde lleva el SPD el número de serie del módulo, según el tipo de memoria
# (byte 2). Ninguna suma de control lo cubre: la de DDR4 acaba en el 253 y la
# de DDR5 en el 509. silux no lo decodifica, y por eso ni la foto ni el
# comprobador lo verían: se borra aquí, por posición.
SPD_SERIAL = {0x0C: (325, 329), 0x12: (517, 521)}


def _spd_without_serial(data: bytes) -> tuple[bytes, bytes]:
    """El SPD con el número de serie a ceros, y el número que se quitó."""
    if len(data) < 3 or data[2] not in SPD_SERIAL:
        return data, b""
    start, end = SPD_SERIAL[data[2]]
    if len(data) < end:
        return data, b""
    return data[:start] + bytes(end - start) + data[end:], data[start:end]


# Las interfaces que una herramienta crea en serie: Docker, un puente por red
# y un `veth` por contenedor en marcha. Dicen cuánto hay montado en la máquina
# y no añaden nada al volcado: de cada familia se queda una.
IN_SERIES = (re.compile(r"br-[0-9a-f]{12}"), re.compile(r"veth[0-9a-f]+"))


# An ATA IDENTIFY's words that identify the piece: serial number, WWN and
# media serial number.
IDENTIFY_SERIAL = (*range(10, 20), *range(108, 112), *range(176, 206))


def _identify_without_serial(text: str) -> tuple[str, str]:
    """`ata_device/*/id` with its serial words at zero, and the serial.

    The model stays: it is what says the unit of the disk's counters.
    """
    try:
        words = [int(p, 16) for p in text.split()]
    except ValueError:
        return re.sub(r"[0-9a-fA-F]", "0", text), ""
    serial = b"".join(words[i].to_bytes(2, "big") for i in range(10, 20)
                     if i < len(words)).decode("ascii", "replace").strip()
    for i in IDENTIFY_SERIAL:
        if i < len(words):
            words[i] = 0
    lines = [" ".join(f"{p:04x}" for p in words[i:i + 8]) for i in range(0, len(words), 8)]
    return "\n".join(lines) + "\n", serial


def _cards_without_names(text: str) -> str:
    """`/proc/asound/cards` sin el nombre de los aparatos de sonido USB.

    Cada tarjeta son dos renglones. De las USB se deja que lo son y por dónde
    cuelgan, y se quita cómo se llaman; las de la placa y la gráfica se quedan
    como están, que no identifican a nadie.
    """
    lines = text.splitlines()
    out = []
    for first, second in zip(lines[::2], lines[1::2]):
        if "USB-Audio" in first:
            first = first.split("USB-Audio", 1)[0] + "USB-Audio - "
            second = re.sub(r"^(\s*).*?( at usb-)", r"\1Audio USB\2", second)
        out += [first, second]
    return "\n".join(out) + "\n"


def _extra_in_series(names) -> set[str]:
    """De cada familia de interfaces en serie, todas menos la primera."""
    names = list(names)
    extra: set[str] = set()
    for pattern in IN_SERIES:
        extra.update(sorted(n for n in names if pattern.fullmatch(n))[1:])
    return extra


def _ipv4_hex(ip: str) -> str:
    """Una dirección como la escribe /proc/net/route: hexadecimal al revés."""
    return "".join(f"{int(x):02X}" for x in reversed(ip.split(".")))


# What the dumper itself writes in place of something, as it writes it: the
# router and its network in /proc/net/route, the IPv6 in if_inet6.
HEX_SUBSTITUTES = frozenset(s.lower() for s in (
    _ipv4_hex(privacidad.GATEWAY), _ipv4_hex(privacidad.GATEWAY.rsplit(".", 1)[0] + ".0"),
    "20010db8" + "0" * 20 + "0011", EMAIL_SUBSTITUTE))


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


class _Anonymizer:
    def __init__(self, target: pathlib.Path, recording: dict):
        self.target = target
        self.recording = recording
        # Lo que se quitó, por su clase (`QUE`), para buscarlo al final.
        self.secrets: dict[str, str] = {}
        # Lo quitado de un archivo binario, que no se busca como texto.
        self.raw_secrets: dict[bytes, str] = {}
        name = pathlib.Path(sysroot.path("/proc/sys/kernel/hostname"))
        self.host = name.read_text().strip() if name.is_file() else ""
        # A machine named as everyone's (the distribution, the brand): it is
        # neither replaced in the texts nor looked for.
        if privacidad.is_common_host_name(self.host, privacidad.machine_words(str(target))):
            self.host = ""
        self.user = getpass.getuser()
        self.home = str(pathlib.Path.home())
        self.interfaces = self._interfaces()
        # El nombre que alguien le puso a una interfaz es suyo: además de
        # sustituirlo donde se sabe que sale, se busca al final en cada byte.
        for old in self.interfaces:
            self._secret(old, "mac" if privacidad.MAC_IN_NAME.fullmatch(old)
                          else "interface")
        self.mounts: dict[str, str] = {}

    def _secret(self, value: Optional[str], kind: str) -> None:
        """Lo que se quitó, para buscarlo después en cada byte. Lo que es un
        sustituto no: una puerta de enlace de verdad puede ser 192.168.1.1, y
        encontrarla al final era encontrar el sustituto (el primer anexo de un
        portátil con Wi-Fi no salió por eso)."""
        value = (value or "").strip()
        if len(value) >= 4 and not privacidad.is_substitute(value) \
                and value.lower() not in HEX_SUBSTITUTES:
            self.secrets.setdefault(value, kind)

    def _interfaces(self) -> dict[str, str]:
        names = {}
        net_dir = self.target / "sys" / "class" / "net"
        entries = sorted(e.name for e in net_dir.iterdir()) if net_dir.is_dir() else []
        for entry in entries:
            if not privacidad.is_system_name(entry):
                names[entry] = privacidad.INTERFACE.format(len(names) + 1)
        # A USB adapter's name carries its MAC: the same substitute the report
        # gives it, in the same order.
        with_mac = [e for e in entries if privacidad.MAC_IN_NAME.fullmatch(e)]
        for index, entry in enumerate(with_mac):
            if (new := privacidad.name_without_mac(entry, index)) != entry:
                names[entry] = new
        return names

    def drop_serial_interfaces(self) -> int:
        """Quita las interfaces en serie que sobran, y dice cuántas eran.

        De todas partes: su carpeta, su enlace, sus líneas en las tablas de
        `/proc/net` y lo que se grabó de ellas.
        """
        net_dir = self.target / "sys" / "class" / "net"
        if not net_dir.is_dir():
            return 0
        extra = _extra_in_series(e.name for e in net_dir.iterdir())
        for name in extra:
            link = net_dir / name
            folder = link.resolve()
            if link.is_symlink():
                link.unlink()
            if folder.is_dir() and self.target in folder.parents:
                shutil.rmtree(folder)
        for table in ("route", "if_inet6"):
            for path in (self.target / "proc").glob(f"*/net/{table}"):
                if path.is_symlink() or not path.is_file():
                    continue
                lines = path.read_text().splitlines()
                path.write_text("".join(
                    line + "\n" for line in lines if not extra.intersection(line.split())))
        addresses = self.recording.get("ioctl_red")
        if isinstance(addresses, dict):
            for key in [c for c in addresses if c.partition(":")[0] in extra]:
                del addresses[key]
        return len(extra)

    def _replace_text(self, text: str) -> str:
        for old, new in self.interfaces.items():
            text = re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w.-])", new, text)
        text = privacidad._without_host(text, self.host) or text
        text = text.replace(self.home, "/home/usuario")
        if len(self.user) >= 3:
            text = re.sub(rf"(?<![\w.-]){re.escape(self.user)}(?![\w.-])", "usuario", text)
        text = MAC.sub(lambda m: m.group(0) if m.group(0) in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")
                        else privacidad.MAC, text)
        text = UUID.sub("00000000-0000-0000-0000-000000000000", text)
        # An address, wherever it is: /proc/version names whoever built the
        # kernel, and a kernel compiled at home names its owner. The same
        # rule as the checker that runs before publishing.
        def email(m: re.Match) -> str:
            if privacidad.ALLOWED_EMAILS.search(m.group()):
                return m.group()
            self._secret(m.group(), "email")
            return EMAIL_SUBSTITUTE
        return privacidad.EMAIL.sub(email, text)

    def _mount(self, mount_point: str) -> str:
        if mount_point in privacidad._SYSTEM_MOUNTS:
            return mount_point
        return self.mounts.setdefault(mount_point, privacidad.MOUNT.format(len(self.mounts) + 1))

    def clean_contents(self) -> None:
        models = {(_text_of(m) or "").strip().lower() for m in self.target.rglob("model")
                   if m.is_file() and not m.is_symlink()}
        for path in sorted(self.target.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            name = path.name
            relative = "/" + str(path.relative_to(self.target))
            data = path.read_bytes()
            if name in SERIAL_FILES and data.strip():
                self._secret(data.strip().decode(errors="replace"), "serial")
                path.write_bytes(re.sub(rb"[^\n\x00]", b"0", data))
                continue
            if name == "id" and "/ata_device/" in relative:
                clean, serial = _identify_without_serial(data.decode(errors="replace"))
                if serial:
                    self._secret(serial, "disk_serial")
                path.write_text(clean)
                continue
            if name == "edid":
                if len(data) >= 16 and any(data[12:16]):
                    self.raw_secrets[data[12:16]] = "monitor_serial"
                path.write_bytes(_edid_without_serial(data))
                continue
            if name == "eeprom":
                clean, serial = _spd_without_serial(data)
                if any(serial):
                    self.raw_secrets[serial] = "memory_serial"
                path.write_bytes(clean)
                continue
            if name in ADDRESS_FILES and "/net/" in relative:
                if data.strip() and data.strip() not in (b"00:00:00:00:00:00",):
                    self._secret(data.strip().decode(errors="replace"), "mac")
                    path.write_text(privacidad.MAC + "\n")
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
            if name in USB_IDENTIFYING_FILES and re.search(r"/usb\d+/", relative):
                usb_text = data.decode(errors="replace").strip()
                # A USB stick's name is also its disk's model, which the dump
                # keeps as any disk's (and the report shows): not looked for.
                if name == "product" and len(usb_text) >= 6 \
                        and not USB_GENERIC.search(usb_text) \
                        and usb_text.lower() not in models:
                    self._secret(usb_text, "usb")
                path.unlink()
                continue
            if relative.startswith("/sys/") and "/video4linux/" in relative and name == "name":
                if len(data.strip()) >= 6:
                    self._secret(data.decode(errors="replace").strip().split(":")[0], "camera")
                path.unlink()
                continue
            if relative == "/proc/asound/cards":
                path.write_text(_cards_without_names(data.decode(errors="replace")))
                continue
            if relative == "/proc/sys/kernel/hostname":
                path.write_text(privacidad.HOST_NAME + "\n")
                continue
            if relative == "/proc/cmdline":
                # The disks' UUIDs, an encrypted volume, the machine's name.
                path.write_text(" ".join(privacidad.hide_cmdline_identifiers(
                    data.decode(errors="replace"))) + "\n")
                continue
            # /proc/net es un enlace a self/net: el archivo de verdad acaba en
            # /proc/<pid>/net/, así que se reconoce por cómo termina.
            if relative.startswith("/proc/") and relative.endswith("/net/route"):
                path.write_text(self._replace_text(self._network_path(data.decode())))
                continue
            if relative.startswith("/proc/") and relative.endswith("/net/if_inet6"):
                path.write_text(self._replace_text(self._ipv6(data.decode())))
                continue
            if relative.startswith("/proc/") and relative.endswith("/mounts"):
                path.write_text(self._replace_text(self._mounts(data.decode())))
                continue
            text = _text_of(path)
            if text is not None:
                changed = self._replace_text(text)
                if changed != text:
                    path.write_text(changed)

    def _network_path(self, text: str) -> str:
        lines = text.splitlines()
        out = lines[:1]
        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) > 2:
                if fields[1] != "00000000":
                    fields[1] = _ipv4_hex(privacidad.GATEWAY.rsplit(".", 1)[0] + ".0")
                if fields[2] != "00000000":
                    self._secret(fields[2], "router")
                    fields[2] = _ipv4_hex(privacidad.GATEWAY)
            out.append("\t".join(fields))
        return "\n".join(out) + "\n"

    def _ipv6(self, text: str) -> str:
        # privacidad.IPV6, 2001:db8::11, en los 32 dígitos de /proc/net/if_inet6.
        substitute = "20010db8" + "0" * 20 + "0011"
        out = []
        for line in text.splitlines():
            fields = line.split()
            if fields and fields[0] != "0" * 31 + "1":
                self._secret(fields[0], "ipv6")
                line = line.replace(fields[0], substitute, 1)
            out.append(line)
        return "\n".join(out) + "\n"

    def _mounts(self, text: str) -> str:
        """Los montajes de los discos, con los puntos que puso alguien tapados.

        Solo se quedan las líneas de un dispositivo, que son las que lee el
        proveedor. Las demás no describen el equipo sino la sesión: el
        AppImage abierto, los contenedores, la carpeta del usuario.
        """
        out = []
        for line in text.splitlines():
            fields = line.split(" ")
            if not fields[0].startswith("/dev/"):
                continue
            if len(fields) > 1:
                mount_point = fields[1].replace("\\040", " ")
                new = self._mount(mount_point)
                if new != mount_point:
                    fields[1] = new
            out.append(" ".join(fields))
        return "\n".join(out) + "\n"

    def rename_interfaces(self) -> None:
        """Las interfaces con nombre propio, también en carpetas y enlaces."""
        if not self.interfaces:
            return
        for path in sorted(self.target.rglob("*"), key=lambda r: -len(r.parts)):
            if path.is_symlink():
                target = os.readlink(path)
                new = self._replace_text(target)
                if new != target:
                    path.unlink()
                    os.symlink(new, path)
            if path.name in self.interfaces:
                path.rename(path.with_name(self.interfaces[path.name]))

    def clean_recording(self) -> dict:
        # NVML's UUID («GPU-» and a UUID) names the card. The rule for UUIDs
        # zeroed its UUID and left «GPU-», which anonimizar still covered: a
        # laptop with an awake NVIDIA had no annex. It goes as anonimizar
        # leaves it, and the real one is looked for in every byte.
        for card in (self.recording.get("nvml") or {}).get("tarjetas") or ():
            if isinstance(card, dict) and card.get("uuid"):
                self._secret(card["uuid"], "gpu_id")
                self._secret(card["uuid"].removeprefix("GPU-"), "gpu_id")
        # Mount points are numbered by their real path, as in /proc/mounts:
        # covered first, a path holding the user's name became another one.
        mounted_points = {self._mount(p): v for p, v in (self.recording.get("statvfs") or {}).items()}
        clean = json.loads(self._replace_text(json.dumps(self.recording, ensure_ascii=False)))
        for card in (clean.get("nvml") or {}).get("tarjetas") or ():
            if isinstance(card, dict) and card.get("uuid"):
                card["uuid"] = privacidad._mask(card["uuid"])
        for key in list(clean.get("ioctl_red", {})):
            value = clean["ioctl_red"][key]
            name, _sep, code = key.partition(":")
            if value and code == "0x8915" and not value.startswith("127."):
                self._secret(value, "ip")
                clean["ioctl_red"][key] = privacidad.IPV4
        if "statvfs" in clean:
            clean["statvfs"] = mounted_points
        env = clean.get("plataforma", {}).get("uname")
        if isinstance(env, dict) and env.get("node"):
            env["node"] = privacidad.HOST_NAME
        return clean


# -- comprobar ------------------------------------------------------------------

# Looked for as a word and not inside another: a machine's or a
# connection's name is part of driver names (a «thinkpad» in thinkpad_hwmon
# blocked an annex), and an IP is the start of a longer one. A serial number
# is looked for anywhere.
AS_WORD = frozenset({"machine_name", "interface", "usb", "ip"})
_AROUND = rb"[A-Za-z0-9_.-]"


def _own_class(description: str) -> str:
    """The kind of one of `privacidad.de_esta_maquina`'s identifiers."""
    if description == "el nombre de este equipo":
        return "machine_name"
    if "interfaz" in description:
        return "interface"
    if "IPv4" in description:
        return "ip"
    return "machine"


def found_in(target: pathlib.Path, secrets, raw_secrets=(),
                own: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Where something of this machine is in the dump: (path, kind), the
    kinds of `QUE`. Empty if nothing.

    `secretos` and `crudos`, what the dumper took away (a dict by kind, or
    any collection); `propios`, what identifies this machine, without which
    `privacidad.de_esta_maquina`'s. A substitute is never looked for.
    """
    if own is None:
        own = privacidad.of_this_machine()
    by_kind = lambda group, kind: (group.items() if isinstance(group, dict)
                                      else ((g, kind) for g in group))
    wanted: list[tuple[bytes, str]] = []
    for value, kind in [*((d, _own_class(q)) for d, q in own.items()),
                         *by_kind(secrets, "machine")]:
        if value and len(value) >= 4 and not privacidad.is_substitute(value):
            wanted.append((value.encode(), kind))
    wanted += [(c, kind) for c, kind in by_kind(raw_secrets, "serial") if any(c)]
    patterns = [(re.compile(rb"(?<!" + _AROUND + rb")" + re.escape(b) + rb"(?!" + _AROUND + rb")")
                 if kind in AS_WORD else None, b, kind) for b, kind in wanted]
    findings = []
    for path in sorted(target.rglob("*")):
        if path.is_symlink():
            content = os.readlink(path).encode()
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b""
        relative = str(path.relative_to(target))
        for pattern, raw, kind in patterns:
            for where in (content, relative.encode()):
                if (pattern.search(where) if pattern is not None else raw in where):
                    findings.append((relative, kind, pattern or raw))
                    break
    return findings


def check(target: pathlib.Path, secrets, raw_secrets=(),
              own: dict[str, str] | None = None) -> list[str]:
    """Lo que delata a esta máquina dentro del volcado, en palabras. Vacío si nada."""
    return [f"{path}: {QUE.get(kind, kind)}"
            for path, kind, _wanted in found_in(target, secrets, raw_secrets, own)]


class Refusal(SystemExit):
    """Nothing is written: anonimizar would still cover these fields of the
    photo. They are named by position («gpus[1].unique_id»), never by value."""

    def __init__(self, fields: list[str]):
        self.fields = list(fields)
        super().__init__("anonimizar todavía encuentra qué tapar: "
                         + "; ".join(self.fields[:10]) + ". No se escribe nada.")


def _contains(wanted, text: str) -> bool:
    data = text.encode()
    return bool(wanted.search(data)) if isinstance(wanted, re.Pattern) else wanted in data


def _json_without(datum, wanted, path: str = "") -> tuple[object, list[str]]:
    """The JSON without what holds `buscado`: a string goes to None, a key or
    a list item goes. And where it was, as a path of keys."""
    if isinstance(datum, dict):
        out, removed = {}, []
        for key, value in datum.items():
            key_path = f"{path}.{key}" if path else str(key)
            if _contains(wanted, str(key)):
                removed.append(key_path)
                continue
            out[key], inside = _json_without(value, wanted, key_path)
            removed += inside
        return out, removed
    if isinstance(datum, list):
        out, removed = [], []
        for i, value in enumerate(datum):
            if isinstance(value, str) and _contains(wanted, value):
                removed.append(f"{path}[{i}]")
                continue
            clean, inside = _json_without(value, wanted, f"{path}[{i}]")
            out.append(clean)
            removed += inside
        return out, removed
    if isinstance(datum, str) and _contains(wanted, datum):
        return None, [path]
    return datum, []


def _covered(text: str, wanted) -> str:
    """The path as the annex says it, with what was found covered: it can
    be in the name of a folder (it was, on the CI's machine)."""
    data = text.encode()
    data = (wanted.sub(b"\xe2\x80\xa6", data) if isinstance(wanted, re.Pattern)
             else data.replace(wanted, "…".encode()))
    return data.decode(errors="replace")


def _without_found(work: pathlib.Path, findings) -> list[dict]:
    """Takes away what could not be covered safely, instead of writing
    nothing: the file, or in the two JSON files the answer that holds it.
    Says what each was, by kind, and where, with it covered."""
    removed: list[dict] = []
    for relative, kind, wanted in findings:
        path = work / relative
        if relative in (sysroot.RECORDING_FILE, MANIFEST) and path.is_file():
            clean, paths = _json_without(json.loads(path.read_text()), wanted)
            path.write_text(json.dumps(clean, ensure_ascii=False, indent=1,
                                       sort_keys=relative == sysroot.RECORDING_FILE) + "\n")
            removed += [{"ruta": _covered(f"{relative}: {c}", wanted), "dato": kind}
                         for c in paths]
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            continue
        removed.append({"ruta": _covered("/" + relative, wanted), "dato": kind})
    return removed


@contextlib.contextmanager
def mounted(folder: pathlib.Path):
    """El volcado listo para leer: una copia con los ilegibles sin permiso."""
    with tempfile.TemporaryDirectory(prefix="silux-equipo-") as tmp:
        copy = pathlib.Path(tmp) / "raiz"
        shutil.copytree(folder, copy, symlinks=True)
        manifest = json.loads((copy / MANIFEST).read_text())
        for empty_dir in manifest.get("vacios", []):
            (copy / empty_dir.lstrip("/")).mkdir(parents=True, exist_ok=True)
        for unreadable_path in manifest.get("ilegibles", []):
            path = copy / unreadable_path.lstrip("/")
            if path.exists():
                path.chmod(0)
        previous = os.environ.get(sysroot.VARIABLE)
        os.environ[sysroot.VARIABLE] = str(copy)
        sysroot.forget()
        try:
            yield copy
        finally:
            for unreadable_path in manifest.get("ilegibles", []):
                path = copy / unreadable_path.lstrip("/")
                if path.exists():
                    path.chmod(0o600)
            if previous is None:
                os.environ.pop(sysroot.VARIABLE, None)
            else:
                os.environ[sysroot.VARIABLE] = previous
            sysroot.forget()


def snapshot_of(folder: pathlib.Path):
    """La foto que da el Collector leyendo el volcado."""
    from silux.collector import Collector

    with mounted(folder):
        collector = Collector()
        try:
            collector.snapshot()
            return collector.snapshot()
        finally:
            collector.close()


# -- principal ------------------------------------------------------------------

def dump(name: str, base: pathlib.Path,
           own: dict[str, str] | None = None) -> pathlib.Path:
    target = base / name
    if target.exists():
        raise SystemExit(f"ya existe {target}: bórralo antes para volcar otra vez")

    # Lo primero, antes de que nada la despierte: cómo está cada gráfica.
    sleeping = _SleepingCards()
    read_paths, listed, checked, recording = _collect(sleeping)
    read_paths |= _alternatives(read_paths) | sleeping.power_files() | _gpu_extras()
    # Copiar también es leer: lo de una gráfica dormida no pasa ni por aquí.
    read_paths = {c for c in read_paths if not sleeping.forbidden(c)}
    checked = {c for c in checked if not sleeping.forbidden(c)}
    with tempfile.TemporaryDirectory(prefix="silux-volcado-") as tmp:
        work = pathlib.Path(tmp) / name
        work.mkdir()
        copy = _Copy(work)
        for path in sorted(listed):
            copy.directory(path)
        for path in sorted(read_paths):
            copy.copy_file(path)
        for path in sorted(checked - read_paths - listed):
            # Un `exists()` o un `is_dir()` que salió que sí: que siga saliendo.
            if os.path.lexists(sysroot.path(path)):
                (copy.directory(path) if os.path.isdir(sysroot.path(path))
                 else copy.copy_file(path))

        clean = _Anonymizer(work, recording)
        dropped = clean.drop_serial_interfaces()
        clean.clean_contents()
        clean.rename_interfaces()
        (work / sysroot.RECORDING_FILE).write_text(
            json.dumps(clean.clean_recording(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")

        # Git no guarda directorios vacíos, y algunos cuentan: los procesos de
        # /proc, o un /sys/firmware/efi que solo se mira si existe. Se apuntan
        # y se recrean al montar.
        empty_dirs = sorted("/" + str(d.relative_to(work)) for d in work.rglob("*")
                        if d.is_dir() and not d.is_symlink() and not any(d.iterdir()))
        (work / MANIFEST).write_text(json.dumps({
            "herramienta": 1,
            "vacios": empty_dirs,
            "ilegibles": sorted(clean._replace_text(c) for c in copy.unreadable),
            # Cómo estaba cada gráfica antes de leer nada, por su ranura.
            "energia_de_las_graficas": sleeping.states,
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
            ] + sleeping.not_recorded() + ([f"{dropped} interfaces de red en serie (puentes de Docker y "
                  "veth): queda una de cada"] if dropped else []),
        }, ensure_ascii=False, indent=1) + "\n")

        # What was not covered goes, file by file, and the annex says so: a
        # dump with a file less is still a dump, and with nothing written
        # three of three testers had no annex.
        removed = _without_found(
            work, found_in(work, clean.secrets, clean.raw_secrets, own))
        if removed:
            manifest = json.loads((work / MANIFEST).read_text())
            manifest["quitados"] = removed
            (work / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
        snapshot = snapshot_of(work)
        if left := _what_anonymize_would_cover(snapshot):
            raise Refusal(left)
        if findings := check(work, clean.secrets, clean.raw_secrets, own):
            raise SystemExit("El volcado delata a esta máquina; no se escribe nada:\n  "
                             + "\n  ".join(findings[:20]))

        manifest = json.loads((work / MANIFEST).read_text())
        cpu = snapshot.cpu.types[0].brand if snapshot.cpu.types else None
        manifest.update(cpu=cpu, kernel=snapshot.system.kernel if snapshot.system else None,
                          gpus=[g.name for g in snapshot.gpus], fuentes=sorted(snapshot.capabilities))
        (work / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, target, symlinks=True)
    return target


# Lo que `anonimizar` sustituye aunque no identifique a nadie: el bucle local
# y una MAC a ceros. Que lo cambie no significa que el volcado se lo dejara.
HARMLESS = {"127.0.0.1", "::1", "00:00:00:00:00:00", None, ()}
ALREADY_SUBSTITUTED = re.compile(re.escape(privacidad.MOUNT).replace(r"\{\}", r"\d+"))


def _unnumbered(disks):
    """Los discos con los montajes ya sustituidos sin su número.

    `anonimizar` numera por el orden de los discos y el volcado por el de
    `/proc/mounts`: un `/media/unidad3` que pasa a `/media/unidad1` no es un
    dato que quedara por tapar.
    """
    return tuple(
        dataclasses.replace(d, partitions=tuple(
            dataclasses.replace(p, mountpoint=privacidad.MOUNT.format(""))
            if p.mountpoint and ALREADY_SUBSTITUTED.fullmatch(p.mountpoint) else p
            for p in d.partitions))
        for d in disks)


def _differences(before, after, path: str) -> list[str]:
    """Where two values differ, as field paths («gpus[1].unique_id»): what
    the refusal says, without the value, which is what it protects."""
    if before == after:
        return []
    if (dataclasses.is_dataclass(before) and type(before) is type(after)):
        return [d for field in dataclasses.fields(before)
                for d in _differences(getattr(before, field.name), getattr(after, field.name),
                                      f"{path}.{field.name}")]
    if isinstance(before, tuple) and isinstance(after, tuple) and len(before) == len(after):
        return [d for i, (a, b) in enumerate(zip(before, after))
                for d in _differences(a, b, f"{path}[{i}]")]
    return [path]


def _what_anonymize_would_cover(snapshot) -> list[str]:
    """Lo que `privacidad.anonimizar` cambiaría en la foto del volcado.

    Si cambia algo, es que el volcado dejó un dato que identifica a alguien.
    Lo único que se acepta es lo que anonimizar tapa por sistema sin que sea
    de nadie, como `127.0.0.1`.
    """
    covered = privacidad.anonymize(snapshot)
    left = []
    for field in dataclasses.fields(snapshot):
        before, after = getattr(snapshot, field.name), getattr(covered, field.name)
        if before == after:
            continue
        if field.name == "network":
            for i, j in zip(before, after):
                for sub in dataclasses.fields(i):
                    a, b = getattr(i, sub.name), getattr(j, sub.name)
                    leftovers = [x for x in (a if isinstance(a, tuple) else (a,))
                              if x not in HARMLESS and x not in privacidad.OLD_SUBSTITUTES]
                    if a != b and leftovers:
                        # By position: the name may be what is protected.
                        left.append(f"network[{before.index(i)}].{sub.name}")
            continue
        if field.name == "disks" and _unnumbered(before) == _unnumbered(after):
            continue
        if (field.name == "system" and before.hostname in privacidad.OLD_SUBSTITUTES
                and dataclasses.replace(before, hostname=after.hostname) == after):
            continue
        left += _differences(before, after, field.name)
    return left
