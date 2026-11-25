"""The disk test: what a folder sits on, the run in its child, and its history."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from silux import disktest, sysroot
from silux.disktest import GIB, KIB, MIB, Lap, Measure, Place
from tests.per_dump import per_dump
from tests.test_disk_native import _base
from tests.test_equipos import shared_snapshot

# Kernel `/proc/mounts` lines, as real systems print them.
MOUNTS = """\
/dev/nvme0n1p2 / btrfs rw,noatime,compress=zstd:1,ssd,subvolid=256,subvol=/@ 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
tmpfs /tmp tmpfs rw,nosuid,nodev,size=16G 0 0
/dev/nvme0n1p2 /home btrfs rw,noatime,compress=zstd:1,ssd,subvolid=257,subvol=/@home 0 0
/dev/nvme0n1p1 /boot vfat rw,relatime,fmask=0077,dmask=0077 0 0
/dev/mapper/luks-1f2e /home/secret ext4 rw,relatime 0 0
/dev/mapper/vg-data /srv/data xfs rw,relatime 0 0
/dev/md0 /srv/raid ext4 rw,relatime 0 0
/dev/sdb1 /media/My\\040Disk fuseblk rw,nosuid,nodev,user_id=0,group_id=0,allow_other,blksize=4096 0 0
/dev/sdc1 /media/readonly ext4 ro,relatime 0 0
/dev/sdd1 /srv/pool btrfs rw,relatime 0 0
/dev/loop3 /media/image ext4 rw,relatime 0 0
server:/export /mnt/nfs nfs4 rw,relatime,vers=4.2,addr=192.0.2.1 0 0
//server/share /mnt/smb cifs rw,relatime,vers=3.1.1 0 0
user@host:/home/user /mnt/ssh fuse.sshfs rw,nosuid,nodev,user_id=1000,group_id=1000 0 0
tank/data /tank/data zfs rw,xattr,noacl 0 0
overlay /var/lib/containers/merged overlay rw,relatime,lowerdir=/l,upperdir=/u,workdir=/w 0 0
gocryptfs /home/vault fuse.gocryptfs rw,nosuid,nodev,user_id=1000,group_id=1000 0 0
hostshare /mnt/host 9p rw,relatime,trans=virtio 0 0
/dev/sde1 /mnt/over ext4 rw,relatime 0 0
/dev/sdf1 /mnt/over ext4 rw,relatime 0 0
"""


class TestNames(unittest.TestCase):
    def test_a_test_is_named_as_crystaldiskmark_names_it(self):
        for test, name in ((disktest.Test("sequential", MIB, 8), "SEQ1M Q8T1"),
                           (disktest.Test("sequential", MIB, 1), "SEQ1M Q1T1"),
                           (disktest.Test("random", 4 * KIB, 32), "RND4K Q32T1"),
                           (disktest.Test("random", 4 * KIB, 1), "RND4K Q1T1"),
                           (disktest.Test("sequential", 128 * KIB, 32), "SEQ128K Q32T1"),
                           (disktest.Test("random", 4 * KIB, 32, 16), "RND4K Q32T16"),
                           (disktest.Test("random", 512, 1), "RND512B Q1T1")):
            self.assertEqual(test.name, name)
        self.assertEqual([test.name for test in disktest.PROFILES["standard"]],
                         ["SEQ1M Q8T1", "SEQ1M Q1T1", "RND4K Q32T1", "RND4K Q1T1"])

    def test_a_queue_made_of_threads_is_another_test_and_is_named_so(self):
        for asked, ran in (("SEQ1M Q8T1", "SEQ1M Q1T8"), ("SEQ1M Q1T1", "SEQ1M Q1T1"),
                           ("RND4K Q32T1", "RND4K Q1T32"), ("RND4K Q1T1", "RND4K Q1T1")):
            test = next(t for t in disktest.PROFILES["standard"] if t.name == asked)
            self.assertEqual(test.as_run_by("threads").name, ran)
            self.assertEqual(test.as_run_by("uring").name, asked)
        self.assertEqual(disktest.Test("random", 4 * KIB, 32, 16).as_run_by("threads").name,
                         "RND4K Q1T512")


class TestWhere(unittest.TestCase):
    """What a folder sits on, from a table of mounts and a tree of block
    devices laid out as the kernel does."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="silux-where-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "proc").mkdir()
        (self.root / "proc" / "mounts").write_text(MOUNTS, encoding="utf-8")
        block = self.root / "sys" / "block"
        for disk, partitions in (("nvme0n1", ("nvme0n1p1", "nvme0n1p2", "nvme0n1p3")),
                                 ("sda", ("sda1", "sda2")), ("sdb", ("sdb1",)),
                                 ("sdc", ("sdc1",)), ("sdd", ("sdd1",)), ("sde", ("sde1",)),
                                 ("sdf", ("sdf1",)), ("sdg", ()), ("loop3", ())):
            for partition in partitions:
                (block / disk / partition).mkdir(parents=True)
            (block / disk / "slaves").mkdir(parents=True, exist_ok=True)
        # LUKS over a partition, LVM over two disks, a RAID of two.
        for name, uuid, below in (("dm-0", "CRYPT-LUKS2-1f2e-luks-1f2e", ("nvme0n1p3",)),
                                  ("dm-1", "LVM-abcdef", ("sda1", "sdg")),
                                  ("md0", None, ("sda2", "sdc1"))):
            for one in below:
                (block / name / "slaves" / one).mkdir(parents=True)
            if uuid:
                (block / name / "dm").mkdir()
                (block / name / "dm" / "uuid").write_text(uuid + "\n", encoding="utf-8")
        # A btrfs over two devices names one in its mount.
        for device in ("sdd1", "sde1"):
            (self.root / "sys" / "fs" / "btrfs" / "0a1b" / "devices" / device).mkdir(parents=True)
        (self.root / "sys" / "fs" / "btrfs" / "9f8e" / "devices" / "nvme0n1p2").mkdir(parents=True)
        # What `/dev/mapper/…` pointed at, recorded as in a dumped machine:
        # `/dev` itself isn't part of one.
        (self.root / sysroot.RECORDING_FILE).write_text(json.dumps({"realpath": {
            "/dev/mapper/luks-1f2e": "/dev/dm-0", "/dev/mapper/vg-data": "/dev/dm-1"}}),
            encoding="utf-8")
        # The folders asked about are the table's, not this machine's.
        patches = (mock.patch.dict(os.environ, {sysroot.VARIABLE: str(self.root)}),
                   mock.patch.object(os.path, "realpath", lambda p, **_k: p))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        sysroot.forget()
        self.addCleanup(sysroot.forget)

    def assert_place(self, folder, mountpoint, filesystem, disks, layers=(), refusal=None,
                     warnings=()):
        place = disktest.where(folder)
        self.assertEqual(
            (place.mountpoint, place.filesystem, place.disks, place.layers, place.refusal,
             place.warnings),
            (mountpoint, filesystem, tuple(disks), tuple(layers), refusal, tuple(warnings)),
            folder)

    def test_the_deepest_mount_holds_the_folder(self):
        self.assert_place("/", "/", "btrfs", ["nvme0n1"])
        self.assert_place("/usr/lib", "/", "btrfs", ["nvme0n1"])
        self.assert_place("/home/someone/.cache/silux", "/home", "btrfs", ["nvme0n1"])
        # Not `/home`, though its name begins the same.
        self.assert_place("/homework", "/", "btrfs", ["nvme0n1"])
        self.assert_place("/boot/EFI", "/boot", "vfat", ["nvme0n1"])

    def test_of_two_mounts_in_one_place_the_last_is_the_one_seen(self):
        self.assert_place("/mnt/over/folder", "/mnt/over", "ext4", ["sdf"])

    def test_a_folder_in_memory_or_on_another_machine_is_refused(self):
        self.assert_place("/tmp/work", "/tmp", "tmpfs", [], refusal="in_memory")
        for folder, mountpoint, filesystem in (
                ("/mnt/nfs/a", "/mnt/nfs", "nfs4"), ("/mnt/smb", "/mnt/smb", "cifs"),
                ("/mnt/ssh/b", "/mnt/ssh", "fuse.sshfs"), ("/mnt/host", "/mnt/host", "9p")):
            self.assert_place(folder, mountpoint, filesystem, [], refusal="network")
        self.assert_place("/proc/self", "/proc", "proc", [], refusal="not_a_disk")
        self.assert_place("/media/readonly", "/media/readonly", "ext4", ["sdc"],
                          refusal="read_only")

    def test_what_lies_between_the_folder_and_its_disks_is_found(self):
        self.assert_place("/home/secret/x", "/home/secret", "ext4", ["nvme0n1"], ["crypt"],
                          warnings=["encrypted"])
        self.assert_place("/srv/data", "/srv/data", "xfs", ["sda", "sdg"], ["lvm"],
                          warnings=["several_disks"])
        self.assert_place("/srv/raid", "/srv/raid", "ext4", ["sda", "sdc"], ["raid"],
                          warnings=["several_disks"])
        self.assert_place("/srv/pool", "/srv/pool", "btrfs", ["sdd", "sde"],
                          warnings=["several_disks"])
        self.assert_place("/media/image", "/media/image", "ext4", [], ["loop"],
                          warnings=["loop"])

    def test_a_driver_outside_the_kernel_is_measured_with_its_warning(self):
        # The space in its name comes escaped in the table.
        self.assert_place("/media/My Disk/folder", "/media/My Disk", "fuseblk", ["sdb"],
                          warnings=["fuse_driver"])
        self.assert_place("/home/vault", "/home/vault", "fuse.gocryptfs", [],
                          warnings=["fuse"])
        self.assert_place("/tank/data/x", "/tank/data", "zfs", [], warnings=["zfs"])
        self.assert_place("/var/lib/containers/merged", "/var/lib/containers/merged",
                          "overlay", [], warnings=["overlay"])

    def test_a_plan_carries_where_it_measures(self):
        plan = disktest.make_plan("/home/secret/x", bytes_=64 * MIB, write=False)
        self.assertEqual((plan.mountpoint, plan.filesystem, plan.disks, plan.layers,
                          plan.warnings),
                         ("/home/secret", "ext4", ("nvme0n1",), ("crypt",), ("encrypted",)))
        self.assertEqual((plan.bytes_, plan.write, plan.laps), (64 * MIB, False, 5))
        self.assertEqual(plan.tests, disktest.PROFILES["standard"])


class TestWhereOnEveryDump(unittest.TestCase):
    pass


def _every_partition_resolves_to_its_disk(self, folder):
    """Each mounted partition the storage page shows sits on the disk it is
    shown under."""
    snapshot = shared_snapshot(folder)
    from tests.test_equipos import _herramienta

    with _herramienta().mounted(folder):
        sysroot.forget()
        for disk in snapshot.disks:
            for partition in disk.partitions:
                if not partition.mountpoint:
                    continue
                with mock.patch.object(os.path, "realpath", lambda p, **_k: p):
                    place = disktest.where(partition.mountpoint)
                self.assertIsNotNone(place, partition.mountpoint)
                self.assertEqual(place.mountpoint, partition.mountpoint)
                self.assertEqual(place.disks, (disk.name,), partition.mountpoint)
                self.assertEqual(place.filesystem, partition.filesystem)
    sysroot.forget()


per_dump(TestWhereOnEveryDump, "every_partition_resolves_to_its_disk",
         _every_partition_resolves_to_its_disk)


FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "disktest"


def recorded(name: str) -> disktest.Result:
    return disktest._from_dict(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


def _laps(*rates: int) -> tuple[Lap, ...]:
    return tuple(Lap(number, rate, rate / 4096, rate * 5, 50_000.0, 20_000, 48_000, 90_000,
                     200_000, 900_000, ((250_000_000, rate // 4),))
                 for number, rate in enumerate(rates))


class TestFigures(unittest.TestCase):
    def test_the_figure_is_the_middle_lap_and_the_first_doesnt_count(self):
        measure = Measure("random", 4096, 1, 1, "read", laps=_laps(999, 80, 100, 90, 85, 95))
        self.assertEqual([lap.number for lap in measure.counted], [1, 2, 3, 4, 5])
        self.assertEqual(measure.median.bytes_per_second, 90)
        self.assertEqual(measure.best.bytes_per_second, 100)
        self.assertEqual(measure.worst.bytes_per_second, 80)
        # The median of |80 100 90 85 95 - 90| is 5, over 90.
        self.assertAlmostEqual(measure.spread, 5 / 90)
        self.assertTrue(measure.noisy)
        self.assertEqual(measure.moved_bytes, 5 * (999 + 80 + 100 + 90 + 85 + 95))
        steady = Measure("random", 4096, 1, 1, "read", laps=_laps(50, 100, 101, 99, 100, 102))
        self.assertFalse(steady.noisy)
        # With an even number of laps, a lap that was run and not a mean.
        even = Measure("random", 4096, 1, 1, "read", laps=_laps(1, 10, 40, 20, 30))
        self.assertEqual(even.median.bytes_per_second, 20)

    def test_a_test_without_laps_has_no_figures(self):
        empty = Measure("random", 4096, 1, 1, "read", laps=_laps(999))
        self.assertEqual((empty.median, empty.best, empty.worst, empty.spread, empty.noisy),
                         (None, None, None, None, False))

    def test_what_the_checks_find_becomes_a_warning(self):
        def result(**changes):
            measure = dataclasses.replace(
                Measure("random", 4096, 1, 1, "read", laps=_laps(1, 100, 100)),
                **{k: v for k, v in changes.items() if k in ("cached_bytes", "disk_bytes",
                                                              "stands_for")})
            rest = {k: v for k, v in changes.items() if k == "no_cow"}
            return disktest.Result(measures=(measure,), **rest)

        moved = 5 * 201
        for changes, expected in (
                ({}, ()),
                ({"cached_bytes": 0, "disk_bytes": moved, "no_cow": True}, ()),
                ({"no_cow": False}, ("copy_on_write",)),
                ({"cached_bytes": 4096}, ("through_the_cache",)),
                ({"stands_for": "RND4K Q32T1"}, ("queue_of_threads",)),
                ({"disk_bytes": moved // 2}, ("disk_moved_less",)),
                ({"disk_bytes": moved * 2}, ("disk_was_busy",)),
                ({"disk_bytes": int(moved * 1.2)}, ())):
            self.assertEqual(disktest.warnings_of(result(**changes)), expected, changes)
        self.assertEqual(disktest.warnings_of(result(no_cow=False), ("encrypted",)),
                         ("encrypted", "copy_on_write"))

    def test_what_a_run_writes_and_lasts_is_said_before(self):
        plan = disktest.make_plan("/nowhere", place=Place("/", "ext4", "/dev/sda1"))
        # Four tests, read and written: a pause and six laps of five seconds.
        self.assertEqual(disktest.seconds_estimate(plan), 4 * 2 * (5 + 6 * 5))
        self.assertEqual(disktest.written_estimate(plan, 1e9), disktest.GIB + 4 * 6 * 5 * 10**9)
        reading = dataclasses.replace(plan, write=False)
        self.assertEqual(disktest.seconds_estimate(reading), 4 * (5 + 6 * 5))
        self.assertEqual(disktest.written_estimate(reading, 1e9), disktest.GIB)


@unittest.skipUnless(disktest.native_module(), "silux_bench has no disk benchmark")
class TestRunning(unittest.TestCase):
    def setUp(self):
        _base().mkdir(parents=True, exist_ok=True)
        self.folder = pathlib.Path(tempfile.mkdtemp(prefix="disktest-", dir=_base()))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def plan(self, **changes) -> disktest.Plan:
        settings = dict(bytes_=8 * MIB, laps=2, lap_seconds=0.1, pause_seconds=0.0, write=False)
        return disktest.make_plan(self.folder, **{**settings, **changes})

    def run_it(self, plan, *more) -> disktest.Result:
        result = disktest.run(plan, *more)
        if result.reason in ("in_memory", "no_direct", "no_space"):
            self.skipTest(result.detail)
        return result

    def test_a_run_measures_each_test_and_leaves_nothing(self):
        messages: list[dict] = []
        # The least a run with writes can write: one lap that counts.
        plan = self.plan(write=True, laps=1, lap_seconds=0.05)
        result = self.run_it(plan, messages.append)
        self.assertEqual((result.reason, result.detail), (None, ""))
        self.assertTrue(result.measured)
        self.assertIn(result.engine, ("uring", "threads"))
        ran = [test.as_run_by(result.engine) for test in plan.tests]
        self.assertEqual([(m.name, m.direction) for m in result.measures],
                         [(test.name, direction) for test in ran
                          for direction in ("read", "write")])
        for measure in result.measures:
            self.assertEqual([lap.number for lap in measure.laps], [0, 1], measure.name)
            for lap in measure.laps:
                self.assertGreater(lap.bytes_per_second, 0)
                self.assertEqual(lap.bytes_ % measure.block, 0)
                self.assertLessEqual(lap.latency_min_ns, lap.latency_max_ns)
            if result.no_cow is not False:
                self.assertEqual(measure.cached_bytes, 0, measure.name)
        # The file once, and every lap that wrote.
        self.assertEqual(result.written_bytes, 8 * MIB + sum(
            m.moved_bytes for m in result.measures if m.direction == "write"))
        self.assertEqual((result.bytes_, result.laps, result.lap_seconds, result.profile),
                         (8 * MIB, 1, 0.05, "standard"))
        self.assertEqual((result.mountpoint, result.filesystem, result.disks),
                         (plan.mountpoint, plan.filesystem, plan.disks))
        self.assertIn(result.creation, ("unnamed", "unlinked"))
        self.assertEqual(os.listdir(self.folder), [])
        # Each lap was announced and then told, and it ended at the whole.
        told = [(m["test"], m["direction"], m["lap"]) for m in messages if m["phase"] == "lapped"]
        self.assertEqual(told, [(m.name, m.direction, lap.number)
                                for m in result.measures for lap in m.laps])
        self.assertEqual(messages[-1]["done"], 1.0)
        self.assertEqual(sum(1 for m in messages if m["phase"] == "pause"), len(result.measures))

    def test_where_the_file_lay_is_said_where_it_can_be(self):
        result = self.run_it(self.plan(laps=1))
        plan = self.plan()
        if plan.filesystem in disktest.PLACEABLE and not plan.layers and len(plan.disks) == 1:
            first, last = result.placement
            self.assertLessEqual(0, first)
            self.assertLess(first, last)
            self.assertLessEqual(last, 1)
        else:
            self.assertIsNone(result.placement)

    def test_without_a_ring_the_tests_are_the_ones_threads_can_run(self):
        result = self.run_it(self.plan(engine="threads", laps=1))
        self.assertEqual(result.engine, "threads")
        self.assertEqual([(m.name, m.stands_for) for m in result.measures],
                         [("SEQ1M Q1T8", "SEQ1M Q8T1"), ("SEQ1M Q1T1", ""),
                          ("RND4K Q1T32", "RND4K Q32T1"), ("RND4K Q1T1", "")])
        self.assertIn("queue_of_threads", result.warnings)
        # Asked for by the name of either, it is the same row.
        self.assertIs(result.measure("RND4K Q32T1", "read"), result.measure("RND4K Q1T32", "read"))
        self.assertIsNone(result.measure("RND4K Q32T1", "write"))

    def test_a_cancelled_run_leaves_nothing_either(self):
        stop = threading.Event()
        threading.Timer(1.0, stop.set).start()
        began = time.monotonic()
        result = self.run_it(self.plan(laps=5, lap_seconds=5.0, bytes_=64 * MIB), None, stop)
        self.assertEqual(result.reason, "cancelled")
        self.assertLess(time.monotonic() - began, 15)
        self.assertFalse(result.measured)
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_folder_that_cant_be_measured_says_why(self):
        missing = disktest.run(dataclasses.replace(
            self.plan(), folder=str(self.folder / "missing")))
        self.assertEqual((missing.reason, dict(missing.figures)), ("no_folder", {"errno": 2}))
        self.assertFalse(missing.measured)
        if os.path.isdir("/dev/shm") and disktest.where("/dev/shm").refusal == "in_memory":
            in_memory = disktest.run(dataclasses.replace(self.plan(), folder="/dev/shm"))
            self.assertEqual(in_memory.reason, "in_memory")

    def test_the_child_dies_with_whoever_started_it(self):
        """As when the window is killed: nobody is left to stop the test."""
        if self.run_it(self.plan(laps=1)).reason is not None:
            self.skipTest("nothing to measure here")
        plan = json.dumps(dataclasses.asdict(
            self.plan(laps=5, lap_seconds=5.0, bytes_=64 * MIB)))
        starter = subprocess.Popen(
            [sys.executable, "-c",
             "import subprocess, sys, time\n"
             "child = subprocess.Popen([sys.executable, '-m', 'silux.disktest', sys.argv[1]],"
             " stdout=subprocess.DEVNULL)\n"
             "print(child.pid, flush=True)\n"
             "time.sleep(60)\n", plan],
            stdout=subprocess.PIPE, text=True, cwd=pathlib.Path(__file__).parent.parent)
        self.addCleanup(starter.wait)
        self.addCleanup(starter.kill)
        child = int(starter.stdout.readline())
        time.sleep(1.5)
        os.kill(child, 0)       # still measuring
        starter.send_signal(signal.SIGKILL)
        starter.wait()
        for _attempt in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(child, signal.SIGKILL)
            self.fail("the child outlived the process that started it")
        self.assertEqual(os.listdir(self.folder), [])


class _CachedFile:
    """The engine's file, real in everything but the cache check, which
    answers as on a file system that fell back to the page cache."""

    def __init__(self, file):
        self._file = file

    def cached_bytes(self) -> int:
        return self._file.cached_bytes() + 4 * MIB

    def __getattr__(self, name):
        return getattr(self._file, name)


class TestThroughTheCache(unittest.TestCase):
    """FAT32, exFAT and NTFS fall back to the page cache without an error:
    the check after each test stops them, and only them."""

    def setUp(self):
        silux_bench = disktest.native_module()
        if silux_bench is None:
            self.skipTest("silux_bench has no disk benchmark")
        real = silux_bench.DiskFile
        patch = mock.patch.object(silux_bench, "DiskFile",
                                  lambda *args, **kwargs: _CachedFile(real(*args, **kwargs)))
        patch.start()
        self.addCleanup(patch.stop)
        _base().mkdir(parents=True, exist_ok=True)
        self.folder = pathlib.Path(tempfile.mkdtemp(prefix="disktest-", dir=_base()))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def measure(self, filesystem: str) -> dict:
        plan = disktest.make_plan(self.folder, bytes_=8 * MIB, laps=1, lap_seconds=0.05,
                                  pause_seconds=0.0, write=False)
        answer = disktest._measure(dataclasses.asdict(
            dataclasses.replace(plan, filesystem=filesystem)), lambda _message: None)
        if answer.get("reason") in ("in_memory", "no_direct", "no_space"):
            self.skipTest(answer["detail"])
        return answer

    def test_it_stops_where_the_fall_back_is_silent(self):
        for filesystem in ("vfat", "exfat", "ntfs3"):
            with self.subTest(filesystem):
                answer = self.measure(filesystem)
                self.assertEqual(answer["reason"], "cache_fallback")
                self.assertEqual(answer["figures"], {"cached_bytes": 4 * MIB})
                # The measure that timed the memory isn't kept; the report
                # has its figure.
                self.assertEqual(answer["measures"], [])
                self.assertIn("B/s", answer["detail"])
                self.assertEqual(os.listdir(self.folder), [])

    def test_elsewhere_it_goes_on_and_says_it(self):
        answer = self.measure("ext4")
        self.assertIsNone(answer.get("reason"))
        self.assertEqual(len(answer["measures"]), len(disktest.PROFILES["standard"]))
        self.assertTrue(all(m["cached_bytes"] for m in answer["measures"]))


class TestPenDrives(unittest.TestCase):
    def test_fat32_takes_files_below_4_gib_and_it_is_known_before_starting(self):
        self.assertEqual(disktest.largest_file("vfat"), 4095 * MIB)
        self.assertEqual(disktest.largest_file("msdos"), 4095 * MIB)
        for filesystem in ("exfat", "ntfs3", "ext4", None):
            self.assertIsNone(disktest.largest_file(filesystem), filesystem)
        plan = disktest.Plan("/media/pen", disktest.PROFILES["standard"], bytes_=4 * GIB,
                             filesystem="vfat")
        self.assertFalse(disktest.fits(plan))
        self.assertTrue(disktest.fits(dataclasses.replace(plan, bytes_=4095 * MIB)))
        self.assertTrue(disktest.fits(dataclasses.replace(plan, filesystem="exfat")))
        # Refused before the child, which would stop half way.
        with mock.patch.object(disktest.childrun, "run", side_effect=AssertionError):
            result = disktest.run(plan)
        if disktest.native_module() is not None:
            self.assertEqual((result.reason, dict(result.figures)),
                             ("too_big_for_fat", {"largest": 4095 * MIB}))

    def test_writing_the_file_says_how_long_it_has_left_at_its_pace(self):
        self.assertIsNone(disktest.fill_left(1.0, 0.5))
        self.assertIsNone(disktest.fill_left(10.0, 0.0))
        self.assertEqual(disktest.fill_left(30.0, 0.25), 90.0)

    def test_how_long_writing_the_file_takes_comes_from_what_is_known(self):
        plan = disktest.Plan("/media/pen", disktest.PROFILES["standard"], bytes_=GIB,
                             disks=("sdb",))
        mine = dataclasses.replace(recorded("sn850x-btrfs"), disks=("sdb",), model="Pen")
        rate = mine.measure("SEQ1M Q8T1", "write").median.bytes_per_second
        self.assertEqual(disktest.fill_estimate(plan, [mine], "Pen", 60e6), (GIB / rate, "last"))
        # Another disk under the same name: only its link is known.
        self.assertEqual(disktest.fill_estimate(plan, [mine], "Other", 60e6),
                         (GIB / 60e6, "link"))
        self.assertIsNone(disktest.fill_estimate(plan, [mine], "Other", None))


class TestWhereTheFileLay(unittest.TestCase):
    SECTOR = 512

    def test_its_extents_as_fractions_of_the_disk(self):
        start, size = 2048 * 512, 1_000_000 * 512
        extents = [(0, 600_000 * 512, 8 * 512, 0), (8 * 512, 610_000 * 512, 2000 * 512, 1)]
        first, last = disktest.span(extents, start, size)
        self.assertAlmostEqual(first, 0.602048)
        self.assertAlmostEqual(last, 0.614048)
        # A place not known, or past the disk's end, is no place.
        self.assertIsNone(disktest.span([(0, 0, 4096, 0x2 | 0x1)], start, size))
        self.assertIsNone(disktest.span([(0, size, 4096, 1)], start, size))
        self.assertIsNone(disktest.span([], start, size))

    def test_only_where_the_offsets_are_the_disk_s(self):
        plan = disktest.Plan("/media/hdd", disktest.PROFILES["standard"], filesystem="ext4",
                             disks=("sda",), device="sda2")
        extents = [(0, 4096, 4096, 1)]
        for changes in (dict(filesystem="btrfs"), dict(layers=("crypt",)),
                        dict(disks=("sda", "sdb")), dict(device=None)):
            with self.subTest(**changes):
                self.assertIsNone(disktest.placement_of(dataclasses.replace(plan, **changes),
                                                        extents))
        self.assertIsNone(disktest.placement_of(plan, None))

    def test_a_partition_starts_where_lsblk_says(self):
        """On this machine's disks, if it has a partition."""
        found = sorted(pathlib.Path("/sys/class/block").glob("*/partition"))
        if not found or shutil.which("lsblk") is None:
            self.skipTest("no partition here, or no lsblk")
        partition = found[0].parent.name
        disk = (found[0].parent / "..").resolve().name
        told = subprocess.run(["lsblk", "-bno", "START", f"/dev/{partition}"],
                              capture_output=True, text=True).stdout.split()
        if not told:
            self.skipTest("this lsblk doesn't say where a partition starts")
        self.assertEqual(disktest._sectors(f"/sys/block/{disk}/{partition}/start"), int(told[0]))


class TestRecordedRuns(unittest.TestCase):
    """Two whole runs with the defaults, recorded on real disks: an NVMe on
    btrfs and another on ext4."""

    def test_they_read_back_whole(self):
        for name, disk, filesystem in (("sn850x-btrfs", "nvme0n1", "btrfs"),
                                       ("970-evo-plus-ext4", "nvme1n1", "ext4")):
            result = recorded(name)
            self.assertEqual((result.disks, result.filesystem, result.engine, result.reason),
                             ((disk,), filesystem, "uring", None), name)
            self.assertEqual([(m.name, m.direction) for m in result.measures],
                             [(test.name, direction) for test in disktest.PROFILES["standard"]
                              for direction in ("read", "write")])
            for measure in result.measures:
                self.assertEqual([lap.number for lap in measure.laps], [0, 1, 2, 3, 4, 5])
                self.assertEqual(measure.cached_bytes, 0)
                self.assertLessEqual(measure.worst.bytes_per_second,
                                     measure.median.bytes_per_second)
                self.assertLessEqual(measure.median.bytes_per_second,
                                     measure.best.bytes_per_second)
                # The disk's own counters agree with what was counted.
                self.assertAlmostEqual(measure.disk_bytes / measure.moved_bytes, 1.0, delta=0.05)
            self.assertEqual(result.written_bytes, result.bytes_ + sum(
                m.moved_bytes for m in result.measures if m.direction == "write"))
            self.assertEqual(disktest.warnings_of(result), ())
            self.assertGreater(result.temperature_peak_c, result.temperature_start_c)
            # Saved and read again, it is the same.
            self.assertEqual(
                disktest._from_dict(json.loads(json.dumps(dataclasses.asdict(result)))), result)


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.remove()
        self.addCleanup(self.remove)

    def remove(self) -> None:
        for file in disktest.history_path().parent.glob("disk-tests.json*"):
            file.unlink()

    def result(self, timestamp: float = 1_800_000_000.5) -> disktest.Result:
        measures = (
            Measure("sequential", MIB, 8, 1, "read", laps=_laps(5, 7000, 7100, 6900),
                    cached_bytes=0, disk_bytes=123, temperature_c=51.5),
            Measure("random", 4096, 1, 32, "write", stands_for="RND4K Q32T1",
                    laps=_laps(5, 300, 310)))
        return disktest.Result(
            timestamp=timestamp, measures=measures, engine="threads", uring_errno=1,
            bytes_=disktest.GIB, laps=3, lap_seconds=5.0, pause_seconds=5.0, mountpoint="/home",
            filesystem="btrfs", disks=("nvme0n1",), layers=("crypt",), model="A disk",
            creation="unnamed", no_cow=True, align_declared=False, written_bytes=10**11,
            temperature_start_c=41.0, temperature_peak_c=63.0, temperature_end_c=52.0,
            seconds=312.4, warnings=("encrypted", "queue_of_threads"),
            figures=(("errno", 28), ("call", "pwrite")), label="with the heatsink")

    def test_what_is_saved_comes_back_the_same(self):
        first, second = self.result(), self.result(1_800_000_600.0)
        disktest.append_history(first)
        self.assertEqual(disktest.append_history(second), [second, first])
        self.assertEqual(disktest.load_history(), [second, first])
        self.assertEqual(disktest.load_history()[0].measures[0].laps[1].samples,
                         ((250_000_000, 1750),))

    def test_the_report_carries_the_latest_whole_and_the_code_of_what_failed(self):
        from silux import report
        from tests.test_equipos import EQUIPOS

        snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        self.assertNotIn("## Prueba de disco", report.build(snapshot))
        disktest.append_history(recorded("sn850x-btrfs"))
        text = report.build(snapshot)
        for expected in (
                "## Prueba de disco",
                "| SEQ1M Q8T1 | read | 6592.5 | 6616.4 | 6583.7 | 6248.3 | "
                "6583.7 6585.6 6608.0 6616.4 6592.5 | 6287 | 1272.2 | 1785.9 | 0 | 1.00 | 59.9 |",
                "| SEQ1M Q8T1 | write | 3946.1 (varió) | 5041.9 |",
                "| RND4K Q1T1 | read | 63.3 |",
                "| 15464 | 64.5 | 85.0 | 0 | 1.03 | 55.9 |",
                "perfil standard · motor: uring · WD_BLACK SN850X HS 1000GB · /home (btrfs) · "
                "sobre nvme0n1 · archivo de 1 GiB (unnamed) · +C sí · alineación supuesta · "
                "5 vueltas de 5 s, pausa 5 s · escribió 241.7 GB en 280.6 s · "
                "temperatura 50.85 → 62.85 → 53.85 °C"):
            self.assertIn(expected, text)
        self.assertNotIn("No terminó", text)

        # A run through threads says what ran, in place of what, and why;
        # and one that broke, its key, the module's words and its figures.
        threads = dataclasses.replace(recorded("sn850x-btrfs-threads"), uring_errno=1,
                                      timestamp=1_900_000_000.0)
        disktest.append_history(threads)
        text = report.build(snapshot)
        for expected in ("| RND4K Q1T32 (por RND4K Q32T1) | read |", "motor: threads",
                         "io_uring_setup: errno 1", "avisos: queue_of_threads"):
            self.assertIn(expected, text)
        disktest.append_history(disktest.Result(
            timestamp=1_900_000_100.0, reason="io", detail="pwrite failed (errno 5)",
            figures=(("call", "pwrite"), ("errno", 5)), engine="uring"))
        text = report.build(snapshot)
        self.assertIn("No terminó: io. pwrite failed (errno 5) (call=pwrite, errno=5)", text)

    def test_what_a_newer_version_saved_is_read_and_kept_down_to_each_lap(self):
        disktest.append_history(self.result())
        path = disktest.history_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        row = data["tests"][0]
        row["later"] = 1
        row["measures"][1]["later"] = "the second test"
        row["measures"][1]["laps"][2]["later"] = "its third lap"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(disktest.load_history(), [self.result()])

        # Saved again with its tests and their laps in another order.
        again = self.result(1_800_000_600.0)
        saved_one = self.result()
        shuffled = dataclasses.replace(saved_one, measures=tuple(
            dataclasses.replace(m, laps=m.laps[::-1]) for m in saved_one.measures[::-1]))
        disktest.save_history([again, shuffled])
        new, old = json.loads(path.read_text(encoding="utf-8"))["tests"]
        self.assertEqual(old["later"], 1)
        self.assertNotIn("later", new)
        self.assertEqual([m.get("later") for m in old["measures"]], ["the second test", None])
        self.assertEqual([lap.get("later") for lap in old["measures"][0]["laps"]],
                         ["its third lap", None, None])
        self.assertEqual([lap["number"] for lap in old["measures"][0]["laps"]], [2, 1, 0])

    def test_a_file_of_another_version_or_broken_is_set_aside(self):
        path = disktest.history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        for text, aside in (('{"version": 7, "tests": []}', "disk-tests.json.v7"),
                            ('{"version": 1, "tests": [{"timest', "disk-tests.json.broken")):
            path.write_text(text, encoding="utf-8")
            self.assertEqual(disktest.load_history(), [])
            self.assertEqual(disktest.append_history(self.result()), [self.result()])
            self.assertEqual(path.with_name(aside).read_text(encoding="utf-8"), text)
            self.assertEqual(disktest.load_history(), [self.result()])


if __name__ == "__main__":
    unittest.main()
