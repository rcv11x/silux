"""A root the kernel mounted itself, without an initramfs, is /dev/root in
/proc/mounts, a name no file has. As findmnt, it is found by the device
number of what is mounted there: Storage gives that partition its mount,
and a disk test in it knows its disk. Without it, a disk test's result
there was saved and never shown.

The dump is a virtual machine's, mounted as a machine booted that way would
be dumped: /dev/root in its mounts, and its realpath and device recorded.
"""

import json
import os
import unittest

from silux import disktest, sysroot, volcado
from tests.test_equipos import EQUIPOS


def _booted_without_initramfs(root) -> None:
    mounts = root / "proc/self/mounts"
    text = mounts.read_text()
    assert text.count("/dev/sda1 / ext4 ") == 1
    mounts.write_text(text.replace("/dev/sda1 / ext4 ", "/dev/root / ext4 "))
    recording = json.loads((root / sysroot.RECORDING_FILE).read_text())
    recording["realpath"]["/dev/root"] = "/dev/root"
    recording.setdefault("mount_device", {})["/"] = "sda1"
    (root / sysroot.RECORDING_FILE).write_text(json.dumps(recording))
    sysroot.forget()


class TestKernelRoot(unittest.TestCase):
    def test_storage_gives_the_partition_its_mount(self):
        from silux.collector import Collector

        with volcado.mounted(EQUIPOS / "qemu-kvm") as root:
            _booted_without_initramfs(root)
            collector = Collector()
            try:
                snapshot = collector.snapshot()
            finally:
                collector.close()
        partition = next(p for disk in snapshot.disks for p in disk.partitions
                         if p.name == "sda1")
        self.assertEqual(partition.mountpoint, "/")
        self.assertEqual(partition.filesystem, "ext4")

    def test_a_disk_test_there_knows_its_disk(self):
        with volcado.mounted(EQUIPOS / "qemu-kvm") as root:
            _booted_without_initramfs(root)
            place = disktest.where(os.sep)
        self.assertEqual(place.mountpoint, "/")
        self.assertEqual(place.disks, ("sda",))


if __name__ == "__main__":
    unittest.main()
