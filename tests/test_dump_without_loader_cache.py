"""The loader's cache (/etc/ld.so.cache) stays out of a dump.

Reading the system's dependencies opens it, so collection notes it; but its
answer is recorded apart («paquetes»), so a mounted dump never reads it. On
a distribution with many libraries it was most of a report's annex.
"""

import pathlib
import unittest

from silux import annex, volcado
from tests.test_equipos import EQUIPOS


class _AllAwake:
    def forbidden(self, path):
        return False


class TestTheLoaderCache(unittest.TestCase):

    def test_read_but_not_copied(self):
        read = {"/etc/ld.so.cache", "/etc/os-release", "/proc/cpuinfo"}
        self.assertEqual(volcado._to_copy(read, _AllAwake()), {"/etc/os-release", "/proc/cpuinfo"})

    def test_no_suite_dump_carries_it(self):
        self.assertEqual(sorted(str(p.relative_to(EQUIPOS)) for p in EQUIPOS.glob("*/etc/ld.so.cache")), [])

    def test_the_answer_travels_instead(self):
        """Every dump recorded since the packages are recorded has them."""
        import json
        for folder in sorted(EQUIPOS.iterdir()):
            recording = json.loads((folder / "grabado.json").read_text(encoding="utf-8"))
            if "paquetes" in recording:
                with self.subTest(dump=folder.name):
                    self.assertTrue(recording["paquetes"])

    def test_an_annex_without_it_is_small(self):
        text = annex.to_text(pathlib.Path(EQUIPOS / "i5-3330"))
        self.assertLess(len(text.encode()), 400_000, "what makes the annex this large?")


if __name__ == "__main__":
    unittest.main()
