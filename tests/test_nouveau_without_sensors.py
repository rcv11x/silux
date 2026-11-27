"""A GeForce RTX 3070 with nouveau, from Linux Mint run from a USB stick
(Felix's prueba13 report): nouveau registers no hwmon for it, so there is
no temperature either. The notice said «with nouveau you're left with the
temperature», and Graphics showed «Temperature: —». The card has its
sensor: what is missing is the driver's, and every page says so, never that
the card has none. An older card on nouveau keeps its temperature and its
notice."""

import unittest

from silux import render
from silux.i18n import _
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts


def nouveau_card(dump):
    snapshot = shared_snapshot(EQUIPOS / dump)
    return snapshot, next(g for g in snapshot.gpus if g.driver == "nouveau")


class TestNouveauWithoutSensors(unittest.TestCase):
    def test_the_3070_says_nouveau_publishes_none(self):
        snapshot, gpu = nouveau_card("ryzen7-5800x-nouveau")
        note = next(n for n in snapshot.notes if n.key == "prov.drm.nouveau")
        self.assertEqual(note.hint, _("prov.drm.nouveau.hint.nosensor"))
        app = qt.app()
        has_none = _("gpu.na.notemp")
        with pantalla.Ventana(snapshot) as window:
            seen = {}
            for page in ("Inicio", "Gráficos", "Sensores"):
                window.select_section(page)
                geometry.settle(app)
                seen[page] = "\n".join(visible_texts(window.stack.currentWidget()))
                with self.subTest(page=page):
                    self.assertNotIn(has_none, seen[page])
                    self.assertNotIn(_("sensors.absent.gputemp").format(
                        nombre=render.gpu_name(gpu)), seen[page])
            from silux.ui.pages.graphics import GpuSection
            section = window.graphics_page.findChildren(GpuSection)[0]
            self.assertFalse(section.tile_temp.isVisibleTo(window.graphics_page))
        self.assertIn(_("gpu.na.unpublished.temp").format(driver="nouveau"), seen["Inicio"])
        self.assertIn(_("sensors.absent.gputemp.driver").format(
            nombre=render.gpu_name(gpu), driver="nouveau"), seen["Sensores"])
        self.assertTrue(gpu.temperature_unpublished)
        self.assertFalse(gpu.no_temperature_sensor)

    def test_an_older_card_keeps_its_temperature(self):
        snapshot, gpu = nouveau_card("core2-p8400")
        self.assertFalse(gpu.temperature_unpublished)
        self.assertIsNotNone(gpu.temp_c)
        note = next(n for n in snapshot.notes if n.key == "prov.drm.nouveau")
        self.assertEqual(note.hint, _("prov.drm.nouveau.hint"))


if __name__ == "__main__":
    unittest.main()
