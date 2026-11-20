"""A laptop's NVIDIA has no fan of its own to show.

widecoocaa23's LOQ read «Ventilador: —» on its RTX 4050: the fans are the
laptop's, run by its embedded controller, and NVML gives none. Here the
i5-10400's dump as a laptop (chassis type 10, Notebook) with that card as
the kernel and NVML show it: its PCI device with the `nvidia` driver and
its DRM node, card2.
"""

import json
import pathlib
import unittest

from silux import volcado
from silux.collector import Collector
from silux.i18n import _
from tests import pantalla, qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"
RTX_4050 = {"index": 0, "pci_slot": "0000:02:00.0", "uuid": None, "serial": None,
            "name": "NVIDIA GeForce RTX 4050 Laptop GPU", "driver_version": "550.163.01",
            "cuda_cores": 2560, "memory_total_bytes": 6 << 30, "memory_bus_bits": 96,
            "temp_c": 32.0, "power_w": 1.4, "fan_percent": None,
            # Its report: «Estado: sin límites», so NVML gave the reasons.
            "throttled": False, "throttle_reasons": []}


TARJETA = "devices/pci0000:00/0000:00:01.0/0000:02:00.0"


def _the_card(root: pathlib.Path) -> None:
    card = root / "sys" / TARJETA
    for name, value in (("vendor", "0x10de"), ("device", "0x28e1"), ("class", "0x030000"),
                        ("subsystem_vendor", "0x17aa"), ("revision", "0xa1"),
                        ("boot_vga", "0"), ("power/runtime_status", "active"),
                        ("power_state", "D0")):
        (card / name).parent.mkdir(parents=True, exist_ok=True)
        (card / name).write_text(value + "\n")
    (root / "sys/bus/pci/drivers/nvidia").mkdir(parents=True, exist_ok=True)
    (card / "driver").symlink_to("../../../../bus/pci/drivers/nvidia")
    (card / "drm/card2").mkdir(parents=True)
    (card / "drm/card2/device").symlink_to("../../../0000:02:00.0")
    (root / "sys/class/drm/card2").symlink_to(f"../../{TARJETA}/drm/card2")
    (root / "sys/bus/pci/devices/0000:02:00.0").symlink_to(f"../../../{TARJETA}")


def _photo(chassis: str):
    with volcado.montado(EQUIPOS / "i5-10400") as root:
        (root / "sys/class/dmi/id/chassis_type").write_text(chassis + "\n")
        _the_card(root)
        grabado = json.loads((root / "grabado.json").read_text())
        grabado["nvml"] = {"abierta": True, "tarjetas": [RTX_4050]}
        (root / "grabado.json").write_text(json.dumps(grabado))
        collector = Collector()
        try:
            collector.snapshot()
            return collector.snapshot()
        finally:
            collector.close()


class TestALaptopsNvidiaFan(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _nvidia(self, photo):
        return next(g for g in photo.gpus if g.vendor == "NVIDIA")

    def test_in_a_laptop_it_is_the_machines(self):
        photo = _photo("10")
        self.assertTrue(self._nvidia(photo).fan_of_the_machine)
        from silux.ui.pages.graphics import no_aplica
        ocultos, pies = no_aplica(self._nvidia(photo))
        self.assertIn("gpu.sensor.fan", ocultos["sensors"])
        self.assertIn(_("gpu.na.laptop.fan"), pies["sensors"])

    def test_in_a_desktop_a_card_without_it_is_not(self):
        # A desktop GeForce does publish its fan: its absence is not this.
        self.assertFalse(self._nvidia(_photo("3")).fan_of_the_machine)


if __name__ == "__main__":
    unittest.main()
