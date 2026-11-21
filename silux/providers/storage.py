"""The machine's disks, from /sys/block.

Almost everything is read without permissions: model, size, whether it
spins, how it is connected, its partitions and how full they are. What the
kernel keeps for the administrator are the SMART commands, the same ones
that can wipe a disk; that comes separately, through the privileged helper.

Harder than it looks: **what kind of disk it is**. No field says it. It comes
from whether the kernel considers it rotational and from its bus, as a SATA
SSD and an NVMe are both «not rotational» and alike in nothing.

What cannot be known, and so is not shown, is the form factor: whether an
NVMe is M.2, U.2 or a PCIe card is nowhere. Guessing it from the connection
would be right almost always and lie the rest.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import time
from typing import Iterator, Optional

from .. import smart as smart_module
from .. import sysroot
from ..i18n import _
from ..model import Disk, DiskHealth, DiskIo, Need, Partition, PcieLink
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider, read_int, read_text
from .counters import rate

# How often a disk's diagnosis is asked again, in seconds. Hours and writes
# change slowly; temperature does not.
HEALTH_INTERVAL_S = 30.0

SYS_BLOCK = pathlib.Path("/sys/block")
PROC_MOUNTS = "/proc/mounts"

# A sector is 512 bytes in the kernel's statistics, always, even if the disk
# uses 4 KB sectors inside.
SECTOR = 512

# What is not a disk: RAM disks, loops, the distribution's boot devices and
# compressed memory.
NOT_DISKS = re.compile(r"^(ram|loop|zram|dm-|md|sr|fd)\d*")

# File systems that do not live on a disk and only clutter the list.
VIRTUAL_FILESYSTEMS = {
    "proc", "sysfs", "devtmpfs", "tmpfs", "devpts", "cgroup", "cgroup2",
    "securityfs", "debugfs", "tracefs", "configfs", "fusectl", "pstore",
    "bpf", "mqueue", "hugetlbfs", "autofs", "efivarfs", "nsfs", "overlay",
    "squashfs", "ramfs", "binfmt_misc",
}


class Disks(Provider):
    """Each drive's identity, partitions and read and write rates."""

    name = "storage"
    provides = "disks"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        # The previous pass's counters, to subtract for the rate.
        self._previous: dict[str, tuple[float, int, int]] = {}
        self._interval_s = 1.0
        self.client = client or PrivilegedClient()
        # The diagnosis does not change from one second to the next: power-on
        # hours and terabytes written. Read and kept.
        self._health: dict[str, object] = {}
        self._no_health: set[str] = set()
        # The temperature that came with the diagnosis, kept apart. The disk
        # is rebuilt from sysfs on every sample: without keeping it, it showed
        # for an instant on unlocking and went back to «—».
        self._temperatures: dict[str, float] = {}
        # When each disk's last diagnosis was asked.
        self._read_at: dict[str, float] = {}
        # The collector sets it when the user presses the button. Without it
        # the diagnosis is read only if permissions were given for another thing.
        self.requested = False

    def available(self) -> bool:
        return sysroot.ruta(SYS_BLOCK).is_dir()

    def collect(self, draft: Draft) -> None:
        self._interval_s = draft.interval_s
        names = [p.name for p in sorted(sysroot.ruta(SYS_BLOCK).iterdir())
                   if not NOT_DISKS.match(p.name)]
        if not names:
            return

        draft.capabilities.add("storage")
        mounts = _mounts()
        draft.disks = [self._read(name, mounts) for name in names]
        self._diagnosis(draft)

    def _diagnosis(self, draft: Draft) -> None:
        """Ask each disk's SMART, if there are permissions for it.

        Only with the helper already connected: connecting opens an
        authentication window, and doing it on its own to show some power-on
        hours would be asking a password of someone who did not ask.
        """
        # A virtual disk's SMART is the hypervisor's invention: nothing to
        # unlock, nothing to read.
        if draft.disks and all(d.kind == "Virtual" for d in draft.disks):
            return
        if not self.client.connected() and self.requested:
            self.requested = False
            try:
                self.client.connect()
            except Exception:                          # noqa: BLE001
                pass
        if not self.client.connected():
            # Without this note the status bar counted one value needing
            # permissions where there were two: the memory detail and the
            # disks' diagnosis. A cancelled window keeps it too.
            draft.note(
                "disks.health", Need.ROOT,
                _("prov.disk.health"), _("prov.disk.health.hint"),
                _("what.disks.health"),
            )
            return

        for index, disk in enumerate(draft.disks):
            name = disk.name
            if name in self._no_health or disk.kind == "Virtual":
                continue
            if self._due_for_reading(name):
                try:
                    data, family = self.client.read_smart(name)
                except (HelperError, OSError):
                    data = None
                health = (smart_module.parse(
                    data, family, vendor=disk.vendor,
                    model=_ata_model(sysroot.ruta(SYS_BLOCK) / name) or disk.model,
                    firmware=disk.firmware)
                         if data is not None else None)
                health = _fits_what_is_used(health, disk)
                self._read_at[name] = time.monotonic()

                if health is None:
                    # A failed refresh does not erase what was known: the
                    # previous value stays and it is tried again later. A disk is
                    # taken as silent only if it never answered.
                    if name not in self._health:
                        self._no_health.add(name)
                        continue
                else:
                    self._health[name] = health
                    # And the temperature of disks that do not publish it in
                    # hwmon: SATA ones without `drivetemp` loaded bring it here.
                    degrees = (smart_module.nvme_temperature(data)
                              if family == "nvme"
                              else smart_module.ata_temperature(data))
                    if degrees is not None:
                        self._temperatures[name] = degrees

            # What hwmon publishes wins, as it is reread every sample; the
            # diagnosis's only fills the gap when there is no other.
            if disk.temp_c is None and name in self._temperatures:
                disk = dataclasses.replace(disk, temp_c=self._temperatures[name])
            draft.disks[index] = dataclasses.replace(
                disk, health=self._health[name])

    def _due_for_reading(self, name: str) -> bool:
        """Whether to ask this disk's diagnosis again.

        Read from time to time, not once: hours and terabytes written change
        slowly, but temperature does not, and a frozen number labelled
        «Temperature» misleads more than a gap. The interval is long on
        purpose: each reading is a trip to the privileged process and a
        command to the disk, and the disk updates those counters slowly.
        """
        previous = self._read_at.get(name)
        return previous is None or (time.monotonic() - previous) >= HEALTH_INTERVAL_S

    # -- internals ----------------------------------------------------------

    def _read(self, name: str, mounts: dict[str, tuple[str, str]]) -> Disk:
        base = sysroot.ruta(SYS_BLOCK) / name
        sectors = read_int(str(base / "size")) or 0
        rotational = read_int(str(base / "queue" / "rotational"))
        transport = _transport(base, name)
        removable = read_int(str(base / "removable")) == 1

        model = _clean(read_text(str(base / "device" / "model")))
        virtual = is_virtual(name, model, read_text(str(base / "device" / "vendor")))
        return Disk(
            name=name,
            model=model,
            vendor=_vendor(base, model),
            firmware=_clean(read_text(str(base / "device" / "firmware_rev"))
                             or read_text(str(base / "device" / "rev"))),
            serial=_clean(read_text(str(base / "device" / "serial"))),
            size_bytes=sectors * SECTOR,
            kind=_kind(rotational, transport, virtual, removable),
            transport=transport,
            rotational=None if rotational is None else bool(rotational),
            logical_sector=read_int(str(base / "queue" / "logical_block_size")),
            physical_sector=read_int(str(base / "queue" / "physical_block_size")),
            scheduler=_scheduler(base),
            removable=removable,
            pci_slot=_pci_slot(base) if transport == "nvme" else None,
            link=_link(base) if transport == "nvme" else None,
            temp_c=_temperature(base),
            discard=_supports_discard(base),
            discard_mounted=any(mounted_name.startswith(name)
                                for mounted_name in _mounted_with_discard()),
            fstrim_timer=_fstrim_enabled(),
            partitions=tuple(_partitions(base, name, mounts)),
            io=self._traffic(name, base),
        )

    def _traffic(self, name: str, base: pathlib.Path) -> DiskIo:
        raw = read_text(str(base / "stat"))
        if not raw:
            return DiskIo()
        fields = raw.split()
        if len(fields) < 8:
            return DiskIo()

        read_total = int(fields[2]) * SECTOR
        written_total = int(fields[6]) * SECTOR
        now = time.monotonic()
        read_rate = write_rate = None

        previous = self._previous.get(name)
        if previous is not None:
            before, rx, tx = previous
            # The counters restart when an external disk is reconnected; a
            # negative delta is that, not a negative rate.
            read_rate = rate(rx, before, read_total, now, self._interval_s)
            write_rate = rate(tx, before, written_total, now, self._interval_s)
            if read_rate is None or write_rate is None:
                read_rate = write_rate = None
        self._previous[name] = (now, read_total, written_total)

        return DiskIo(
            read_bytes=read_total, write_bytes=written_total,
            read_ops=int(fields[0]), write_ops=int(fields[4]),
            read_rate_bps=read_rate, write_rate_bps=write_rate,
        )


# -- single readings --------------------------------------------------------

def _ata_model(base: pathlib.Path) -> Optional[str]:
    """The whole model, from the ATA IDENTIFY the kernel publishes.

    sysfs's `model` is the SCSI one, cut to 16 characters («KINGSTON
    SA400S3»), and smartmontools' patterns need the whole one to know the
    unit of the counters. `ata_device/*/id` is the IDENTIFY in hex words,
    readable by anyone; the model is words 27 to 46, two characters each.
    """
    try:
        real = (base / "device").resolve()
    except OSError:
        return None
    port = next((p for p in (real, *real.parents) if re.fullmatch(r"ata\d+", p.name)), None)
    if port is None:
        return None
    for path in sorted(port.glob("link*/dev*/ata_device/dev*/id")):
        try:
            words = [int(p, 16) for p in (read_text(str(path)) or "").split()]
        except ValueError:
            continue
        if len(words) >= 47:
            raw = b"".join(p.to_bytes(2, "big") for p in words[27:47])
            return raw.decode("ascii", "replace").strip() or None
    return None


def _fits_what_is_used(health: Optional[DiskHealth], disk: Disk) -> Optional[DiskHealth]:
    """No counter shown that says less was ever written than the disk holds.

    A unit nobody knows looks like a believable figure: 33 MB written by a
    disk with 316 GB on it. Whatever the unit, what is stored was written.
    """
    used = disk.used_bytes
    if health is None or health.written_bytes is None or not used:
        return health
    if health.written_bytes >= used:
        return health
    return dataclasses.replace(health, written_bytes=None, read_bytes=None,
                               counters_unit_unknown=True)


def _clean(text: Optional[str]) -> Optional[str]:
    """A disk's fields come padded with spaces to their fixed length."""
    return " ".join(text.split()) if text else None


# How each maker's model starts, and its real name. Disks do not publish who
# made them: sysfs's `vendor` says «ATA» on SATA and nothing on NVMe, so the
# name is only inside the model.
MAKERS = {
    "samsung": "Samsung", "kingston": "Kingston", "crucial": "Crucial",
    "wdc": "Western Digital", "wd_black": "Western Digital",
    "wd_blue": "Western Digital", "wd_green": "Western Digital",
    "wd_red": "Western Digital", "wd ": "Western Digital",
    "seagate": "Seagate", "st1": "Seagate", "st2": "Seagate",
    "st3": "Seagate", "st4": "Seagate", "st5": "Seagate", "st6": "Seagate",
    "st8": "Seagate", "kioxia": "Kioxia", "toshiba": "Toshiba",
    "intel": "Intel", "micron": "Micron", "sandisk": "SanDisk",
    "adata": "ADATA", "xpg": "ADATA", "corsair": "Corsair",
    "sk hynix": "SK hynix", "skhynix": "SK hynix", "hynix": "SK hynix",
    "patriot": "Patriot",
    "pny": "PNY", "team": "Team Group", "transcend": "Transcend",
    "lexar": "Lexar", "intenso": "Intenso", "netac": "Netac",
    "silicon power": "Silicon Power", "sabrent": "Sabrent",
    "gigabyte": "Gigabyte", "hgst": "HGST", "hitachi": "Hitachi",
    "apacer": "Apacer", "verbatim": "Verbatim", "goodram": "GOODRAM",
    "solidigm": "Solidigm", "phison": "Phison", "ct": "Crucial",
}


def _maker_from_model(model: Optional[str]) -> Optional[str]:
    """Who makes a disk, from how its model starts."""
    if not model:
        return None
    lower = model.strip().lower()
    # Longest first: «wd_black» before «wd », «sk hynix» before «hynix», or
    # the short prefix takes the match.
    for prefix in sorted(MAKERS, key=len, reverse=True):
        if lower.startswith(prefix):
            return MAKERS[prefix]
    return None


def _vendor(base: pathlib.Path, model: Optional[str] = None) -> Optional[str]:
    """A SATA disk's `vendor` field says «ATA», which is no maker."""
    value = _clean(read_text(str(base / "device" / "vendor")))
    if value not in (None, "ATA", "NVME"):
        return value
    return _maker_from_model(model)


def _transport(base: pathlib.Path, name: str) -> Optional[str]:
    if name.startswith("nvme"):
        return "nvme"
    try:
        path = str((base / "device").resolve())
    except OSError:
        return None
    for marker, bus in (("/usb", "usb"), ("/ata", "sata"),
                              ("/nvme", "nvme"), ("/mmc", "mmc")):
        if marker in path:
            return bus
    return None


# The disks a hypervisor makes up: their model, their vendor or their name
# says so. QEMU's say they spin (rotational 1) unless told otherwise, and
# with discard on they admit TRIM: it read «HDD» and «disco SMR».
_VIRTUAL_MODELS = re.compile(r"^(QEMU |VBOX |VMware|Virtual (disk|HD)|Msft Virtual)", re.I)


def is_virtual(name: str, model: Optional[str], vendor: Optional[str]) -> bool:
    return (name.startswith(("vd", "xvd"))
            or bool(model and _VIRTUAL_MODELS.match(model))
            or (vendor or "").strip().upper() in ("QEMU", "VBOX", "VMWARE", "MSFT"))


def _kind(rotational: Optional[int], transport: Optional[str],
          virtual: bool = False, removable: bool = False) -> Optional[str]:
    """HDD, SSD, NVMe, Flash or Virtual.

    No field says it. «Not rotational» covers a SATA SSD and an NVMe, alike
    in neither speed nor connection, so the bus decides between them.
    """
    if virtual:
        return "Virtual"
    if rotational is None:
        return None
    if transport == "usb" and rotational:
        # Over USB the kernel marks nearly everything as rotational, so it
        # says nothing. A removable device is flash (a pen drive, a card in
        # a reader); a fixed one may spin or not, and that isn't known.
        return "Flash" if removable else None
    if rotational:
        return "HDD"
    return "NVMe" if transport == "nvme" else "SSD"


def _scheduler(base: pathlib.Path) -> Optional[str]:
    """The active one is in brackets: «none mq-deadline kyber [bfq]»."""
    raw = read_text(str(base / "queue" / "scheduler"))
    if not raw:
        return None
    match = re.search(r"\[([^\]]+)\]", raw)
    return match.group(1) if match else None


def _pci_slot(base: pathlib.Path) -> Optional[str]:
    try:
        current = (base / "device").resolve()
    except OSError:
        return None
    for _level in range(6):
        if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", current.name):
            return current.name
        if current.parent == current:
            break
        current = current.parent
    return None


def _link(base: pathlib.Path) -> Optional[PcieLink]:
    """An NVMe's PCIe link, worked out as a graphics card's.

    Only for NVMe. A SATA disk does not negotiate PCIe: its controller does,
    shared with the other disks. Climbing the tree to a PCI address gave the
    chipset controller's link and showed it as the disk's.
    """
    slot = _pci_slot(base)
    if not slot:
        return None
    node = pathlib.Path(sysroot.ruta("/sys/bus/pci/devices")) / slot
    if not node.is_dir():
        return None

    def speed(field: str) -> Optional[float]:
        raw = read_text(str(node / field))
        match = re.search(r"([\d.]+)\s*GT/s", raw or "")
        return float(match.group(1)) if match else None

    current = speed("current_link_speed")
    if current is None:
        return None
    return PcieLink(
        current_speed_gts=current,
        current_width=read_int(str(node / "current_link_width")),
        max_speed_gts=speed("max_link_speed"),
        max_width=read_int(str(node / "max_link_width")),
    )


def _temperature(base: pathlib.Path) -> Optional[float]:
    """The disk's temperature, if a driver publishes it.

    Each kind hangs it somewhere else: NVMe disks carry it under their own
    controller, and SATA ones only with `drivetemp` loaded, which almost no
    distribution does by default. So the tree is searched rather than
    assuming a path.
    """
    try:
        root = (base / "device").resolve()
    except OSError:
        return None
    for _step in range(4):
        for hwmon in sorted(root.glob("hwmon*")) + sorted(root.glob("hwmon/hwmon*")):
            millidegrees = read_int(str(hwmon / "temp1_input"))
            if millidegrees is not None:
                return round(millidegrees / 1000, 1)
        if root.parent == root:
            break
        root = root.parent
    return None


def _partitions(base: pathlib.Path, disk: str,
                 mounts: dict[str, tuple[str, str]]) -> Iterator[Partition]:
    for entry in sorted(base.iterdir()):
        if not entry.name.startswith(disk) or not (entry / "partition").exists():
            continue
        sectors = read_int(str(entry / "size")) or 0
        filesystem, mountpoint = mounts.get(entry.name, (None, None))
        used = free = None
        if mountpoint:
            used, free = _usage(mountpoint)
        yield Partition(
            name=entry.name,
            size_bytes=sectors * SECTOR,
            filesystem=filesystem,
            mountpoint=mountpoint,
            used_bytes=used,
            free_bytes=free,
        )


def _usage(mountpoint: str) -> tuple[Optional[int], Optional[int]]:
    """How much a mounted file system uses, and how much it has free.

    Used is what is free to nobody (f_blocks − f_bfree) and free what anyone
    can use (f_bavail), as `df` counts them. What ext4 keeps for root (5 %
    by default) is neither: it stays out with the tables, and `render.space`
    calls it «Reserved». Counted as used, it read as several times the data.
    """
    def measure() -> tuple[Optional[int], Optional[int]]:
        try:
            st = os.statvfs(mountpoint)
        except OSError:
            return None, None
        return (st.f_blocks - st.f_bfree) * st.f_frsize, st.f_bavail * st.f_frsize

    # With a dump, what was recorded: the mount point is another machine's.
    return sysroot.a_traves("statvfs", mountpoint, measure) or (None, None)


def _supports_discard(base: pathlib.Path) -> Optional[bool]:
    """Whether the drive accepts being told which blocks are unused (TRIM)."""
    maximum = read_int(str(base / "queue" / "discard_max_bytes"))
    return None if maximum is None else maximum > 0


def _mounted_with_discard() -> set[str]:
    """The partitions mounted with the `discard` option."""
    found: set[str] = set()
    for line in (read_text(PROC_MOUNTS) or "").splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0].startswith("/dev/") \
                and "discard" in fields[3].replace("=", ",").split(","):
            found.add(fields[0][len("/dev/"):])
    return found


# Where systemd leaves the link of an enabled timer.
FSTRIM_ENABLED = "/etc/systemd/system/timers.target.wants/fstrim.timer"


def _fstrim_enabled() -> bool:
    return os.path.lexists(sysroot.ruta(FSTRIM_ENABLED))


def _mounts() -> dict[str, tuple[str, str]]:
    """Which partition is mounted where, and with what file system."""
    found: dict[str, tuple[str, str]] = {}
    try:
        with open(sysroot.ruta(PROC_MOUNTS), encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) < 3:
                    continue
                source, mountpoint, filesystem = fields[0], fields[1], fields[2]
                if filesystem in VIRTUAL_FILESYSTEMS or not source.startswith("/dev/"):
                    continue
                # A /dev/mapper/… ends in dm-N: recorded, as /dev is not dumped.
                name = os.path.basename(
                    sysroot.a_traves("realpath", source, os.path.realpath, source) or source)
                # The first mount wins: with btrfs subvolumes the same partition
                # shows many times, and the root is the one that matters.
                found.setdefault(name, (filesystem, _unescape(mountpoint)))
    except OSError:
        return {}
    return found


def _unescape(mountpoint: str) -> str:
    """`/proc/mounts` escapes spaces as \\040."""
    return mountpoint.replace("\\040", " ").replace("\\011", "\t")
