"""DDR2 modules read from their SPD chip.

A real Samsung M470T2953EZ3-CE6 (1 GB, 2Rx8, PC2-5300S-555) in a laptop
whose firmware declares DDR for its DDR2 modules.
"""

import unittest

from silux import render, spd
from silux.i18n import _
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

CHIP = EQUIPOS / "celeron-560/sys/devices/pci0000:00/0000:00:1f.3/i2c-0/0-0050/eeprom"


class TestDecoding(unittest.TestCase):

    def test_the_module(self):
        info = spd.decode(CHIP.read_bytes(), "0-0050")
        self.assertEqual((info.dram_type, info.module_type, info.capacity_bytes, info.ranks,
                          info.device_width, info.manufacturer, info.manufactured_year,
                          info.manufactured_week),
                         ("DDR2", "SODIMM", 1024**3, 2, 8, "Samsung", 2008, 14))
        self.assertEqual((info.jedec.speed_mts, info.jedec.summary, info.jedec.voltage_v),
                         (667, "5-5-5-15", 1.8))

    def test_cycle_times_in_quarters_and_thirds(self):
        self.assertEqual([round(spd._ddr2_cycle_ns(b), 2) for b in (0x30, 0x3D, 0x25, 0x50, 0x3C)],
                         [3.0, 3.75, 2.5, 5.0, 3.67])


class TestOnTheMemoryPage(unittest.TestCase):

    def test_named_ddr2_with_no_dash(self):
        from tests import pantalla, qt

        qt.app()
        snapshot = shared_snapshot(EQUIPOS / "celeron-560")
        self.assertEqual(snapshot.spd[0].dram_type, "DDR2")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Memoria")
            text = " ".join(pantalla.textos_de(window.stack.currentWidget()))
        self.assertIn("M4 70T2953EZ3-CE6", text)
        self.assertIn(_("memory.na.ddr2.chips"), text)
        self.assertNotIn(_("prov.spd.unsupported").format(tipos="DDR2"), text)

    def test_the_chip_wins_over_a_firmware_saying_ddr(self):
        import dataclasses

        from silux.providers.base import Draft
        from silux.providers.spd_modules import SpdModules
        from tests.test_nada_en_bruto import _con_permisos
        from tests.test_smbios import _end, _memory_array, _memory_device

        snapshot = shared_snapshot(EQUIPOS / "celeron-560")
        # 0x12 is DDR: what this laptop's BIOS writes for its DDR2.
        table = (_memory_array() + _memory_device(memory_type=0x12, configured_mts=667,
                                                  part="M4 70T2953EZ3-CE6") + _end())
        snapshot = _con_permisos(snapshot, table)
        draft = Draft()
        draft.modules = list(snapshot.modules)
        SpdModules._merge(draft, list(snapshot.spd))
        module = next(m for m in draft.modules if m.populated)
        self.assertEqual((module.type, render.module_type(module)), ("DDR2", "DDR2"))


class TestOneClockForAll(unittest.TestCase):
    """Firmware that writes each module's own speed as the one in use."""

    def test_the_set_runs_at_the_slowest(self):
        from silux.model import MemoryModule

        modules = [MemoryModule(populated=True, type="DDR2", speed_mts=mts, configured_mts=mts)
                   for mts in (667, 800)]
        self.assertEqual(render.memory_speed_warning(modules, None, chipset=True),
                         _("mem.mixed").format(actual=667, lento=667, rapido=800))


if __name__ == "__main__":
    unittest.main()
