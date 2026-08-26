"""El generador de la base de datos, contra fragmentos de C sintéticos.

Estos tests son la red de seguridad del punto más frágil del proyecto: si
libcpuid cambia el formato de sus tablas, el generador debe fallar de forma
visible y no producir una base de datos a medio parsear.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import gen_cpu_db as gen  # noqa: E402


TABLA_X86 = """
const struct match_entry_t cpudb_intel[] = {
/*  F   M   S  XF    XM  Cores  L2    L3       Brand              Score   Codename            Technology */
	{ -1, -1, -1, -1, -1,   1,    -1,    -1, { "",              0 }, "Unknown Intel CPU", UNKN_STR },
	/* Comet Lake (2019, 14++ nm) */
	{  6,  5, -1, -1, 165,  6,    -1,    -1, { "Core(TM) i5-10###", 8 }, "Core i5 (Comet Lake-S)", "14++ nm" },
	// una fila comentada que no debe aparecer:
	// { 6, 5, -1, -1, 165, 4, -1, -1, { "", 0 }, "Fantasma", "0 nm" },
	{ 15, -1, -1, 15, 0x4f,  1,   512,    -1, { "Athlon(tm) 64",  4 }, "Athlon 64 (Orleans)", "90 nm" },
};
"""

TABLA_ARM = """
static const struct arm_id_part arm_part[] = {
	{ 0x810, "ARM810",     UNKN_STR, UNKN_STR },
	{ 0xd07, "Cortex-A57", UNKN_STR, "20 nm"  },
	{ -1,    UNKN_STR,     UNKN_STR, UNKN_STR },
};

static const struct arm_id_part apple_part[] = {
	{ 0x022, "M1",     UNKN_STR, "5 nm" },
	{ -1,    UNKN_STR, UNKN_STR, UNKN_STR },
};

static const struct arm_hw_impl hw_implementer[] = {
	{ 0x41, VENDOR_ARM,     arm_part,     "ARM"           },
	{ 0x61, VENDOR_APPLE,   apple_part,   "Apple"         },
	{ -1,   VENDOR_UNKNOWN, unknown_part, UNKN_STR        },
};
"""

TABLA_SOCKETS = """
const Package_DB package_intel[] = {
	{ "Bloomfield",  NULL,                             "LGA 1366" },
	{ NULL,          "Intel(R) Core(TM) i5-10500 CPU", "LGA 1200" },
	{ NULL,          NULL,                             NULL       }
};
"""


class TestParseoX86(unittest.TestCase):
    def setUp(self):
        self.filas = gen.parse_x86_table(TABLA_X86, "match_entry_t cpudb_intel[]")

    def test_ignora_filas_comentadas(self):
        self.assertEqual(len(self.filas), 3)
        self.assertNotIn("Fantasma", [f["name"] for f in self.filas])

    def test_campos_y_marca(self):
        comet = self.filas[1]
        self.assertEqual((comet["f"], comet["m"], comet["xm"], comet["nc"]), (6, 5, 165, 6))
        self.assertEqual(comet["bp"], "Core(TM) i5-10###")
        self.assertEqual(comet["bs"], 8)
        self.assertEqual(comet["tech"], "14++ nm")

    def test_acepta_hexadecimal(self):
        athlon = self.filas[2]
        self.assertEqual(athlon["xm"], 0x4F)
        self.assertEqual(athlon["l2"], 512)

    def test_unkn_str_se_convierte_en_nulo(self):
        self.assertIsNone(self.filas[0]["tech"])

    def test_una_tabla_vacia_es_un_error_ruidoso(self):
        with self.assertRaises(LookupError):
            gen.parse_x86_table("int nada = 0;", "match_entry_t cpudb_intel[]")


class TestParseoArm(unittest.TestCase):
    def test_implementadores_y_piezas(self):
        arm = gen.parse_arm_tables(TABLA_ARM)
        self.assertEqual(set(arm), {"65", "97"})            # 0x41 y 0x61 en decimal
        self.assertEqual(arm["65"]["vendor"], "ARM")
        self.assertEqual(arm["65"]["parts"][str(0xD07)]["name"], "Cortex-A57")
        self.assertEqual(arm["97"]["parts"][str(0x022)]["tech"], "5 nm")

    def test_descarta_el_centinela(self):
        arm = gen.parse_arm_tables(TABLA_ARM)
        self.assertNotIn("-1", arm)
        self.assertEqual(len(arm["97"]["parts"]), 1)


class TestParseoSockets(unittest.TestCase):
    def test_filas_y_centinela(self):
        filas = gen.parse_socket_table(TABLA_SOCKETS, "Package_DB package_intel[]")
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0], {"codename": "Bloomfield", "model": None, "socket": "LGA 1366"})
        self.assertIsNone(filas[1]["codename"])


if __name__ == "__main__":
    unittest.main()
