"""La identificación: puntuación, patrones de marca y sockets."""

import unittest

from silux import db


class TestPatrones(unittest.TestCase):
    def test_almohadilla_es_un_digito(self):
        regex = db._compile_pattern("Core(TM) i5-10###")
        self.assertTrue(regex.search("Intel(R) Core(TM) i5-10400 @ 2.90GHz"))
        self.assertFalse(regex.search("Intel(R) Core(TM) i5-9400"))

    def test_punto_es_cualquier_caracter(self):
        self.assertTrue(db._compile_pattern("Ryzen . 5800X").search("AMD Ryzen 7 5800X"))

    def test_corchetes_son_literales_no_rangos(self):
        regex = db._compile_pattern("Xeon[(R)]")
        self.assertTrue(regex.search("Xeon("))
        self.assertFalse(regex.search("Xeon-"))

    def test_normalizacion_quita_relleno(self):
        self.assertEqual(
            db.normalize_brand("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz"),
            "Intel(R) Core(TM) i5-10400 @ 2.90GHz",
        )
        self.assertEqual(
            db.normalize_brand("AMD Ryzen 7 5800X 8-Core Processor"),
            "AMD Ryzen 7 5800X 8-Core",
        )


class TestPuntuacion(unittest.TestCase):
    def _entrada(self, **kwargs):
        base = {"f": -1, "m": -1, "s": -1, "xf": -1, "xm": -1, "nc": -1,
                "l2": -1, "l3": -1, "bp": None, "bs": 0}
        base.update(kwargs)
        return base

    def test_campos_en_minus_uno_no_puntuan(self):
        prueba = {"f": 6, "m": 5, "s": 3, "xf": 6, "xm": 165, "nc": 6, "l2": 256, "l3": 12288}
        self.assertEqual(db._score(self._entrada(), prueba, ""), 0)

    def test_cada_campo_vale_lo_documentado(self):
        prueba = {"f": 6, "m": 5, "s": 3, "xf": 6, "xm": 165, "nc": 6, "l2": 256, "l3": 12288}
        self.assertEqual(db._score(self._entrada(f=6), prueba, ""), 2)
        self.assertEqual(db._score(self._entrada(l3=12288), prueba, ""), 1)
        self.assertEqual(db._score(self._entrada(f=6, m=5, nc=6), prueba, ""), 6)

    def test_la_marca_desempata(self):
        prueba = {"f": 6, "m": 5, "s": 3, "xf": 6, "xm": 165, "nc": 6, "l2": -1, "l3": -1}
        entrada = self._entrada(f=6, bp="Core(TM) i5-10###", bs=8)
        self.assertEqual(db._score(entrada, prueba, "Intel(R) Core(TM) i5-10400 @ 2.90GHz"), 10)
        self.assertEqual(db._score(entrada, prueba, "Intel(R) Core(TM) i9-10900K"), 2)


@unittest.skipUnless(db.available(), "hace falta generar la base con tools/gen_cpu_db.py")
class TestBaseReal(unittest.TestCase):
    def test_identifica_un_comet_lake(self):
        ident = db.identify_x86(
            vendor_id="GenuineIntel", family=6, model=5, stepping=3,
            ext_family=6, ext_model=165, cores=6,
            brand="Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz",
            l2_kb=256, l3_kb=12288,
        )
        self.assertTrue(ident.matched)
        self.assertIn("Comet Lake", ident.codename)
        self.assertIn("nm", ident.technology)

    def test_sockets_por_microarquitectura(self):
        casos = {
            "Core i5 (Comet Lake-S)": "LGA 1200",
            "Core i9 (Raptor Lake-S)": "LGA 1700",
            "Core Ultra 9 (Arrow Lake-S)": "LGA 1851",
        }
        for codename, esperado in casos.items():
            with self.subTest(codename=codename):
                self.assertEqual(db.find_socket("GenuineIntel", codename, ""), esperado)

    def test_fabricante_desconocido_no_revienta(self):
        ident = db.identify_x86(vendor_id="AcmeCPU", family=1, model=1, stepping=1,
                                ext_family=1, ext_model=1, cores=1)
        self.assertFalse(ident.matched)


if __name__ == "__main__":
    unittest.main()


class TestElSilicioMandaSobreElNombre(unittest.TestCase):
    """La familia y el modelo no admiten interpretación; la marca sí.

    Un probador con un Ryzen 7 7445HS (familia 25, modelo 0x7C) vio «Dragon
    Range», que es el modelo 0x61. Casó porque el patrón de marca «Ryzen 7
    7###H» de esa entrada le encajaba el nombre comercial, y el modelo, que no
    cuadraba, solo restaba puntos en vez de descartarla. El resultado era un
    nombre en clave, una litografía y un encapsulado de otro chip, dados con
    toda seguridad. Es peor que no saberlo.
    """

    def test_un_modelo_que_no_cuadra_descarta_la_entrada(self):
        resultado = db.identify_x86(
            vendor_id="AuthenticAMD", family=15, model=12, stepping=0,
            ext_family=25, ext_model=124, cores=6,
            brand="AMD Ryzen 7 7445HS w/ Radeon 740M Graphics",
            l2_kb=1024, l3_kb=16384,
        )
        self.assertFalse(resultado.matched)
        self.assertIsNone(resultado.codename)

    def test_lo_que_sí_cuadra_se_sigue_identificando(self):
        resultado = db.identify_x86(
            vendor_id="AuthenticAMD", family=15, model=1, stepping=2,
            ext_family=25, ext_model=33, cores=8,
            brand="AMD Ryzen 7 5800X3D 8-Core Processor",
            l2_kb=512, l3_kb=98304,
        )
        self.assertTrue(resultado.matched)
        self.assertIn("Vermeer", resultado.codename)

    def test_una_familia_de_otra_epoca_no_puede_ganar(self):
        # Antes de exigir la familia, un Ryzen sin entrada acababa
        # identificándose como un K6-2 de 250 nm.
        resultado = db.identify_x86(
            vendor_id="AuthenticAMD", family=15, model=99, stepping=0,
            ext_family=25, ext_model=250, cores=6, brand="AMD Ryzen 7 Futuro",
            l2_kb=1024, l3_kb=16384,
        )
        self.assertIsNone(resultado.codename)

    def test_el_comodin_de_libcpuid_no_es_una_identificacion(self):
        # libcpuid usa «Unknown …» para lo que no reconoce. Enseñarlo sería
        # contestar «no lo sé» con cara de saberlo.
        resultado = db.identify_x86(
            vendor_id="AuthenticAMD", family=15, model=12, stepping=0,
            ext_family=25, ext_model=124, cores=6, brand="AMD Ryzen 7 7445HS",
            l2_kb=1024, l3_kb=16384,
        )
        self.assertIsNone(resultado.codename)
