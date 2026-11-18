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


class TestLasFichasDeIntelGuardadas(unittest.TestCase):
    """`--intel-desde`: fichas de ark.intel.com guardadas desde el navegador.

    PROVISIONAL: aún no hay una ficha guardada de verdad en el repositorio.
    Esta lleva solo lo que se sabe que enseña la del i5-10400 (su título y
    «Memory Types: DDR4-2666», vistos en los resultados de búsqueda) y una
    dirección canónica. Se cambia por la ficha real en cuanto el autor la
    guarde en ~/Descargas/intel-ark.
    """

    FICHA = ("<html><head><title>Intel® Core™ i5-10400 Processor (12M Cache, up to 4.30 GHz)"
             " - Product Specifications | Intel</title>"
             '<link rel="canonical" href="https://www.intel.com/content/www/us/en/products/'
             'sku/199271/intel-core-i510400-processor-12m-cache-up-to-4-30-ghz/'
             'specifications.html"></head><body>'
             "<div>Max Memory Size (dependent on memory type)</div><div>128 GB</div>"
             "<div>Memory Types</div><div>DDR4-2666</div>"
             "<div>Max # of Memory Channels</div><div>2</div></body></html>")

    def test_lee_modelo_memoria_y_fuente(self):
        fila = gen.ficha_intel(self.FICHA)
        self.assertEqual(fila["models"], ["i5-10400"])
        self.assertEqual(fila["types"], {"DDR4": 2666})
        self.assertIn("/sku/199271/", fila["source"])
        self.assertEqual(fila["origin"], "saved-page")

    def test_una_pagina_que_no_es_una_ficha_no_da_fila(self):
        self.assertIsNone(gen.ficha_intel("<html><title>Intel</title><body>hola</body></html>"))

    def test_una_ficha_guardada_sustituye_a_la_fila_a_mano(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            pathlib.Path(carpeta, "i5-10400.html").write_text(self.FICHA)
            filas, ilegibles = gen.filas_intel(pathlib.Path(carpeta))
        self.assertEqual(ilegibles, [])
        por_modelo = {m: f for f in filas for m in f["models"]}
        self.assertEqual(por_modelo["i5-10400"]["origin"], "saved-page")
        self.assertEqual(por_modelo["i5-10400F"]["origin"], "manual")


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
                    self.assertRegex(tipo, r"^DDR[45]$")
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
