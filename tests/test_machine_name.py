"""The machine's name: never a version, never a platform code.

Some makers leave the BIOS version in the system's version and Intel's
platform code («BDW») in its family, and write the commercial name in the
product name instead.
"""

import unittest

from silux.model import Board, clean_dmi
from tests.test_equipos import foto, volcados


class TestTheName(unittest.TestCase):

    def test_a_version_and_a_platform_code_name_nothing(self):
        board = Board(vendor="Acer", name="Robin_BH", version="V1.13", bios_version="V1.13",
                      system_vendor="Acer", system_name="Aspire E5-473",
                      system_version="V1.13", system_family="BDW")
        self.assertEqual(board.display_name, "Acer Aspire E5-473")

    def test_a_part_code_is_not_a_name(self):
        board = Board(vendor="LENOVO", name="LNVNB161216", system_vendor="LENOVO",
                      system_name="81HL", system_version="1.0", system_family="BDW")
        self.assertEqual(board.display_name, "Lenovo LNVNB161216")

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
