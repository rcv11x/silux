"""A TV that writes its proportion where its size goes.

A 32" Sony TV declared 160 × 90 cm, and the monitors table read 72.3". Those
are its 16:9 tenfold, not a panel: a real 72" one measures 1594 × 897 mm.
"""

import pathlib
import unittest

from silux import edid, render
from silux.i18n import _

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "edid"


def _with_size(raw: bytes, cm: tuple[int, int], mm: tuple[int, int]) -> bytes:
    """The EDID with another size in its base block and its native timing,
    and its checksum made right again."""
    block = bytearray(raw[:128])
    block[21], block[22] = cm
    block[54 + 12] = mm[0] & 0xFF
    block[54 + 13] = mm[1] & 0xFF
    block[54 + 14] = ((mm[0] >> 8) << 4) | (mm[1] >> 8)
    block[127] = (-sum(block[:127])) & 0xFF
    return bytes(block) + raw[128:]


class TestTheProportionIsNoSize(unittest.TestCase):

    def setUp(self):
        self.raw = (FIXTURES / "lg-27gl850-144hz.bin").read_bytes()

    def test_tenfold_in_both_places(self):
        tv = edid.parse(_with_size(self.raw, (160, 90), (1600, 900)))
        self.assertTrue(tv.size_is_ratio)
        self.assertIsNone(tv.diagonal_inches)
        self.assertEqual(render.monitor_size(tv),
                         _("gpu.display.size.ratio").format(ratio="16:9"))
        self.assertNotIn("1600", render.monitor_summary(tv))

    def test_in_centimetres_alone(self):
        tv = edid.parse(_with_size(self.raw, (16, 9), (0, 0)))
        self.assertTrue(tv.size_is_ratio)

    def test_a_real_panel_of_that_size(self):
        big = edid.parse(_with_size(self.raw, (159, 90), (1594, 897)))
        self.assertFalse(big.size_is_ratio)
        self.assertEqual(render.monitor_size(big), '72.0"')
        self.assertEqual(render.monitor_size(edid.parse(self.raw)),
                         render.monitor_diagonal(edid.parse(self.raw)))


if __name__ == "__main__":
    unittest.main()
