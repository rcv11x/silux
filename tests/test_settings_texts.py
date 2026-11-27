"""Settings explains each row in a line or two: what it does and what it
costs, no more."""

import json
import pathlib
import unittest

LANG = pathlib.Path(__file__).resolve().parent.parent / "silux" / "db" / "lang"
# Two lines of the row's help at the normal width.
LONGEST = 160


def _helps(language: str) -> dict:
    texts = json.loads((LANG / f"{language}.json").read_text(encoding="utf-8"))
    return {key: text for key, text in texts.items()
            if key.startswith("settings.") and key.endswith(".help")}


class TestShortHelps(unittest.TestCase):
    def test_the_authors_words(self):
        helps = _helps("es")
        self.assertEqual(helps["settings.interval.help"],
                         "Cada cuánto se leen los sensores. Menos de 0.5 s gasta más; "
                         "más de 2 s, las gráficas pierden detalle.")
        self.assertTrue(helps["settings.fluid.help"].endswith(
            "se deslizan en vez de saltar. Gasta un poco más de procesador."))

    def test_only_what_changes_a_choice(self):
        # Obvious ones, or ones explaining what the user doesn't decide, went.
        helps = _helps("es")
        for row in ("language", "accent", "density", "fontsize", "updates", "welcome",
                    "shortcut.desktop"):
            self.assertNotIn(f"settings.{row}.help", helps)

    def test_none_is_long(self):
        for language in ("es", "en"):
            for key, text in _helps(language).items():
                with self.subTest(language=language, key=key):
                    self.assertLessEqual(len(text), LONGEST, text)


if __name__ == "__main__":
    unittest.main()
