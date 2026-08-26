"""Las interfaces de red: qué son, cómo están conectadas y cuánto mueven.

Casi todo está en `/sys/class/net`, que es de lectura libre: estado del enlace,
velocidad negociada, MAC, MTU y los contadores de tráfico. Lo único que el
kernel no publica ahí es la dirección IP, y para esa hay que preguntarle al
sistema con un ioctl de toda la vida (el mismo que usa `ifconfig`) porque las
direcciones no viven en el dispositivo sino en la pila de red.

El ritmo de subida y bajada se calcula entre dos muestreos. Los contadores son
totales desde que arrancó la interfaz, así que restar dos lecturas y dividir
por el tiempo transcurrido es la única forma de saber a qué velocidad va ahora.
"""

from __future__ import annotations

import fcntl
import os
import pathlib
import socket
import struct
import time
from typing import Iterator, Optional

from .. import pciids
from ..model import NetworkInterface, NetworkTraffic
from .base import Draft, Provider, read_int, read_text

SYS_NET = "/sys/class/net"
PROC_ROUTE = "/proc/net/route"
PROC_IPV6 = "/proc/net/if_inet6"

# Los de <linux/sockios.h>. Piden un socket abierto, pero no permisos.
SIOCGIFADDR = 0x8915
SIOCGIFNETMASK = 0x891B

CONTADORES = ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
              "rx_errors", "tx_errors", "rx_dropped", "tx_dropped")

# El valor de `type` en sysfs, que viene de ARPHRD_* del kernel.
TIPO_ETHERNET, TIPO_LOOPBACK = 1, 772

# Interfaces que existen pero no son una tarjeta: puentes de máquinas
# virtuales, túneles, contenedores. Se enseñan igual (quien tiene libvirt
# quiere ver su puente) pero marcadas como lo que son.
PREFIJOS_VIRTUALES = ("virbr", "docker", "veth", "br-", "tun", "tap", "vmnet",
                      "wg", "tailscale", "zt", "bond", "dummy")


class NetworkInterfaces(Provider):
    """Enumera las interfaces y calcula el ritmo de tráfico de cada una."""

    name = "network"
    provides = "network"

    def __init__(self) -> None:
        # Contadores de la vuelta anterior, para poder restar.
        self._previo: dict[str, tuple[float, int, int]] = {}

    def available(self) -> bool:
        return os.path.isdir(SYS_NET)

    def collect(self, draft: Draft) -> None:
        nombres = sorted(p.name for p in pathlib.Path(SYS_NET).iterdir())
        if not nombres:
            return

        draft.capabilities.add("network")
        rutas = _rutas_por_defecto()
        direcciones = _Direcciones()
        ipv6 = _ipv6_por_interfaz()
        try:
            draft.network = [
                self._leer(nombre, rutas, direcciones, ipv6.get(nombre, ()))
                for nombre in nombres
            ]
        finally:
            direcciones.close()

    # -- interno ------------------------------------------------------------

    def _leer(self, nombre: str, rutas: dict[str, str], direcciones: "_Direcciones",
              ipv6: tuple[str, ...]) -> NetworkInterface:
        base = pathlib.Path(SYS_NET, nombre)
        tipo_crudo = read_int(str(base / "type"))
        velocidad = read_int(str(base / "speed"))

        return NetworkInterface(
            name=nombre,
            kind=_clase(nombre, base, tipo_crudo),
            up=_activa(read_text(str(base / "operstate")), base),
            carrier=_bandera(base / "carrier"),
            mac=read_text(str(base / "address")) or None,
            ipv4=direcciones.ip(nombre),
            netmask=direcciones.mascara(nombre),
            ipv6=ipv6,
            gateway=rutas.get(nombre),
            default_route=nombre in rutas,
            # Una interfaz caída devuelve -1 en `speed`, no su velocidad.
            speed_mbps=velocidad if velocidad and velocidad > 0 else None,
            duplex=read_text(str(base / "duplex")) or None,
            mtu=read_int(str(base / "mtu")),
            driver=_driver(base),
            traffic=self._trafico(nombre, base),
            **_identidad_pci(base),
        )

    def _trafico(self, nombre: str, base: pathlib.Path) -> NetworkTraffic:
        valores = {campo: read_int(str(base / "statistics" / campo)) or 0
                   for campo in CONTADORES}
        ahora = time.monotonic()
        subida = bajada = None

        anterior = self._previo.get(nombre)
        if anterior is not None:
            antes, rx, tx = anterior
            transcurrido = ahora - antes
            # Los contadores se reinician si la interfaz se cae y vuelve; un
            # delta negativo es eso, no un ritmo negativo.
            if transcurrido > 0 and valores["rx_bytes"] >= rx and valores["tx_bytes"] >= tx:
                bajada = (valores["rx_bytes"] - rx) / transcurrido
                subida = (valores["tx_bytes"] - tx) / transcurrido
        self._previo[nombre] = (ahora, valores["rx_bytes"], valores["tx_bytes"])

        return NetworkTraffic(**valores, rx_rate_bps=bajada, tx_rate_bps=subida)


class _Direcciones:
    """Un socket abierto para preguntar las direcciones IPv4 por ioctl."""

    def __init__(self) -> None:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            self._socket = None

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def ip(self, nombre: str) -> Optional[str]:
        return self._preguntar(nombre, SIOCGIFADDR)

    def mascara(self, nombre: str) -> Optional[str]:
        return self._preguntar(nombre, SIOCGIFNETMASK)

    def _preguntar(self, nombre: str, codigo: int) -> Optional[str]:
        if self._socket is None:
            return None
        try:
            respuesta = fcntl.ioctl(self._socket.fileno(), codigo,
                                    struct.pack("256s", nombre[:15].encode()))
        except OSError:
            # Una interfaz sin dirección asignada responde con error, y eso es
            # una respuesta legítima: todavía no tiene IP.
            return None
        return socket.inet_ntoa(respuesta[20:24])


# -- lectura suelta ----------------------------------------------------------

def _activa(operstate: Optional[str], base: pathlib.Path) -> bool:
    """Si la interfaz está funcionando.

    No basta con mirar si `operstate` dice «up»: el bucle local y los túneles
    responden «unknown» porque su driver no informa del estado del enlace, y
    llamarlas paradas sería mentir sobre una interfaz que está trabajando. Ahí
    manda el `carrier`.
    """
    estado = (operstate or "").lower()
    if estado == "up":
        return True
    if estado == "unknown":
        return read_int(str(base / "carrier")) == 1
    return False


def _bandera(ruta: pathlib.Path) -> Optional[bool]:
    valor = read_int(str(ruta))
    return None if valor is None else bool(valor)


def _clase(nombre: str, base: pathlib.Path, tipo: Optional[int]) -> str:
    if tipo == TIPO_LOOPBACK:
        return "loopback"
    if (base / "wireless").is_dir() or (base / "phy80211").exists():
        return "wifi"
    if (base / "bridge").is_dir():
        return "puente"
    if nombre.startswith(PREFIJOS_VIRTUALES) or not (base / "device").exists():
        return "virtual"
    return "ethernet" if tipo == TIPO_ETHERNET else "otro"


def _driver(base: pathlib.Path) -> Optional[str]:
    enlace = base / "device" / "driver"
    try:
        return enlace.resolve().name if enlace.exists() else None
    except OSError:
        return None


def _identidad_pci(base: pathlib.Path) -> dict:
    """El modelo de la tarjeta, si cuelga del bus PCI."""
    dispositivo = base / "device"
    if not dispositivo.exists():
        return {}

    def hexa(campo: str) -> Optional[int]:
        crudo = read_text(str(dispositivo / campo))
        try:
            return int(crudo, 16) if crudo else None
        except ValueError:
            return None

    vendedor, aparato = hexa("vendor"), hexa("device")
    datos: dict = {}
    try:
        datos["pci_slot"] = dispositivo.resolve().name
    except OSError:
        pass
    if vendedor is None or aparato is None:
        return datos

    nombres = pciids.lookup([(vendedor, aparato)])
    if encontrado := nombres.get((vendedor, aparato)):
        datos["vendor"], datos["model"] = encontrado
    return datos


def _rutas_por_defecto() -> dict[str, str]:
    """Por qué interfaz sale el tráfico a internet, y hacia qué puerta.

    Las direcciones en `/proc/net/route` van en hexadecimal y del revés, que es
    como las guarda el kernel en memoria.
    """
    encontradas: dict[str, str] = {}
    try:
        with open(PROC_ROUTE, encoding="utf-8") as fichero:
            next(fichero, None)
            for linea in fichero:
                campos = linea.split()
                if len(campos) < 3 or campos[1] != "00000000":
                    continue
                try:
                    puerta = socket.inet_ntoa(bytes.fromhex(campos[2])[::-1])
                except (ValueError, OSError):
                    continue
                encontradas.setdefault(campos[0], puerta)
    except OSError:
        return {}
    return encontradas


def _ipv6_por_interfaz() -> dict[str, tuple[str, ...]]:
    """Las direcciones IPv6, que el kernel escribe sin los dos puntos."""
    encontradas: dict[str, list[str]] = {}
    try:
        with open(PROC_IPV6, encoding="utf-8") as fichero:
            for linea in fichero:
                campos = linea.split()
                if len(campos) < 6:
                    continue
                try:
                    direccion = socket.inet_ntop(socket.AF_INET6,
                                                 bytes.fromhex(campos[0]))
                except (ValueError, OSError):
                    continue
                encontradas.setdefault(campos[5], []).append(direccion)
    except OSError:
        return {}
    return {nombre: tuple(lista) for nombre, lista in encontradas.items()}
