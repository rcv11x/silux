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

    def available(self) -> bool:
        return True

    def collect(self, draft: Draft) -> None:
        draft.usb_devices = self._usb()
        draft.sound_cards = self._sonido()
        draft.cameras = self._camaras()
        draft.bluetooth = self._bluetooth()

    @staticmethod
    def _usb() -> list[UsbDevice]:
        salida = []
        for camino in sorted(glob.glob(os.path.join(sysroot.ruta(USB), "*"))):
            puerto = os.path.basename(camino)
            if not _PUERTO.fullmatch(puerto):
                continue                 # las interfaces («1-3:1.0») y las raíces («usb1»)
            nodo = sysroot.fuera(camino)
            fabricante, modelo = read_text(f"{nodo}/idVendor"), read_text(f"{nodo}/idProduct")
            try:
                velocidad = float(read_text(f"{nodo}/speed") or "")
            except ValueError:
                velocidad = None
            salida.append(UsbDevice(
                port=puerto,
                vendor=read_text(f"{nodo}/manufacturer") or None,
                product=read_text(f"{nodo}/product") or None,
                usb_id=f"{fabricante}:{modelo}" if fabricante and modelo else None,
                kind=_clase(nodo),
                speed_mbps=velocidad,
                version=(read_text(f"{nodo}/version") or "").strip() or None,
            ))
        return salida

    @staticmethod
    def _sonido() -> list[SoundCard]:
        salida = []
        lineas = (read_text("/proc/asound/cards") or "").splitlines()
        for primera, segunda in zip(lineas[::2], lineas[1::2]):
            encaje = re.match(r"\s*(\d+)\s+\[.*?\]:\s*(\S+)\s+-\s+(.*)", primera)
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
                salida.append(SoundCard(name=nombre, kind="usb"))
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
