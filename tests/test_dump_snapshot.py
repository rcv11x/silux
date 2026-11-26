"""The snapshot a dump gives when it is made or imported has its rates.

It was taken back to back after the first, so every rate (the processor's
use, RAPL's watts) fell short of a valid window and was left out, and the
manifest's sources missed RAPL on a machine that read it without
permissions. The mounted dump an interval later had it, as the sampler does.
"""

import unittest

from silux import volcado
from tests.test_equipos import EQUIPOS, foto


class TestTheDumpsSnapshot(unittest.TestCase):
    def test_has_the_rates_of_its_second_reading(self):
        snapshot = volcado.snapshot_of(EQUIPOS / "5800x3d")
        self.assertIsNotNone(snapshot.cpu.usage_percent)

    def test_its_sources_are_the_mounted_dumps(self):
        folder = EQUIPOS / "5800x3d"
        self.assertEqual(sorted(volcado.snapshot_of(folder).capabilities),
                         sorted(foto(folder)[0].capabilities))
