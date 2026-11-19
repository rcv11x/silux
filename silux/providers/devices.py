"""Lo que hay enchufado: USB, sonido, cámaras y el adaptador Bluetooth.

No es hardware del equipo sino de alrededor, y por eso tiene su sección.
Todo se lee de sysfs y de `/proc/asound`, sin permisos, en cada muestreo:
las cosas se enchufan y se quitan con el programa abierto.

**Lo que no se lee, a propósito.** El número de serie de un dispositivo USB
(`serial`), la dirección de un adaptador Bluetooth (`address`) y lo que
tenga emparejado. Lo primero identifica un aparato concreto; lo último es de
otros. Si no se abre el archivo, no llega al modelo ni a un volcado.
"""

from __future__ import annotations

import glob
import os
import pathlib
import re
from typing import Optional

from .. import sysroot
from ..model import BluetoothAdapter, Camera, SoundCard, UsbDevice
from .base import Draft, Provider, read_text

USB = "/sys/bus/usb/devices"

# Qué es un dispositivo según la clase de sus interfaces, de la más
# específica a la más genérica: un teclado con lector de tarjetas es antes
# un lector, y una cámara con micrófono es antes una cámara.
POR_INTERFAZ = (
    ("0e", "video"), ("08", "storage"), ("0b", "smartcard"), ("01", "audio"),
    ("e0", "wireless"), ("07", "printer"), ("03", "input"),
    ("02", "comm"), ("0a", "comm"), ("ff", "vendor"),
)
_PUERTO = re.compile(r"\d+-\d+(\.\d+)*")


def _clase(nodo: str) -> str:
    """Qué es: nunca «según la interfaz», que es lo que dice el dispositivo
    cuando delega la respuesta en sus interfaces. Se les pregunta a ellas."""
    propia = (read_text(f"{nodo}/bDeviceClass") or "").lower()
    if propia == "09":
        return "hub"
    if propia == "e0":
        return "wireless"
    interfaces = glob.glob(os.path.join(sysroot.ruta(nodo), "*:*"))
    clases, protocolos = set(), set()
    for interfaz in interfaces:
        base = sysroot.fuera(interfaz)
        clase = (read_text(f"{base}/bInterfaceClass") or "").lower()
        clases.add(clase)
        if clase == "03":
            protocolos.add((read_text(f"{base}/bInterfaceProtocol") or "").lower())
    for clase, tipo in POR_INTERFAZ:
        if clase in clases:
            if tipo == "input":
                # El protocolo de arranque: 01 teclado, 02 ratón.
                if {"01", "02"} <= protocolos:
                    return "keyboard_mouse"         # un receptor con los dos
                return "keyboard" if "01" in protocolos else "mouse" if "02" in protocolos \
                    else "input"
            return tipo
    return "other"


class ConnectedDevices(Provider):
    name = "devices"
    provides = "usb_devices"

    def __init__(self) -> None:
        # Lo leído de cada dispositivo USB, por su puerto y el inodo de su
        # entrada en sysfs: una cosa que se quita y otra que se enchufa en el
        # mismo puerto es otra entrada, con otro inodo. Mientras no cambie
        # nada, cada muestreo solo lista la carpeta.
        self._usb_leidos: dict[tuple[str, int], UsbDevice] = {}
        # Y las tarjetas de sonido, por el texto de `/proc/asound/cards`: leer
        # sus códecs cuesta, porque `codec#N` es el volcado entero del códec
        # y el kernel lo genera al abrirlo.
        self._sonido_leido: tuple[Optional[str], list[SoundCard]] = (None, [])

    def available(self) -> bool:
        return True

    def collect(self, draft: Draft) -> None:
        draft.usb_devices = self._usb()
        draft.sound_cards = self._sonido()
        draft.cameras = self._camaras()
        draft.bluetooth = self._bluetooth()

    def _usb(self) -> list[UsbDevice]:
        salida = []
        vistos: dict[tuple[str, int], UsbDevice] = {}
        try:
            entradas = sorted(os.scandir(sysroot.ruta(USB)), key=lambda e: e.name)
        except OSError:
            entradas = []
        for entrada in entradas:
            puerto = entrada.name
            if not _PUERTO.fullmatch(puerto):
                continue                 # las interfaces («1-3:1.0») y las raíces («usb1»)
            clave = (puerto, entrada.inode())
            if (ya := self._usb_leidos.get(clave)) is not None:
                vistos[clave] = ya
                salida.append(ya)
                continue
            nodo = sysroot.fuera(entrada.path)
            fabricante, modelo = read_text(f"{nodo}/idVendor"), read_text(f"{nodo}/idProduct")
            try:
                velocidad = float(read_text(f"{nodo}/speed") or "")
            except ValueError:
                velocidad = None
            dispositivo = UsbDevice(
                port=puerto,
                vendor=read_text(f"{nodo}/manufacturer") or None,
                product=read_text(f"{nodo}/product") or None,
                usb_id=f"{fabricante}:{modelo}" if fabricante and modelo else None,
                kind=_clase(nodo),
                speed_mbps=velocidad,
                version=(read_text(f"{nodo}/version") or "").strip() or None,
            )
            vistos[clave] = dispositivo
            salida.append(dispositivo)
        self._usb_leidos = vistos
        return salida

    def _sonido(self) -> list[SoundCard]:
        tarjetas = read_text("/proc/asound/cards")
        if tarjetas == self._sonido_leido[0]:
            return list(self._sonido_leido[1])
        salida = self._leer_sonido(tarjetas)
        self._sonido_leido = (tarjetas, salida)
        return list(salida)

    @staticmethod
    def _leer_sonido(tarjetas: Optional[str]) -> list[SoundCard]:
        salida = []
        lineas = (tarjetas or "").splitlines()
        for primera, segunda in zip(lineas[::2], lineas[1::2]):
            encaje = re.match(r"\s*(\d+)\s+\[.*?\]:\s*(\S+)\s+-\s*(.*)", primera)
            if not encaje:
                continue
            indice, driver, nombre = encaje.group(1), encaje.group(2), encaje.group(3).strip()
            codecs = []
            for camino in sorted(glob.glob(os.path.join(
                    sysroot.ruta(f"/proc/asound/card{indice}"), "codec#*"))):
                linea = (read_text(sysroot.fuera(camino)) or "").split("\n", 1)[0]
                if (codec := linea.partition(":")[2].strip()):
                    codecs.append(codec)
            if "usb" in driver.lower() or "usb-" in segunda:
                salida.append(SoundCard(name=nombre or None, kind="usb",
                                        camera=_de_una_camara(segunda)))
            elif codecs and all("HDMI" in c for c in codecs):
                salida.append(SoundCard(kind="hdmi", codec=codecs[0]))
            elif codecs:
                salida.append(SoundCard(kind="board",
                                        codec=next(c for c in codecs if "HDMI" not in c)))
            else:
                salida.append(SoundCard(name=nombre, kind="other"))
        return salida

    @staticmethod
    def _camaras() -> list[Camera]:
        # Un aparato crea varios nodos (imagen y metadatos): se agrupan por
        # el dispositivo del que cuelgan. Una cámara virtual no cuelga de
        # ninguno.
        grupos: dict[str, list] = {}
        for camino in sorted(glob.glob(os.path.join(sysroot.ruta("/sys/class/video4linux"), "video*"))):
            nombre = (read_text(f"{sysroot.fuera(camino)}/name") or "").split(":")[0].strip()
            enlace = pathlib.Path(camino, "device")
            try:
                fisico = str(enlace.resolve()) if enlace.exists() else None
            except OSError:
                fisico = None
            # Las interfaces de un mismo aparato USB («…:1.0», «…:1.2») son el mismo.
            clave = re.sub(r":\d+\.\d+$", "", fisico) if fisico else f"virtual:{nombre}"
            grupo = grupos.setdefault(clave, [nombre, 0, fisico is None])
            grupo[1] += 1
        return [Camera(name=nombre or None, nodes=nodos, virtual=virtual)
                for nombre, nodos, virtual in grupos.values()]

    @staticmethod
    def _bluetooth() -> list[BluetoothAdapter]:
        salida = []
        for camino in sorted(glob.glob(os.path.join(sysroot.ruta("/sys/class/bluetooth"), "hci*"))):
            nombre = os.path.basename(camino)
            if ":" in nombre:
                continue                 # las conexiones («hci0:256») no son adaptadores
            try:
                fisico = pathlib.Path(camino, "device").resolve()
            except OSError:
                fisico = None
            por_usb = bool(fisico and "/usb" in str(fisico))
            producto = None
            if por_usb:
                producto = read_text(f"{sysroot.fuera(str(fisico.parent))}/product") or None
            estado = None
            for rfkill in glob.glob(os.path.join(camino, "rfkill*", "state")):
                estado = (read_text(sysroot.fuera(rfkill)) or "").strip() == "1"
            salida.append(BluetoothAdapter(name=nombre, product=producto,
                                           bus="usb" if por_usb else "board", powered=estado))
        return salida


# Clase USB de video (USB-IF): la de una cámara.
CLASE_VIDEO = "0e"


def _de_una_camara(linea: str) -> bool:
    """Si una tarjeta de sonido USB es el micrófono de una cámara.

    `/proc/asound/cards` dice dónde cuelga: «… at usb-0000:0e:00.3-4.1.4, high
    speed», el controlador y el camino de puertos. El aparato de ese camino,
    en el bus de ese controlador, es una cámara si alguna de sus interfaces
    es de video.
    """
    encaje = re.search(r"usb-([0-9a-fA-F:.]+)-([\d.]+)", linea)
    if not encaje:
        return False
    controlador, puertos = encaje.groups()
    for bus in glob.glob(os.path.join(sysroot.ruta("/sys/bus/usb/devices"), "usb*")):
        if controlador not in os.path.realpath(bus):
            continue
        numero = os.path.basename(bus)[3:]
        aparato = os.path.join(os.path.dirname(bus), f"{numero}-{puertos}")
        for interfaz in glob.glob(aparato + ":*"):
            if (read_text(sysroot.fuera(os.path.join(interfaz, "bInterfaceClass"))) or "").strip() == CLASE_VIDEO:
                return True
    return False
