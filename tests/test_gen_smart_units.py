"""The reader of smartmontools' drivedb.h (tools/gen_smart_units.py)."""

import importlib.util
import pathlib
import unittest

RUTA = pathlib.Path(__file__).resolve().parent.parent / "tools" / "gen_smart_units.py"
spec = importlib.util.spec_from_file_location("gen_smart_units", RUTA)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

# Two entries as drivedb.h writes them: comments between strings, a URL with
# «//» inside one, and the presets split over several literals.
FUENTE = r'''
  { "VERSION: 8.0", "-", "-", "Version information", "" },
  { "Phison Driven SSDs", // see MKP_521_Phison_SMART_attribute.pdf
    "KINGSTON  ?SA400(M8|S37)(120|240|480|960)G|" // Kingston A400 SSD
    "PNY CS900 240GB SSD",
    "", "See https://www.smartmontools.org/ticket/801",
  //"-v 1,raw48,Raw_Read_Error_Rate "
    "-v 231,raw48,SSD_Life_Left "
    "-v 241,raw48,Lifetime_Writes_GiB " // KIOXIA: 32MiB ?
    "-v 242,raw48,Lifetime_Reads_GiB "
  },
  { "ATP SATA III Superior Line SSDs", "ATP I-Temp M\\.2 22(42|80)", "", "",
    "-v 241,raw48,Sectors_Written_to_NAND"
  },
'''


class TestTheReader(unittest.TestCase):

    def test_entries_with_their_five_fields(self):
        entradas = gen.entries(FUENTE)
        self.assertEqual(len(entradas), 3)
        self.assertEqual(entradas[1][3], "See https://www.smartmontools.org/ticket/801")
        self.assertEqual(entradas[1][1], "KINGSTON  ?SA400(M8|S37)(120|240|480|960)G|PNY CS900 240GB SSD")

    def test_the_unit_from_the_name(self):
        filas = gen.table(FUENTE)
        self.assertEqual(filas[0]["units"], {"241": 1024 ** 3, "242": 1024 ** 3})
        # What the flash wrote is not what the computer did.
        self.assertEqual(filas[1]["units"], {"241": None})


if __name__ == "__main__":
    unittest.main()
