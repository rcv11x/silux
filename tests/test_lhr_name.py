"""NVIDIA sells its «Lite Hash Rate» revisions as LHR: «GeForce RTX 3070
Lite Hash Rate», as pci.ids writes it, ate the title of Felix's 5800X's
Graphics page. The revision stays in the name, short."""

import unittest

from tests.test_equipos import EQUIPOS, shared_snapshot


class TestLhrName(unittest.TestCase):
    def test_the_3070_is_an_lhr(self):
        for dump in ("ryzen7-5800x", "ryzen7-5800x-nouveau"):
            with self.subTest(dump=dump):
                names = [g.name for g in shared_snapshot(EQUIPOS / dump).gpus]
                self.assertEqual(names, ["GeForce RTX 3070 LHR"])


if __name__ == "__main__":
    unittest.main()
