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


class TestLaVersionSeCuentaEnAlgunSitio(unittest.TestCase):
    """Que subir la versión y no decir qué cambió no se pueda hacer sin querer.

    La versión es lo único que un usuario puede comparar de un vistazo para
    saber si va atrasado; el identificador de construcción sirve para otra cosa
    y no se compara. Pero una versión nueva sin nota de qué trae es casi tan
    poco útil como no cambiarla: quien la ve no sabe si le interesa actualizar.

    Se comprueba lo único comprobable sin leer el contenido: que la versión que
    declara el paquete tenga su entrada en el archivo de cambios.
    """

    def _changelog(self) -> str:
        camino = RAIZ / "CHANGELOG.md"
        if not camino.is_file():
            self.fail("no hay CHANGELOG.md y la versión dice que debería")
        return camino.read_text(encoding="utf-8")

    def test_la_version_actual_esta_contada(self):
        import silux

        self.assertIn(f"## {silux.__version__}", self._changelog(),
                      f"la versión {silux.__version__} no tiene entrada en "
                      "CHANGELOG.md: subirla sin contar qué trae deja al que "
                      "la ve sin saber si le interesa")

    def test_las_entradas_van_de_la_mas_nueva_a_la_mas_vieja(self):
        """La de arriba es la que se publica; si no, se copia la que no es."""
        versiones = re.findall(r"^## (\d+)\.(\d+)\.(\d+)", self._changelog(),
                               re.MULTILINE)
        numeros = [tuple(int(p) for p in v) for v in versiones]
        self.assertEqual(numeros, sorted(numeros, reverse=True),
                         "las versiones del CHANGELOG no van de nueva a vieja")

    def test_la_primera_entrada_es_la_version_que_se_publica(self):
        import silux

        versiones = re.findall(r"^## (\d+\.\d+\.\d+)", self._changelog(),
                               re.MULTILINE)
        self.assertTrue(versiones, "el CHANGELOG no tiene ninguna entrada")
        self.assertEqual(versiones[0], silux.__version__,
                         "la entrada de arriba del CHANGELOG no es la versión "
                         "que declara el paquete")
