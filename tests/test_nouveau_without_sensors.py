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

    def test_home_says_why_the_card_has_no_figure(self):
        """Home showed the 3070 with its name and nothing else: no usage,
        clock, temperature or power, and no word on why."""
        snapshot, _gpu = nouveau_card("ryzen7-5800x-nouveau")
        app = qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Inicio")
            geometry.settle(app)
            card = window.home_page.gpu
            self.assertFalse(card.cifras.isVisibleTo(card))
            self.assertIn(_("prov.drm.nouveau"), card.pie.text())
            self.assertTrue(card.pie.isVisibleTo(card))

    def test_a_card_with_a_figure_keeps_its_foot_as_it_was(self):
        snapshot, _gpu = nouveau_card("core2-p8400")
        app = qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Inicio")
            geometry.settle(app)
            self.assertNotIn(_("prov.drm.nouveau"), window.home_page.gpu.pie.text())

    def test_an_older_card_keeps_its_temperature(self):
        snapshot, gpu = nouveau_card("core2-p8400")
        self.assertFalse(gpu.temperature_unpublished)
        self.assertIsNotNone(gpu.temp_c)
        note = next(n for n in snapshot.notes if n.key == "prov.drm.nouveau")
        self.assertEqual(note.hint, _("prov.drm.nouveau.hint"))



class TestTheOpenDriversNotice(unittest.TestCase):
    """The notice read «Falta un driver» over a card that has one: nouveau,
    the open driver."""

    def test_titled_by_the_driver_it_has(self):
        app = qt.app()
        snapshot, _gpu = nouveau_card("ryzen7-5800x-nouveau")
        note = next(n for n in snapshot.notes if n.key == "prov.drm.nouveau")
        self.assertEqual(note.title, _("prov.drm.nouveau.title"))
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            geometry.settle(app)
            texts = "\n".join(visible_texts(window.stack.currentWidget()))
        self.assertIn(_("prov.drm.nouveau.title"), texts)
        self.assertNotIn(_("note.needsdriver"), texts)


if __name__ == "__main__":
    unittest.main()
