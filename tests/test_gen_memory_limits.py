"""La tabla de máximos de memoria y la herramienta que la genera.

`tests/fixtures/amd-5800x3d-memoria.html` es el bloque «Max Memory Speed»
de la ficha del 5800X3D en amd.com, recortado tal cual de la descarga del
18 de noviembre de 2026.
"""

import json
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import gen_memory_limits as gen  # noqa: E402

TABLA = json.loads((RAIZ / "silux" / "db" / "memory_limits.json").read_text(encoding="utf-8"))


class TestLaFicha(unittest.TestCase):

    def test_lee_las_cuatro_disposiciones(self):
        ficha = (RAIZ / "tests" / "fixtures" / "amd-5800x3d-memoria.html").read_text()
        self.assertEqual(gen.disposiciones(ficha),
                         {"DDR4": {"2x1R": 3200, "2x2R": 3200, "4x1R": 2933, "4x2R": 2667}})

    def test_sin_el_bloque_no_inventa(self):
        self.assertEqual(gen.disposiciones("<html><dt>Max. Memory</dt><dd>128 GB</dd></html>"), {})


class TestLasPaginasDeArkGuardadas(unittest.TestCase):
    """`--intel-desde`: páginas de ark.intel.com guardadas desde el navegador.

    Los dos fixtures son recortes de páginas que el autor guardó el 18 de
    noviembre de 2026: la comparación de los Core i5 de 10.ª (las cabeceras
    de los tres primeros modelos y su fila «Memory Types») y la ficha del
    i7-12700K, que escribe la memoria de otra forma («Up to DDR5 4800 MT/s»).
    """

    COMPARACION = (RAIZ / "tests" / "fixtures" / "intel-ark-comparacion.html").read_text()
    FICHA = (RAIZ / "tests" / "fixtures" / "intel-ark-12700k.html").read_text()

    def test_la_comparacion_da_una_fila_por_modelo_con_su_ficha(self):
        filas = gen.comparacion_intel(self.COMPARACION)
        self.assertEqual([f["models"][0] for f in filas], ["i5-10210U", "i5-10310Y", "i5-10210Y"])
        self.assertEqual(filas[0]["types"], {"DDR4": 2666, "LPDDR3": 2133, "LPDDR4": 2933})
        # DDR3L es DDR3 para la tabla del firmware.
        self.assertEqual(filas[1]["types"], {"LPDDR3": 2133, "DDR3": 1600})
        self.assertTrue(all("/products/sku/" in f["source"] and f["source"].startswith(
            "https://www.intel.com/") for f in filas))

    def test_la_ficha_de_un_hibrido_con_dos_tipos(self):
        fila = gen.ficha_intel(self.FICHA)
        self.assertEqual(fila["models"], ["i7-12700K"])
        self.assertEqual(fila["types"], {"DDR5": 4800, "DDR4": 3200})
        self.assertIn("/sku/134594/", fila["source"])

    def test_una_pagina_que_no_trae_memoria_no_da_fila(self):
        self.assertIsNone(gen.ficha_intel("<html><title>Intel</title><body>hola</body></html>"))
        self.assertEqual(gen.comparacion_intel("<html><body>hola</body></html>"), [])

    def test_lo_guardado_sustituye_a_lo_escrito_a_mano(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            pathlib.Path(carpeta, "comparacion.html").write_text(self.COMPARACION)
            pathlib.Path(carpeta, "12700k.html").write_text(self.FICHA)
            filas, ilegibles = gen.filas_intel(pathlib.Path(carpeta))
        self.assertEqual(ilegibles, [])
        por_modelo = {m: f for f in filas for m in f["models"]}
        self.assertEqual(por_modelo["i7-12700K"]["origin"], "saved-page")
        self.assertEqual(por_modelo["i5-10400"]["origin"], "manual")


class TestLaTablaGenerada(unittest.TestCase):

    def test_dice_que_es_generada(self):
        self.assertIn("gen_memory_limits.py", TABLA["_"])

    def test_cada_fila_con_su_fuente_y_su_origen(self):
        for fila in TABLA["cpus"]:
            with self.subTest(modelos=fila["models"][:2]):
                dominio = {"AMD": "https://www.amd.com/", "Intel": "https://www.intel.com/"}
                self.assertTrue(fila["source"].startswith(dominio[fila["vendor"]]))
                # Intel no se puede descargar: lo dice cada fila suya.
                self.assertEqual(fila["origin"] in ("manual", "saved-page"),
                                 fila["vendor"] == "Intel")

    def test_las_cifras_son_de_memoria_de_verdad(self):
        for fila in TABLA["cpus"]:
            for tipo, cifra in fila["types"].items():
                with self.subTest(modelos=fila["models"][:1], tipo=tipo):
                    self.assertRegex(tipo, r"^(LP)?DDR[345]X?$")
                    cifras = cifra.values() if isinstance(cifra, dict) else [cifra]
                    for disposicion in (cifra if isinstance(cifra, dict) else {}):
                        self.assertRegex(disposicion, r"^[24]x[12]R$")
                    for mts in cifras:
                        self.assertTrue(1600 <= mts <= 8000, mts)

    def test_ningun_modelo_dos_veces_ni_con_ruido_en_el_nombre(self):
        modelos = [m for f in TABLA["cpus"] for m in f["models"]]
        self.assertEqual(len(modelos), len(set(modelos)))
        self.assertFalse([m for m in modelos if re.search(r"™|®|OEM|Processor|^AMD", m)])

    def test_cubre_ryzen_3000_a_9000(self):
        series = {re.search(r" (\d)\d{3}", m).group(1) for f in TABLA["cpus"]
                  if f["vendor"] == "AMD" for m in f["models"] if re.search(r" \d{4}", m)}
        self.assertEqual(series, {"3", "4", "5", "7", "8", "9"})


if __name__ == "__main__":
    unittest.main()


class TestTheFourteenthGenComparison(unittest.TestCase):
    """A comparison saved from ARK (Core i5, 14th gen) gave no row: its table
    has an empty last column, so 16 cells for 15 models, and the reader
    wanted as many cells as model links. The models now come from the
    «Processor Number» row."""

    PAGE = (RAIZ / "tests" / "fixtures" / "intel-ark-comparacion-14-i5.html").read_text()

    def rows(self):
        return {row["models"][0]: row for row in gen.comparacion_intel(self.PAGE)}

    def test_one_row_per_model(self):
        rows = self.rows()
        self.assertEqual(len(rows), 15)
        for model in ("i5-14600K", "i5-14400F", "i5-14450HX", "i5-14501TE"):
            with self.subTest(model=model):
                self.assertIn(model, rows)

    def test_each_row_with_its_memory_and_its_own_page(self):
        row = self.rows()["i5-14600K"]
        self.assertEqual(row["types"], {"DDR5": 5600, "DDR4": 3200})
        self.assertRegex(row["source"], r"/products/sku/236799/")
        self.assertEqual(row["origin"], "saved-page")
