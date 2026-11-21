"""Every dumped machine is shown exactly as its reference says.

`tests/fixtures/screens/NAME.md` is what the window shows for each dump,
page by page (`tools/update_screen_references.py`). A change that alters it
fails here with the diff: if the change is intended, run the tool again and
review the new reference in the same commit; if not, it is a regression.
"""

import difflib
import pathlib
import re
import unittest

from tests.test_equipos import volcados

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

SCREENS = pathlib.Path(__file__).resolve().parent / "fixtures" / "screens"


@unittest.skipIf(QApplication is None, "no PySide6")
class TestScreenReferences(unittest.TestCase):

    def test_every_dump_has_its_reference(self):
        names = {d.name for d in volcados()}
        self.assertTrue(names)
        self.assertEqual({p.stem for p in SCREENS.glob("*.md")}, names)

    def test_every_dump_is_shown_as_its_reference_says(self):
        from tools.update_screen_references import screen

        for dump in volcados():
            with self.subTest(dump=dump.name):
                expected = (SCREENS / f"{dump.name}.md").read_text(encoding="utf-8")
                actual = screen(dump)
                if actual != expected:
                    diff = "".join(list(difflib.unified_diff(
                        expected.splitlines(True), actual.splitlines(True),
                        "reference", "now", n=1))[:60])
                    self.fail(f"{dump.name} is shown differently. If that's intended, run "
                              f"tools/update_screen_references.py and review the diff.\n{diff}")

    def test_the_clock_does_not_leak_in(self):
        from tools.update_screen_references import normalize

        a = normalize("# x\n| Python | 3.14 |\n\n## Sistema\n- Encendido desde: 2026-11-19 20:37\n")
        b = normalize("# y\n| Python | 3.10 |\n\n## Sistema\n- Encendido desde: 2026-11-20 08:01\n")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()


class TestOneIsSingular(unittest.TestCase):
    """«1 hilos» on the CPU page of every processor with one thread per core."""

    PLURAL = re.compile(r"(?<![\d.,×])\b1 (hilos|núcleos|módulos|discos|dispositivos|monitores"
                        r"|salidas|ranuras|canales|vías|threads|cores|modules|disks|devices"
                        r"|monitors|outputs|slots|channels|ways)\b")

    def test_one_with_a_singular_noun(self):
        for referencia in sorted(SCREENS.glob("*.md")):
            for numero, linea in enumerate(referencia.read_text(encoding="utf-8").splitlines(), 1):
                with self.subTest(referencia=referencia.name, linea=numero):
                    self.assertIsNone(self.PLURAL.search(linea), linea)
