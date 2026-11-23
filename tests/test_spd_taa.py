"""The CAS latency as each chip declares it (tAAmin), in nanoseconds.

Checked against the real SPDs in the dumps and their makers' datasheets, not
against what the decoder computes: DDR4-3200 CL22 at 13.75 ns (Crucial's
CT8G4DFRA32A), DDR3L-1600 CL11 at 13.125 ns (SK hynix's HMT451S6BFR8A-PB),
an XMP 3200 CL16 at 10 ns (16 cycles of 625 ps), the LOQ's DDR5-4800 at
16 ns (read by hand, test_loq_spd_page_zero) and, for DDR2, which has no
such field, CL times the cycle the chip gives for it: 5 × 3 ns on a
DDR2-667 CL5.
"""

import pathlib
import unittest

from silux import render, spd
from tests.test_equipos import EQUIPOS, shared_snapshot


def _taa(dump: str, part: str, profile: str = "JEDEC") -> int:
    for info in shared_snapshot(EQUIPOS / dump).spd:
        if (info.part_number or "") == part:
            return next(t.taa_ps for t in (info.jedec, *info.profiles) if t.name == profile)
    raise AssertionError(f"{part} is not in {dump}")


class TestEachChipsOwnTime(unittest.TestCase):

    def test_ddr4(self):
        data = pathlib.Path(__file__).parent / "fixtures" / "ddr4-crucial-3200.spd"
        self.assertEqual(spd.decode(data.read_bytes()).jedec.taa_ps, 13750)
        self.assertEqual(_taa("i5-10400", "CT8G4DFRA32A.M8FR"), 13750)

    def test_ddr3(self):
        self.assertEqual(_taa("i5-5200u", "HMT451S6BFR8A-PB"), 13125)

    def test_an_xmp_profile_has_its_own(self):
        self.assertEqual(_taa("ryzen5-5600g", "KF3200C16D4/8GX", "XMP 1"), 10000)

    def test_ddr5_from_page_zero(self):
        self.assertEqual(_taa("i5-12450h", ""), 16000)

    def test_ddr2_is_cl_times_its_cycle(self):
        self.assertEqual(_taa("celeron-560", "M4 70T2953EZ3-CE6"), 15000)


class TestHowItIsWritten(unittest.TestCase):

    def test_exact_to_the_picosecond(self):
        self.assertEqual(render.spd_time(13750), "13.75 ns")
        self.assertEqual(render.spd_time(13125), "13.125 ns")
        self.assertEqual(render.spd_time(16000), "16 ns")
        self.assertEqual(render.spd_time(None), render.DASH)


if __name__ == "__main__":
    unittest.main()
