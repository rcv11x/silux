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

    # Los dos archivos que dicen cuántos tests hay, cada uno con su forma de
    # escribirlo. El README se quedó en 592 con la suite ya por encima de mil:
    # solo se vigilaba CLAUDE.md, y quien lee el README es quien no conoce el
    # proyecto y no tiene con qué contrastarlo.
    CIFRAS_DE_TESTS = (
        ("CLAUDE.md", r"Los tests son \*\*(\d+)\*\*"),
        ("README.md", r"^Son (\d+) y tardan"),
    )

    def test_el_numero_de_tests_es_el_que_hay(self):
        import unittest as ut

        suite = ut.defaultTestLoader.discover(str(RAIZ / "tests"),
                                              top_level_dir=str(RAIZ))
        real = suite.countTestCases()

        for archivo, patron in self.CIFRAS_DE_TESTS:
            with self.subTest(archivo=archivo):
                camino = RAIZ / archivo
                if not camino.is_file():
                    self.skipTest(f"no hay {archivo}")
                escrito = re.search(patron, camino.read_text(encoding="utf-8"),
                                    re.MULTILINE)
                self.assertIsNotNone(
                    escrito, f"no se encuentra la cifra de tests en {archivo}")
                dicho = int(escrito.group(1))
                self.assertLessEqual(
                    abs(real - dicho) / real, MARGEN,
                    f"{archivo} dice {dicho} tests y hay {real}")

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


class TestLaVersionSeEscribeUnaSolaVez(unittest.TestCase):
    """Una versión copiada a mano en dos archivos se separa sola.

    `pyproject.toml` se toca al empaquetar y `silux/__init__.py` al publicar,
    así que llevaban un ciclo entero diciendo cosas distintas —0.1.0 y 0.2.0—
    sin que nada fallara. Y la página de Ajustes tenía una tercera copia, que
    es la única que el usuario ve: el rótulo del programa decía 0.1.0.
    """

    _LITERAL = re.compile(r"^\d+\.\d+(\.\d+)?$")

    def test_pyproject_no_escribe_la_version(self):
        texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotRegex(
            texto, r'(?m)^\s*version\s*=\s*"\d',
            "pyproject.toml declara la versión a mano: se desincroniza de "
            "silux.__version__. Va con dynamic = [\"version\"]")
        self.assertRegex(
            texto, r'attr\s*=\s*"silux\.__version__"',
            "pyproject.toml tiene que leer la versión del propio paquete")

    def test_ningun_modulo_guarda_su_propia_version(self):
        """Solo `silux/__init__.py` puede tener un número de versión suelto."""
        import ast

        for archivo in sorted((RAIZ / "silux").rglob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            for nodo in arbol.body:
                if not isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                    continue
                valor = nodo.value
                if not (isinstance(valor, ast.Constant)
                        and isinstance(valor.value, str)
                        and self._LITERAL.match(valor.value)):
                    continue
                objetivos = (nodo.targets if isinstance(nodo, ast.Assign)
                             else [nodo.target])
                nombres = [t.id for t in objetivos if isinstance(t, ast.Name)]
                with self.subTest(archivo=archivo.name, nombres=nombres):
                    self.assertEqual(
                        (archivo.name, nombres), ("__init__.py", ["__version__"]),
                        f"{archivo.relative_to(RAIZ)} guarda «{valor.value}» "
                        "en una constante: si es la versión del programa, va "
                        "importada de silux.__version__")
