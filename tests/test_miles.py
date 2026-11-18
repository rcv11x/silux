"""Los miles se separan con un espacio fino, nunca con punto ni con coma.

Revisión del autor: las horas de uso de un disco salían «4.136 h», que se lee
como cuatro horas con decimales. Era `f"{n:n}"`, que sigue el locale: en
español pone punto y en inglés coma, justo los dos signos que el otro idioma
lee como decimal. La norma (ISO 80000-1, el SI) agrupa con un espacio fino y
no con signos, y así se lee igual en los dos idiomas. Sistema usaba un
espacio normal, que además puede partir la cifra en dos líneas.
"""

import locale
import pathlib
import re
import unittest

from silux import render

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "silux"
ESPACIO_FINO = " "


class TestLaFuncion(unittest.TestCase):

    def test_agrupa_de_tres_en_tres_con_espacio_fino(self):
        self.assertEqual(render.thousands(4136), f"4{ESPACIO_FINO}136")
        self.assertEqual(render.thousands(1_234_567), f"1{ESPACIO_FINO}234{ESPACIO_FINO}567")
        self.assertEqual(render.thousands(999), "999")
        self.assertEqual(render.thousands(0), "0")
        self.assertEqual(render.thousands(-4136), f"-4{ESPACIO_FINO}136")
        self.assertEqual(render.thousands(None), render.DASH)

    def test_no_depende_del_locale(self):
        """La interfaz fija el locale del sistema al arrancar (Qt llama a
        setlocale), y con es_ES `:n` daba «4.136»."""
        for nombre in ("es_ES.UTF-8", "de_DE.UTF-8", "en_US.UTF-8"):
            with self.subTest(locale=nombre):
                try:
                    anterior = locale.setlocale(locale.LC_NUMERIC, nombre)
                except locale.Error:
                    self.skipTest(f"sin el locale {nombre}")
                try:
                    self.assertEqual(render.thousands(4136), f"4{ESPACIO_FINO}136")
                finally:
                    locale.setlocale(locale.LC_NUMERIC, "C")
                del anterior


class TestNadieAgrupaPorSuCuenta(unittest.TestCase):
    """Que nadie vuelva a agrupar con `:n` o `:,` fuera de render."""

    PATRON = re.compile(r"\{[^{}]*:(?:[<>^=]?\d*)?[n,_]\}")

    def test_en_todo_el_codigo(self):
        culpables = []
        for archivo in sorted(RAIZ.rglob("*.py")):
            for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
                # La única que agrupa es render.thousands, y lo hace con este espacio.
                if self.PATRON.search(linea) and "ESPACIO_DE_MILES" not in linea:
                    culpables.append(f"{archivo.relative_to(RAIZ.parent)}:{numero}: {linea.strip()}")
        self.assertEqual(culpables, [])


if __name__ == "__main__":
    unittest.main()
