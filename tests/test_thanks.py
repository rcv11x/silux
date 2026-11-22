"""Who sends reports, by name, and only with their permission.

The names live in silux/db/thanks.json, which only the author fills, with
the names each person has allowed. The About page, the two READMEs and the
CHANGELOG's «Con informes de…» lines take theirs from there: nobody is named
anywhere who is not in that file.
"""

import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock

from silux import db
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLISHED = ROOT / "silux" / "db" / "thanks.json"

# The names the author has approved, written here by hand and only by the
# author. A name in the published thanks.json that is not here fails the
# suite, and with it the CI of any release: nobody is named without being
# written twice.
APPROVED: frozenset[str] = frozenset({"Felix Lara"})
READMES = ("README.md", "README.en.md")
BETWEEN_MARKS = re.compile(r"<!-- thanks:start -->\n(.*?)<!-- thanks:end -->", re.S)
WITH_REPORTS_FROM = re.compile(r"^Con informes de (.+?)\.?$", re.M)


def names_in_readme(text: str):
    """The «- name» lines between the marks, or None without the marks."""
    found = BETWEEN_MARKS.search(text)
    if found is None:
        return None
    return [line[2:].strip() for line in found.group(1).splitlines() if line.startswith("- ")]


def names_in_changelog(text: str) -> list[str]:
    """Every name on a «Con informes de Ana, Luis y Marta.» line."""
    names: list[str] = []
    for line in WITH_REPORTS_FROM.findall(text):
        names += [n.strip() for n in re.split(r",\s*|\s+y\s+", line) if n.strip()]
    return names


class _AList(unittest.TestCase):
    """thanks.json with these contents, as the author would leave it."""

    def _with(self, contents: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        archivo = pathlib.Path(tmp.name) / "thanks.json"
        archivo.write_text(contents, encoding="utf-8")
        parche = mock.patch.object(db, "THANKS", archivo)
        parche.start()
        db.thanks.cache_clear()
        self.addCleanup(db.thanks.cache_clear)
        self.addCleanup(parche.stop)


class TestThePublishedList(unittest.TestCase):

    def test_only_names_the_author_approved(self):
        nombres = json.loads(PUBLISHED.read_text(encoding="utf-8"))
        self.assertIsInstance(nombres, list)
        self.assertEqual([n for n in nombres
                          if not (isinstance(n, str) and n.strip() in APPROVED)], [])


class TestTheList(_AList):

    def test_each_name_once_as_written(self):
        self._with(json.dumps(["Ana", " Luis ", "Ana", 3, "", None, "Marta"]))
        self.assertEqual(db.thanks(), ("Ana", "Luis", "Marta"))

    def test_a_broken_file_names_nobody(self):
        for contents in ("{", '{"names": ["Ana"]}', "", '"Ana"'):
            with self.subTest(contents=contents):
                self._with(contents)
                self.assertEqual(db.thanks(), ())


class TestTheAboutPage(_AList):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.photo = foto(EQUIPOS / "i5-10400")[0]

    def _textos(self):
        with pantalla.Ventana(self.photo) as ventana:
            ventana.select_section("Ajustes")
            return pantalla.textos_de(ventana.settings_page)

    def test_with_names_it_thanks_them(self):
        self._with(json.dumps(["Ana", "Luis", "Marta"]))
        textos = self._textos()
        self.assertIn(_("about.thanks").upper(), textos)
        self.assertIn("Ana, Luis y Marta", textos)

    def test_without_names_there_is_no_section(self):
        self._with("[]")
        self.assertNotIn(_("about.thanks").upper(), self._textos())


class TestTheReadmes(unittest.TestCase):

    def test_both_name_exactly_the_list(self):
        for readme in READMES:
            with self.subTest(readme=readme):
                texto = (ROOT / readme).read_text(encoding="utf-8")
                self.assertEqual(names_in_readme(texto), list(db.thanks()))

    def test_the_check_reads_the_names(self):
        texto = "## Gracias\n\n<!-- thanks:start -->\n- Ana\n- Luis\n<!-- thanks:end -->\n"
        self.assertEqual(names_in_readme(texto), ["Ana", "Luis"])
        self.assertIsNone(names_in_readme("## Gracias\n\n- Ana\n"))


class TestTheChangelog(unittest.TestCase):

    def test_nobody_outside_the_list(self):
        texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual([n for n in names_in_changelog(texto) if n not in db.thanks()], [])

    def test_the_check_sees_a_stranger(self):
        texto = "## 0.4\n\nCon informes de Ana, Luis y Marta.\n\n### Memoria\n"
        self.assertEqual(names_in_changelog(texto), ["Ana", "Luis", "Marta"])


if __name__ == "__main__":
    unittest.main()
