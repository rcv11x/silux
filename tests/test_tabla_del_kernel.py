"""La microarquitectura de Intel por familia y modelo, de `intel-family.h`.

libcpuid no tiene Panther Lake, Wildcat Lake ni Nova Lake, y el kernel sí:
`tools/gen_cpu_db.py` lee su `intel-family.h` de una etiqueta fija y la
tabla lo guarda en `intel_family`. Se mira solo cuando la tabla de libcpuid
no reconoce el procesador, así que nunca pisa un dato que ya se sabía. Da el
nombre en clave y nada más: el nodo y el encapsulado no salen del kernel, y
no se inventan.
"""

import unittest

from silux import db


def _identificar(familia: int, modelo: int, marca: str = ""):
    # Firma de Intel con la familia 6 o la 18/19 «a la nueva»: el modelo
    # extendido es el que publica el kernel.
    return db.identify_x86(vendor_id="GenuineIntel", family=familia if familia < 15 else 15,
                           model=modelo & 0xF, stepping=0, ext_family=familia,
                           ext_model=modelo, cores=0, brand=marca)


class TestLoQueLibcpuidNoTiene(unittest.TestCase):

    def test_panther_lake_wildcat_lake_y_nova_lake(self):
        for familia, modelo, nombre in ((6, 0xCC, "Panther Lake"), (6, 0xE5, "Panther Lake"),
                                        (6, 0xD5, "Wildcat Lake"), (18, 0x01, "Nova Lake")):
            with self.subTest(nombre=nombre, modelo=hex(modelo)):
                ident = _identificar(familia, modelo)
                self.assertTrue(ident.matched)
                self.assertEqual(ident.codename, nombre)
                # The kernel doesn't say the node; cpuid's table does, and
                # nothing is made up: it's that table's row or nothing.
                self.assertEqual(ident.technology, db.cpuid_node("GenuineIntel", familia, modelo))

    def test_no_pisa_lo_que_libcpuid_ya_sabe(self):
        # Arrow Lake-S está en libcpuid con su gama y su nodo; el kernel diría
        # «Arrow Lake» a secas.
        ident = _identificar(6, 0xC6, "Intel(R) Core(TM) Ultra 7 265K")
        self.assertEqual(ident.codename, "Core Ultra 7 (Arrow Lake-S)")
        self.assertEqual(ident.technology, "TSMC N3B")

    def test_amd_no_lo_mira(self):
        ident = db.identify_x86(vendor_id="AuthenticAMD", family=6, model=0xC, stepping=0,
                                ext_family=6, ext_model=0xCC, cores=0)
        self.assertNotEqual(ident.codename, "Panther Lake")


class TestLaTabla(unittest.TestCase):

    def test_sale_del_kernel_con_su_etiqueta(self):
        datos = db.load()
        self.assertIn("linux", datos["sources"])
        self.assertTrue(datos["sources"]["linux"]["tag"].startswith("v"))
        self.assertGreater(len(datos["intel_family"]), 50)

    def test_sin_atom_ni_modelos_compartidos(self):
        definidos = {f["define"] for f in db.load()["intel_family"]}
        self.assertFalse({d for d in definidos if "ATOM" in d or "XEON_PHI" in d})
        # 0x9E es Kaby Lake y también Coffee Lake: el nombre fallaría.
        self.assertNotIn("INTEL_KABYLAKE", definidos)
        self.assertNotIn("INTEL_SKYLAKE_X", definidos)
        # Antes de Nehalem el kernel nombra el núcleo: un Conroe saldría «Merom».
        self.assertFalse({d for d in definidos if d.startswith(("INTEL_CORE", "INTEL_P4"))})


class TestLosNombres(unittest.TestCase):

    def test_como_se_escriben(self):
        import tools.gen_cpu_db as gen
        for simbolo, esperado in (("PANTHERLAKE_L", ("Panther Lake", "L")),
                                  ("SAPPHIRERAPIDS_X", ("Sapphire Rapids", "X")),
                                  ("HASWELL", ("Haswell", "")),
                                  ("BROADWELL_G", ("Broadwell", "G")),
                                  ("LAKEFIELD", ("Lakefield", "")),
                                  ("SKYLAKE_L", ("Skylake", "L")),
                                  ("CORE2_MEROM_L", ("Merom", "L")),
                                  ("NOVALAKE", ("Nova Lake", ""))):
            with self.subTest(simbolo=simbolo):
                self.assertEqual(gen.nombre_de_intel(simbolo), esperado)


if __name__ == "__main__":
    unittest.main()
