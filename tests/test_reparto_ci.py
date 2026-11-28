"""How the CI shares the suite out: the normal pair in two halves that run
every test once between them, the width tests with that pair only, and the
three that measure, once per pair (`tests/reparto.py`)."""

import pathlib
import re
import unittest

from tests import reparto

FLOW = (pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"
        / "appimage.yml").read_text()


class TestTheParts(unittest.TestCase):
    NODES = [f"tests/test_{n % 7}.py::Test{n % 5}::test_{n}" for n in range(101)]

    def test_two_halves_run_every_test_once(self):
        first, second = (reparto.part_of(self.NODES, f"{n}/2") for n in (1, 2))
        self.assertEqual(first | second, set(self.NODES))
        self.assertFalse(first & second)
        self.assertLessEqual(abs(len(first) - len(second)), 1)

    def test_whole_is_everything(self):
        self.assertEqual(reparto.part_of(self.NODES, "1/1"), set(self.NODES))

    def test_the_same_whatever_the_order(self):
        self.assertEqual(reparto.part_of(self.NODES, "2/2"),
                         reparto.part_of(list(reversed(self.NODES)), "2/2"))

    def test_no_such_part(self):
        for spec in ("0/2", "3/2"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                reparto.part_of(self.NODES, spec)


class TestTheWidthTests(unittest.TestCase):
    def test_the_classes_it_names_exist(self):
        # Renamed, they would run everywhere again without anyone noticing.
        from tests import test_anchura
        for name in reparto.WIDTH_CLASSES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(test_anchura, name))
                self.assertTrue(reparto.is_width_test(f"tests/test_anchura.py::{name}::test_x"))
        self.assertFalse(reparto.is_width_test("tests/test_anchura.py::TestAWordInABigTile::test_x"))


class TestTheWorkflow(unittest.TestCase):
    def test_the_normal_pair_in_two_halves_and_compat_whole(self):
        parts = re.findall(r'paquete: (\w+)\n\s+python: "[\d.]+"\n\s+modulo: \w+\n\s+parte: "([\d/]+)"',
                           FLOW)
        self.assertEqual(sorted(p for k, p in parts if k == "normal"), ["1/2", "2/2"])
        self.assertEqual([p for k, p in parts if k == "compat"], ["1/1", "1/1"])

    def test_compat_leaves_the_width_tests_out_and_both_steal_work(self):
        step = FLOW[FLOW.index("- name: Pasar los tests"):FLOW.index("build:")]
        self.assertIn('marcas="not a_solas and not anchura"', step)
        self.assertIn('--parte "${{ matrix.parte }}"', step)
        self.assertIn("--dist worksteal", step)
        # The three that measure: not in the second half, which would run
        # them twice for the same pair.
        self.assertIn('[ "${{ matrix.parte }}" = "2/2" ] || python -m pytest -q -m a_solas', step)

    def test_pip_keeps_its_cache(self):
        self.assertIn("cache: pip", FLOW)


if __name__ == "__main__":
    unittest.main()
