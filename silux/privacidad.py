"""Take out of a snapshot what identifies whoever took it.

The bug report already covers these fields when writing them, since it is
meant for a public issue. A screenshot has the same problem: the graphics
card's serial number and the machine's name appear in the window, and from
there to a forum or a repository's README is one step.

The data isn't deleted: it is replaced by something of the same length and
look, so the window measures the same and the screenshot shows how the
program really looks.
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

# What goes in place of each person's own. The name and IPv4 look like any
# home's on purpose: a 192.168.1.x network with its gateway at .1 is the most
# common there is, and whoever reads a report doesn't stop at it.
# `tools/comprobar_privacidad.py` accepts these for being these; any other
# private one it takes as real.
HOST_NAME = "silux-pc"
IPV4 = "192.168.1.120"
GATEWAY = "192.168.1.1"
# From the block RFC 3849 and RFC 7042 reserve for documentation: they route
# nowhere.
IPV6 = "2001:db8::11"
MAC = "00:00:5e:00:53:af"
# That of an interface that has none: the loopback. Nobody's.
NO_MAC = "00:00:00:00:00:00"
# The earlier substitutes, as made up as today's: older dumps carry them.
# «equipo» is also a word, and taking it for the machine's name covered
# «Este equipo no publica…».
OLD_SUBSTITUTES = frozenset({"equipo", "192.0.2.11", "192.0.2.1"})
# What goes in place of an interface whose name someone chose.
INTERFACE = "interfaz{}"

# The names the system gives, not a person: systemd's predictable ones
# (`enp6s0`, `wlo1`, `enx001122334455`), the kernel's classic ones, and those
# of tools that create interfaces on their own (Docker, libvirt, Tailscale,
# WireGuard with its example name). They are what diagnosis needs and say
# nothing about anyone. The rest someone chose, and that is exactly what can
# carry their name: `wg-quick` with a `<user>_wg0.conf` file creates a
# `<user>_wg0` interface, and no hostname substitute knows that is a person.
# So what's allowed is listed, not what's forbidden, and the patterns are
# strict: with a bare `en*`, `enrique-vpn` would pass for a network card.
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


# The mount points the system sets, which say nothing about anyone. The rest
# carry the user's name or the label someone gave a disk:
# `/run/media/<user>/PHOTOS`, `/home/<user>/data`.
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
    """Whether an interface is named as the system names it, not a person."""
    return bool(_SYSTEM_NAME.fullmatch(name))


# A USB network adapter is named after its MAC: «enx» and twelve digits.
# The name is the system's, but it carries the address.
MAC_IN_NAME = re.compile(r"((?:en|wl|ww)x)([0-9a-f]{12})")


def name_without_mac(name: str, index: int) -> str:
    """`enx001122334455` with substitute MAC number `index` in its name."""
    match = MAC_IN_NAME.fullmatch(name)
    if match is None:
        return name
    return match.group(1) + fake_mac(index).replace(":", "")


# What the anonymizer writes, and so nobody's: finding it in a dump is
# finding the substitute. A real value may be the same (a 192.168.1.1
# gateway is the most common), and then it is as covered as the rest.
_NUMBERED_SUBSTITUTE = re.compile(r"interfaz\d+|/media/unidad\d+|00:00:5e:00:53:[0-9a-f]{2}"
                                 r"|(?:en|wl|ww)x00005e0053[0-9a-f]{2}")


def is_substitute(value: str) -> bool:
    """Whether it's what the anonymizer writes (or zeros), not someone's."""
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
    """The same, read from a system: `/etc/os-release` and the makers in the
    DMI table (of this machine, or of a dump)."""
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
    """Replace each interface name where it appears as a whole word."""
    if not text:
        return text
    for old, new in changes.items():
        text = re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w.-])", new, text)
    return text


_A_MAC = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")


def _any_mac(text: Optional[str]) -> Optional[str]:
    """Every MAC in a free text, the documentation one: a kernel message can
    name the router a card joined, which places the machine."""
    return _A_MAC.sub(MAC, text) if text else text


def unit_without_instance(unit: str) -> str:
    """A unit with an instance, the name after its «@», with «…» for it."""
    template, at, rest = unit.partition("@")
    if not at:
        return unit
    _instance, dot, kind = rest.rpartition(".")
    return f"{template}@…{dot}{kind}" if dot else f"{template}@…"


def fake_mac(index: int) -> str:
    """The documentation address number `index`, starting from `MAC`.

    The block RFC 7042 reserves has 256, and it wraps around: with more
    distinct cards than that one would repeat, which beats leaving the block.
    """
    prefix, _sep, last = MAC.rpartition(":")
    return f"{prefix}:{(int(last, 16) + index) % 256:02x}"


def _mask(value: Optional[str], fill: str = "0") -> Optional[str]:
    """Keep the length so nothing shifts when it's covered."""
    if not value:
        return value
    return fill * len(value)


def _without_host(text: Optional[str], host: Optional[str]) -> Optional[str]:
    """Take the machine's name out of wherever it slipped in.

    Needed because the name doesn't live only in its field: a Tailscale or
    ZeroTier interface, or a bridge made by hand, are named after the
    machine, and so is the sensor device that names it.

    Looked for as a whole word, case-insensitive, as the system itself
    treats it. As an exact substring it missed «LAPTOP-NAME» and, with a
    short hostname, wrecked unrelated text: «lan» turned `wlan0` into
    `wequipo0`. As a whole word, a two-letter name breaks nothing, so there's
    no need to stop covering it either.
    """
    if not text or not host or len(host) < 2:
        return text
    if host == HOST_NAME or host in OLD_SUBSTITUTES:
        return text            # already covered
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
    and the drivers and sensor chips (`machine_words` does the same reading a
    system)."""
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


def mount_substitutes(snapshot: Snapshot) -> dict[str, str]:
    """What goes in place of each mount point someone chose, decided once on
    the real ones so the same disk is the same «unidadN» all over a report.
    A pen drive's mount carries its owner's name and its label."""
    mounts: dict[str, str] = {}
    for disk in snapshot.disks:
        for partition in disk.partitions:
            path = partition.mountpoint
            if path and path not in _SYSTEM_MOUNTS:
                mounts.setdefault(path, MOUNT.format(len(mounts) + 1))
    return mounts


def mount_substitute(path: Optional[str], mounts: dict[str, str]) -> Optional[str]:
    """`path` as `mount_substitutes` covers it. One no longer mounted (the
    pen drive a disk test ran on) gets a number of its own."""
    if not path or path in _SYSTEM_MOUNTS:
        return path
    return mounts.get(path) or MOUNT.format(len(mounts) + 1)


def anonymize(snapshot: Snapshot) -> Snapshot:
    """The same snapshot without what points to one specific machine."""
    changes: dict = {}
    host = snapshot.system.hostname if snapshot.system else None
    # Interfaces named by someone, numbered in the order they come. The same
    # change is then applied to everything naming them: the network makes a
    # sensor-tree branch per interface, and a notice may cite one by name.
    names: dict[str, str] = {}
    for interface in snapshot.network:
        if not is_system_name(interface.name) and interface.name not in names:
            names[interface.name] = INTERFACE.format(len(names) + 1)
    with_mac = sorted({i.name for i in snapshot.network if MAC_IN_NAME.fullmatch(i.name)})
    for index, name in enumerate(with_mac):
        names[name] = name_without_mac(name, index)

    # A machine named after its brand («lenovo» on a Lenovo): the brand is in
    # the report a dozen times and hides nothing, and looked for in the texts
    # it broke them («silux-pc LOQ 15IRH8»). The field still goes.
    if host and is_common_host_name(host, _common_words_of(snapshot)):
        host = None
    if snapshot.system:
        system = snapshot.system
        covered = dataclasses.replace(
            system, hostname=HOST_NAME if system.hostname else system.hostname,
            # Where someone lives, to the city.
            timezone=None,
            # An instance can carry a name: a network, a VPN, a user.
            failed_units=(tuple(unit_without_instance(u) for u in system.failed_units)
                          if system.failed_units is not None else None),
            kernel_errors=(tuple((_any_mac(_clean(text, host, names)), times)
                                 for text, times in system.kernel_errors)
                           if system.kernel_errors is not None else None))
        if covered != system:
            changes["system"] = covered

    if snapshot.gpus:
        # The monitor carries its serial number too, in the EDID: it's shown
        # on each display's card.
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

    # What's plugged in keeps its vendor:product ids and the names it writes,
    # which name the model: without them a fingerprint reader or an infrared
    # camera can't be told apart. Its serial number is never read. The same
    # for the Bluetooth adapter, a USB device like the rest.

    if snapshot.batteries:
        changes["batteries"] = tuple(
            dataclasses.replace(b, serial=_mask(b.serial))
            for b in snapshot.batteries)

    if snapshot.network:
        # Each distinct physical address gets a distinct fake one: with the
        # same for all, two cards came out with one address. And the same
        # real one gives the same fake, as with a bridge and the card under it.
        macs: dict[str, str] = {}

        def _mac_index(real: Optional[str]) -> Optional[str]:
            if not real or real == NO_MAC:
                return real
            return macs.setdefault(real.lower(), fake_mac(len(macs)))

        changes["network"] = tuple(
            dataclasses.replace(
                i,
                # The name too: virtual interfaces are named after the machine
                # more often than it seems. The system's stay as they are,
                # even if the machine is called «lo» or «docker»; the rest go
                # by their substitute.
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
        mounts = mount_substitutes(snapshot)
        changes["disks"] = tuple(
            dataclasses.replace(
                d, serial=_mask(d.serial),
                partitions=tuple(dataclasses.replace(p, mountpoint=mount_substitute(
                    p.mountpoint, mounts)) for p in d.partitions))
            for d in snapshot.disks
        )

    if snapshot.sensors and (names or host):
        sensors = tuple(
            # The key too, though not painted: it's in the snapshot and in
            # whatever is exported from it. The change is the same every
            # sample, so the minimums and maximums hanging from it aren't lost.
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


# -- this machine's ---------------------------------------------------------------

def _ipv6_parts(address: ipaddress.IPv6Address) -> dict[str, str]:
    """The address and the parts of it enough to recognize the machine.

    The low half (the interface identifier) is stable within a connection
    and doesn't change with the network; in a global address the high half
    also says whose connection it is.
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
    # /proc/net/fib_trie gives each local address with «/32 host LOCAL» under it.
    previous = None
    for line in _read(pathlib.Path("/proc/net/fib_trie")).splitlines():
        if (m := re.search(r"\|-- (\d+\.\d+\.\d+\.\d+)$", line)):
            previous = m.group(1)
        elif "/32 host LOCAL" in line and previous and not previous.startswith("127."):
            data[previous] = "una dirección IPv4 de este equipo"
    return data


# What the firmware writes when there's no serial number. Looking for it would
# flag any line of code that recognizes it.
_FILLER = re.compile(r"(?i)filled by o\.?e\.?m|default string|not specified|system serial|"
                      r"chassis serial|^none$|^n/a$|0123456789|^unknown$")


# A USB root hub gives its PCI address («0000:00:14.0») as its «serial
# number», which is in any sysfs path and nobody's.
_PCI_ADDRESS = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def _own_serials() -> dict[str, str]:
    """The serial numbers readable without permissions (and the others, if possible)."""
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
    """The text of the serial number descriptor (0xFF), unless it's zeros."""
    serials = []
    for start in range(54, 126, 18):
        block = edid[start:start + 18]
        if len(block) == 18 and block[:3] == b"\0\0\0" and block[3] == 0xFF:
            text = block[5:].split(b"\n")[0].decode("latin-1").strip()
            if len(text) >= 4 and text.strip("0 "):
                serials.append(text)
    return serials


def of_this_machine() -> dict[str, str]:
    """What identifies the machine being worked on right now."""
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


# An email address, and those that are nobody's.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAILS = re.compile(
    r"(noreply@anthropic\.com|noreply@github\.com|git@github\.com"
    r"|@example\.(com|org|net)|@kernel\.org)$", re.I)
