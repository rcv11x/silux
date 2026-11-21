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
HOST_NAME = "silux-pc"
IPV4 = "192.168.1.120"
GATEWAY = "192.168.1.1"
# Del bloque que la RFC 3849 y la RFC 7042 reservan para documentación: no
# encaminan a ninguna parte.
IPV6 = "2001:db8::11"
MAC = "00:00:5e:00:53:af"
# La de una interfaz que no tiene: el bucle local. No es de nadie.
NO_MAC = "00:00:00:00:00:00"
# Lo que se ponía hasta el 19 de noviembre de 2026, tan inventado como lo de
# ahora: los volcados de antes lo llevan. «equipo» además es una palabra, y
# tomarlo por el nombre de la máquina tapaba «Este equipo no publica…».
OLD_SUBSTITUTES = frozenset({"equipo", "192.0.2.11", "192.0.2.1"})
# Lo que se pone en lugar de una interfaz con un nombre elegido por alguien.
INTERFACE = "interfaz{}"

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
_SYSTEM_NAME = re.compile(r"""
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
_SYSTEM_MOUNTS = frozenset((
    "/", "/boot", "/boot/efi", "/efi", "/home", "/root", "/usr", "/var",
    "/var/log", "/var/lib", "/var/cache", "/opt", "/srv", "/tmp", "/nix",
    "/gnu", "/snap", "/swap", "/recovery",
))
MOUNT = "/media/unidad{}"


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


def is_system_name(name: str) -> bool:
    """Si una interfaz se llama como la llama el sistema y no una persona."""
    return bool(_SYSTEM_NAME.fullmatch(name))


# A USB network adapter is named after its MAC: «enx» and twelve digits.
# The name is the system's, but it carries the address.
MAC_IN_NAME = re.compile(r"((?:en|wl|ww)x)([0-9a-f]{12})")


def name_without_mac(name: str, index: int) -> str:
    """`enx001122334455` with the substitute MAC number `orden` in its name."""
    match = MAC_IN_NAME.fullmatch(name)
    if match is None:
        return name
    return match.group(1) + _fake_mac(index).replace(":", "")


# Lo que pone el anonimizado, y por eso no es de nadie: encontrarlo en un
# volcado es encontrar el sustituto. Uno de verdad puede valer lo mismo —una
# puerta de enlace 192.168.1.1 es lo más común—, y entonces está tan tapado
# como el resto.
_NUMBERED_SUBSTITUTE = re.compile(r"interfaz\d+|/media/unidad\d+|00:00:5e:00:53:[0-9a-f]{2}"
                                 r"|(?:en|wl|ww)x00005e0053[0-9a-f]{2}")


def is_substitute(value: str) -> bool:
    """Si es lo que pone el anonimizado (o ceros), no algo de alguien."""
    clean = (value or "").strip().lower()
    return (clean in {HOST_NAME, IPV4, GATEWAY, IPV6, MAC, NO_MAC, *OLD_SUBSTITUTES}
            or not clean.strip("0:.- ") or bool(_NUMBERED_SUBSTITUTE.fullmatch(clean)))


# The names a machine can have that are everyone's: the installer's default
# is the distribution («debian»), or it is the brand («lenovo»). Covered in
# the texts it broke them («ID=silux-pc» in os-release), and looked for it
# was found in the distribution's name.
_COMMON_HOST_NAMES = frozenset({
    "localhost", "localhost.localdomain", "linux", "home", "casa", "server", "servidor",
    "desktop", "escritorio", "laptop", "notebook", "portatil", "portátil", "computer",
    "ordenador", "workstation", "gaming", "router", "nas", "pc", "user", "usuario"})
# A name this short is a word or initials: it cannot block the annex.
SHORT_HOST_NAME = 4


def common_words(*texts: Optional[str]) -> frozenset[str]:
    """The words of a system's description (distribution, brand) and the
    default names, lowercased."""
    words = set(_COMMON_HOST_NAMES)
    for text in texts:
        if text:
            words.add(text.strip().lower())
            words.update(p for p in re.split(r"[\s/(),\"]+", text.lower()) if len(p) >= 3)
            if (short := short_vendor(text)):
                words.add(short.lower())
    return frozenset(words)


def machine_words(root: str = "/") -> frozenset[str]:
    """Lo mismo, leído de un sistema: `/etc/os-release` y los fabricantes de
    la tabla DMI (de esta máquina, o de un volcado)."""
    base = pathlib.Path(root)
    texts = []
    for line in _read(base / "etc/os-release").splitlines():
        key, _sep, value = line.partition("=")
        if key in ("ID", "ID_LIKE", "NAME", "VERSION_CODENAME"):
            texts.append(value.strip().strip('"'))
    for name in ("sys_vendor", "board_vendor", "chassis_vendor", "product_family",
                   "product_name", "board_name"):
        texts.append(_read(base / "sys/class/dmi/id" / name))
    # And what drivers, modules and sensor chips are called: «thinkpad» is
    # thinkpad_acpi's chip and a common name for a ThinkPad.
    names = set()
    for pattern in ("sys/module/*", "sys/bus/*/drivers/*"):
        names.update(p.name for p in base.glob(pattern))
    names.update(_read(p) for p in base.glob("sys/class/hwmon/*/name"))
    return common_words(*texts) | {n.lower() for n in names if n} | {
        part for n in names if n for part in re.split(r"[_-]", n.lower()) if len(part) >= 3}


def is_common_host_name(name: Optional[str], words: frozenset[str]) -> bool:
    """A machine's name that is everyone's: the brand, the distribution, a
    driver, a common word or a short one. It cannot block the annex."""
    if not name:
        return False
    clean = name.strip().lower()
    return len(clean) <= SHORT_HOST_NAME or clean in words


def _rename(text: Optional[str], changes: dict[str, str]) -> Optional[str]:
    """Sustituye cada nombre de interfaz cuando aparece como nombre entero."""
    if not text:
        return text
    for old, new in changes.items():
        text = re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w.-])", new, text)
    return text


def _fake_mac(index: int) -> str:
    """La dirección de documentación número `orden`, empezando por `MAC`.

    El bloque que reserva la RFC 7042 tiene 256, y se da la vuelta: con más
    tarjetas distintas que eso se repetiría alguna, que es mejor que salirse
    de él.
    """
    prefix, _sep, last = MAC.rpartition(":")
    return f"{prefix}:{(int(last, 16) + index) % 256:02x}"


def _mask(value: Optional[str], fill: str = "0") -> Optional[str]:
    """Mantiene el largo para que nada se recoloque al ocultarlo."""
    if not value:
        return value
    return fill * len(value)


def _without_host(text: Optional[str], host: Optional[str]) -> Optional[str]:
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
    if not text or not host or len(host) < 2:
        return text
    if host == HOST_NAME or host in OLD_SUBSTITUTES:
        return text            # ya está tapado
    return re.sub(rf"(?<![0-9A-Za-z]){re.escape(host)}(?![0-9A-Za-z])",
                  HOST_NAME, text, flags=re.IGNORECASE)


def _clean(text: Optional[str], host: Optional[str],
             names: dict[str, str]) -> Optional[str]:
    return _without_host(_rename(text, names), host)


def without_home(text: str) -> str:
    """A traceback names where Silux runs from, and from a checkout that is
    inside the user's home folder."""
    home = str(pathlib.Path.home())
    return text.replace(home, "~") if len(home) > 1 else text


def _common_words_of(snapshot: Snapshot) -> frozenset[str]:
    """The words of this photo that are everyone's: the makers and the
    machine's family and name as the firmware writes them, the distribution,
    and the drivers and sensor chips (`palabras_del_equipo` does the same
    reading a system)."""
    board, system = snapshot.board, snapshot.system
    texts = [*((board.system_vendor, board.vendor, board.chassis_vendor, board.system_family,
                 board.system_name, board.system_version, board.name) if board else ()),
              *((system.distribution, system.distribution_id) if system else ())]
    names = ({s.chip for s in snapshot.sensors if s.chip}
               | {g.driver for g in snapshot.gpus if g.driver}
               | {getattr(i, "driver", None) for i in snapshot.network} - {None})
    return common_words(*texts) | {n.lower() for n in names} | {
        part for n in names for part in re.split(r"[_-]", n.lower()) if len(part) >= 3}


def _mask_address(address: Optional[str], substitute: str) -> Optional[str]:
    """The substitute, but the loopback stays: 127.0.0.1 and ::1 are
    everyone's, and with the substitute «lo» read like a network card. A
    link-local address (fe80::) is covered: it can carry the MAC."""
    if not address:
        return None
    try:
        if ipaddress.ip_address(address.split("/")[0].split("%")[0]).is_loopback:
            return address
    except ValueError:
        pass
    return substitute


def anonymize(snapshot: Snapshot) -> Snapshot:
    """La misma foto sin lo que señala a un equipo concreto."""
    changes: dict = {}
    host = snapshot.system.hostname if snapshot.system else None
    # Las interfaces con nombre puesto por alguien, numeradas en el orden en
    # que vienen. El mismo cambio se aplica después a todo lo que las nombra:
    # la red crea una rama del árbol de sensores por interfaz, y un aviso
    # puede citar una por su nombre.
    names: dict[str, str] = {}
    for interface in snapshot.network:
        if not is_system_name(interface.name) and interface.name not in names:
            names[interface.name] = INTERFACE.format(len(names) + 1)
    with_mac = sorted({i.name for i in snapshot.network if MAC_IN_NAME.fullmatch(i.name)})
    for index, name in enumerate(with_mac):
        names[name] = name_without_mac(name, index)

    if snapshot.system and snapshot.system.hostname:
        changes["system"] = dataclasses.replace(snapshot.system, hostname=HOST_NAME)
    # A machine named after its brand («lenovo» on a Lenovo): the brand is in
    # the report a dozen times and hides nothing, and looked for in the texts
    # it broke them («silux-pc LOQ 15IRH8»). The field still goes.
    if host and is_common_host_name(host, _common_words_of(snapshot)):
        host = None

    if snapshot.gpus:
        # El monitor también lleva su número de serie, en el EDID: se enseña
        # en la ficha de cada pantalla.
        changes["gpus"] = tuple(
            dataclasses.replace(
                g, unique_id=_mask(g.unique_id),
                displays=tuple(
                    dataclasses.replace(d, monitor=dataclasses.replace(
                        d.monitor, serial=_mask(d.monitor.serial)))
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
        changes["usb_devices"] = tuple(
            dataclasses.replace(u, vendor=None, product=None, usb_id=None)
            for u in snapshot.usb_devices)
    if snapshot.sound_cards:
        changes["sound_cards"] = tuple(
            dataclasses.replace(s, name=None) if s.kind == "usb" else s
            for s in snapshot.sound_cards)
    if snapshot.cameras:
        changes["cameras"] = tuple(dataclasses.replace(c, name=None) for c in snapshot.cameras)
    if snapshot.bluetooth:
        changes["bluetooth"] = tuple(
            dataclasses.replace(b, product=None) for b in snapshot.bluetooth)

    if snapshot.batteries:
        changes["batteries"] = tuple(
            dataclasses.replace(b, serial=_mask(b.serial))
            for b in snapshot.batteries)

    if snapshot.network:
        # Cada dirección física distinta, una falsa distinta: con la misma en
        # todas, dos tarjetas salían con una sola dirección. Y la misma de
        # verdad da la misma falsa, que es lo que pasa con un puente y la
        # tarjeta que tiene debajo.
        macs: dict[str, str] = {}

        def _mac_index(real: Optional[str]) -> Optional[str]:
            if not real or real == NO_MAC:
                return real
            return macs.setdefault(real.lower(), _fake_mac(len(macs)))

        changes["network"] = tuple(
            dataclasses.replace(
                i,
                # El nombre también: las interfaces virtuales se llaman como
                # la máquina más veces de lo que parece.
                # Las del sistema se quedan como están, aunque el equipo se
                # llame «lo» o «docker»; las demás, por su sustituto.
                name=(names.get(i.name, i.name) if is_system_name(i.name)
                      else _clean(i.name, host, names) or i.name),
                mac=_mac_index(i.mac),
                ipv4=_mask_address(i.ipv4, IPV4),
                ipv6=tuple(_mask_address(d, IPV6) for d in i.ipv6),
                gateway=GATEWAY if i.gateway else None,
            )
            for i in snapshot.network
        )

    if snapshot.disks:
        mounts: dict[str, str] = {}

        def _mount_index(path: Optional[str]) -> Optional[str]:
            if not path or path in _SYSTEM_MOUNTS:
                return path
            return mounts.setdefault(path, MOUNT.format(len(mounts) + 1))

        changes["disks"] = tuple(
            dataclasses.replace(
                d, serial=_mask(d.serial),
                partitions=tuple(dataclasses.replace(p, mountpoint=_mount_index(p.mountpoint))
                                 for p in d.partitions))
            for d in snapshot.disks
        )

    if snapshot.sensors and (names or host):
        sensors = tuple(
            # La clave también, aunque no se pinte: va en la foto y en lo que
            # se exporte de ella. El cambio es el mismo en cada muestreo, así
            # que los mínimos y máximos que cuelgan de ella no se pierden.
            dataclasses.replace(s, key=_clean(s.key, host, names),
                                device=_clean(s.device, host, names),
                                label=_clean(s.label, host, names))
            for s in snapshot.sensors)
        if sensors != snapshot.sensors:
            changes["sensors"] = sensors

    if snapshot.notes:
        notes = tuple(
            dataclasses.replace(n, message=without_home(_clean(n.message, host, names) or ""),
                                hint=_clean(n.hint, host, names),
                                detail=without_home(_clean(n.detail, host, names) or ""))
            for n in snapshot.notes)
        if notes != snapshot.notes:
            changes["notes"] = notes

    if snapshot.failures:
        changes["failures"] = tuple(
            dataclasses.replace(f, error=without_home(_clean(f.error, host, names) or ""),
                                trace=without_home(_clean(f.trace, host, names) or ""))
            for f in snapshot.failures)

    return dataclasses.replace(snapshot, **changes) if changes else snapshot


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(errors="ignore").strip()
    except OSError:
        return ""


# -- lo de esta máquina ----------------------------------------------------------

def _ipv6_parts(address: ipaddress.IPv6Address) -> dict[str, str]:
    """La dirección y lo que de ella basta para reconocer la máquina.

    La mitad baja (el identificador de interfaz) es estable en una conexión y
    no cambia con la red; en una global, además, la mitad alta dice de quién
    es la conexión. Un test llegó a llevar una `fe80::` con los dos primeros
    grupos del identificador de la máquina del autor y el resto a mano.
    """
    parts = {}
    hex_text = address.exploded.replace(":", "")
    parts[hex_text] = "una dirección IPv6 de este equipo"
    parts[str(address)] = "una dirección IPv6 de este equipo"
    groups = address.exploded.split(":")
    interface_id = groups[4:]
    for i in range(3):
        pair = interface_id[i:i + 2]
        if all(int(g, 16) == 0 for g in pair):
            continue
        parts["".join(pair)] = "parte del identificador IPv6 de este equipo"
        parts[":".join(f"{int(g, 16):x}" for g in pair)] = \
            "parte del identificador IPv6 de este equipo"
    if address.is_global:
        prefix = ":".join(f"{int(g, 16):x}" for g in groups[:3])
        parts[prefix] = "el prefijo IPv6 de la conexión de este equipo"
    return parts


def _own_addresses() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in _read(pathlib.Path("/proc/net/if_inet6")).splitlines():
        fields = line.split()
        if not fields:
            continue
        try:
            address = ipaddress.IPv6Address(int(fields[0], 16))
        except ValueError:
            continue
        if address.is_loopback:
            continue
        data.update(_ipv6_parts(address))
    # /proc/net/fib_trie dice cada dirección local con «/32 host LOCAL» debajo.
    previous = None
    for line in _read(pathlib.Path("/proc/net/fib_trie")).splitlines():
        if (m := re.search(r"\|-- (\d+\.\d+\.\d+\.\d+)$", line)):
            previous = m.group(1)
        elif "/32 host LOCAL" in line and previous and not previous.startswith("127."):
            data[previous] = "una dirección IPv4 de este equipo"
    return data


# Lo que el firmware pone cuando no hay número de serie. Buscarlo daría por
# delatora cualquier línea de código que lo reconozca.
_FILLER = re.compile(r"(?i)filled by o\.?e\.?m|default string|not specified|system serial|"
                      r"chassis serial|^none$|^n/a$|0123456789|^unknown$")


# Un concentrador raíz de USB da como «número de serie» su dirección PCI
# («0000:00:14.0»), que está en cualquier ruta de sysfs y no es de nadie.
_PCI_ADDRESS = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def _own_serials() -> dict[str, str]:
    """Los números de serie que se leen sin permisos (y los otros, si se puede)."""
    data: dict[str, str] = {}
    places = {
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
    for pattern, kind in places.items():
        for path in pathlib.Path("/").glob(pattern.lstrip("/")):
            value = _read(path)
            for chunk in {value, value.split()[-1] if value.split() else ""}:
                if (len(chunk) >= 6 and chunk.strip("0 ") and not _FILLER.search(chunk)
                        and not _PCI_ADDRESS.match(chunk)):
                    data[chunk] = kind
    for path in pathlib.Path("/sys/class/drm").glob("card*-*/edid"):
        try:
            edid = path.read_bytes()
        except OSError:
            continue
        for text in _edid_serials(edid):
            data[text] = "el número de serie de un monitor"
    return data


def _edid_serials(edid: bytes) -> list[str]:
    """El texto del descriptor de número de serie (0xFF), si no está a ceros."""
    serials = []
    for start in range(54, 126, 18):
        block = edid[start:start + 18]
        if len(block) == 18 and block[:3] == b"\0\0\0" and block[3] == 0xFF:
            text = block[5:].split(b"\n")[0].decode("latin-1").strip()
            if len(text) >= 4 and text.strip("0 "):
                serials.append(text)
    return serials


def of_this_machine() -> dict[str, str]:
    """Lo que identifica al equipo donde se está trabajando ahora mismo."""
    data = {}
    if not is_common_host_name(socket.gethostname(), machine_words(str(sysroot.root() or "/"))):
        data[socket.gethostname()] = "el nombre de este equipo"
    for path in pathlib.Path("/sys/class/net").glob("*/address"):
        mac = _read(path)
        if mac and not mac.startswith("00:00:00"):
            data[mac] = f"la dirección física de {path.parent.name}"
            # As a USB adapter's name carries it: «enx» and the digits.
            data[mac.replace(":", "").lower()] = f"la dirección física de {path.parent.name}"
        name = path.parent.name
        if not is_system_name(name) or MAC_IN_NAME.fullmatch(name):
            data[name] = "una interfaz de red con nombre puesto a mano"
    data.update(_own_addresses())
    data.update(_own_serials())
    if (home := pathlib.Path.home()).name:
        data[str(home)] = "la carpeta personal"
    try:
        real_name = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except KeyError:
        real_name = ""
    if len(real_name) >= 4 and real_name != pwd.getpwuid(os.getuid()).pw_name:
        data[real_name] = "el nombre de quien usa este equipo"
    # What is a substitute is not this machine's, though it may be its value
    # (a real 192.168.1.120 is the report's IPv4).
    return {d: q for d, q in data.items() if d and len(d) >= 4 and not is_substitute(d)}


# Una dirección de correo, y las que no son de nadie.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAILS = re.compile(
    r"(noreply@anthropic\.com|noreply@github\.com|git@github\.com"
    r"|@example\.(com|org|net)|@kernel\.org)$", re.I)
