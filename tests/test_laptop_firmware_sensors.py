"""A laptop maker's firmware sensors belong to the machine.

The Vostro A840 and the Latitude E6400 (Felix's prueba13 reports) showed a
device called «dell_smm» with «CPU (dell_smm)» twice; the ThinkPads one
called «thinkpad», HP's «hp», a FX's «fam15h_power». Now they hang from the
machine (or the processor), two readings of one chip with the same name
are numbered, a chip is named in plain words where two chips' readings
share a name, and a firmware interface is no «sensor chip» of the board.
"""

import unittest

from silux.model import Snapshot
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot, volcados

RAW = ("dell_smm", "thinkpad", "hp", "fam15h_power", "acpitz", "asus", "gigabyte_wmi")


class TestLaptopFirmwareSensors(unittest.TestCase):
    def test_no_device_is_a_chip_s_name(self):
        for folder in volcados():
            names = [Snapshot.device_name(c)
                     for c in shared_snapshot(folder).sensor_tree().values()]
            with self.subTest(dump=folder.name):
                self.assertFalse([n for n in names if n in RAW or n.startswith("pch_")])

    def test_in_the_vostro_each_reading_has_its_own_name(self):
        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "celeron-560")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Sensores")
            geometry.settle(app)
            tree = window.monitor_page.tree
            board = next(item for key, item in tree._rows.items()
                         if key.startswith("::board/") and "temperature" in key)
            names = [board.child(i).text(0) for i in range(board.childCount())]
        self.assertEqual(len(names), len(set(names)), names)
        self.assertEqual(sorted(n for n in names if n.startswith("CPU")), ["CPU 1", "CPU 2"])
        self.assertFalse([n for n in names if any(f"({raw})" in n for raw in RAW)])

    def test_a_firmware_interface_is_no_sensor_chip(self):
        for dump in ("celeron-560", "i5-8350u", "i7-4710hq", "ryzen5-9600x"):
            with self.subTest(dump=dump):
                self.assertIsNone(shared_snapshot(EQUIPOS / dump).platform.sensor_chip)

    def test_a_laptop_s_fan_in_words(self):
        from silux import render
        from silux.i18n import _

        snapshot = shared_snapshot(EQUIPOS / "i7-4710hq")
        fan = next(s for s in snapshot.sensors if s.label == "cpu_fan")
        self.assertEqual(render.sensor_label(fan), _("sensor.fan.cpu"))


if __name__ == "__main__":
    unittest.main()
