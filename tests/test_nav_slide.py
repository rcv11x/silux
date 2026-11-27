"""The sidebar's mark and Performance's tab line slide to the one opened
instead of jumping, for a moment and only then: nothing keeps running after
the click. «Smooth motion» in Settings moves them, as the charts; off, they
jump."""

import time
import unittest
from dataclasses import replace

from PySide6.QtCore import QAbstractAnimation, QEasingCurve

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


def _smooth(window, on: bool) -> None:
    window._on_preferences(replace(window.prefs, fluid_charts=on))


class TestTheMarkSlides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-10400")

    def test_it_goes_between_the_two_rows_and_stops(self):
        with pantalla.Ventana(self.snapshot) as window:
            _smooth(window, True)
            geometry.settle(self.app)
            # From the first row to one far down: Sensors.
            target = window.section_names().index("Sensores")
            window.select_section("Sensores")
            glide = window.nav.glide
            self.assertEqual(glide.animation.state(), QAbstractAnimation.State.Running)
            self.assertEqual(glide.animation.duration(), 180)
            self.assertEqual(glide.animation.easingCurve().type(), QEasingCurve.Type.OutCubic)
            _wait(self.app, 0.06)
            top = glide.animation.currentValue().top()
            self.assertGreater(top, _row_top(window, 0))
            self.assertLess(top, _row_top(window, target))
            _wait(self.app, 0.3)
            # Over: nothing left running after the click.
            self.assertEqual(glide.animation.state(), QAbstractAnimation.State.Stopped)

    def test_without_smooth_motion_it_jumps(self):
        with pantalla.Ventana(self.snapshot) as window:
            _smooth(window, False)
            geometry.settle(self.app)
            window.select_section("CPU")
            self.assertEqual(window.nav.glide.animation.state(),
                             QAbstractAnimation.State.Stopped)

    def test_one_switch_for_every_motion(self):
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("Ajustes")
            geometry.settle(self.app)
            page = window.settings_page
            self.assertFalse(hasattr(page, "nav_slide"))
            self.assertNotIn("nav_slide", vars(window.prefs))
            self.assertIn(_("settings.fluid.help"), visible_texts(page))


class TestTheTabLineSlides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "i5-10400")

    def test_it_goes_to_the_tab_opened_and_stops(self):
        with pantalla.Ventana(self.snapshot) as window:
            _smooth(window, True)
            window.select_section("Rendimiento")
            geometry.settle(self.app)
            page = window.benchmarks_page
            start = page.buttons["cpu"].geometry().left()
            end = page.buttons["disk"].geometry().left()
            page.select_tab("disk")
            glide = page.tab_strip.glide
            self.assertEqual(glide.animation.state(), QAbstractAnimation.State.Running)
            _wait(self.app, 0.06)
            left = glide.animation.currentValue().left()
            self.assertGreater(left, start)
            self.assertLess(left, end)
            _wait(self.app, 0.3)
            self.assertEqual(glide.animation.state(), QAbstractAnimation.State.Stopped)

    def test_without_smooth_motion_it_jumps(self):
        with pantalla.Ventana(self.snapshot) as window:
            _smooth(window, False)
            window.select_section("Rendimiento")
            geometry.settle(self.app)
            window.benchmarks_page.select_tab("memory")
            self.assertEqual(window.benchmarks_page.tab_strip.glide.animation.state(),
                             QAbstractAnimation.State.Stopped)


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
            # With smooth motion, on by default, it slides first: at rest is
            # once that is over, however long a busy machine takes.
            glide = window.nav.glide.animation
            end = time.monotonic() + 5
            while glide.state() == QAbstractAnimation.State.Running and time.monotonic() < end:
                app.processEvents()
            self.assertEqual(glide.state(), QAbstractAnimation.State.Stopped)
            geometry.settle(app)
            image = window.nav.viewport().grab().toImage()
            opened = window.nav.visualItemRect(window.nav.item(2))
            other = window.nav.visualItemRect(window.nav.item(4))
            x = opened.right() - 12
            for row in (opened, other):
                # A point outside the image reads as #000000 on both rows.
                self.assertTrue(image.rect().contains(x, row.center().y()),
                                f"{image.size()}, row {row}, nav visible "
                                f"{window.nav.isVisible()}, window {window.size()}")
            self.assertNotEqual(image.pixelColor(x, opened.center().y()).name(),
                                image.pixelColor(x, other.center().y()).name())


if __name__ == "__main__":
    unittest.main()
