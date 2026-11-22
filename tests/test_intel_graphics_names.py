"""An Intel integrated GPU by its commercial name, not its family.

pci.ids calls an HD Graphics 4600 «4th Gen Core Processor Integrated
Graphics Controller», and an old chipset's graphics «… (primary)». The name
by device ID comes from Mesa's tables (silux/db/intel_gpus.json).
"""

import unittest

from silux import db
from silux.providers.drm import _intel_commercial_name
from tests import pantalla, qt
from tests.test_interface_language import visible_texts
from tests.test_equipos import EQUIPOS, foto, volcados


class TestTheName(unittest.TestCase):

    def test_by_device_id_where_pci_ids_gives_a_family(self):
        self.assertEqual(_intel_commercial_name(
            "4th Gen Core Processor Integrated Graphics Controller", 0x8086, 0x0416),
            "HD Graphics 4600")
        self.assertEqual(_intel_commercial_name(
            "Mobile GM965/GL960 Integrated Graphics Controller (primary)", 0x8086, 0x2A02),
            "Mobile GM965/GL960 Integrated Graphics")
        # A real name stays; another maker's too.
        self.assertEqual(_intel_commercial_name("UHD Graphics 620", 0x8086, 0x5917),
                         "UHD Graphics 620")
        self.assertEqual(_intel_commercial_name("Graphics Controller X", 0x10DE, 0x0416),
                         "Graphics Controller X")

    def test_the_table_has_no_generic_names(self):
        names = db.intel_gpus()
        self.assertGreater(len(names), 250)
        self.assertNotIn("Graphics", names.values())
        # Mesa's chipset names for the oldest ones are not a GPU's.
        self.assertNotIn("965GM", names.values())

    def test_no_dump_shows_a_family_or_primary(self):
        qt.app()
        for folder in volcados():
            snapshot = foto(folder)[0]
            with self.subTest(folder.name), pantalla.Ventana(snapshot) as window:
                window.select_section("Inicio")
                text = " ".join(visible_texts(window.stack.currentWidget()))
                self.assertNotIn("Graphics Controller", text)
                self.assertNotIn("(primary)", text)

    def test_the_asus_on_home(self):
        snapshot = foto(EQUIPOS / "i7-4710hq")[0]
        self.assertIn("HD Graphics 4600", [g.name for g in snapshot.gpus])


if __name__ == "__main__":
    unittest.main()
