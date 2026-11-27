"""The disk test: how fast a folder's disk reads and writes, with its context.

The native module (`silux_bench`) makes a file without a name in the folder
and runs one lap of a test at a time; this decides the tests, their laps and
the pauses between them, runs them in a child process and reads what came
back. It also says what a folder sits on (which file system, which disks,
what lies in between), since that decides whether a test there means
anything.

In a child process so that the file goes with it: it has no name, and the
kernel frees it when the child ends, is killed to cancel the test or dies
with the window. The child says how far it has got on its standard output,
one JSON object per line.

A test is named as CrystalDiskMark names it, by what really ran: «RND4K
Q32T1» is one thread keeping 32 requests in flight. Where there is no
io_uring a queue is made of threads with one request each, and that is
«RND4K Q1T32»: another test, with another figure.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Union

from . import childrun, saved, sysroot

KIB = 1024
MIB = 1024 * KIB
GIB = 1024 * MIB

# CrystalDiskMark's defaults: the lap is timed, not a set amount of data.
FILE_BYTES = GIB
LAPS = 5
LAP_SECONDS = 5.0
PAUSE_SECONDS = 5.0
# A test whose laps are scattered above this is flagged, as in the memory
# test: the median absolute deviation over the median.
NOISY_SPREAD = 0.05
# A change from the test before smaller than this is within what the same
# disk moves from one test to the next: noise, which isn't said.
NOISE = 0.03

HISTORY_VERSION = 1
MAX_ENTRIES = 60

PROC_MOUNTS = "/proc/mounts"
SYS_BLOCK = "/sys/block"
SYS_BTRFS = "/sys/fs/btrfs"
SECTOR = 512

# Mount types that are a folder in memory.
IN_MEMORY = frozenset({"tmpfs", "ramfs", "devtmpfs", "hugetlbfs"})
# Mount types that are a folder on another machine. Several come through
# FUSE, which the file's own magic number can't tell from a local driver.
NETWORK = frozenset({
    "nfs", "nfs4", "cifs", "smb3", "smbfs", "ncpfs", "afs", "coda", "ceph", "9p",
    "glusterfs", "lustre", "beegfs", "davfs", "virtiofs", "vboxsf",
    "fuse.sshfs", "fuse.glusterfs", "fuse.ceph", "fuse.ceph-fuse", "fuse.davfs2",
    "fuse.rclone", "fuse.s3fs", "fuse.curlftpfs", "fuse.gvfsd-fuse", "fuse.smbnetfs",
    "fuse.vmhgfs-fuse", "fuse.nfs", "fuse.portal",
})
# FAT keeps a file's size in 32 bits: the kernel takes files of up to
# 2^32 - 1 bytes there (`s_maxbytes` in fs/fat/inode.c).
LARGEST_FILE = {"vfat": 2**32 - 1, "msdos": 2**32 - 1}
# Free space a test leaves alone besides its file. All of the native
# module's margin on the file system the system itself writes to, where
# running out breaks logs, updates and logging in, and on btrfs, which full
# can be left without room for its own metadata. Elsewhere it only keeps
# room for what other programs write there meanwhile: a share of the file
# system, between the least the module takes and the whole margin, so that
# a small pen drive can be measured.
FREE_MARGIN = GIB
LEAST_FREE_MARGIN = 32 * MIB
MARGIN_SHARE = 0.05
SYSTEM_MOUNTS = frozenset({"/", "/home", "/var"})
# These go through the page cache without an error where they can't read or
# write directly, so the cache check after each test is what tells.
SILENT_FALLBACK = frozenset({"vfat", "msdos", "exfat", "ntfs3"})
# Where FIEMAP's offsets are on the device under the file system. btrfs's
# are in its own address space, not the disk's.
PLACEABLE = frozenset({"ext4", "xfs", "f2fs"})
# FIEMAP flags of an extent whose place isn't known, or isn't the file's
# alone: unknown, delayed allocation, encoded, inline and tail.
UNPLACED = 0x2 | 0x4 | 0x8 | 0x200 | 0x400
# Writing the file says how long it has left once it has gone on this long:
# before, the pace is the disk's cache, not the disk.
FILL_PACE_SECONDS = 3.0


@dataclass(frozen=True)
class Test:
    """What one row of the table asks of the disk."""

    pattern: str                     # "sequential" | "random"
    block: int
    depth: int                       # requests each thread keeps in flight
    threads: int = 1

    @property
    def name(self) -> str:
        """As CrystalDiskMark writes it: «SEQ1M Q8T1»."""
        size = next((f"{self.block // unit}{letter}" for unit, letter in ((MIB, "M"), (KIB, "K"))
                     if self.block % unit == 0), f"{self.block}B")
        kind = "SEQ" if self.pattern == "sequential" else "RND"
        return f"{kind}{size} Q{self.depth}T{self.threads}"

    def as_run_by(self, engine: str) -> "Test":
        """The test that really runs: without a ring a queue is made of
        threads with one request each."""
        if engine != "threads" or self.depth == 1:
            return self
        return dataclasses.replace(self, depth=1, threads=self.depth * self.threads)


# What each profile measures. Only the standard one for now; the table and
# the history take whatever tests a result brings.
PROFILES = {
    "standard": (Test("sequential", MIB, 8), Test("sequential", MIB, 1),
                 Test("random", 4 * KIB, 32), Test("random", 4 * KIB, 1)),
    # What almost every program asks of a disk: one request at a time.
    "real": (Test("sequential", MIB, 1), Test("random", 4 * KIB, 1)),
    # The one test the user puts together: its tests go in its plan.
    "custom": (),
}
CUSTOM = "custom"


def tests_of(result: "Result") -> tuple[str, ...]:
    """The tests a result measured, by name, in their order."""
    return tuple(dict.fromkeys(m.name for m in result.measures))


def previous(result: "Result", history: Sequence["Result"]) -> Optional["Result"]:
    """The test before `result` of the same disk, engine, profile and tests,
    the only one its figures compare with; `history` newest first. Two
    custom runs of different tests compare with nothing."""
    return next((older for older in history
                 if older.timestamp < result.timestamp and older.measured
                 and (older.profile, older.engine) == (result.profile, result.engine)
                 and tests_of(older) == tests_of(result)
                 and older.is_of(result.disks, result.model)), None)


def change(now: Optional["Measure"], before: Optional["Measure"]) -> Optional[float]:
    """How much a figure moved from the same test before, as a fraction of
    that one's; None without both."""
    new = now.median if now is not None else None
    old = before.median if before is not None else None
    if new is None or old is None or not old.bytes_per_second:
        return None
    return new.bytes_per_second / old.bytes_per_second - 1


def noticeable(fraction: Optional[float]) -> bool:
    """Whether a change (`change`) is more than the noise."""
    return fraction is not None and abs(fraction) >= NOISE


def headline_test(profile: str) -> str:
    """The sequential test a profile's result is told by: its first."""
    return next((test.name for test in PROFILES.get(profile, ()) if test.pattern == "sequential"),
                PROFILES["standard"][0].name)


@dataclass(frozen=True)
class Lap:
    """One timed lap of a test."""

    number: int                      # 0 is the first, which doesn't count
    bytes_per_second: int = 0
    requests_per_second: float = 0.0
    bytes_: int = 0
    latency_mean_ns: Optional[float] = None
    latency_min_ns: Optional[int] = None
    latency_p50_ns: Optional[int] = None
    latency_p99_ns: Optional[int] = None
    latency_p999_ns: Optional[int] = None
    latency_max_ns: Optional[int] = None
    # How much had moved in all, and how far into the lap: (ns, bytes).
    samples: tuple[tuple[int, int], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "samples", tuple((int(a), int(b)) for a, b in self.samples))


@dataclass(frozen=True)
class Measure:
    """One test in one direction: its laps and what was checked after them."""

    pattern: str
    block: int
    depth: int
    threads: int
    direction: str                   # "read" | "write"
    # The test this one ran in place of, when it isn't the one asked for.
    stands_for: str = ""
    laps: tuple[Lap, ...] = ()
    # Bytes of the file left in the page cache: none, if every request went
    # past it. None where it couldn't be asked.
    cached_bytes: Optional[int] = None
    # What the disks' own counters say they moved meanwhile.
    disk_bytes: Optional[int] = None
    temperature_c: Optional[float] = None

    def __post_init__(self):
        object.__setattr__(self, "laps", tuple(self.laps))

    @property
    def test(self) -> Test:
        return Test(self.pattern, self.block, self.depth, self.threads)

    @property
    def name(self) -> str:
        return self.test.name

    @property
    def counted(self) -> tuple[Lap, ...]:
        return tuple(lap for lap in self.laps if lap.number > 0)

    @property
    def median(self) -> Optional[Lap]:
        """The lap in the middle: the figure of the test, with the requests
        and the latency of that same lap."""
        laps = sorted(self.counted, key=lambda lap: lap.bytes_per_second)
        return laps[(len(laps) - 1) // 2] if laps else None

    @property
    def best(self) -> Optional[Lap]:
        """The fastest lap: the one CrystalDiskMark would give."""
        return max(self.counted, key=lambda lap: lap.bytes_per_second, default=None)

    @property
    def worst(self) -> Optional[Lap]:
        return min(self.counted, key=lambda lap: lap.bytes_per_second, default=None)

    @property
    def spread(self) -> Optional[float]:
        rates = [lap.bytes_per_second for lap in self.counted]
        if not rates:
            return None
        middle = statistics.median(rates)
        if middle <= 0:
            return 0.0
        return statistics.median(abs(rate - middle) for rate in rates) / middle

    @property
    def noisy(self) -> bool:
        spread = self.spread
        return spread is not None and spread > NOISY_SPREAD

    @property
    def moved_bytes(self) -> int:
        """Every lap's, the one that doesn't count too."""
        return sum(lap.bytes_ for lap in self.laps)


@dataclass(frozen=True)
class Place:
    """What a folder sits on."""

    mountpoint: str
    filesystem: str                  # the mount's type: "ext4", "fuseblk"
    source: str                      # what is mounted: "/dev/sda1", "host:/export"
    options: tuple[str, ...] = ()
    # The whole disks under it, by their kernel name; none where they can't
    # be told.
    disks: tuple[str, ...] = ()
    # What lies between the file system and them: "crypt", "lvm", "raid",
    # "mapped", "loop".
    layers: tuple[str, ...] = ()
    # Why no test makes sense here: a key the interface translates.
    refusal: Optional[str] = None
    warnings: tuple[str, ...] = ()
    # The kernel's name of what is mounted, when it is a block device:
    # "sda2", "dm-0".
    device: Optional[str] = None


@dataclass(frozen=True)
class Plan:
    """What the child is asked to measure."""

    folder: str
    tests: tuple[Test, ...]
    profile: str = "standard"
    bytes_: int = FILE_BYTES
    laps: int = LAPS
    lap_seconds: float = LAP_SECONDS
    pause_seconds: float = PAUSE_SECONDS
    write: bool = True
    # None: the ring where there is one, and threads where there isn't.
    engine: Optional[str] = None
    mountpoint: Optional[str] = None
    filesystem: Optional[str] = None
    disks: tuple[str, ...] = ()
    layers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    device: Optional[str] = None
    # Free space left besides the file (`free_margin`).
    margin: int = FREE_MARGIN


@dataclass(frozen=True)
class Result:
    timestamp: float = 0.0
    profile: str = "standard"
    measures: tuple[Measure, ...] = ()
    engine: Optional[str] = None             # "uring" | "threads"
    # What the kernel answered to making a ring, where there is none.
    uring_errno: Optional[int] = None
    bytes_: int = 0
    laps: int = 0
    lap_seconds: float = 0.0
    pause_seconds: float = 0.0
    # The mount and not the folder, which carries the user's name.
    mountpoint: Optional[str] = None
    filesystem: Optional[str] = None
    disks: tuple[str, ...] = ()
    layers: tuple[str, ...] = ()
    # The disk's model as it was then, when there is just one.
    model: Optional[str] = None
    creation: Optional[str] = None           # "unnamed" | "unlinked"
    no_cow: Optional[bool] = None
    align_declared: Optional[bool] = None
    # Everything written: the file once, and every lap that wrote.
    written_bytes: int = 0
    temperature_start_c: Optional[float] = None
    temperature_peak_c: Optional[float] = None
    temperature_end_c: Optional[float] = None
    seconds: float = 0.0
    warnings: tuple[str, ...] = ()
    # Why there is nothing, or less than asked: a key the interface
    # translates, the module's message for the report, and its figures.
    reason: Optional[str] = None
    detail: str = ""
    figures: tuple[tuple[str, Union[int, str]], ...] = ()
    # A name the user gives it, as in the processor's history.
    label: str = ""
    # Where the file lay on the disk, from its start (the outer part of a
    # platter) to its end, as fractions: where that can be known.
    placement: Optional[tuple[float, float]] = None

    def __post_init__(self):
        for name in ("measures", "disks", "layers", "warnings"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if self.placement is not None:
            object.__setattr__(self, "placement", tuple(self.placement))
        object.__setattr__(self, "figures", tuple((str(k), v) for k, v in self.figures))

    def measure(self, name: str, direction: str) -> Optional[Measure]:
        return next((m for m in self.measures
                     if m.direction == direction and name in (m.name, m.stands_for)), None)

    @property
    def measured(self) -> bool:
        return any(m.counted for m in self.measures)

    def is_of(self, disks: Sequence[str], model: Optional[str]) -> bool:
        """Whether it was measured on these disks: by their names and, where
        it kept it, the model. Another disk can come up under the same name
        after a reboot or when plugged in again."""
        return bool(disks) and self.disks == tuple(disks) and (
            self.model is None or self.model == model)


# -- what a folder sits on ---------------------------------------------------

def _unescape(text: str) -> str:
    """`/proc/mounts` writes a space as \\040, and so on, in octal."""
    for code in ("040", "011", "012", "134"):
        text = text.replace("\\" + code, chr(int(code, 8)))
    return text


def _mounts() -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Every mount: its source, where, its type and its options."""
    found = []
    try:
        with open(sysroot.path(PROC_MOUNTS), encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) >= 4:
                    found.append((_unescape(fields[0]), _unescape(fields[1]), fields[2],
                                  tuple(fields[3].split(","))))
    except OSError:
        pass
    return found


def _is_inside(folder: str, mountpoint: str) -> bool:
    return (folder == mountpoint or mountpoint == "/"
            or folder.startswith(mountpoint.rstrip("/") + "/"))


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _names(path: pathlib.Path) -> list[str]:
    try:
        return sorted(entry.name for entry in path.iterdir())
    except OSError:
        return []


def _under(name: str, disks: list[str], layers: list[str], seen: set[str]) -> None:
    """Add to `disks` the whole disks a block device stands on, and to
    `layers` what is found on the way down."""
    if name in seen:
        return
    seen.add(name)
    block = pathlib.Path(sysroot.path(SYS_BLOCK))
    if not (block / name).is_dir():
        # A partition: it lives in its disk's folder.
        for disk in _names(block):
            if (block / disk / name).is_dir():
                _under(disk, disks, layers, seen)
        return
    below = _names(block / name / "slaves")
    if name.startswith("dm-"):
        uuid = _read(block / name / "dm" / "uuid")
        layers.append("crypt" if uuid.startswith("CRYPT-") else
                      "lvm" if uuid.startswith("LVM-") else "mapped")
    elif name.startswith("md"):
        layers.append("raid")
    elif name.startswith("loop"):
        layers.append("loop")
        return
    elif name.startswith(("zram", "ram")):
        return
    elif not below:
        disks.append(name)
        return
    for one in below:
        _under(one, disks, layers, seen)


def where(folder: Union[str, os.PathLike]) -> Optional[Place]:
    """What `folder` sits on, as `findmnt -T` would say, down to its disks.
    None if no mount holds it."""
    folder = os.path.realpath(os.fspath(folder))
    held = [mount for mount in _mounts() if _is_inside(folder, mount[1])]
    if not held:
        return None
    # The deepest mount holds it, and of two in the same place, the last.
    longest = max(len(mount[1]) for mount in held)
    source, mountpoint, filesystem, options = [m for m in held if len(m[1]) == longest][-1]

    disks: list[str] = []
    layers: list[str] = []
    device = None
    if source.startswith("/dev/"):
        device = sysroot.block_device(source, mountpoint)
        names = {device}
        # A btrfs over several devices only names one of them in its mount.
        for volume in _names(pathlib.Path(sysroot.path(SYS_BTRFS))):
            devices = _names(pathlib.Path(sysroot.path(SYS_BTRFS)) / volume / "devices")
            if names & set(devices):
                names |= set(devices)
        seen: set[str] = set()
        for name in sorted(names):
            _under(name, disks, layers, seen)

    refusal = None
    warnings: list[str] = []
    if filesystem in IN_MEMORY:
        refusal = "in_memory"
    elif filesystem in NETWORK:
        refusal = "network"
    elif filesystem == "fuseblk":
        # A driver outside the kernel (ntfs-3g): it may be what limits.
        warnings.append("fuse_driver")
    elif filesystem.startswith("fuse"):
        warnings.append("fuse")
    elif filesystem == "zfs":
        warnings.append("zfs")
    elif filesystem == "overlay":
        warnings.append("overlay")
    elif not source.startswith("/dev/"):
        refusal = "not_a_disk"
    if refusal is None and "ro" in options:
        refusal = "read_only"
    if "crypt" in layers:
        warnings.append("encrypted")
    if "loop" in layers:
        warnings.append("loop")
    if len(disks) > 1:
        warnings.append("several_disks")
    return Place(mountpoint, filesystem, source, options, tuple(disks),
                 tuple(dict.fromkeys(layers)), refusal, tuple(warnings), device)


def is_system(place: Place) -> bool:
    """Whether the folder is on the file system the system writes to: the
    one mounted at /, /home or /var, by its source, so that the subvolumes
    of the same btrfs count too."""
    return place.source in {source for source, mountpoint, _type, _options in _mounts()
                            if mountpoint in SYSTEM_MOUNTS}


def free_margin(filesystem: Optional[str], system: bool, size_bytes: Optional[int]) -> int:
    """How much free space a test leaves besides its file, in whole MiB:
    see FREE_MARGIN. All of it where the file system's size isn't known."""
    if system or filesystem == "btrfs" or not size_bytes:
        return FREE_MARGIN
    share = int(size_bytes * MARGIN_SHARE) // MIB * MIB
    return min(FREE_MARGIN, max(LEAST_FREE_MARGIN, share))


def make_plan(folder: Union[str, os.PathLike], place: Optional[Place] = None,
              profile: str = "standard", size_bytes: Optional[int] = None,
              **changes) -> Plan:
    """The plan to measure `folder` with a profile's tests. `size_bytes` is
    its file system's, where it is known, for the margin. `changes` are the
    plan's own fields: the file's size, the laps, whether to write."""
    place = place if place is not None else where(folder)
    plan = Plan(folder=os.fspath(folder), tests=PROFILES[profile], profile=profile)
    if place is not None:
        plan = dataclasses.replace(
            plan, mountpoint=place.mountpoint, filesystem=place.filesystem,
            disks=place.disks, layers=place.layers, warnings=place.warnings,
            device=place.device,
            margin=free_margin(place.filesystem, is_system(place), size_bytes))
    return dataclasses.replace(plan, **changes)


def largest_file(filesystem: Optional[str]) -> Optional[int]:
    """The largest file in whole MiB that the file system takes, where it
    takes less than the sizes offered: 4095 MiB on FAT32."""
    largest = LARGEST_FILE.get(filesystem or "")
    return None if largest is None else largest // MIB * MIB


def largest_that_fits(plan: Plan, free_bytes: Optional[int]) -> Optional[int]:
    """The largest file the folder takes: what its file system holds, and
    what is free less the margin a test leaves. None if neither is a limit
    that is known."""
    limits = [limit for limit in (largest_file(plan.filesystem),
                                  None if free_bytes is None else free_bytes - plan.margin)
              if limit is not None]
    return min(limits) if limits else None


def fits(plan: Plan) -> bool:
    largest = largest_file(plan.filesystem)
    return largest is None or plan.bytes_ <= largest


def fill_estimate(plan: Plan, history: Sequence[Result], model: Optional[str],
                  link_bytes_per_second: Optional[float]) -> Optional[tuple[float, str]]:
    """How long writing the file takes, and what that comes from: "last",
    this disk's sequential write in its last test, or else "link", the most
    its link carries, which makes it the least it can take. None if neither
    is known."""
    for result in history:
        if not result.is_of(plan.disks, model):
            continue
        measure = result.measure(headline_test(result.profile), "write")
        rate = measure.median.bytes_per_second if measure and measure.median else None
        if rate:
            return plan.bytes_ / rate, "last"
    if link_bytes_per_second:
        return plan.bytes_ / link_bytes_per_second, "link"
    return None


def fill_left(elapsed: float, done: float) -> Optional[float]:
    """How long writing the file has left, at the pace it has gone so far."""
    if done <= 0 or elapsed < FILL_PACE_SECONDS:
        return None
    return elapsed * (1 - done) / done


def span(extents: Sequence[Sequence[int]], start: int, size: int) -> Optional[tuple[float, float]]:
    """Where a file's extents lie on a disk of `size` bytes, as fractions
    of it, when they are offsets in a partition that starts at `start`
    bytes. None if any extent's place isn't known, or if they fall past
    the disk's end, which can't be."""
    if not extents or size <= 0 or any(flags & UNPLACED for *_rest, flags in extents):
        return None
    first = start + min(physical for _logical, physical, _length, _flags in extents)
    last = start + max(physical + length for _logical, physical, length, _flags in extents)
    if last > size:
        return None
    return first / size, last / size


def _sectors(path: str) -> Optional[int]:
    try:
        return int(_read(pathlib.Path(sysroot.path(path))))
    except ValueError:
        return None


def unplaceable(filesystem: Optional[str], layers: Sequence[str],
                disks: Sequence[str]) -> Optional[str]:
    """Why where a file lies on its disk can't be known, as a key: its file
    system ("filesystem"), the first layer between it and the disk ("crypt",
    "lvm", "raid", "mapped" or "loop"), or "several_disks". None if nothing
    stands in the way, as with ext4, XFS or f2fs straight on a partition or
    on the whole disk, where FIEMAP's offsets are the disk's."""
    if filesystem not in PLACEABLE:
        return "filesystem"
    if layers:
        return layers[0]
    if len(disks) != 1:
        return "several_disks"
    return None


def placement_of(plan: Plan, extents: Optional[Sequence[Sequence[int]]]) -> Optional[tuple[float, float]]:
    """Where the file lay on its disk, where that can be known."""
    if (not extents or not plan.device
            or unplaceable(plan.filesystem, plan.layers, plan.disks) is not None):
        return None
    disk = plan.disks[0]
    size = _sectors(f"{SYS_BLOCK}/{disk}/size")
    start = 0 if plan.device == disk else _sectors(f"{SYS_BLOCK}/{disk}/{plan.device}/start")
    if not size or start is None:
        return None
    return span(extents, start * SECTOR, size * SECTOR)


def written_estimate(plan: Plan, bytes_per_second: float) -> int:
    """About how much a run of `plan` writes on a disk that writes that
    fast: the file once, and every lap of every test for as long as it
    lasts."""
    if not plan.write:
        return plan.bytes_
    laps = len(plan.tests) * (plan.laps + 1)
    return plan.bytes_ + int(laps * plan.lap_seconds * bytes_per_second)


def writing_seconds(plan: Plan) -> float:
    """For how long a run of `plan` writes, once the file is written."""
    if not plan.write:
        return 0.0
    return len(plan.tests) * (plan.laps + 1) * plan.lap_seconds


def seconds_estimate(plan: Plan, fill_seconds: float = 0.0) -> float:
    """How long a run of `plan` takes: its tests, and writing the file
    first, for as long as `fill_seconds` says that takes."""
    directions = 2 if plan.write else 1
    return fill_seconds + len(plan.tests) * directions * (
        plan.pause_seconds + (plan.laps + 1) * plan.lap_seconds)


# -- running it --------------------------------------------------------------

def native_module():
    """`silux_bench` with its disk test, or None where it isn't there."""
    try:
        import silux_bench
    except ImportError:
        return None
    return silux_bench if hasattr(silux_bench, "DiskFile") else None


def run(plan: Plan, on_progress: Optional[Callable[[dict], None]] = None,
        stop: Optional[threading.Event] = None) -> Result:
    """Measure in a child process and wait for it. Call from a thread.

    `on_progress` gets each of the child's messages: its `phase` ("reserve",
    "fill", "pause", "lap" or "lapped"), the fraction `done` and, for a lap, which
    test, direction and lap. Setting `stop` kills the child, and the file
    goes with it.
    """
    started = time.time()
    if native_module() is None:
        return _result({"reason": "no_module"}, plan, started)
    if not fits(plan):
        return _result({"reason": "too_big_for_fat",
                        "figures": {"largest": largest_file(plan.filesystem)}}, plan, started)
    # Time to write the file on a slow pen drive, and the tests half as
    # long again.
    timeout = 120 + plan.bytes_ / (2 * MIB) + 1.5 * seconds_estimate(plan)
    outcome = childrun.run("silux.disktest", json.dumps(dataclasses.asdict(plan)),
                           on_progress, stop, timeout)
    if outcome.not_started is not None:
        return _result({"reason": "not_started", "detail": outcome.not_started}, plan, started)
    if outcome.cancelled:
        return _result({"reason": "cancelled"}, plan, started)
    if outcome.answer is None:
        return _result({"reason": "failed", "detail": outcome.detail}, plan, started)
    return _result(outcome.answer, plan, started)


def _disconnected(disks: Sequence[str]) -> bool:
    """Whether any of the disks has gone from the system: unplugged, or a
    card taken out of its reader, whose slot stays with nothing in it."""
    from .providers import storage

    return any(not os.path.exists(sysroot.path(f"{SYS_BLOCK}/{disk}")) or storage._no_medium(disk)
               for disk in disks)


def _result(answer: dict, plan: Plan, started: float) -> Result:
    measures = tuple(saved.from_dict(Measure, m, MEASURE_PARTS)
                     for m in answer.get("measures", ()))
    reason = answer.get("reason")
    # Whatever the engine made of it (an I/O error, a folder that went), a
    # disk that went away mid-test is that.
    if reason not in (None, "cancelled") and _disconnected(plan.disks):
        reason = "disconnected"
    result = Result(
        timestamp=started, profile=plan.profile, measures=measures,
        engine=answer.get("engine"), uring_errno=answer.get("uring_errno"),
        bytes_=plan.bytes_, laps=plan.laps, lap_seconds=plan.lap_seconds,
        pause_seconds=plan.pause_seconds, mountpoint=plan.mountpoint,
        filesystem=plan.filesystem, disks=plan.disks, layers=plan.layers,
        creation=answer.get("creation"), no_cow=answer.get("no_cow"),
        align_declared=answer.get("align_declared"),
        written_bytes=int(answer.get("written_bytes", 0)),
        temperature_start_c=answer.get("temperature_start_c"),
        temperature_peak_c=answer.get("temperature_peak_c"),
        temperature_end_c=answer.get("temperature_end_c"),
        seconds=round(time.time() - started, 1),
        reason=reason, detail=answer.get("detail", ""),
        figures=tuple((answer.get("figures") or {}).items()),
        placement=placement_of(plan, answer.get("extents")))
    return dataclasses.replace(result, warnings=warnings_of(result, plan.warnings))


def warnings_of(result: Result, place: Sequence[str] = ()) -> tuple[str, ...]:
    """Everything a result has to be read with: what the folder sits on,
    and what the checks after each test found. Keys the interface translates."""
    found = list(place)
    if result.no_cow is False:
        # btrfs, and the file kept its checksums: direct writes may not be.
        found.append("copy_on_write")
    if any(m.cached_bytes for m in result.measures):
        found.append("through_the_cache")
    if any(m.stands_for for m in result.measures):
        found.append("queue_of_threads")
    for measure in result.measures:
        if measure.disk_bytes is None or not measure.moved_bytes:
            continue
        ratio = measure.disk_bytes / measure.moved_bytes
        # The disks moved much less than was counted: something answered
        # for them. Much more: another program was using them.
        if ratio < 0.9:
            found.append("disk_moved_less")
        elif ratio > 1.5:
            found.append("disk_was_busy")
    return tuple(dict.fromkeys(found))


# -- the child ---------------------------------------------------------------

def _temperature(disks: Sequence[str]) -> Optional[float]:
    """The hottest of the disks, where they say."""
    from .providers import storage

    found = [storage._temperature(pathlib.Path(sysroot.path(SYS_BLOCK)) / name)[0]
             for name in disks]
    return max((t for t in found if t is not None), default=None)


def _disk_bytes(disks: Sequence[str], direction: str) -> Optional[int]:
    """What the disks have read, or written, since they were attached: the
    kernel's own count, in sectors of 512 bytes."""
    total = 0
    for name in disks:
        fields = _read(pathlib.Path(sysroot.path(SYS_BLOCK)) / name / "stat").split()
        try:
            total += int(fields[2 if direction == "read" else 6]) * SECTOR
        except (IndexError, ValueError):
            return None
    return total if disks else None


class _ThroughTheCache(Exception):
    """A file system that falls back to the page cache without a word did:
    what comes after would be the memory's figures."""


def _reserved(silux_bench, plan: dict, emit: Callable[[dict], None]):
    """The test's file, made and its space reserved.

    FAT32 reserves a file by writing all of it with zeros, in one call that
    can take as long as filling it. Meanwhile what the kernel counts written
    to the disk says how far it has got. Elsewhere reserving takes no time
    and nothing is said.
    """
    disks = plan["disks"]
    start = _disk_bytes(disks, "write")
    made = threading.Event()
    began = time.monotonic()

    def report() -> None:
        while not made.wait(0.25):
            now = _disk_bytes(disks, "write")
            if start is None or now is None or now <= start:
                continue
            done = min((now - start) / plan["bytes_"], 0.99)
            left = fill_left(time.monotonic() - began, done)
            emit({"phase": "reserve", "done": done,
                  **({} if left is None else {"left_seconds": round(left)})})

    reporter = threading.Thread(target=report, daemon=True)
    reporter.start()
    try:
        return silux_bench.DiskFile(plan["folder"], bytes=plan["bytes_"], margin=plan["margin"])
    finally:
        made.set()
        reporter.join()


def _measure(plan: dict, emit: Callable[[dict], None]) -> dict:
    """Everything the plan asks for, in this process."""
    import silux_bench

    tests = [Test(**test) for test in plan["tests"]]
    disks = plan["disks"]
    why = silux_bench.uring_error()
    engine = plan["engine"] or ("uring" if why is None else "threads")
    answer: dict = {"engine": engine, "uring_errno": why, "measures": [], "written_bytes": 0}
    answer["temperature_start_c"] = peak = _temperature(disks)

    def hottest(now: Optional[float]) -> Optional[float]:
        return now if peak is None else peak if now is None else max(peak, now)

    try:
        file = _reserved(silux_bench, plan, emit)
        answer.update(creation=file.creation, no_cow=file.no_cow, align_declared=file.align[2])

        control = silux_bench.Control()
        filled = threading.Event()

        began = time.monotonic()

        def report() -> None:
            while not filled.wait(0.1):
                step, of = control.progress()
                if of:
                    left = fill_left(time.monotonic() - began, step / of)
                    emit({"phase": "fill", "done": step / of,
                          **({} if left is None else {"left_seconds": round(left)})})

        reporter = threading.Thread(target=report, daemon=True)
        reporter.start()
        try:
            file.fill(control=control)
        finally:
            filled.set()
            reporter.join()
        answer["written_bytes"] = plan["bytes_"]
        if plan["filesystem"] in PLACEABLE and hasattr(file, "extents"):
            try:
                answer["extents"] = [list(extent) for extent in file.extents()]
            except silux_bench.SiluxBenchError:
                pass

        directions = ("read", "write") if plan["write"] else ("read",)
        steps = len(tests) * len(directions) * (plan["laps"] + 1)
        step = 0
        for asked in tests:
            ran = asked.as_run_by(engine)
            for direction in directions:
                about = {"test": ran.name, "direction": direction, "laps": plan["laps"]}
                emit({"phase": "pause", "done": step / steps, **about})
                time.sleep(plan["pause_seconds"])
                before = _disk_bytes(disks, direction)
                laps = []
                for number in range(plan["laps"] + 1):
                    emit({"phase": "lap", "lap": number, "done": step / steps, **about})
                    lap = file.lap(asked.pattern, direction, block=asked.block,
                                   depth=asked.depth * asked.threads,
                                   seconds=plan["lap_seconds"], engine=engine, seed=number + 1)
                    step += 1
                    laps.append({
                        "number": number,
                        "bytes_per_second": int(lap["bytes_per_second"]),
                        "requests_per_second": lap["requests_per_second"],
                        "bytes_": lap["bytes"],
                        **{name: lap[name] for name in lap if name.startswith("latency_")},
                        "samples": lap["samples"]})
                    if direction == "write":
                        answer["written_bytes"] += lap["bytes"]
                    emit({"phase": "lapped", "lap": number, "done": step / steps,
                          "bytes_per_second": int(lap["bytes_per_second"]), **about})
                after = _disk_bytes(disks, direction)
                now = _temperature(disks)
                peak = hottest(now)
                try:
                    cached = file.cached_bytes()
                except silux_bench.SiluxBenchError:
                    cached = None
                if cached and plan["filesystem"] in SILENT_FALLBACK:
                    rates = sorted(lap["bytes_per_second"] for lap in laps[1:]) or [0]
                    raise _ThroughTheCache(
                        f"{cached} bytes of the file in the page cache after {ran.name} "
                        f"{direction} on {plan['filesystem']}, measured at "
                        f"{rates[len(rates) // 2]} B/s", cached)
                answer["measures"].append({
                    "pattern": ran.pattern, "block": ran.block, "depth": ran.depth,
                    "threads": ran.threads, "direction": direction,
                    "stands_for": asked.name if ran != asked else "", "laps": laps,
                    "cached_bytes": cached, "temperature_c": now,
                    "disk_bytes": None if before is None or after is None else after - before})
        file.close()
    except silux_bench.SiluxBenchError as error:
        # What was measured before it stays in the answer.
        answer.update(reason=str(error.args[0]), detail=str(error.args[-1]),
                      figures=dict(getattr(error, "details", {}) or {}))
    except _ThroughTheCache as error:
        # The measure that went through it isn't kept: it timed the memory.
        answer.update(reason="cache_fallback", detail=str(error.args[0]),
                      figures={"cached_bytes": error.args[1]})
    answer["temperature_end_c"] = now = _temperature(disks)
    answer["temperature_peak_c"] = hottest(now)
    return answer


def main() -> int:
    # The test file goes with this process, whatever the window died of.
    childrun.die_with_parent()
    plan = json.loads(sys.argv[1])

    def emit(message: dict) -> None:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()

    try:
        answer = _measure(plan, emit)
    except BrokenPipeError:
        # Nobody is reading any more: the file goes with this process.
        return 1
    except Exception as error:  # whatever it was, the parent says it
        answer = {"reason": "failed", "detail": f"{type(error).__name__}: {error}"}
    emit({"result": answer})
    return 0


# -- this machine's earlier tests --------------------------------------------

# The parts of a saved test that are lists of rows of their own, and the
# fields that tell one row of each from another.
MEASURE_PARTS = (("laps", Lap, ("number",), ()),)
PARTS = (("measures", Measure, ("pattern", "block", "depth", "threads", "direction"),
          MEASURE_PARTS),)


def history_path() -> pathlib.Path:
    from . import history

    return history.data_dir() / "disk-tests.json"


def _from_dict(row: dict) -> Result:
    return saved.from_dict(Result, row, PARTS)


def load_history() -> list[Result]:
    """Saved tests, newest first."""
    return saved.load(history_path(), HISTORY_VERSION, _from_dict)


def save_history(results: Sequence[Result]) -> bool:
    return saved.save(history_path(), HISTORY_VERSION, results[:MAX_ENTRIES], PARTS)


def append_history(result: Result) -> list[Result]:
    results = [result] + load_history()
    save_history(results)
    return results[:MAX_ENTRIES]


def clear_history() -> None:
    try:
        history_path().unlink()
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
