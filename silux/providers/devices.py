"""What is plugged in: USB, sound, cameras and the Bluetooth adapter.

Not the machine's own hardware but what's around it, so it has its own
page. Read from sysfs and `/proc/asound` without permissions on every
sample, since things get plugged and unplugged with Silux open.

**Never read, on purpose:** a USB device's `serial`, a Bluetooth adapter's
`address` and what it is paired with. The first identifies one device, the
last is someone else's. A file never opened never reaches the model or a
dump.
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

# A device's kind by its interfaces' class, most specific first: a keyboard
# with a card reader is a reader, a camera with a microphone is a camera.
BY_INTERFACE = (
    ("0e", "video"), ("08", "storage"), ("0b", "smartcard"), ("01", "audio"),
    ("e0", "wireless"), ("07", "printer"), ("03", "input"),
    ("02", "comm"), ("0a", "comm"), ("ff", "vendor"),
)
_PORT = re.compile(r"\d+-\d+(\.\d+)*")


def _kind(node: str) -> str:
    """What it is. Never «per interface», which is how a device defers to
    its interfaces; they are asked instead."""
    own = (read_text(f"{node}/bDeviceClass") or "").lower()
    if own == "09":
        return "hub"
    if own == "e0":
        return "wireless"
    interfaces = glob.glob(os.path.join(sysroot.path(node), "*:*"))
    classes, protocols = set(), set()
    for interface in interfaces:
        base = sysroot.unrooted(interface)
        code = (read_text(f"{base}/bInterfaceClass") or "").lower()
        classes.add(code)
        if code == "03":
            protocols.add((read_text(f"{base}/bInterfaceProtocol") or "").lower())
    for code, kind in BY_INTERFACE:
        if code in classes:
            if kind == "input":
                # The boot protocol: 01 keyboard, 02 mouse.
                if {"01", "02"} <= protocols:
                    return "keyboard_mouse"         # a receiver with both
                return "keyboard" if "01" in protocols else "mouse" if "02" in protocols \
                    else "input"
            return kind
    return "other"


class ConnectedDevices(Provider):
    name = "devices"
    provides = "usb_devices"

    def __init__(self) -> None:
        # Each USB device's reading, by port and by its sysfs entry's inode:
        # unplugging one device and plugging another into the same port makes
        # a new entry with a new inode. While nothing changes, a sample only
        # lists the folder.
        self._usb_read: dict[tuple[str, int], UsbDevice] = {}
        # Sound cards, by the text of `/proc/asound/cards`. Reading their
        # codecs is costly: `codec#N` is the codec's full dump, built by the
        # kernel when opened.
        self._sound_read: tuple[Optional[str], list[SoundCard]] = (None, [])

    def available(self) -> bool:
        return True

    def collect(self, draft: Draft) -> None:
        draft.usb_devices = self._usb()
        draft.sound_cards = self._sound()
        draft.cameras = self._cameras()
        draft.bluetooth = self._bluetooth()

    def _usb(self) -> list[UsbDevice]:
        out = []
        seen: dict[tuple[str, int], UsbDevice] = {}
        try:
            entries = sorted(os.scandir(sysroot.path(USB)), key=lambda e: e.name)
        except OSError:
            entries = []
        for entry in entries:
            port = entry.name
            if not _PORT.fullmatch(port):
                continue                 # interfaces («1-3:1.0») and roots («usb1»)
            key = (port, entry.inode())
            if (known := self._usb_read.get(key)) is not None:
                seen[key] = known
                out.append(known)
                continue
            node = sysroot.unrooted(entry.path)
            vendor_id, product_id = read_text(f"{node}/idVendor"), read_text(f"{node}/idProduct")
            try:
                speed = float(read_text(f"{node}/speed") or "")
            except ValueError:
                speed = None
            device = UsbDevice(
                port=port,
                vendor=read_text(f"{node}/manufacturer") or None,
                product=read_text(f"{node}/product") or None,
                usb_id=f"{vendor_id}:{product_id}" if vendor_id and product_id else None,
                kind=_kind(node),
                speed_mbps=speed,
                version=(read_text(f"{node}/version") or "").strip() or None,
            )
            seen[key] = device
            out.append(device)
        self._usb_read = seen
        return out

    def _sound(self) -> list[SoundCard]:
        cards_text = read_text("/proc/asound/cards")
        if cards_text == self._sound_read[0]:
            return list(self._sound_read[1])
        out = self._read_sound(cards_text)
        self._sound_read = (cards_text, out)
        return list(out)

    @staticmethod
    def _read_sound(cards_text: Optional[str]) -> list[SoundCard]:
        out = []
        lines = (cards_text or "").splitlines()
        for first, second in zip(lines[::2], lines[1::2]):
            match = re.match(r"\s*(\d+)\s+\[.*?\]:\s*(\S+)\s+-\s*(.*)", first)
            if not match:
                continue
            index, driver, name = match.group(1), match.group(2), match.group(3).strip()
            codecs = []
            for path in sorted(glob.glob(os.path.join(
                    sysroot.path(f"/proc/asound/card{index}"), "codec#*"))):
                line = (read_text(sysroot.unrooted(path)) or "").split("\n", 1)[0]
                if (codec := line.partition(":")[2].strip()):
                    codecs.append(codec)
            if "usb" in driver.lower() or "usb-" in second:
                out.append(SoundCard(name=name or None, kind="usb",
                                        camera=_is_camera_mic(second)))
            elif codecs and all("HDMI" in c for c in codecs):
                out.append(SoundCard(kind="hdmi", codec=codecs[0]))
            elif codecs:
                out.append(SoundCard(kind="board",
                                        codec=next(c for c in codecs if "HDMI" not in c)))
            else:
                out.append(SoundCard(name=name, kind="other"))
        return out

    @staticmethod
    def _cameras() -> list[Camera]:
        # A device creates several nodes (image and metadata), grouped by the
        # device they hang from. A virtual camera hangs from none.
        groups: dict[str, list] = {}
        for path in sorted(glob.glob(os.path.join(sysroot.path("/sys/class/video4linux"), "video*"))):
            name = (read_text(f"{sysroot.unrooted(path)}/name") or "").split(":")[0].strip()
            link = pathlib.Path(path, "device")
            try:
                physical = str(link.resolve()) if link.exists() else None
            except OSError:
                physical = None
            # A USB device's interfaces («…:1.0», «…:1.2») are the same device.
            key = re.sub(r":\d+\.\d+$", "", physical) if physical else f"virtual:{name}"
            group = groups.setdefault(key, [name, 0, physical is None])
            group[1] += 1
        return [Camera(name=name or None, nodes=nodes, virtual=virtual)
                for name, nodes, virtual in groups.values()]

    @staticmethod
    def _bluetooth() -> list[BluetoothAdapter]:
        out = []
        for path in sorted(glob.glob(os.path.join(sysroot.path("/sys/class/bluetooth"), "hci*"))):
            name = os.path.basename(path)
            if ":" in name:
                continue                 # connections («hci0:256») are not adapters
            try:
                physical = pathlib.Path(path, "device").resolve()
            except OSError:
                physical = None
            on_usb = bool(physical and "/usb" in str(physical))
            product = None
            if on_usb:
                product = read_text(f"{sysroot.unrooted(str(physical.parent))}/product") or None
            powered = None
            for rfkill in glob.glob(os.path.join(path, "rfkill*", "state")):
                powered = (read_text(sysroot.unrooted(rfkill)) or "").strip() == "1"
            out.append(BluetoothAdapter(name=name, product=product,
                                           bus="usb" if on_usb else "board", powered=powered))
        return out


# The USB video class: a camera.
VIDEO_CLASS = "0e"


def _is_camera_mic(line: str) -> bool:
    """Whether a USB sound card is a camera's microphone.

    `/proc/asound/cards` says where it hangs («… at usb-0000:0e:00.3-4.1.4,
    high speed»): the controller and the port path. The device at that path
    on that controller's bus is a camera if any of its interfaces is video.
    """
    match = re.search(r"usb-([0-9a-fA-F:.]+)-([\d.]+)", line)
    if not match:
        return False
    controller, ports = match.groups()
    for bus in glob.glob(os.path.join(sysroot.path("/sys/bus/usb/devices"), "usb*")):
        if controller not in os.path.realpath(bus):
            continue
        number = os.path.basename(bus)[3:]
        device_path = os.path.join(os.path.dirname(bus), f"{number}-{ports}")
        for interface in glob.glob(device_path + ":*"):
            if (read_text(sysroot.unrooted(os.path.join(interface, "bInterfaceClass"))) or "").strip() == VIDEO_CLASS:
                return True
    return False
