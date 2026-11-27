"""A SMART temperature packed in its raw value (194 and 190), shown as
smartctl reads it by default: the office's KIOXIA-EXCERIA S read
«72 · en crudo 176 094 576 668» where smartctl says «27 (Min/Max 14/41)».

The raw value is Silux's reading of the drive; smartctl's 27 was another
moment (the lowest and highest agree). The SanDisk SSD PLUS over USB in
Felix's reports packs the same way: 29 °C, as its temperature said.
"""

import unittest

from silux import render

KIOXIA_194 = 176_094_576_668


class TestPackedTemperature(unittest.TestCase):
    def test_as_smartctl_reads_it(self):
        self.assertEqual(render.smart_temperature(KIOXIA_194), "28 °C, mín 14, máx 41")
        self.assertEqual(render.smart_temperature(240_518_758_429), "29 °C, mín 9, máx 56")
        # Only the current one when the drive keeps no lowest and highest.
        self.assertEqual(render.smart_temperature(73_014_444_079), "47 °C")


if __name__ == "__main__":
    unittest.main()
