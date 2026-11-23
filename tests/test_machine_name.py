"""The machine's name: never a version, never a platform code.

Some makers leave the BIOS version in the system's version and Intel's
platform code («BDW») in its family, and write the commercial name in the
product name instead.
"""

import unittest

from silux.model import Board, clean_dmi
from tests.test_equipos import foto, volcados


def foto_name(dump: str) -> str:
    from tests.test_equipos import EQUIPOS

    return foto(EQUIPOS / dump)[0].board.display_name or ""


class TestTheName(unittest.TestCase):

    def test_a_version_and_a_platform_code_name_nothing(self):
        board = Board(vendor="Acer", name="Robin_BH", version="V1.13", bios_version="V1.13",
                      system_vendor="Acer", system_name="Aspire E5-473",
                      system_version="V1.13", system_family="BDW")
        self.assertEqual(board.display_name, "Acer Aspire E5-473")

    def test_a_series_letter_is_not_a_name(self):
        board = Board(vendor="ASUSTeK COMPUTER INC.", name="X550JK", version="1.0",
                      system_vendor="ASUSTeK COMPUTER INC.", system_name="X550JK",
                      system_version="1.0", system_family="X")
        self.assertEqual(board.display_name, "ASUS X550JK")
        # A branded machine, not a loose board.
        self.assertEqual(board.system_display_name, "X550JK")

    def test_a_part_code_is_not_a_name(self):
        board = Board(vendor="LENOVO", name="LNVNB161216", system_vendor="LENOVO",
                      system_name="81HL", system_version="1.0", system_family="BDW")
        self.assertEqual(board.display_name, "Lenovo LNVNB161216")

    def test_hps_fillers_name_nothing(self):
        # Its consumer laptops leave the template's field in the version and
        # a platform code in the family; the name is in the product name.
        board = Board(vendor="HP", name="881D", version="50.34", bios_version="F.64",
                      system_vendor="HP", system_name="HP Laptop 15-dw3xxx",
                      system_version="Type1ProductConfigId",
                      system_family="103C_5335KV HP Notebook")
        self.assertEqual(board.display_name, "HP Laptop 15-dw3xxx")
        for filler in ("Type1ProductConfigId", "103C_5335KV HP Notebook"):
            self.assertNotIn(filler, foto_name("i3-1115g4"))

    def test_an_oem_machine_is_not_named_after_its_board(self):
        from tests.test_equipos import EQUIPOS

        board = foto(EQUIPOS / "core2-p8400")[0].board
        self.assertEqual((board.name, board.display_name), ("0TN284", "Dell Latitude E6400"))

    def test_no_dump_is_named_after_a_version(self):
        for folder in volcados():
            board = foto(folder)[0].board
            title = board.display_name or ""
            versions = {clean_dmi(board.bios_version), clean_dmi(board.version),
                        clean_dmi(board.system_version) if board.system_version
                        and board.system_version == board.bios_version else None} - {None}
            with self.subTest(folder.name, title=title):
                self.assertTrue(title)
                for version in versions:
                    self.assertNotIn(version, title.split())


if __name__ == "__main__":
    unittest.main()
