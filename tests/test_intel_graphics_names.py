"""An Intel integrated GPU by its commercial name, not its family or codename.

pci.ids calls an HD Graphics 4600 «4th Gen Core Processor Integrated
Graphics Controller», and an old chipset's graphics «… (primary)». The name
by device ID comes from Mesa's tables (silux/db/intel_gpus.json).
"""

import unittest
from unittest import mock

from silux import db
from silux.providers import drm
from silux.providers.base import Draft
from silux.providers.drm import _intel_commercial_name
from tests import pantalla, qt
from tests.test_gpu import BancoDrm
from tests.test_interface_language import visible_texts
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados


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
            snapshot = shared_snapshot(folder)
            with self.subTest(folder.name), pantalla.Ventana(snapshot) as window:
                window.select_section("Inicio")
                text = " ".join(visible_texts(window.stack.currentWidget()))
                self.assertNotIn("Graphics Controller", text)
                self.assertNotIn("(primary)", text)

    def test_the_asus_on_home(self):
        snapshot = shared_snapshot(EQUIPOS / "i7-4710hq")
        self.assertIn("HD Graphics 4600", [g.name for g in snapshot.gpus])


class TestAnOlderPciIds(BancoDrm):
    """An older pci.ids gives only the codename, without brackets.

    From a report: Debian 13's file calls an i7-12700's UHD Graphics 770
    (8086:4680) «AlderLake-S GT1», and that was the card's title.
    """

    def _collect(self, pci_ids_name: str, device: str = "0x4680") -> Draft:
        self.tarjeta(0, ranura="0000:00:02.0", vendor="0x8086", device=device,
                     subsystem_vendor="0x1849", subsystem_device="0x4680",
                     revision="0x0c", **{"class": "0x030000"})
        answer = {(0x8086, int(device, 16)): ("Intel Corporation", pci_ids_name)}
        draft = Draft()
        with mock.patch.object(drm.pciids, "lookup", return_value=answer):
            drm.DrmGpus().collect(draft)
        return draft

    def test_the_name_comes_from_mesa_and_the_codename_stays_one(self):
        gpu = self._collect("AlderLake-S GT1").gpus[0]
        self.assertEqual(gpu["name"], "UHD Graphics 770")
        self.assertEqual(gpu["codename"], "AlderLake-S GT1")

    def test_a_newer_pci_ids_gives_the_same(self):
        gpu = self._collect("Alder Lake-S GT1 [UHD Graphics 770]").gpus[0]
        self.assertEqual((gpu["name"], gpu["codename"]),
                         ("UHD Graphics 770", "Alder Lake-S GT1"))

    def test_a_marketing_name_without_brackets_stays(self):
        gpu = self._collect("UHD Graphics 620", device="0x5917").gpus[0]
        self.assertEqual(gpu["name"], "UHD Graphics 620")
        self.assertIsNone(gpu["codename"])

    def test_on_the_graphics_page(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = qt.app()
        page = GraphicsPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.apply(self._collect("AlderLake-S GT1").freeze())
        section = page._sections[0]
        self.assertEqual(section.title.text(), "UHD Graphics 770")
        self.assertEqual(section.card.value_label(_("gpu.field.codename")).full_text(),
                         "AlderLake-S GT1")


if __name__ == "__main__":
    unittest.main()
