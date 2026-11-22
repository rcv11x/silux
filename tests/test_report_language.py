"""The full report comes out in the chosen language, all of it.

Its header and diagnosis were fixed Spanish around pages in English, and
the model held a firmware type already written in Spanish.
"""

import re
import unittest

from silux import i18n
from tests.test_equipos import foto, volcados

# Letters English doesn't use: a Spanish word in an English report.
SPANISH = re.compile(r"[áéíóúñ¿¡]", re.I)


class TestInEnglish(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tests import qt
        qt.app()
        cls.previous = i18n.current()
        i18n.set_language("en")
        cls.snapshots = {d.name: foto(d)[0] for d in volcados()}

    @classmethod
    def tearDownClass(cls):
        i18n.set_language(cls.previous)

    def test_no_spanish_in_any_report(self):
        from silux.ui import full_report

        for name, snapshot in self.snapshots.items():
            text = full_report.build(snapshot, anonymous=True)
            with self.subTest(name):
                lines = [line for line in text.splitlines() if SPANISH.search(line)]
                self.assertEqual(lines, [])
                self.assertNotIn("Informe de Silux", text)
                self.assertNotIn("?", text.split("\n## ")[0])


if __name__ == "__main__":
    unittest.main()
