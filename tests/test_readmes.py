"""README.md and README.en.md say the same thing in two languages.

Whoever edits one tends to forget the other. This compares what can be
compared without reading either language: the sections, in order and at the
same level, and the links and images each one carries.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
READMES = {"es": "README.md", "en": "README.en.md"}
TARGET = re.compile(r"\]\(([^)\s]+)\)|\bsrc=\"([^\"]+)\"")
SWITCHER = {"es": "**Español** · [English](README.en.md)",
            "en": "[Español](README.md) · **English**"}


def sections(text: str) -> list[tuple[int, list[str]]]:
    """(heading level, link targets) per section; the part above the first
    heading is level 0. Code blocks are left out: their comments are prose."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    found: list[tuple[int, list[str]]] = [(0, [])]
    for line in text.splitlines():
        if heading := re.match(r"(#+)\s", line):
            found.append((len(heading.group(1)), []))
        found[-1][1].extend(a or b for a, b in TARGET.findall(line)
                            if not (a or b).startswith("README"))
    return found


def read(language: str) -> str:
    return (ROOT / READMES[language]).read_text(encoding="utf-8")


class TestTheTwoReadmesMatch(unittest.TestCase):

    def test_same_sections_at_the_same_level(self):
        self.assertEqual([level for level, _links in sections(read("es"))],
                         [level for level, _links in sections(read("en"))])

    def test_same_links_and_images_in_each_section(self):
        spanish, english = sections(read("es")), sections(read("en"))
        for number, ((_l1, es_links), (_l2, en_links)) in enumerate(zip(spanish, english)):
            with self.subTest(section=number):
                self.assertEqual(es_links, en_links)

    def test_each_one_opens_with_the_language_switcher(self):
        for language, line in SWITCHER.items():
            with self.subTest(language=language):
                first = next(l for l in read(language).splitlines() if l.strip())
                self.assertEqual(first, line)


class TestTheComparisonNoticesADifference(unittest.TestCase):
    """The check above, against the two kinds of drift it is there for."""

    def test_a_missing_link(self):
        text = read("en").replace("[LICENSE](LICENSE)", "LICENSE")
        self.assertNotEqual(sections(read("es")), sections(text))

    def test_a_missing_section(self):
        text = read("en").replace("## In the terminal", "In the terminal")
        self.assertNotEqual([l for l, _x in sections(read("es"))],
                            [l for l, _x in sections(text)])


if __name__ == "__main__":
    unittest.main()
