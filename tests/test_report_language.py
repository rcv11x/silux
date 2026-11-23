"""The full report comes out in the chosen language, all of it.

Its header and diagnosis were fixed Spanish around pages in English, and
the model held a firmware type already written in Spanish.
"""

import re
import unittest

from silux import i18n
from tests.per_dump import per_dump
from tests.test_equipos import shared_snapshot

# Letters English doesn't use: a Spanish word in an English report.
SPANISH = re.compile(r"[áéíóúñ¿¡]", re.I)


class TestInEnglish(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tests import qt
        qt.app()
        cls.previous = i18n.current()
        i18n.set_language("en")

    @classmethod
    def tearDownClass(cls):
        i18n.set_language(cls.previous)

    def _no_spanish_in_its_report(self, folder):
        from silux.ui import full_report

        text = full_report.build(shared_snapshot(folder), anonymous=True)
        lines = [line for line in text.splitlines() if SPANISH.search(line)]
        self.assertEqual(lines, [])
        self.assertNotIn("Informe de Silux", text)
        self.assertNotIn("?", text.split("\n## ")[0])


per_dump(TestInEnglish, "no_spanish_in_any_report", TestInEnglish._no_spanish_in_its_report)


if __name__ == "__main__":
    unittest.main()
