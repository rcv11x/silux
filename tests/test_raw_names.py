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
        dispositivo, clase, clave = hwmon.device_for("spd5118", pathlib.Path("/nada"), "CPU", "Placa")
        self.assertEqual(dispositivo, _("sensor.mem"))
        self.assertEqual(clave, "memory")

    def test_a_wifi_card_without_its_interface_is_not_its_chip(self):
        dispositivo, _clase, clave = hwmon.device_for("iwlwifi_1", pathlib.Path("/nada"),
                                                      "CPU", "Placa")
        self.assertNotIn("iwlwifi", dispositivo)
        self.assertEqual(clave, "net-chip:wifi")

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
                self.assertTrue(hwmon._also_in_power_supply("ucsi_source_psy_USBC000:001"))
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
        portatil = list(hwmon.HwmonSensors()._missing_drivers([], laptop=True))
        sobremesa = list(hwmon.HwmonSensors()._missing_drivers([], laptop=False))
        self.assertNotIn(hwmon.SUPERIO, [h.module for h in portatil])
        self.assertIn(hwmon.SUPERIO, [h.module for h in sobremesa])

    def test_it_is_not_called_a_module(self):
        self.assertNotIn("(Super I/O)", _("sensors.driver.body.superio"))



class TestTheOrderOfAChipsChannels(unittest.TestCase):
    """A tester's i5-12450H: coretemp's Package is temp1 and its cores go up
    to temp25, and as text «temp10» sorts before «temp1»: «Núcleo 8, 12,
    Paquete, 20, 21, 22, 23, 0, 4»."""

    def test_by_number_not_as_text(self):
        with tempfile.TemporaryDirectory() as raiz:
            chip = pathlib.Path(raiz) / "hwmon3"
            chip.mkdir()
            (chip / "name").write_text("coretemp\n")
            for n, etiqueta in ((1, "Package id 0"), (2, "Core 0"), (6, "Core 4"),
                                (10, "Core 8"), (14, "Core 12"), (22, "Core 20")):
                (chip / f"temp{n}_input").write_text("50000\n")
                (chip / f"temp{n}_label").write_text(etiqueta + "\n")
            with mock.patch.object(hwmon.sysroot, "ruta", lambda p: pathlib.Path(raiz)
                                   if str(p).endswith("hwmon") else pathlib.Path(p)):
                sensores = list(hwmon.HwmonSensors()._read_hwmon("CPU", "Placa", {}))
        etiquetas = [s.label for s in sorted(sensores, key=lambda s: s.order)]
        self.assertEqual(etiquetas, ["Package id 0", "Core 0", "Core 4", "Core 8",
                                     "Core 12", "Core 20"])


if __name__ == "__main__":
    unittest.main()
