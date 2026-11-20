"""Names that reached a tester's laptop report raw or untranslated.

Sensors: «spd5118», «Red (iwlwifi_1)», «Alimentación · ucsi-source-psy-
USBC000:001» next to a «Puerto USB-C» that was the same port, and an NVMe
sensor called «Composite». Elsewhere: a chassis «Notebook», QEMU's CPU as
«QEMU Virtual version 2.5+», «Cargando (Super I/O) tendrías…» and «1
paquetes perdidos».
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.i18n import _
from silux.providers import hwmon


class TestSensorDevices(unittest.TestCase):

    def test_the_memory_temperature_hangs_from_the_memory(self):
        dispositivo, clase = hwmon.device_for("spd5118", pathlib.Path("/nada"), "CPU", "Placa")
        self.assertEqual(dispositivo, _("sensor.mem"))

    def test_a_wifi_card_without_its_interface_is_not_its_chip(self):
        dispositivo, _clase = hwmon.device_for("iwlwifi_1", pathlib.Path("/nada"), "CPU", "Placa")
        self.assertNotIn("iwlwifi", dispositivo)

    def test_an_nvme_composite_is_said_in_the_language(self):
        self.assertEqual(hwmon._friendly("nvme", "temp", "1", "Composite"),
                         _("sensor.nvme.composite"))

    def test_a_usb_c_port_is_one_device(self):
        with tempfile.TemporaryDirectory() as raiz:
            carpeta = pathlib.Path(raiz) / "ucsi-source-psy-USBC000:001"
            carpeta.mkdir()
            (carpeta / "voltage_now").write_text("0\n")
            with mock.patch.object(hwmon, "POWER_SUPPLY", pathlib.Path(raiz)):
                # hwmon writes underscores where power_supply has dashes.
                self.assertTrue(hwmon._tambien_en_power_supply("ucsi_source_psy_USBC000:001"))
                sensores = list(hwmon.HwmonSensors._read_power_supplies())
        self.assertEqual({s.device for s in sensores}, {_("sensor.dev.usbc")})


class TestTexts(unittest.TestCase):

    def test_a_notebook_is_a_laptop(self):
        self.assertNotEqual(_("chassis.notebook"), "Notebook")

    def test_qemus_cpu_keeps_its_name(self):
        self.assertEqual(render.cpu_short_name("QEMU Virtual CPU version 2.5+"),
                         "QEMU Virtual CPU version 2.5+")
        self.assertEqual(render.cpu_short_name("AMD Ryzen 7 5800X3D 8-Core Processor"),
                         "AMD Ryzen 7 5800X3D")

    def test_one_lost_packet(self):
        self.assertEqual(render.lost_packets(1), _("net.lost.one"))
        self.assertIn("2", render.lost_packets(2))


class TestTheSuperIoHint(unittest.TestCase):

    def test_a_laptop_is_not_sent_to_look_for_one(self):
        # Its fans are the embedded controller's: sensors-detect finds nothing.
        portatil = list(hwmon.HwmonSensors()._missing_drivers([], portatil=True))
        sobremesa = list(hwmon.HwmonSensors()._missing_drivers([], portatil=False))
        self.assertNotIn(hwmon.SUPERIO, [h.module for h in portatil])
        self.assertIn(hwmon.SUPERIO, [h.module for h in sobremesa])

    def test_it_is_not_called_a_module(self):
        self.assertNotIn("(Super I/O)", _("sensors.driver.body.superio"))


if __name__ == "__main__":
    unittest.main()
