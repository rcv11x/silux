"""A dump carries its counters read twice, an interval apart.

Usage, power, traffic and rest come from the difference of two readings, and
a dump kept one: mounted, every machine showed «Calculando…» or a dash where
its owner saw figures. The dumper reads its counter files again an interval
after copying them, and a mounted dump gives the Collector's second snapshot
that second reading. Only counter files, and only into the dump's own copy.
"""

import json
import pathlib
import tempfile
import unittest

from silux import sysroot, volcado
from silux.collector import Collector
from tests.interval import fake_clock, next_snapshot
from tests.test_equipos import EQUIPOS


def _two_snapshots(folder):
    with volcado.mounted(folder), fake_clock() as clock:
        collector = Collector()
        try:
            return collector.snapshot(), next_snapshot(collector, clock)
        finally:
            collector.close()


class TestThisMachineDumped(unittest.TestCase):
    """The machine running the suite, dumped: the CI's runner, or here."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = volcado.dump("equipo", pathlib.Path(cls._tmp.name), own={})
        cls.recorded = json.loads((cls.folder / sysroot.RECORDING_FILE).read_text())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_its_counters_read_twice(self):
        second = self.recorded[sysroot.SECOND_READING]
        self.assertIn("/proc/stat", second)
        for location, text in second.items():
            with self.subTest(location):
                self.assertTrue(sysroot.is_counter_file(location))
                self.assertTrue(sysroot.is_counter_text(text))
                self.assertTrue((self.folder / location.lstrip("/")).is_file())

    def test_its_second_snapshot_has_what_comes_from_two(self):
        first, second = _two_snapshots(self.folder)
        self.assertIsNone(first.cpu.usage_percent)
        self.assertIsNotNone(second.cpu.usage_percent)
        self.assertTrue(any(i.traffic.rx_rate_bps is not None for i in second.network))


class TestWhatIsWrittenBack(unittest.TestCase):
    """A dump can come from someone's report: of its second reading only
    counter files already in the dump take it, and nothing outside it."""

    def test_only_counters_inside_the_dump(self):
        with volcado.mounted(EQUIPOS / "celeron-g3900") as root:
            frequency = "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
            before = {name: (root / name).read_text()
                      for name in ("proc/stat", "proc/cmdline", frequency)}
            recording = json.loads((root / sysroot.RECORDING_FILE).read_text())
            recording[sysroot.SECOND_READING] = {
                "/proc/stat": before["proc/stat"].replace("cpu ", "cpu  ", 1),
                "/proc/cmdline": "otra cosa\n",
                "/proc/../../fuera": "1\n",
                "/sys/devices/../../../fuera/stat": "1\n",
                "/" + frequency: "\x00binario\n",
            }
            (root / sysroot.RECORDING_FILE).write_text(json.dumps(recording))
            (root.parent / "fuera").write_text("0\n")
            sysroot.forget()
            sysroot.apply_second_reading()
            self.assertNotEqual((root / "proc/stat").read_text(), before["proc/stat"])
            self.assertEqual((root / "proc/cmdline").read_text(), before["proc/cmdline"])
            self.assertEqual((root.parent / "fuera").read_text(), "0\n")
            self.assertEqual((root / frequency).read_text(), before[frequency])
            # Once per mount: a third snapshot doesn't move it again.
            (root / "proc/stat").write_text(before["proc/stat"])
            sysroot.apply_second_reading()
            self.assertEqual((root / "proc/stat").read_text(), before["proc/stat"])

    def test_a_dump_without_one_is_as_it_was(self):
        first, second = _two_snapshots(EQUIPOS / "celeron-g3900")
        self.assertIsNone(second.cpu.usage_percent)


if __name__ == "__main__":
    unittest.main()
