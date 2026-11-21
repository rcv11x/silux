"""Network interfaces: what they are, how they connect and how much they move.

Nearly everything is in `/sys/class/net`, readable by anyone: link state,
negotiated speed, MAC, MTU and the traffic counters. The IP address isn't
there, since addresses belong to the network stack rather than the device,
so it is asked for with the old `ifconfig` ioctl.

The counters are totals since the interface came up, so the current upload
and download rates come from two readings.
"""

from __future__ import annotations

import fcntl
import os
import pathlib
import socket
import struct
import time
from typing import Optional

from .. import pciids, sysroot
from ..model import NetworkInterface, NetworkTraffic
from .base import Draft, Provider, read_int, read_text
from .counters import rate

SYS_NET = "/sys/class/net"
PROC_ROUTE = "/proc/net/route"
PROC_IPV6 = "/proc/net/if_inet6"
PROC_DEV = "/proc/net/dev"

# From <linux/sockios.h>. They need an open socket, not permissions.
SIOCGIFADDR = 0x8915
SIOCGIFNETMASK = 0x891B

COUNTERS = ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
              "rx_errors", "tx_errors", "rx_dropped", "tx_dropped")

# `type` in sysfs, from the kernel's ARPHRD_* values.
TYPE_ETHERNET, TYPE_LOOPBACK = 1, 772

# Interfaces that exist but aren't a card: VM bridges, tunnels, containers.
# Shown anyway (libvirt users want to see their bridge), marked for what they
# are.
VIRTUAL_PREFIXES = ("virbr", "docker", "veth", "br-", "tun", "tap", "vmnet",
                      "wg", "tailscale", "zt", "bond", "dummy")


class NetworkInterfaces(Provider):
    """Lists the interfaces and works out each one's traffic rate."""

    name = "network"
    provides = "network"

    def __init__(self) -> None:
        # The previous pass's counters, to subtract from.
        self._previous: dict[str, tuple[float, int, int]] = {}
        self._interval_s = 1.0
        # What doesn't change while an interface exists (its kind, driver and
        # card), by name and `ifindex`, since one deleted and recreated under
        # the same name gets a new index. Docker adds a bridge and a `veth` per
        # network and container; with forty interfaces, rereading everything
        # was about a thousand calls per sample.
        self._fixed: dict[tuple[str, Optional[int]], tuple[str, Optional[str], dict]] = {}

    def available(self) -> bool:
        return os.path.isdir(sysroot.path(SYS_NET))

    def collect(self, draft: Draft) -> None:
        self._interval_s = draft.interval_s
        names = sorted(p.name for p in pathlib.Path(sysroot.path(SYS_NET)).iterdir())
        if not names:
            return

        draft.capabilities.add("network")
        routes = _default_routes()
        addresses = _Addresses()
        ipv6 = _ipv6_by_interface()
        counters = _all_counters()
        fixed = self._fixed
        self._fixed = {}
        try:
            draft.network = [
                self._read(name, routes, addresses, ipv6.get(name, ()),
                           counters.get(name), fixed)
                for name in names
            ]
        finally:
            addresses.close()

    # -- internals ----------------------------------------------------------

    def _read(self, name: str, routes: dict[str, str], addresses: "_Addresses",
              ipv6: tuple[str, ...], counters: Optional[dict[str, int]],
              fixed: dict) -> NetworkInterface:
        base = pathlib.Path(sysroot.path(SYS_NET), name)
        key = (name, read_int(str(base / "ifindex")))
        if (known := fixed.get(key)) is None:
            known = (_kind(name, base, read_int(str(base / "type"))),
                  _driver(base), _pci_identity(base))
        self._fixed[key] = known
        kind, driver, identity = known
        speed = read_int(str(base / "speed"))

        return NetworkInterface(
            name=name,
            kind=kind,
            up=_is_up(read_text(str(base / "operstate")), base),
            carrier=_flag(base / "carrier"),
            mac=read_text(str(base / "address")) or None,
            ipv4=addresses.ip(name),
            netmask=addresses.netmask(name),
            ipv6=ipv6,
            gateway=routes.get(name),
            default_route=name in routes,
            # A down interface reports -1 as its `speed`.
            speed_mbps=speed if speed and speed > 0 else None,
            duplex=read_text(str(base / "duplex")) or None,
            mtu=read_int(str(base / "mtu")),
            driver=driver,
            traffic=self._traffic(name, base, counters),
            **identity,
        )

    def _traffic(self, name: str, base: pathlib.Path,
                 counters: Optional[dict[str, int]] = None) -> NetworkTraffic:
        values = counters or {field: read_int(str(base / "statistics" / field)) or 0
                                 for field in COUNTERS}
        now = time.monotonic()
        up = down = None

        previous = self._previous.get(name)
        if previous is not None:
            before, rx, tx = previous
            # The counters restart when the interface goes down and up again; a
            # negative delta is that, not a negative rate.
            down = rate(rx, before, values["rx_bytes"], now, self._interval_s)
            up = rate(tx, before, values["tx_bytes"], now, self._interval_s)
            if down is None or up is None:
                down = up = None
        self._previous[name] = (now, values["rx_bytes"], values["tx_bytes"])

        return NetworkTraffic(**values, rx_rate_bps=down, tx_rate_bps=up)


def _all_counters() -> dict[str, dict[str, int]]:
    """Every interface's eight counters in a single read.

    `/proc/net/dev` holds them together, where sysfs is eight files per
    interface per sample. The columns follow `dev_seq_printf_stats`
    (net/core/net-procfs.c): bytes, packets, errors and drops received, four
    more, then the same sent. Receive drops add `rx_dropped` and
    `rx_missed_errors`. A dump without this file falls back to sysfs.
    """
    out = {}
    for line in (read_text(PROC_DEV) or "").splitlines():
        name, sep, rest = line.partition(":")
        fields = rest.split()
        if not sep or len(fields) < 16:
            continue                       # the two header lines
        try:
            n = [int(c) for c in fields[:16]]
        except ValueError:
            continue
        out[name.strip()] = {
            "rx_bytes": n[0], "rx_packets": n[1], "rx_errors": n[2], "rx_dropped": n[3],
            "tx_bytes": n[8], "tx_packets": n[9], "tx_errors": n[10], "tx_dropped": n[11],
        }
    return out


class _Addresses:
    """An open socket for asking IPv4 addresses by ioctl."""

    def __init__(self) -> None:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            self._socket = None

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def ip(self, name: str) -> Optional[str]:
        return self._ask(name, SIOCGIFADDR)

    def netmask(self, name: str) -> Optional[str]:
        return self._ask(name, SIOCGIFNETMASK)

    def _ask(self, name: str, code: int) -> Optional[str]:
        return sysroot.recorded("ioctl_red", f"{name}:{code:#x}",
                                self._ask_the_kernel, name, code)

    def _ask_the_kernel(self, name: str, code: int) -> Optional[str]:
        if self._socket is None:
            return None
        try:
            reply = fcntl.ioctl(self._socket.fileno(), code,
                                    struct.pack("256s", name[:15].encode()))
        except OSError:
            # An interface without an address answers with an error, which is
            # a legitimate answer: it has no IP yet.
            return None
        return socket.inet_ntoa(reply[20:24])


# -- single readings --------------------------------------------------------

def _is_up(operstate: Optional[str], base: pathlib.Path) -> bool:
    """Whether the interface is working.

    `operstate` saying «up» isn't enough: loopback and tunnels say «unknown»
    because their driver doesn't report link state, and calling them down
    would be wrong. For those, `carrier` decides.
    """
    state = (operstate or "").lower()
    if state == "up":
        return True
    if state == "unknown":
        return read_int(str(base / "carrier")) == 1
    return False


def _flag(path: pathlib.Path) -> Optional[bool]:
    value = read_int(str(path))
    return None if value is None else bool(value)


def _kind(name: str, base: pathlib.Path, arphrd: Optional[int]) -> str:
    if arphrd == TYPE_LOOPBACK:
        return "loopback"
    if (base / "wireless").is_dir() or (base / "phy80211").exists():
        return "wifi"
    if (base / "bridge").is_dir():
        return "puente"
    if name.startswith(VIRTUAL_PREFIXES) or not (base / "device").exists():
        return "virtual"
    return "ethernet" if arphrd == TYPE_ETHERNET else "otro"


def _driver(base: pathlib.Path) -> Optional[str]:
    link = base / "device" / "driver"
    try:
        return link.resolve().name if link.exists() else None
    except OSError:
        return None


def _pci_identity(base: pathlib.Path) -> dict:
    """The card's model, if it sits on the PCI bus."""
    device = base / "device"
    if not device.exists():
        return {}

    def hex_field(field: str) -> Optional[int]:
        raw = read_text(str(device / field))
        try:
            return int(raw, 16) if raw else None
        except ValueError:
            return None

    vendor_id, device_id = hex_field("vendor"), hex_field("device")
    data: dict = {}
    try:
        data["pci_slot"] = device.resolve().name
    except OSError:
        pass
    if vendor_id is None or device_id is None:
        return data

    names = pciids.lookup([(vendor_id, device_id)])
    if found := names.get((vendor_id, device_id)):
        data["vendor"], data["model"] = found
    return data


def _default_routes() -> dict[str, str]:
    """The interface and gateway that internet traffic leaves through.

    `/proc/net/route` writes addresses in hex, byte-reversed, as the kernel
    keeps them in memory.
    """
    found: dict[str, str] = {}
    try:
        with open(sysroot.path(PROC_ROUTE), encoding="utf-8") as handle:
            next(handle, None)
            for line in handle:
                fields = line.split()
                if len(fields) < 3 or fields[1] != "00000000":
                    continue
                try:
                    gateway = socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])
                except (ValueError, OSError):
                    continue
                found.setdefault(fields[0], gateway)
    except OSError:
        return {}
    return found


def _ipv6_by_interface() -> dict[str, tuple[str, ...]]:
    """IPv6 addresses, which the kernel writes without colons."""
    found: dict[str, list[str]] = {}
    try:
        with open(sysroot.path(PROC_IPV6), encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) < 6:
                    continue
                try:
                    address = socket.inet_ntop(socket.AF_INET6,
                                                 bytes.fromhex(fields[0]))
                except (ValueError, OSError):
                    continue
                found.setdefault(fields[5], []).append(address)
    except OSError:
        return {}
    return {name: tuple(addresses_list) for name, addresses_list in found.items()}
