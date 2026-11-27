"""Checking for a new version comes on by default, and switches itself on
once for settings saved while it came off. Switched off by hand after that,
it stays off.

`PRUEBA14` is what the 0.4.0rc14 code saved with its defaults, generated
from its `settings.py`.
"""

import dataclasses
import json
import os
import tempfile
import unittest
from unittest import mock

from silux import settings

PRUEBA14 = {
    "interval_s": 1.0, "fluid_charts": False, "theme": "system", "temperature_unit": "c",
    "density": "normal", "font_scale": "grande", "network_unit": "bytes",
    "show_all_features": False, "check_updates": False, "update_channel": "",
    "language": "es", "sensor_columns": [], "sensor_collapsed": [], "sensor_expanded": [],
    "window_width": 900, "window_height": 680, "permission_notice_dismissed": False,
    "welcome_shown": False,
}


class TestCheckingByDefault(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": folder.name})
        patch.start()
        self.addCleanup(patch.stop)

    def _write(self, saved: dict) -> None:
        settings.config_dir().mkdir(parents=True, exist_ok=True)
        settings.config_path().write_text(json.dumps(saved), encoding="utf-8")

    def test_on_by_default(self):
        self.assertTrue(settings.Preferences().check_updates)
        self.assertTrue(settings.load().check_updates)

    def test_the_prueba14_settings_switch_it_on(self):
        self._write(PRUEBA14)
        loaded = settings.load()
        self.assertTrue(loaded.check_updates)
        # The rest as it was saved.
        self.assertEqual(loaded.font_scale, "grande")
        self.assertFalse(loaded.welcome_shown)

    def test_switched_off_after_that_it_stays_off(self):
        self._write(PRUEBA14)
        settings.save(dataclasses.replace(settings.load(), check_updates=False))
        self.assertFalse(settings.load().check_updates)
        self.assertFalse(settings.load().check_updates)

    def test_a_fresh_file_switched_off_stays_off(self):
        settings.save(dataclasses.replace(settings.Preferences(), check_updates=False))
        self.assertFalse(settings.load().check_updates)


if __name__ == "__main__":
    unittest.main()
