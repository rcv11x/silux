"""DDR3 modules read from their SPD chip (JEDEC 21-C, annex K).

Two real modules of one machine: 4 GB at 1333 with no maker declared, and
an 8 GB Kingston at 1600, fitted together.
"""

import dataclasses
import pathlib
import unittest

from silux import render, spd
from silux.i18n import _
from tests.test_equipos import EQUIPOS, foto

BUS = EQUIPOS / "i5-3330/sys/devices/pci0000:00/0000:00:1f.3/i2c-8"


def _chip(name: str) -> bytes:
    return (BUS / name / "eeprom").read_bytes()


def _with_voltage(data: bytes, byte6: int) -> bytes:
    """The same module declaring other voltages (byte 6)."""
    return data[:6] + bytes((byte6,)) + data[7:]


class TestDecoding(unittest.TestCase):

    def test_both_modules(self):
        small, large = spd.decode(_chip("8-0050"), "8-0050"), spd.decode(_chip("8-0052"), "8-0052")
        self.assertEqual((small.dram_type, small.module_type, small.capacity_bytes, small.ranks,
                          small.device_width, small.jedec.speed_mts, small.jedec.summary,
                          small.jedec.voltage_v, small.manufacturer),
                         ("DDR3", "UDIMM", 4 * 1024**3, 1, 8, 1333, "9-9-9-24", 1.5, None))
        self.assertEqual((large.capacity_bytes, large.ranks, large.jedec.speed_mts,
                          large.jedec.summary, large.manufacturer,
                          large.manufactured_year, large.manufactured_week),
                         (8 * 1024**3, 2, 1600, "11-11-11-28", "Kingston", 2024, 25))

    def test_ddr3l(self):
        both = spd.decode(_with_voltage(_chip("8-0052"), 0x02))
        only_low = spd.decode(_with_voltage(_chip("8-0052"), 0x03))
        self.assertEqual((both.voltages_v, both.jedec.voltage_v), ((1.5, 1.35), 1.5))
        self.assertEqual((only_low.voltages_v, only_low.jedec.voltage_v), ((1.35,), 1.35))


class TestOnTheMemoryPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tests import pantalla, qt
        qt.app()
        cls.snapshot = foto(EQUIPOS / "i5-3330")[0]
        with pantalla.Ventana(cls.snapshot) as window:
            window.select_section("Memoria")
            cls.text = "\n".join(pantalla.textos_de(window.stack.currentWidget()))

    def test_capacity_speeds_and_the_slowest(self):
        self.assertIn("12 GiB", self.text)
        self.assertIn(_("memory.spd.rated.many").format(mts="1333 " + _("list.and") + " 1600"), self.text)
        self.assertIn(_("mem.mixed.rated").format(lento=1333, rapido=1600), self.text)

    def test_what_a_module_does_not_declare_is_said_not_dashed(self):
        self.assertIn(_("memory.na.undeclared").format(n=1, fields=render.enumeration(
            [_("memory.na.vendor"), _("memory.na.chips"), _("memory.na.part"), _("memory.na.made")],
            "list.nor")), self.text)
        self.assertNotIn(_("prov.spd.unsupported"), self.text)

    def test_ddr3l_is_named_and_its_two_voltages_said(self):
        from silux.model import MemoryModule
        module = MemoryModule(populated=True, type="DDR3",
                              spd=spd.decode(_with_voltage(_chip("8-0052"), 0x02)))
        self.assertEqual(render.module_type(module), "DDR3L")
        self.assertEqual(render.memory_voltage(module), "1.35 V " + _("list.or") + " 1.50 V")
        # With the firmware's table, the voltage in use.
        configured = dataclasses.replace(module, voltage_configured_mv=1350)
        self.assertEqual(render.memory_voltage(configured), "1.35 V")
        # The timings table says both for the profile valid at both.
        self.assertEqual(render.timing_voltage(module.spd.jedec, module.spd), "1.35 / 1.50 V")

    def test_a_real_ddr3l_on_the_page(self):
        from tests import pantalla
        snapshot = foto(EQUIPOS / "i5-5200u")[0]
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Memoria")
            page = window.stack.currentWidget()
            text = " ".join(pantalla.textos_de(page))
        self.assertIn("DDR3L", text)
        self.assertIn("1.35 / 1.50 V", text)
        self.assertIn("1.35 V " + _("list.or") + " 1.50 V", text)


if __name__ == "__main__":
    unittest.main()
