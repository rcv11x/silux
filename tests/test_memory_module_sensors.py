"""A memory module's temperature sensor says which module it is.

A DDR5 module's SPD hub carries a temperature sensor, and Sensors read
«Memoria · Temperatura 1» with nothing saying of which module. It is named by
its module and its address on the bus, and shows in that module's card.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import MemoryModule, SensorKind, module_numbers
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, volcados

DUMP = EQUIPOS / "i5-12450h"


def _with_permissions(snapshot):
    """Its two modules as the firmware's table lists them (its prueba8
    report), with their SPD unread as on the machine."""
    return dataclasses.replace(snapshot, modules=tuple(
        MemoryModule(locator=f"Controller{n}-ChannelA-DIMM0", populated=True, type="DDR5",
                     size_bytes=8 << 30, form_factor=0x0D, part_number="M425R1GB4BB0-CQKOL")
        for n in (0, 1)))


class TestTheMatch(unittest.TestCase):

    def test_by_its_spd_reading_or_else_in_order(self):
        from silux.spd import SpdInfo
        on_51 = MemoryModule(locator="DIMM_B1", populated=True,
                             spd=SpdInfo(address="0-0051", slot=1))
        plain = MemoryModule(locator="DIMM_A1", populated=True)
        empty = MemoryModule(locator="DIMM_A2", populated=False)
        self.assertEqual(module_numbers([plain, empty, on_51], {"0-0050", "0-0051"}),
                         {"0-0051": 2, "0-0050": 1})
        soldered = MemoryModule(locator="Controller0-ChannelA", populated=True, form_factor=0x0B)
        self.assertEqual(module_numbers([soldered], {"0-0050"}), {})


class TestOnItsPages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _memory_sensors(self, snapshot):
        return [s for s in snapshot.sensors if s.bus_address and s.kind is SensorKind.TEMPERATURE]

    def test_named_by_its_module_and_its_address(self):
        # Without permissions its module is the one its SPD's page 0 gives.
        sensor, = self._memory_sensors(foto(DUMP)[0])
        self.assertEqual(sensor.bus_address, "0-0050")
        self.assertEqual(sensor.label, _("sensor.mem.module").format(n=1, direccion="0x50"))
        self.assertNotIn("/temp1", sensor.key.split("-", 1)[0])

    def test_by_its_address_alone_without_a_module(self):
        from silux import volcado
        from silux.collector import Collector
        from tests.interval import fake_clock, next_snapshot
        with volcado.mounted(DUMP) as root, fake_clock() as clock:
            (root / "sys/bus/i2c/devices/0-0050/eeprom").unlink()
            collector = Collector()
            try:
                collector.snapshot()
                snapshot = next_snapshot(collector, clock)
            finally:
                collector.close()
        sensor, = self._memory_sensors(snapshot)
        self.assertEqual(sensor.label, _("sensor.mem.address").format(direccion="0x50"))

    def test_in_its_modules_card(self):
        snapshot = _with_permissions(foto(DUMP)[0])
        sensor, = self._memory_sensors(snapshot)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Memoria")
            page = window.stack.currentWidget()
            first, second = page._slot_grids
            shown = first._values[_("memory.field.temp")]
            # The cards sit in a row that the test window doesn't lay out:
            # what is hidden on purpose is `isHidden()`.
            self.assertFalse(shown.isHidden())
            self.assertEqual(shown.full_text(), render.temperature(sensor.value))
            self.assertTrue(second._values[_("memory.field.temp")].isHidden())

    def test_every_dump_names_each_by_its_address(self):
        for folder in volcados():
            for sensor in self._memory_sensors(foto(folder)[0]):
                with self.subTest(folder.name, sensor=sensor.key):
                    self.assertIn(render.bus_address(sensor.bus_address), sensor.label)


if __name__ == "__main__":
    unittest.main()
