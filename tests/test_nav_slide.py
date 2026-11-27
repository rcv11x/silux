"""The sidebar's mark slides to the section opened instead of jumping, for a
moment and only then: nothing keeps running after the click. Settings can
switch it off, and then it jumps."""

import time
import unittest
from dataclasses import replace

from PySide6.QtCore import QAbstractAnimation

from silux.i18n import _
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts


def _row_top(window, row: int) -> float:
    return window.nav.visualItemRect(window.nav.item(row)).top()


def _wait(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()


class TestTheMarkSlides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-10400")

    def test_it_goes_between_the_two_rows_and_stops(self):
        with pantalla.Ventana(self.snapshot) as window:
            geometry.settle(self.app)
            # From the first row to one far down: Sensors.
            target = window.section_names().index("Sensores")
            window.select_section("Sensores")
            slide = window.nav.slide
            self.assertEqual(slide.state(), QAbstractAnimation.State.Running)
            _wait(self.app, 0.06)
            top = slide.currentValue().top()
            self.assertGreater(top, _row_top(window, 0))
            self.assertLess(top, _row_top(window, target))
            _wait(self.app, 0.3)
            # Over: nothing left running after the click.
            self.assertEqual(slide.state(), QAbstractAnimation.State.Stopped)

    def test_switched_off_it_jumps(self):
        with pantalla.Ventana(self.snapshot) as window:
            window._on_preferences(replace(window.prefs, nav_slide=False))
            geometry.settle(self.app)
            window.nav.setCurrentRow(5)
            self.assertEqual(window.nav.slide.state(), QAbstractAnimation.State.Stopped)

    def test_the_switch_is_in_appearance_and_acts_at_once(self):
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("Ajustes")
            geometry.settle(self.app)
            page = window.settings_page
            self.assertTrue(page.nav_slide.isChecked())
            page.nav_slide.click()
            geometry.settle(self.app)
            self.assertFalse(window.prefs.nav_slide)
            self.assertFalse(window.nav.slides)
            self.assertIn(_("settings.navslide.label"), visible_texts(page))


class TestThePillIsPainted(unittest.TestCase):
    """The style sheet no longer paints the open row: the list does."""

    @classmethod
    def setUpClass(cls):
        from silux.ui import theme

        cls.app = qt.app()
        theme.apply(cls.app, "dark", "normal")

    def test_the_open_row_has_its_pill_at_rest(self):
        app = self.app
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.nav.setCurrentRow(2)
            _wait(app, 0.3)
            image = window.nav.viewport().grab().toImage()
            opened = window.nav.visualItemRect(window.nav.item(2))
            other = window.nav.visualItemRect(window.nav.item(4))
            x = opened.right() - 12
            self.assertNotEqual(image.pixelColor(x, opened.center().y()).name(),
                                image.pixelColor(x, other.center().y()).name())


if __name__ == "__main__":
    unittest.main()
