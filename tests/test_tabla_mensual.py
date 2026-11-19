"""La tarea mensual que regenera la tabla de procesadores y abre un PR.

Lo que se vigila es lo que no se puede ver hasta el día 1 de cada mes: que
corre sola, que regenera con los mismos generadores que en local, que pasa
la suite antes de abrir nada, y que lo único que puede escribir es su rama y
su PR.
"""

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FLUJO = RAIZ / ".github" / "workflows" / "tabla-cpu.yml"


class TestLaTareaMensual(unittest.TestCase):

    def setUp(self):
        self.texto = FLUJO.read_text(encoding="utf-8")

    def test_una_vez_al_mes_y_a_mano(self):
        cron = re.search(r'cron:\s*"([^"]+)"', self.texto)
        self.assertIsNotNone(cron)
        minuto, hora, dia, mes, semana = cron.group(1).split()
        self.assertEqual((dia, mes, semana), ("1", "*", "*"))
        self.assertIn("workflow_dispatch:", self.texto)

    def test_regenera_con_los_generadores_de_casa(self):
        for herramienta in ("tools/gen_cpu_db.py", "tools/gen_referencias_cpu.py"):
            with self.subTest(herramienta=herramienta):
                self.assertTrue((RAIZ / herramienta).is_file())
                self.assertIn(f"python {herramienta}", self.texto)

    def test_los_tests_van_antes_que_el_pr(self):
        tests = self.texto.index("python -m pytest")
        pr = self.texto.index("gh pr create")
        self.assertLess(tests, pr)
        # Y el PR va a master, sin fusionarse solo.
        self.assertIn("--base master", self.texto)
        self.assertNotIn("gh pr merge", self.texto)

    def test_solo_el_trabajo_puede_escribir(self):
        arriba = self.texto[:self.texto.index("jobs:")]
        self.assertRegex(arriba, r"permissions:\s*\n\s*contents:\s*read")
        self.assertNotIn("write", arriba)

    def test_sube_solo_lo_que_genera(self):
        add = re.search(r"git add ([^\n]+)", self.texto).group(1).split()
        self.assertEqual(sorted(add), ["silux/db/cpu_ids.json",
                                       "tests/fixtures/referencias_cpu.json"])


if __name__ == "__main__":
    unittest.main()
