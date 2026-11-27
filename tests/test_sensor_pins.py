"""Sensors pinned on top: a branch of their own above the rest, with the
same figures as their rows below, kept in the settings."""

import unittest

from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

DUMP = "5800x3d"


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / DUMP)

    def window(self, prefs=None):
        ventana = pantalla.Ventana(self.snapshot)
        window = ventana.__enter__()
        self.addCleanup(ventana.__exit__, None, None, None)
        window.resize(1300, 900)
        window.select_section("Sensores")
        geometry.settle(self.app)
        return window

    def a_sensor(self):
        return next(s for s in self.snapshot.sensors
                    if not s.mirror_of and s.value is not None and s.kind.value == "temperature")


class TestPinning(Case):
    def test_a_pinned_sensor_goes_on_top_with_its_figures(self):
        window = self.window()
        tree = window.monitor_page.tree
        sensor = self.a_sensor()
        tree.toggle_pinned(sensor.key)
        window._on_sample(self.snapshot)
        geometry.settle(self.app)
        top = tree.topLevelItem(0)
        self.assertIs(top, tree.pinned_branch)
        self.assertEqual(top.childCount(), 1)
        pinned, original = top.child(0), tree._rows[sensor.key]
        # The figures, the same; its name says its device too.
        self.assertIn(original.text(0).split(" (")[0], pinned.text(0))
        for column in range(1, tree.columnCount() - 1):
            self.assertEqual(pinned.text(column), original.text(column))

    def test_unpinned_the_branch_goes(self):
        window = self.window()
        tree = window.monitor_page.tree
        sensor = self.a_sensor()
        tree.toggle_pinned(sensor.key)
        window._on_sample(self.snapshot)
        tree.toggle_pinned(sensor.key)
        window._on_sample(self.snapshot)
        geometry.settle(self.app)
        self.assertIsNone(tree.pinned_branch)

    def test_its_menu_says_what_a_click_does(self):
        from silux.i18n import _

        window = self.window()
        tree = window.monitor_page.tree
        sensor = self.a_sensor()
        menu = tree.pin_menu(tree._rows[sensor.key])
        self.assertEqual([a.text() for a in menu.actions()], [_("sensors.pin")])
        menu.actions()[0].trigger()
        window._on_sample(self.snapshot)
        menu = tree.pin_menu(tree.pinned_branch.child(0))
        self.assertEqual([a.text() for a in menu.actions()], [_("sensors.unpin")])
        # A branch is no sensor: it has no menu.
        self.assertIsNone(tree.pin_menu(tree.topLevelItem(1)))

    def test_a_search_keeps_the_pinned_that_match(self):
        window = self.window()
        tree = window.monitor_page.tree
        sensor = self.a_sensor()
        tree.toggle_pinned(sensor.key)
        window._on_sample(self.snapshot)
        pinned = tree.pinned_branch.child(0)
        tree.set_filter(pinned.text(0))
        self.assertFalse(pinned.isHidden())
        tree.set_filter("zzz nothing")
        self.assertTrue(pinned.isHidden())
        tree.set_filter("")
        self.assertFalse(pinned.isHidden())
        self.assertFalse(tree.pinned_branch.isHidden())


class TestRemembered(Case):
    def test_the_window_keeps_them_and_opens_with_them(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        window = self.window()
        sensor = self.a_sensor()
        window.monitor_page.tree.toggle_pinned(sensor.key)
        self.assertEqual(window.prefs.sensor_pinned, (sensor.key,))
        again = MainWindow(Preferences(sensor_pinned=(sensor.key,)).normalized())
        self.addCleanup(again.close)
        again.show()
        again._on_sample(self.snapshot)
        again.select_section("Sensores")
        geometry.settle(self.app)
        self.assertIsNotNone(again.monitor_page.tree.pinned_branch)

    def test_one_this_machine_lacks_is_kept_and_not_shown(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        again = MainWindow(Preferences(sensor_pinned=("hwmon/nothing/temp9",)).normalized())
        self.addCleanup(again.close)
        again.show()
        again._on_sample(self.snapshot)
        geometry.settle(self.app)
        self.assertIsNone(again.monitor_page.tree.pinned_branch)
        self.assertEqual(again.prefs.sensor_pinned, ("hwmon/nothing/temp9",))


if __name__ == "__main__":
    unittest.main()
