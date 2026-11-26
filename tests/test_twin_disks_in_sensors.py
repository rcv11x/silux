"""Two disks of the same model are two devices in Sensors.

A desktop with two identical NVMe drives showed them as one, with «Del
disco» twice: the tree grouped disks by their model. And as two labels
clashed under it, every row got the hwmon chip's name, «(nvme)».
"""

import unittest

from silux.model import DeviceKind, SensorKind
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

MODEL = "KINGSTON SNV3S500G"


class TestTwinDisks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = shared_snapshot(EQUIPOS / "ryzen5-9600x")

    def disk_sensors(self):
        return [s for s in self.snapshot.sensors if s.device_kind == DeviceKind.DISK]

    def test_the_dump_has_two_of_one_model(self):
        self.assertEqual([d.model for d in self.snapshot.disks].count(MODEL), 2)

    def test_each_is_its_own_device_named_after_its_drive(self):
        groups = {s.group: s.device for s in self.disk_sensors() if MODEL in s.device}
        self.assertEqual(sorted(groups.values()),
                         [f"{MODEL} (nvme0n1)", f"{MODEL} (nvme1n1)"])
        for group in groups:
            labels = [s.label for s in self.disk_sensors()
                      if s.group == group and s.kind is SensorKind.TEMPERATURE]
            self.assertEqual(len(labels), len(set(labels)), labels)

    def test_disks_of_different_models_keep_their_plain_names(self):
        snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        devices = {s.device for s in snapshot.sensors if s.device_kind == DeviceKind.DISK}
        self.assertEqual(devices, {"Samsung SSD 970 EVO Plus 2TB", "WD_BLACK SN850X HS 1000GB"})

    def test_sensors_shows_two_without_the_chip(self):
        qt.app()
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("Sensores")
            texts = "\n".join(pantalla.textos_de(window.monitor_page))
        self.assertIn(f"{MODEL} (nvme0n1)", texts)
        self.assertIn(f"{MODEL} (nvme1n1)", texts)
        self.assertNotIn("(nvme)", texts)
