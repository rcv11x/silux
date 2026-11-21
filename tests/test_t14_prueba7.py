"""What a laptop's prueba7 report left: each fix for a case, not a machine.

Its L2 read «4 × 1.2 MB» for 5 MB; its wireless card «2 506 packets lost»
that the kernel had just discarded; «Chipset: —» over «500 Series Chipset
Family On-Package eSPI Controller»; «N34ET64W (1.64 )»; two modules on two
controllers, both «Channel A»; a voltage the SPD confirms still «per the
BIOS»; and soldered memory whose card said «SODIMM».
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import Board, NetworkTraffic, clean_dmi
from silux.providers.dmi import chipset
from tests.test_equipos import EQUIPOS, foto


class TestCacheSizes(unittest.TestCase):

    def test_exact_enough_to_add_up(self):
        for bytes_, texto in ((1280 * 1024, "1.25 MB"), (48 * 1024, "48 KB"),
                              (1536 * 1024, "1.5 MB"), (12 * 1024**2, "12 MB"),
                              (5 * 1024**2, "5 MB")):
            with self.subTest(texto=texto):
                self.assertEqual(render.cache_size(bytes_), texto)

    def test_on_a_dump(self):
        l2 = [c for t in foto(EQUIPOS / "i5-1135g7")[0].cpu.types for c in t.caches if c.level == 2][0]
        self.assertIn("4 × 1.25 MB", render.cache_summary(l2))


class TestDroppedIsNotLost(unittest.TestCase):

    def test_dropped_and_errors_apart(self):
        t = NetworkTraffic(rx_dropped=2500, tx_dropped=6, rx_errors=3)
        self.assertEqual(render.packet_problems(t), _("net.lost").format(n=render.thousands(2506))
                         + " · " + _("net.errors").format(n="3"))
        self.assertEqual(render.packet_problems(NetworkTraffic()), _("net.nolost"))


class TestTheBoard(unittest.TestCase):

    def test_padding_spaces_go(self):
        self.assertEqual(clean_dmi("N34ET64W (1.64 )"), "N34ET64W (1.64)")
        self.assertEqual(clean_dmi("  F40   "), "F40")

    def test_a_chipset_in_the_package(self):
        nombre = "500 Series Chipset Family On-Package eSPI Controller"
        self.assertEqual(chipset(("Intel Corporation", nombre), None), "Intel 500 Series")
        board = Board(chipset="Intel 500 Series", chipset_full=nombre, chipset_on_package=True)
        self.assertEqual(render.board_chipset(board),
                         "Intel 500 Series · " + _("board.chipset.onpackage"))
        self.assertEqual(chipset(("Intel Corporation", "H510 Chipset eSPI Controller"), None),
                         "Intel H510")


class TestTheMemoryOfALaptop(unittest.TestCase):
    """Its firmware's places, as the code documents them: one module per
    controller, both on their controller's channel A."""

    def test_two_controllers_are_two_channels_by_name(self):
        nombres = render.slot_names([("Controller0-ChannelA", "BANK 0"),
                                     ("Controller1-ChannelA-DIMM0", "BANK 0")])
        self.assertEqual(len(set(nombres)), 2)
        self.assertTrue(all(_("memory.slot.controller").split("{")[0] in n for n in nombres), nombres)
        # One controller, two DIMMs: the DIMM number tells them apart.
        self.assertEqual(render.slot_names([("ChannelA-DIMM0", None), ("ChannelA-DIMM1", None)]),
                         [_("memory.slot.channel").format(c="A") + " · " + _("memory.slot.dimm").format(n=0),
                          _("memory.slot.channel").format(c="A") + " · " + _("memory.slot.dimm").format(n=1)])

    def test_a_voltage_the_spd_confirms(self):
        from silux.model import MemoryModule
        spd = foto(EQUIPOS / "i5-1135g7")[0].spd[0]
        modulo = MemoryModule(voltage_configured_mv=round(spd.jedec.voltage_v * 1000), spd=spd)
        self.assertFalse(modulo.voltage_from_firmware)
        self.assertTrue(dataclasses.replace(modulo, spd=None).voltage_from_firmware)

    def test_soldered_memory_says_so(self):
        from silux.model import MemoryModule
        soldada = MemoryModule(locator="Controller0-ChannelA", form_factor=0x0D, populated=True)
        self.assertEqual(soldada.soldered_by, "place")
        self.assertIsNone(MemoryModule(locator="Controller1-ChannelA-DIMM0", form_factor=0x0D,
                                       populated=True).soldered_by)
        # Read from its own SPD, with no place from the firmware: not soldered.
        spd = foto(EQUIPOS / "i5-1135g7")[0].spd[0]
        self.assertIsNone(MemoryModule(spd=spd, populated=True).soldered_by)


class TestOnTheMemoryPage(unittest.TestCase):
    """A soldered module on controller 0 and a SODIMM with its SPD on
    controller 1, as such a laptop's firmware lays them out."""

    def _page_text(self):
        from silux.providers.base import Draft
        from silux.providers.spd_modules import SpdModules
        from tests import pantalla, qt
        from tests.test_nada_en_bruto import _con_permisos
        from tests.test_smbios import _end, _memory_array, _memory_device

        f = foto(EQUIPOS / "i5-1135g7")[0]
        sodimm = f.spd[0]
        tabla = (_memory_array()
                 + _memory_device(configured_mts=3200, locator="Controller0-ChannelA",
                                  bank="BANK 0", part="M471A1G44AB0-CWE")
                 + _memory_device(configured_mts=3200, locator="Controller1-ChannelA-DIMM0",
                                  bank="BANK 0", part=sodimm.part_number or "")
                 + _end())
        f = _con_permisos(f, tabla)
        borrador = Draft()
        borrador.modules = list(f.modules)
        SpdModules._merge(borrador, list(f.spd))
        f = dataclasses.replace(f, modules=tuple(borrador.modules))
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Memoria")
            pagina = ventana.stack.currentWidget()
            fichas = {g._values[_("memory.field.part")].full_text(): g for g in pagina._slot_grids}
            soldada = fichas["M471A1G44AB0-CWE"]
            del fichas["M471A1G44AB0-CWE"]
            zocalo = next(iter(fichas.values()))
            return (soldada._values[_("memory.field.form")].full_text(),
                    soldada._values[_("memory.field.form")].toolTip(),
                    [g._values[_("memory.field.slot")].full_text() for g in pagina._slot_grids],
                    zocalo._values[_("memory.field.voltage")].full_text())

    def test_each_on_its_controllers_channel_soldered_and_confirmed(self):
        formato, motivo, zocalos, voltaje = self._page_text()
        self.assertEqual(formato, _("memory.form.soldered"))
        self.assertIn(_("memory.tip.soldered.nospd"), motivo)
        self.assertEqual(len(set(zocalos)), 2)
        self.assertTrue(all(_("memory.slot.controller").split("{")[0] in z for z in zocalos), zocalos)
        self.assertNotIn(_("memory.source.bios"), voltaje)


class TestTheBaseClock(unittest.TestCase):
    """The specification's base (CPUID 0x16) and the one the configured TDP
    gives (intel_pstate's base_frequency): «Base 900 MHz × 9.0» under a
    brand string saying «@ 2.40GHz» read as a contradiction."""

    def test_both_said_on_the_cpu_page(self):
        from silux.ui.pages.cpu import TypeSection
        from tests import pantalla, qt
        f = foto(EQUIPOS / "i5-1135g7")[0]
        relojes = f.cpu.types[0].clocks
        self.assertEqual((relojes.base_hz, relojes.base_configured_hz), (2_400_000_000, 900_000_000))
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("CPU")
            seccion = ventana.stack.currentWidget().findChildren(TypeSection)[0]
            base = seccion.clocks._values[_("cpu.clock.base")].full_text()
        self.assertTrue(base.startswith(render.hz(2_400_000_000)), base)
        self.assertIn(_("cpu.base.tdp").format(f=render.hz(900_000_000)), base)

    def test_a_single_base_says_one(self):
        from silux.model import Clocks
        self.assertEqual(render.base_clock(Clocks(base_hz=3_400_000_000, base_configured_hz=3_400_000_000,
                                                  bus_hz=100_000_000)),
                         render.clock_and_multiplier(3_400_000_000, 34.0))


class TestTwoCopiesOfTheLimits(unittest.TestCase):
    """PL1 and PL2 of 64 W on a 28 W processor: the MSR copy. The memory
    controller keeps another (intel-rapl-mmio), and the lower is enforced."""

    def _snapshot(self, mmio_long_uw):
        from silux import sysroot, volcado
        from silux.collector import Collector
        from tests.interval import second_snapshot
        with volcado.montado(EQUIPOS / "i5-1135g7") as raiz:
            zona = raiz / "sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0"
            zona.mkdir(parents=True)
            for nombre, valor in (("name", "package-0"),
                                  ("constraint_0_name", "long_term"),
                                  ("constraint_0_power_limit_uw", str(mmio_long_uw)),
                                  ("constraint_0_time_window_us", "27983872"),
                                  ("constraint_1_name", "short_term"),
                                  ("constraint_1_power_limit_uw", "64000000"),
                                  ("constraint_1_time_window_us", "2440")):
                (zona / nombre).write_text(valor + "\n")
            enlace = raiz / "sys/class/powercap/intel-rapl-mmio:0"
            if not enlace.exists():
                import os
                os.symlink("../../devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0", enlace)
            sysroot.olvidar()
            recolector = Collector()
            try:
                return second_snapshot(recolector)
            finally:
                recolector.close()

    def test_the_lower_is_shown_and_the_other_named(self):
        potencia = self._snapshot(28_000_000).cpu.power
        self.assertEqual((potencia.limit_long_w, potencia.limit_long_other_w), (28.0, 64.0))
        # PL2 is the same in both: nothing else to say.
        self.assertEqual((potencia.limit_short_w, potencia.limit_short_other_w), (64.0, None))

    def test_on_the_cpu_page(self):
        from tests import pantalla, qt
        f = self._snapshot(28_000_000)
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("CPU")
            texto = "\n".join(pantalla.textos_de(ventana.stack.currentWidget()))
        self.assertIn(_("cpu.limit.lowest").format(otro=render.watts(64.0)), texto)

    def test_without_the_mmio_copy_nothing_changes(self):
        from silux.providers.rapl import effective_limits
        msr = {"limit_long_w": 64.0, "window_long_s": 28.0}
        self.assertEqual(effective_limits(msr, {}), msr)


if __name__ == "__main__":
    unittest.main()
