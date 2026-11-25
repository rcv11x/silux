"""The disk benchmark of the native module, as Python calls it.

What it measures is checked in the crate's own tests; here, that the file
and a lap arrive in Python as they should.
"""

from __future__ import annotations

import errno
import itertools
import os
import pathlib
import shutil
import tempfile
import threading
import time
import unittest

try:
    import silux_bench
except ImportError:
    silux_bench = None

MIB = 1024 * 1024
# The same place the crate's tests use, and the same way to move them to
# another disk: the suite's own folder is in memory on many systems.
BUILD = pathlib.Path(__file__).parent.parent / "native" / "silux_bench" / "target"


def _base() -> pathlib.Path:
    chosen = os.environ.get("SILUX_BENCH_DISK_DIR")
    if chosen:
        return pathlib.Path(chosen)
    if BUILD.is_dir():
        return BUILD / "disk-tests"
    return pathlib.Path(tempfile.gettempdir())


@unittest.skipUnless(hasattr(silux_bench, "DiskFile"), "silux_bench has no disk benchmark")
class TestDiskFile(unittest.TestCase):
    def setUp(self):
        _base().mkdir(parents=True, exist_ok=True)
        self.folder = pathlib.Path(tempfile.mkdtemp(prefix="python-", dir=_base()))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def file(self, size: int = 8 * MIB):
        """A file to test with, or a skip where this folder can't hold one
        read and written past the page cache."""
        try:
            file = silux_bench.DiskFile(self.folder, bytes=size)
        except silux_bench.SiluxBenchError as error:
            if error.args[0] in ("in_memory", "no_direct", "no_space"):
                self.skipTest(error.args[1])
            raise
        self.addCleanup(file.close)
        return file

    def test_where_the_file_lies_is_what_filefrag_says(self):
        import re
        import subprocess

        file = self.file()
        file.fill()
        try:
            ours = file.extents()
        except silux_bench.SiluxBenchError as error:
            self.skipTest(f"no FIEMAP here: {error.args[1]}")
        if shutil.which("filefrag") is None:
            self.skipTest("filefrag isn't installed")
        told = subprocess.run(["filefrag", "-v", "-b512", f"/proc/{os.getpid()}/fd/{file.fileno()}"],
                              capture_output=True, text=True, check=True).stdout
        theirs = [(int(logical) * 512, int(physical) * 512, int(length) * 512)
                  for logical, physical, length in re.findall(
                      r"^\s*\d+:\s+(\d+)\.\.\s*\d+:\s+(\d+)\.\.\s*\d+:\s+(\d+):", told, re.M)]
        self.assertEqual([extent[:3] for extent in ours], theirs, told)
        self.assertEqual(sum(length for _l, _p, length, _f in ours), 8 * MIB)

    def test_the_file_says_what_it_is_and_isnt_in_its_folder(self):
        file = self.file()
        self.assertEqual(file.bytes, 8 * MIB)
        self.assertIn(file.creation, ("unnamed", "unlinked"))
        self.assertIn(file.no_cow, (None, True, False))
        memory, offset, declared = file.align
        self.assertGreaterEqual(memory, 4096)
        self.assertEqual(MIB % offset, 0)
        self.assertIsInstance(declared, bool)
        self.assertEqual(os.listdir(self.folder), [])
        about = os.fstat(file.fileno())
        self.assertEqual((about.st_nlink, about.st_size), (0, 8 * MIB))

    def test_filling_counts_its_blocks(self):
        file = self.file()
        control = silux_bench.Control()
        file.fill(control=control)
        self.assertEqual(control.progress(), (8, 8))
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_lap_says_what_moved_and_how_long_each_request_took(self):
        file = self.file()
        file.fill()
        engines = ["threads"] + ([] if silux_bench.uring_error() else ["uring"])
        for engine, (pattern, direction, block, depth) in itertools.product(engines, (
                ("sequential", "read", MIB, 2), ("random", "write", 4096, 4))):
            lap = file.lap(pattern, direction, block=block, depth=depth, seconds=0.6,
                           engine=engine)
            # A thread for each request in flight, or one for them all.
            self.assertEqual((lap["engine"], lap["threads"]),
                             (engine, depth if engine == "threads" else 1))
            self.assertGreater(lap["requests"], 0)
            self.assertEqual(lap["bytes"], lap["requests"] * block)
            self.assertGreaterEqual(lap["elapsed_ns"], 550_000_000)
            self.assertAlmostEqual(lap["bytes_per_second"],
                                   lap["bytes"] * 1e9 / lap["elapsed_ns"], delta=1)
            self.assertAlmostEqual(lap["requests_per_second"],
                                   lap["requests"] * 1e9 / lap["elapsed_ns"], delta=1)
            self.assertLessEqual(lap["latency_min_ns"], lap["latency_p50_ns"])
            self.assertLessEqual(lap["latency_p50_ns"], lap["latency_p99_ns"])
            self.assertLessEqual(lap["latency_p99_ns"], lap["latency_p999_ns"])
            self.assertLessEqual(lap["latency_p999_ns"], lap["latency_max_ns"])
            self.assertLessEqual(lap["latency_min_ns"], lap["latency_mean_ns"])
            # One every quarter of a second while the lap ran: a slow
            # machine finishing its last requests can run past the third.
            samples = lap["samples"]
            self.assertGreaterEqual(len(samples), 2)
            self.assertLessEqual(len(samples), lap["elapsed_ns"] // 250_000_000)
            for (first_at, first), (second_at, second) in zip(samples, samples[1:]):
                self.assertLess(first_at, second_at)
                self.assertLessEqual(first, second)
            self.assertLessEqual(samples[-1][1], lap["bytes"])
        if file.no_cow is not False:
            self.assertEqual(file.cached_bytes(), 0)

    def test_a_lap_leaves_python_running_and_can_be_cancelled_from_it(self):
        file = self.file()
        file.fill()
        control = silux_bench.Control()
        threading.Timer(0.2, control.cancel).start()
        began = time.monotonic()
        with self.assertRaises(silux_bench.Cancelled) as raised:
            file.lap("random", "read", block=4096, depth=2, seconds=60, control=control)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(raised.exception.args[0], "cancelled")

    def test_an_error_carries_its_key_and_its_figures(self):
        file = self.file()
        cases = (
            (lambda: silux_bench.DiskFile(self.folder / "missing", bytes=MIB),
             "no_folder", {"errno": errno.ENOENT}),
            (lambda: silux_bench.DiskFile(self.folder, bytes=MIB + 1),
             "bad_setting", {"setting": "bytes"}),
            (lambda: file.lap("diagonal", "read", block=4096, depth=1, seconds=1),
             "bad_setting", {"setting": "pattern"}),
            (lambda: file.lap("random", "sideways", block=4096, depth=1, seconds=1),
             "bad_setting", {"setting": "direction"}),
            (lambda: file.lap("random", "read", block=4096, depth=0, seconds=1),
             "bad_setting", {"setting": "depth"}),
            (lambda: file.lap("random", "read", block=4096, depth=1, seconds=1, engine="libaio"),
             "bad_setting", {"setting": "engine"}),
            (lambda: file.lap("random", "read", block=4097, depth=1, seconds=1),
             "bad_size", {"bytes": 4097}),
        )
        for call, key, details in cases:
            with self.assertRaises(silux_bench.SiluxBenchError) as raised:
                call()
            error = raised.exception
            # Two, as every error of the module: the memory test tells one
            # of its own from any other by that.
            self.assertEqual(len(error.args), 2)
            self.assertEqual((error.args[0], error.details), (key, details))

    def test_a_file_that_doesnt_fit_says_what_it_needed_and_what_was_free(self):
        self.file()
        free = shutil.disk_usage(self.folder).free
        asked = (free // MIB + 1024) * MIB
        with self.assertRaises(silux_bench.SiluxBenchError) as raised:
            silux_bench.DiskFile(self.folder, bytes=asked)
        error = raised.exception
        self.assertEqual(error.args[0], "no_space")
        self.assertEqual(error.details["needed"], asked + 1024 * MIB)
        self.assertLess(error.details["free"], error.details["needed"])
        self.assertGreater(error.details["free"], 0)
        self.assertEqual(os.listdir(self.folder), [])

    def test_the_margin_asked_is_the_one_left_and_never_below_the_least(self):
        self.file()
        free = shutil.disk_usage(self.folder).free
        asked = (free // MIB + 1) * MIB
        with self.assertRaises(silux_bench.SiluxBenchError) as raised:
            silux_bench.DiskFile(self.folder, bytes=asked, margin=64 * MIB)
        self.assertEqual(raised.exception.details["needed"], asked + 64 * MIB)
        with self.assertRaises(silux_bench.SiluxBenchError) as raised:
            silux_bench.DiskFile(self.folder, bytes=MIB,
                                 margin=silux_bench.LEAST_FREE_MARGIN - 1)
        self.assertEqual(raised.exception.args[0], "bad_setting")
        self.assertEqual(os.listdir(self.folder), [])

    def test_the_ring_is_there_or_the_kernel_says_why_not(self):
        why = silux_bench.uring_error()
        file = self.file()
        file.fill()
        if why is None:
            lap = file.lap("random", "read", block=4096, depth=4, seconds=0.3)
            self.assertEqual(lap["engine"], "uring")
            return
        # A container, or a system that forbids them: the lap says the same
        # and the threads still measure.
        self.assertGreater(why, 0)
        with self.assertRaises(silux_bench.SiluxBenchError) as raised:
            file.lap("random", "read", block=4096, depth=4, seconds=0.3)
        self.assertEqual((raised.exception.args[0], raised.exception.details),
                         ("no_uring", {"errno": why}))
        lap = file.lap("random", "read", block=4096, depth=4, seconds=0.3, engine="threads")
        self.assertEqual(lap["engine"], "threads")

    def test_a_closed_file_is_gone_and_says_so(self):
        file = self.file()
        file.fill()
        file.close()
        file.close()
        for call in (lambda: file.bytes, file.fileno, file.fill, file.cached_bytes,
                     lambda: file.lap("random", "read", block=4096, depth=1, seconds=1)):
            with self.assertRaises(silux_bench.SiluxBenchError) as raised:
                call()
            self.assertEqual(raised.exception.args[0], "closed")

    def test_a_folder_in_memory_is_refused(self):
        shm = pathlib.Path("/dev/shm")
        if not shm.is_dir() or "tmpfs" not in _filesystem_of(shm):
            self.skipTest("no folder in memory to try")
        with self.assertRaises(silux_bench.SiluxBenchError) as raised:
            silux_bench.DiskFile(shm, bytes=MIB)
        self.assertEqual((raised.exception.args[0], raised.exception.details), ("in_memory", {}))


def _filesystem_of(path: pathlib.Path) -> str:
    """The type of the mount `path` is itself, from the kernel's table."""
    for line in pathlib.Path("/proc/self/mountinfo").read_text().splitlines():
        before, _separator, after = line.partition(" - ")
        if before.split()[4] == str(path):
            return after.split()[0]
    return ""


if __name__ == "__main__":
    unittest.main()
