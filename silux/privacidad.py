"""Quitarle a una foto del equipo lo que identifica a quien la sacó.

El informe de fallos ya tapa estos campos al escribirlos, porque está pensado
para pegarlo en un issue público. Una captura de pantalla tiene el mismo
problema y no tenía la misma salida: el número de serie de la gráfica y el
nombre del equipo salen en la ventana, y de ahí a un foro o al README de un
repositorio hay un paso.

No se borran los datos: se sustituyen por algo del mismo largo y con la misma
pinta, para que la ventana siga midiendo lo mismo y la captura enseñe cómo se
ve el programa de verdad.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import os
import pathlib
import pwd
import re
import socket
from typing import Optional

from . import sysroot
from .model import Snapshot, short_vendor

# Lo que se pone en lugar de lo de cada uno. El nombre y la IPv4 parecen de
# una casa cualquiera a propósito (decisión del autor, 19 de noviembre de
# 2026): una red 192.168.1.x con su puerta en .1 es la más común que hay, y
# quien lee un informe no se para en ella. `tools/comprobar_privacidad.py` las
# acepta por ser estas; cualquier otra privada la da por real.
EQUIPO = "silux-pc"
IPV4 = "192.168.1.120"
PUERTA = "192.168.1.1"
# Del bloque que la RFC 3849 y la RFC 7042 reservan para documentación: no
# encaminan a ninguna parte.
IPV6 = "2001:db8::11"
MAC = "00:00:5e:00:53:af"
# La de una interfaz que no tiene: el bucle local. No es de nadie.
SIN_MAC = "00:00:00:00:00:00"
# Lo que se ponía hasta el 19 de noviembre de 2026, tan inventado como lo de
# ahora: los volcados de antes lo llevan. «equipo» además es una palabra, y
# tomarlo por el nombre de la máquina tapaba «Este equipo no publica…».
SUSTITUTOS_ANTERIORES = frozenset({"equipo", "192.0.2.11", "192.0.2.1"})
# Lo que se pone en lugar de una interfaz con un nombre elegido por alguien.
INTERFAZ = "interfaz{}"

# Los nombres que pone el sistema y no una persona: los predecibles de systemd
# (`enp6s0`, `wlo1`, `enx001122334455`), los clásicos del kernel y los de las
# herramientas que crean interfaces solas —Docker, libvirt, Tailscale,
# WireGuard con su nombre de ejemplo—. Son los que hacen falta para
# diagnosticar y no dicen nada de nadie. Lo demás lo eligió alguien, y eso es
# justo lo que puede llevar su nombre: un `wg-quick` con el fichero
# `ana_wg0.conf` crea una interfaz `ana_wg0`, y ningún sustituto del hostname
# sabe que «ana» es una persona. Por eso aquí se enumera lo permitido, no lo
# prohibido, y los patrones son estrictos: con `en*` a secas, `enrique-vpn`
# pasaría por una tarjeta de red.
_DEL_SISTEMA = re.compile(r"""
    lo
  | (?:en|wl|ww|ib|sl)(?:x[0-9a-f]{12}|[oPpscvabui]\d+(?:[fdnsupcvi]\d+)*)
  | (?:eth|wlan|wwan|usb|bond|team|dummy|tun|tap|ppp|wg|vmnet|vboxnet|virbr
      |lxcbr|lxdbr|incusbr|podman|docker|tailscale|cni|vxlan|macvtap|can|sit
      |gre|gretap|erspan|ip6tnl|ipip|ip_vti|ip6_vti|nlmon|rndis|br)\d+(?:-nic)?
  | interfaz\d+
  | br-[0-9a-f]{12}
  | veth[0-9a-f]+
  | zt[0-9a-z]{8,10}
  | flannel\.\d+
  | cali[0-9a-f]{11}
  | nordlynx
""", re.VERBOSE)


# Los puntos de montaje que pone el sistema y no dicen nada de nadie. Los
# demás llevan el nombre del usuario o la etiqueta que alguien le puso a un
# disco: `/run/media/ana/FOTOS`, `/home/ana/datos`.
_MONTAJES_DEL_SISTEMA = frozenset((
    "/", "/boot", "/boot/efi", "/efi", "/home", "/root", "/usr", "/var",
    "/var/log", "/var/lib", "/var/cache", "/opt", "/srv", "/tmp", "/nix",
    "/gnu", "/snap", "/swap", "/recovery",
))
MONTAJE = "/media/unidad{}"


# Kernel parameters whose value names this machine: a disk, an encrypted
# volume, the machine itself or its address.
_IDENTIFYING_PARAMETERS = {
    "root", "resume", "cryptdevice", "cryptkey", "rd.luks.uuid", "rd.luks.name",
    "luks.uuid", "luks.name", "rd.md.uuid", "rd.lvm.lv", "ip", "hostname",
    "systemd.hostname", "systemd.machine_id", "netroot", "nfsroot",
}
_TAGGED = re.compile(r"\b(UUID|PARTUUID|LABEL|PARTLABEL)=[^\s,:]+")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def hide_cmdline_identifiers(cmdline: str) -> tuple[str, ...]:
    """The kernel command line, parameter by parameter, without what names
    the machine: every parameter stays, with its name, but the value of the
    ones above, and any UUID or label, become «…». Done when it is read, so
    neither the window, nor a report, nor a dump ever holds it."""
    hidden = []
    for parameter in cmdline.split():
        key, separator, _value = parameter.partition("=")
        if separator and key in _IDENTIFYING_PARAMETERS:
            parameter = f"{key}=…"
        else:
            parameter = _UUID.sub("…", _TAGGED.sub(lambda m: f"{m.group(1)}=…", parameter))
        hidden.append(parameter)
    return tuple(hidden)


def de_sistema(nombre: str) -> bool:
    """Si una interfaz se llama como la llama el sistema y no una persona."""
    return bool(_DEL_SISTEMA.fullmatch(nombre))


# A USB network adapter is named after its MAC: «enx» and twelve digits.
# The name is the system's, but it carries the address.
MAC_EN_EL_NOMBRE = re.compile(r"((?:en|wl|ww)x)([0-9a-f]{12})")


def nombre_sin_mac(nombre: str, orden: int) -> str:
    """`enx001122334455` with the substitute MAC number `orden` in its name."""
    encaje = MAC_EN_EL_NOMBRE.fullmatch(nombre)
    if encaje is None:
        return nombre
    return encaje.group(1) + _mac_falsa(orden).replace(":", "")


# Lo que pone el anonimizado, y por eso no es de nadie: encontrarlo en un
# volcado es encontrar el sustituto. Uno de verdad puede valer lo mismo —una
# puerta de enlace 192.168.1.1 es lo más común—, y entonces está tan tapado
# como el resto.
_SUSTITUTO_NUMERADO = re.compile(r"interfaz\d+|/media/unidad\d+|00:00:5e:00:53:[0-9a-f]{2}"
                                 r"|(?:en|wl|ww)x00005e0053[0-9a-f]{2}")


def es_sustituto(valor: str) -> bool:
    """Si es lo que pone el anonimizado (o ceros), no algo de alguien."""
    limpio = (valor or "").strip().lower()
    return (limpio in {EQUIPO, IPV4, PUERTA, IPV6, MAC, SIN_MAC, *SUSTITUTOS_ANTERIORES}
            or not limpio.strip("0:.- ") or bool(_SUSTITUTO_NUMERADO.fullmatch(limpio)))


# The names a machine can have that are everyone's: the installer's default
# is the distribution («debian»), or it is the brand («lenovo»). Covered in
# the texts it broke them («ID=silux-pc» in os-release), and looked for it
# was found in the distribution's name.
_EQUIPOS_DE_TODOS = frozenset({
    "localhost", "localhost.localdomain", "linux", "home", "casa", "server", "servidor",
    "desktop", "escritorio", "laptop", "notebook", "portatil", "portátil", "computer",
    "ordenador", "workstation", "gaming", "router", "nas", "pc", "user", "usuario"})
# A name this short is a word or initials: it cannot block the annex.
EQUIPO_CORTO = 4


def palabras_de_todos(*textos: Optional[str]) -> frozenset[str]:
    """The words of a system's description (distribution, brand) and the
    default names, lowercased."""
    palabras = set(_EQUIPOS_DE_TODOS)
    for texto in textos:
        if texto:
            palabras.add(texto.strip().lower())
            palabras.update(p for p in re.split(r"[\s/(),\"]+", texto.lower()) if len(p) >= 3)
            if (corto := short_vendor(texto)):
                palabras.add(corto.lower())
    return frozenset(palabras)


def palabras_del_equipo(raiz: str = "/") -> frozenset[str]:
    """Lo mismo, leído de un sistema: `/etc/os-release` y los fabricantes de
    la tabla DMI (de esta máquina, o de un volcado)."""
    base = pathlib.Path(raiz)
    textos = []
    for linea in _leer(base / "etc/os-release").splitlines():
        clave, _igual, valor = linea.partition("=")
        if clave in ("ID", "ID_LIKE", "NAME", "VERSION_CODENAME"):
            textos.append(valor.strip().strip('"'))
    for nombre in ("sys_vendor", "board_vendor", "chassis_vendor", "product_family",
                   "product_name", "board_name"):
        textos.append(_leer(base / "sys/class/dmi/id" / nombre))
    # And what drivers, modules and sensor chips are called: «thinkpad» is
    # thinkpad_acpi's chip and a common name for a ThinkPad.
    nombres = set()
    for patron in ("sys/module/*", "sys/bus/*/drivers/*"):
        nombres.update(p.name for p in base.glob(patron))
    nombres.update(_leer(p) for p in base.glob("sys/class/hwmon/*/name"))
    return palabras_de_todos(*textos) | {n.lower() for n in nombres if n} | {
        parte for n in nombres if n for parte in re.split(r"[_-]", n.lower()) if len(parte) >= 3}


def equipo_de_todos(nombre: Optional[str], palabras: frozenset[str]) -> bool:
    """A machine's name that is everyone's: the brand, the distribution, a
    driver, a common word or a short one. It cannot block the annex."""
    if not nombre:
        return False
    limpio = nombre.strip().lower()
    return len(limpio) <= EQUIPO_CORTO or limpio in palabras


def _cambiar_nombres(texto: Optional[str], cambios: dict[str, str]) -> Optional[str]:
    """Sustituye cada nombre de interfaz cuando aparece como nombre entero."""
    if not texto:
        return texto
    for viejo, nuevo in cambios.items():
        texto = re.sub(rf"(?<![\w.-]){re.escape(viejo)}(?![\w.-])", nuevo, texto)
    return texto


def _mac_falsa(orden: int) -> str:
    """La dirección de documentación número `orden`, empezando por `MAC`.

    El bloque que reserva la RFC 7042 tiene 256, y se da la vuelta: con más
    tarjetas distintas que eso se repetiría alguna, que es mejor que salirse
    de él.
    """
    prefijo, _sep, ultimo = MAC.rpartition(":")
    return f"{prefijo}:{(int(ultimo, 16) + orden) % 256:02x}"


def _tapar(valor: Optional[str], relleno: str = "0") -> Optional[str]:
    """Mantiene el largo para que nada se recoloque al ocultarlo."""
    if not valor:
        return valor
    return relleno * len(valor)


def _sin_el_equipo(texto: Optional[str], equipo: Optional[str]) -> Optional[str]:
    """Quita el nombre del equipo de donde se haya colado.

    Hace falta porque el nombre no vive solo en su campo: una interfaz de
    Tailscale, de ZeroTier o un puente creado a mano se llaman como la
    máquina, y lo mismo el aparato de sensores que la nombra.

    Se busca como nombre entero y sin distinguir mayúsculas, que es como lo
    trata el propio sistema. Como subcadena exacta se escapaba
    «PORTATIL-ANA» y, con un hostname corto, destrozaba lo que no tenía nada
    que ver: «lan» convertía `wlan0` en `wequipo0`. Entero, un nombre de dos
    letras ya no rompe nada, así que tampoco hay que dejar de taparlo.
    """
    if not texto or not equipo or len(equipo) < 2:
        return texto
    if equipo == EQUIPO or equipo in SUSTITUTOS_ANTERIORES:
        return texto            # ya está tapado
    return re.sub(rf"(?<![0-9A-Za-z]){re.escape(equipo)}(?![0-9A-Za-z])",
                  EQUIPO, texto, flags=re.IGNORECASE)


def _limpiar(texto: Optional[str], equipo: Optional[str],
             nombres: dict[str, str]) -> Optional[str]:
    return _sin_el_equipo(_cambiar_nombres(texto, nombres), equipo)


def _de_todos(snapshot: Snapshot) -> frozenset[str]:
    """The words of this photo that are everyone's: the makers and the
    machine's family and name as the firmware writes them, the distribution,
    and the drivers and sensor chips (`palabras_del_equipo` does the same
    reading a system)."""
    placa, sistema = snapshot.board, snapshot.system
    textos = [*((placa.system_vendor, placa.vendor, placa.chassis_vendor, placa.system_family,
                 placa.system_name, placa.system_version, placa.name) if placa else ()),
              *((sistema.distribution, sistema.distribution_id) if sistema else ())]
    nombres = ({s.chip for s in snapshot.sensors if s.chip}
               | {g.driver for g in snapshot.gpus if g.driver}
               | {getattr(i, "driver", None) for i in snapshot.network} - {None})
    return palabras_de_todos(*textos) | {n.lower() for n in nombres} | {
        parte for n in nombres for parte in re.split(r"[_-]", n.lower()) if len(parte) >= 3}


def anonimizar(snapshot: Snapshot) -> Snapshot:
    """La misma foto sin lo que señala a un equipo concreto."""
    cambios: dict = {}
    equipo = snapshot.system.hostname if snapshot.system else None
    # Las interfaces con nombre puesto por alguien, numeradas en el orden en
    # que vienen. El mismo cambio se aplica después a todo lo que las nombra:
    # la red crea una rama del árbol de sensores por interfaz, y un aviso
    # puede citar una por su nombre.
    nombres: dict[str, str] = {}
    for interfaz in snapshot.network:
        if not de_sistema(interfaz.name) and interfaz.name not in nombres:
            nombres[interfaz.name] = INTERFAZ.format(len(nombres) + 1)
    con_mac = sorted({i.name for i in snapshot.network if MAC_EN_EL_NOMBRE.fullmatch(i.name)})
    for orden, nombre in enumerate(con_mac):
        nombres[nombre] = nombre_sin_mac(nombre, orden)

    if snapshot.system and snapshot.system.hostname:
        cambios["system"] = dataclasses.replace(snapshot.system, hostname=EQUIPO)
    # A machine named after its brand («lenovo» on a Lenovo): the brand is in
    # the report a dozen times and hides nothing, and looked for in the texts
    # it broke them («silux-pc LOQ 15IRH8»). The field still goes.
    if equipo and equipo_de_todos(equipo, _de_todos(snapshot)):
        equipo = None

    if snapshot.gpus:
        # El monitor también lleva su número de serie, en el EDID: se enseña
        # en la ficha de cada pantalla.
        cambios["gpus"] = tuple(
            dataclasses.replace(
                g, unique_id=_tapar(g.unique_id),
                displays=tuple(
                    dataclasses.replace(d, monitor=dataclasses.replace(
                        d.monitor, serial=_tapar(d.monitor.serial)))
                    if d.monitor else d
                    for d in g.displays))
            for g in snapshot.gpus
        )

    # Lo enchufado. El número de serie no se lee nunca, pero el inventario
    # también señala: una llave de seguridad, un micrófono concreto, el
    # modelo exacto de una cámara. Anónima, la foto dice qué clase de cosa es
    # cada una y a qué velocidad va, que es lo que hace falta para un fallo,
    # y no de qué marca.
    if snapshot.usb_devices:
        cambios["usb_devices"] = tuple(
            dataclasses.replace(u, vendor=None, product=None, usb_id=None)
            for u in snapshot.usb_devices)
    if snapshot.sound_cards:
        cambios["sound_cards"] = tuple(
            dataclasses.replace(s, name=None) if s.kind == "usb" else s
            for s in snapshot.sound_cards)
    if snapshot.cameras:
        cambios["cameras"] = tuple(dataclasses.replace(c, name=None) for c in snapshot.cameras)
    if snapshot.bluetooth:
        cambios["bluetooth"] = tuple(
            dataclasses.replace(b, product=None) for b in snapshot.bluetooth)

    if snapshot.batteries:
        cambios["batteries"] = tuple(
            dataclasses.replace(b, serial=_tapar(b.serial))
            for b in snapshot.batteries)

    if snapshot.network:
        # Cada dirección física distinta, una falsa distinta: con la misma en
        # todas, dos tarjetas salían con una sola dirección. Y la misma de
        # verdad da la misma falsa, que es lo que pasa con un puente y la
        # tarjeta que tiene debajo.
        macs: dict[str, str] = {}

        def _mac(real: Optional[str]) -> Optional[str]:
            if not real or real == SIN_MAC:
                return real
            return macs.setdefault(real.lower(), _mac_falsa(len(macs)))

        cambios["network"] = tuple(
            dataclasses.replace(
                i,
                # El nombre también: las interfaces virtuales se llaman como
                # la máquina más veces de lo que parece.
                # Las del sistema se quedan como están, aunque el equipo se
                # llame «lo» o «docker»; las demás, por su sustituto.
                name=(nombres.get(i.name, i.name) if de_sistema(i.name)
                      else _limpiar(i.name, equipo, nombres) or i.name),
                mac=_mac(i.mac),
                ipv4=IPV4 if i.ipv4 else None,
                ipv6=tuple(IPV6 for _direccion in i.ipv6),
                gateway=PUERTA if i.gateway else None,
            )
            for i in snapshot.network
        )

    if snapshot.disks:
        montajes: dict[str, str] = {}

        def _montaje(ruta: Optional[str]) -> Optional[str]:
            if not ruta or ruta in _MONTAJES_DEL_SISTEMA:
                return ruta
            return montajes.setdefault(ruta, MONTAJE.format(len(montajes) + 1))

        cambios["disks"] = tuple(
            dataclasses.replace(
                d, serial=_tapar(d.serial),
                partitions=tuple(dataclasses.replace(p, mountpoint=_montaje(p.mountpoint))
                                 for p in d.partitions))
            for d in snapshot.disks
        )

    if snapshot.sensors and (nombres or equipo):
        sensores = tuple(
            # La clave también, aunque no se pinte: va en la foto y en lo que
            # se exporte de ella. El cambio es el mismo en cada muestreo, así
            # que los mínimos y máximos que cuelgan de ella no se pierden.
            dataclasses.replace(s, key=_limpiar(s.key, equipo, nombres),
                                device=_limpiar(s.device, equipo, nombres),
                                label=_limpiar(s.label, equipo, nombres))
            for s in snapshot.sensors)
        if sensores != snapshot.sensors:
            cambios["sensors"] = sensores

    if snapshot.notes and (nombres or equipo):
        avisos = tuple(
            dataclasses.replace(n, message=_limpiar(n.message, equipo, nombres),
                                hint=_limpiar(n.hint, equipo, nombres))
            for n in snapshot.notes)
        if avisos != snapshot.notes:
            cambios["notes"] = avisos

    return dataclasses.replace(snapshot, **cambios) if cambios else snapshot


def _leer(ruta: pathlib.Path) -> str:
    try:
        return ruta.read_text(errors="ignore").strip()
    except OSError:
        return ""


# -- lo de esta máquina ----------------------------------------------------------

def _trozos_de_ipv6(direccion: ipaddress.IPv6Address) -> dict[str, str]:
    """La dirección y lo que de ella basta para reconocer la máquina.

    La mitad baja (el identificador de interfaz) es estable en una conexión y
    no cambia con la red; en una global, además, la mitad alta dice de quién
    es la conexión. Un test llegó a llevar una `fe80::` con los dos primeros
    grupos del identificador de la máquina del autor y el resto a mano.
    """
    trozos = {}
    hexa = direccion.exploded.replace(":", "")
    trozos[hexa] = "una dirección IPv6 de este equipo"
    trozos[str(direccion)] = "una dirección IPv6 de este equipo"
    grupos = direccion.exploded.split(":")
    identificador = grupos[4:]
    for i in range(3):
        par = identificador[i:i + 2]
        if all(int(g, 16) == 0 for g in par):
            continue
        trozos["".join(par)] = "parte del identificador IPv6 de este equipo"
        trozos[":".join(f"{int(g, 16):x}" for g in par)] = \
            "parte del identificador IPv6 de este equipo"
    if direccion.is_global:
        prefijo = ":".join(f"{int(g, 16):x}" for g in grupos[:3])
        trozos[prefijo] = "el prefijo IPv6 de la conexión de este equipo"
    return trozos


def _direcciones_propias() -> dict[str, str]:
    datos: dict[str, str] = {}
    for linea in _leer(pathlib.Path("/proc/net/if_inet6")).splitlines():
        campos = linea.split()
        if not campos:
            continue
        try:
            direccion = ipaddress.IPv6Address(int(campos[0], 16))
        except ValueError:
            continue
        if direccion.is_loopback:
            continue
        datos.update(_trozos_de_ipv6(direccion))
    # /proc/net/fib_trie dice cada dirección local con «/32 host LOCAL» debajo.
    anterior = None
    for linea in _leer(pathlib.Path("/proc/net/fib_trie")).splitlines():
        if (m := re.search(r"\|-- (\d+\.\d+\.\d+\.\d+)$", linea)):
            anterior = m.group(1)
        elif "/32 host LOCAL" in linea and anterior and not anterior.startswith("127."):
            datos[anterior] = "una dirección IPv4 de este equipo"
    return datos


# Lo que el firmware pone cuando no hay número de serie. Buscarlo daría por
# delatora cualquier línea de código que lo reconozca.
_RELLENO = re.compile(r"(?i)filled by o\.?e\.?m|default string|not specified|system serial|"
                      r"chassis serial|^none$|^n/a$|0123456789|^unknown$")


# Un concentrador raíz de USB da como «número de serie» su dirección PCI
# («0000:00:14.0»), que está en cualquier ruta de sysfs y no es de nadie.
_DIRECCION_PCI = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def _series_propias() -> dict[str, str]:
    """Los números de serie que se leen sin permisos (y los otros, si se puede)."""
    datos: dict[str, str] = {}
    sitios = {
        "/sys/block/*/device/serial": "el número de serie de un disco",
        "/sys/class/nvme/*/serial": "el número de serie de un disco",
        "/sys/block/*/device/wwid": "el identificador de un disco",
        "/sys/bus/usb/devices/*/serial": "el número de serie de algo enchufado por USB",
        "/sys/class/drm/card*/device/unique_id": "el número de serie de la gráfica",
        "/sys/class/dmi/id/product_uuid": "el UUID del equipo",
        "/sys/class/dmi/id/product_serial": "el número de serie del equipo",
        "/sys/class/dmi/id/board_serial": "el número de serie de la placa",
        "/sys/class/dmi/id/chassis_serial": "el número de serie del chasis",
        "/etc/machine-id": "el machine-id",
    }
    for patron, que_es in sitios.items():
        for ruta in pathlib.Path("/").glob(patron.lstrip("/")):
            valor = _leer(ruta)
            for trozo in {valor, valor.split()[-1] if valor.split() else ""}:
                if (len(trozo) >= 6 and trozo.strip("0 ") and not _RELLENO.search(trozo)
                        and not _DIRECCION_PCI.match(trozo)):
                    datos[trozo] = que_es
    for ruta in pathlib.Path("/sys/class/drm").glob("card*-*/edid"):
        try:
            edid = ruta.read_bytes()
        except OSError:
            continue
        for texto in _series_de_edid(edid):
            datos[texto] = "el número de serie de un monitor"
    return datos


def _series_de_edid(edid: bytes) -> list[str]:
    """El texto del descriptor de número de serie (0xFF), si no está a ceros."""
    series = []
    for inicio in range(54, 126, 18):
        bloque = edid[inicio:inicio + 18]
        if len(bloque) == 18 and bloque[:3] == b"\0\0\0" and bloque[3] == 0xFF:
            texto = bloque[5:].split(b"\n")[0].decode("latin-1").strip()
            if len(texto) >= 4 and texto.strip("0 "):
                series.append(texto)
    return series


def de_esta_maquina() -> dict[str, str]:
    """Lo que identifica al equipo donde se está trabajando ahora mismo."""
    datos = {}
    if not equipo_de_todos(socket.gethostname(), palabras_del_equipo(str(sysroot.raiz() or "/"))):
        datos[socket.gethostname()] = "el nombre de este equipo"
    for ruta in pathlib.Path("/sys/class/net").glob("*/address"):
        mac = _leer(ruta)
        if mac and not mac.startswith("00:00:00"):
            datos[mac] = f"la dirección física de {ruta.parent.name}"
            # As a USB adapter's name carries it: «enx» and the digits.
            datos[mac.replace(":", "").lower()] = f"la dirección física de {ruta.parent.name}"
        nombre = ruta.parent.name
        if not de_sistema(nombre) or MAC_EN_EL_NOMBRE.fullmatch(nombre):
            datos[nombre] = "una interfaz de red con nombre puesto a mano"
    datos.update(_direcciones_propias())
    datos.update(_series_propias())
    if (casa := pathlib.Path.home()).name:
        datos[str(casa)] = "la carpeta personal"
    try:
        nombre_real = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except KeyError:
        nombre_real = ""
    if len(nombre_real) >= 4 and nombre_real != pwd.getpwuid(os.getuid()).pw_name:
        datos[nombre_real] = "el nombre de quien usa este equipo"
    # What is a substitute is not this machine's, though it may be its value
    # (a real 192.168.1.120 is the report's IPv4).
    return {d: q for d, q in datos.items() if d and len(d) >= 4 and not es_sustituto(d)}


# Una dirección de correo, y las que no son de nadie.
CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CORREOS_PERMITIDOS = re.compile(
    r"(noreply@anthropic\.com|noreply@github\.com|git@github\.com"
    r"|@example\.(com|org|net)|@kernel\.org)$", re.I)
