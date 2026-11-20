"""A laptop's USB-C ports in Sensores.

A ThinkPad's two ports read «Tensión (ucsi-source-psy-USBC000:001) ·
0.000 V», twice, with nothing plugged in: both were «Puerto USB-C», and the
tree told their readings apart by the kernel's name.
"""

import pathlib
import shutil
import unittest

from silux import volcado
from silux.collector import Collector

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


class TestUsbCPorts(unittest.TestCase):
    """Two ports, as a ThinkPad has them: one with a charger, one with none."""

    PORTS = {"ucsi-source-psy-USBC000:001": ("0", "0", "0"),
             "ucsi-source-psy-USBC000:002": ("1", "20000000", "2250000")}

    def _sensors(self, ports):
        with volcado.montado(EQUIPOS / "5800x3d") as root:
            supplies = root / "sys/class/power_supply"
            if supplies.exists():
                shutil.rmtree(supplies)
            for name, (online, volts, amps) in ports.items():
                port = root / "sys/devices/platform/USBC000:00/power_supply" / name
                port.mkdir(parents=True)
                for field, value in (("online", online), ("voltage_now", volts),
                                     ("current_now", amps), ("type", "USB")):
                    (port / field).write_text(value + "\n")
                supplies.mkdir(parents=True, exist_ok=True)
                (supplies / name).symlink_to(f"../../devices/platform/USBC000:00/power_supply/{name}")
            collector = Collector()
            try:
                collector.snapshot()
                photo = collector.snapshot()
            finally:
                collector.close()
        return [s for s in photo.sensors if s.key.startswith("power_supply/")]

    def test_the_one_with_nothing_plugged_says_nothing_and_they_are_numbered(self):
        from silux.i18n import _
        sensors = self._sensors(self.PORTS)
        self.assertEqual({s.device for s in sensors}, {_("sensor.dev.usbc") + " 2"})
        self.assertEqual(sorted(s.value for s in sensors), [2.25, 20.0])

    def test_a_single_port_has_no_number(self):
        from silux.i18n import _
        name = "ucsi-source-psy-USBC000:002"
        sensors = self._sensors({name: self.PORTS[name]})
        self.assertEqual({s.device for s in sensors}, {_("sensor.dev.usbc")})


if __name__ == "__main__":
    unittest.main()
