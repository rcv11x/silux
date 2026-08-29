"""Que el archivo de contexto no se quede diciendo cosas que ya no son.

`CLAUDE.md` lleva dos cifras que envejecen solas: cuántos tests hay y cuántas
claves de idioma. Están ahí para que alguien note de un vistazo si falta algo
por recoger, y una cifra vieja hace justo lo contrario: da por bueno un número
que ya no cuadra. Como son las dos comprobables, se comprueban.
"""

import json
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CONTEXTO = RAIZ / "CLAUDE.md"

# Cuánto puede desviarse lo escrito de lo real. Ajustar el número en cada
# commit que añade un test sería ruido; lo que importa es que no se quede a
# medio centenar de distancia.
MARGEN = 0.05


class TestLasCifrasDelContextoSiguenSiendoCiertas(unittest.TestCase):
    def _texto(self) -> str:
        if not CONTEXTO.is_file():
            self.skipTest("no hay CLAUDE.md")
        return CONTEXTO.read_text(encoding="utf-8")

    def test_el_numero_de_tests_es_el_que_hay(self):
        import unittest as ut

        escrito = re.search(r"Los tests son \*\*(\d+)\*\*", self._texto())
        self.assertIsNotNone(escrito, "no se encuentra la cifra en CLAUDE.md")
        dicho = int(escrito.group(1))

        suite = ut.defaultTestLoader.discover(str(RAIZ / "tests"),
                                              top_level_dir=str(RAIZ))
        real = suite.countTestCases()
        self.assertLessEqual(
            abs(real - dicho) / real, MARGEN,
            f"CLAUDE.md dice {dicho} tests y hay {real}")

    def test_el_numero_de_claves_de_idioma_es_el_que_hay(self):
        escrito = re.search(r"(\d+) claves, ninguna sin traducir", self._texto())
        self.assertIsNotNone(escrito, "no se encuentra la cifra en CLAUDE.md")
        dicho = int(escrito.group(1))

        real = len(json.loads(
            (RAIZ / "silux" / "db" / "lang" / "es.json").read_text(
                encoding="utf-8")))
        self.assertLessEqual(
            abs(real - dicho) / real, MARGEN,
            f"CLAUDE.md dice {dicho} claves y hay {real}")
