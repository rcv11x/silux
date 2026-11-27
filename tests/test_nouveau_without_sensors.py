"""A GeForce RTX 3070 with nouveau, from Linux Mint run from a USB stick
(Felix's prueba13 report): nouveau registers no hwmon for it, so there is
no temperature either. The notice said «with nouveau you're left with the
temperature», and Graphics showed «Temperature: —». Now the temperature is
hidden as one the card doesn't publish, and the notice says so; an older
card on nouveau keeps its temperature and its notice."""

import unittest

from silux.i18n import _
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


def nouveau_card(dump):
    snapshot = shared_snapshot(EQUIPOS / dump)
    return snapshot, next(g for g in snapshot.gpus if g.driver == "nouveau")


class TestNouveauWithoutSensors(unittest.TestCase):
    def test_the_3070_says_it_has_none(self):
        snapshot, gpu = nouveau_card("ryzen7-5800x-nouveau")
        self.assertTrue(gpu.no_temperature_sensor)
        note = next(n for n in snapshot.notes if n.key == "prov.drm.nouveau")
        self.assertEqual(note.hint, _("prov.drm.nouveau.hint.nosensor"))
        app = qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            geometry.settle(app)
            from silux.ui.pages.graphics import GpuSection
            section = window.graphics_page.findChildren(GpuSection)[0]
            self.assertFalse(section.tile_temp.isVisibleTo(window.graphics_page))

    def test_an_older_card_keeps_its_temperature(self):
        snapshot, gpu = nouveau_card("core2-p8400")
        self.assertFalse(gpu.no_temperature_sensor)
        self.assertIsNotNone(gpu.temp_c)
        note = next(n for n in snapshot.notes if n.key == "prov.drm.nouveau")
        self.assertEqual(note.hint, _("prov.drm.nouveau.hint"))


if __name__ == "__main__":
    unittest.main()
