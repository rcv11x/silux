"""The README and the documents for users say the same thing in two languages.

Whoever edits one tends to forget the other. This compares what can be
compared without reading either language: the sections, in order and at the
same level, and the links and images each one carries, a document in one
language linking to its pair in the other.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Each document for users in English and in Spanish, the English first: the
# README opens in English.
PAIRS = (("README.md", "README.es.md"),
         ("docs/usage.md", "docs/uso.md"),
         ("docs/compatibility.md", "docs/compatibilidad.md"))
READMES = {"en": "README.md", "es": "README.es.md"}
TARGET = re.compile(r"\]\(([^)\s]+)\)|\bsrc=\"([^\"]+)\"")


def switcher(english: str, spanish: str, language: str) -> str:
    """The first line of each: the other language's link and its own name."""
    other = pathlib.Path(spanish if language == "en" else english).name
    return (f"**English** · [Español]({other})" if language == "en"
            else f"[English]({other}) · **Español**")


def english_target(target: str) -> str:
    """A link of a Spanish document as its English pair would write it: its
    pair, or the same capture in English."""
    if "capturas/es/" in target:
        return target.replace("capturas/es/", "capturas/en/")
    for english, spanish in PAIRS:
        for name_en, name_es in ((english, spanish),
                                 (pathlib.Path(english).name, pathlib.Path(spanish).name)):
            if target == name_es:
                return name_en
    return target


def sections(text: str, spanish: bool = False) -> list[tuple[int, list[str]]]:
    """(heading level, link targets) per section; the part above the first
    heading is level 0. Code blocks are left out: their comments are prose,
    and so is the first line, which links to the other language."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    found: list[tuple[int, list[str]]] = [(0, [])]
    for line in text.splitlines()[1:]:
        if heading := re.match(r"(#+)\s", line):
            found.append((len(heading.group(1)), []))
        targets = [a or b for a, b in TARGET.findall(line)]
        found[-1][1].extend(english_target(t) if spanish else t for t in targets)
    return found


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class TestEachPairMatches(unittest.TestCase):

    def test_same_sections_at_the_same_level(self):
        for english, spanish in PAIRS:
            with self.subTest(document=english):
                self.assertEqual([level for level, _links in sections(read(english))],
                                 [level for level, _links in sections(read(spanish), True)])

    def test_same_links_and_images_in_each_section(self):
        for english, spanish in PAIRS:
            pairs = zip(sections(read(english)), sections(read(spanish), True))
            for number, ((_l1, en_links), (_l2, es_links)) in enumerate(pairs):
                with self.subTest(document=english, section=number):
                    self.assertEqual(en_links, es_links)

    def test_each_one_opens_with_the_language_switcher(self):
        for english, spanish in PAIRS:
            for language, path in (("en", english), ("es", spanish)):
                with self.subTest(document=path):
                    first = next(l for l in read(path).splitlines() if l.strip())
                    self.assertEqual(first, switcher(english, spanish, language))


class TestTheComparisonNoticesADifference(unittest.TestCase):
    """The check above, against the two kinds of drift it is there for."""

    def test_a_missing_link(self):
        text = read("README.md").replace("[LICENSE](LICENSE)", "LICENSE")
        self.assertNotEqual(sections(read("README.es.md"), True), sections(text))

    def test_a_link_to_the_other_language(self):
        text = read("README.es.md").replace("(docs/uso.md)", "(docs/usage.md)", 1)
        self.assertNotEqual(sections(read("README.md")), sections(text))
        self.assertEqual(english_target("docs/uso.md"), "docs/usage.md")
        self.assertEqual(english_target("docs/usage.md"), "docs/usage.md")
        self.assertEqual(english_target("../capturas/es/cpu.png"), "../capturas/en/cpu.png")

    def test_a_capture_in_the_other_language(self):
        text = read("docs/uso.md").replace("capturas/es/cpu.png", "capturas/en/cpu.png")
        self.assertEqual(sections(read("docs/usage.md")), sections(text, True))
        text = read("docs/uso.md").replace("capturas/es/cpu.png", "capturas/es/memoria.png")
        self.assertNotEqual(sections(read("docs/usage.md")), sections(text, True))

    def test_a_missing_section(self):
        text = read("README.md").replace("## Roadmap", "Roadmap")
        self.assertNotEqual([l for l, _x in sections(read("README.es.md"), True)],
                            [l for l, _x in sections(text)])


RELEASE_NOTES = ".github/release-notes.md"
GLIBC = re.compile(r"glibc (\d+\.\d+)")


class TestTheReleaseNotesMatchTheReadme(unittest.TestCase):
    """The release notes template repeats which glibc each AppImage needs.
    It said 2.35 for the compat one long after the README said 2.30."""

    def test_same_glibc_floors_in_the_same_order(self):
        notes = GLIBC.findall((ROOT / RELEASE_NOTES).read_text(encoding="utf-8"))
        for language, path in READMES.items():
            with self.subTest(readme=path):
                self.assertEqual(notes, GLIBC.findall(read(path)))

    def test_the_comparison_notices_a_different_floor(self):
        notes = (ROOT / RELEASE_NOTES).read_text(encoding="utf-8")
        changed = notes.replace("glibc 2.34", "glibc 2.36")
        self.assertNotEqual(GLIBC.findall(changed), GLIBC.findall(read("README.md")))


if __name__ == "__main__":
    unittest.main()
