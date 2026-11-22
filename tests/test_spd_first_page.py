"""A DDR5 SPD whose pages past the first can't be read.

The machine blocked SPD writes, and the driver needs one to switch pages:
page 0 read, pages 1 to 7 gave ENXIO. Page 0 holds the type, the speed and
the JEDEC timings; its CRC is elsewhere, so it is checked by hand, and the
rest is said to be blocked rather than unreadable.
"""

import errno
import pathlib
import unittest
from unittest import mock

from silux import spd, sysroot, volcado
from silux.i18n import _
from silux.model import Need
from tests.test_equipos import EQUIPOS
from tests.test_spd import construir_ddr5

CHIP = "sys/devices/pci0000:00/0000:00:1f.4/i2c-0/0-0050"


class TestPageZeroAlone(unittest.TestCase):

    def test_what_it_gives_and_what_it_leaves_unknown(self):
        info = spd.first_page(construir_ddr5()[:128], "0-0050", 0)
        self.assertTrue(info.partial)
        self.assertEqual((info.dram_type, info.jedec.speed_mts), ("DDR5", 5600))
        self.assertEqual((info.ranks, info.capacity_bytes, info.bus_width,
                          info.manufacturer, info.part_number, info.manufactured_year),
                         (None,) * 6)

    def test_nothing_that_fails_the_checks(self):
        pagina = bytearray(construir_ddr5()[:128])
        for byte, valor, motivo in ((2, 0x0C, "not DDR5"), (20, 0xFF, "a cycle too long"),
                                    (3, 0x0F, "an unknown module type"), (24, None, "no CL")):
            with self.subTest(motivo=motivo):
                roto = bytearray(pagina)
                if valor is None:
                    roto[24] = roto[25] = 0                 # tAA, both bytes
                else:
                    roto[byte] = valor
                if byte == 20:
                    roto[21] = 0x03                       # 1023 ps: below 3200 MT/s
                self.assertIsNone(spd.first_page(bytes(roto), "0-0050", 0))

    def test_a_whole_chip_is_not_partial(self):
        self.assertFalse(spd.decode(construir_ddr5(), "0-0050", 0).partial)


class TestTheKernelsAnswer(unittest.TestCase):
    """The emulation is the kernel's: the prueba7 fix read page 0 with a
    buffered 128-byte read, which asks for a block and failed whole."""

    def test_only_a_read_of_page_zero_alone_works(self):
        from tests.blocked_eeprom import blocked_past_page_zero
        whole = construir_ddr5()
        with blocked_past_page_zero("0-0050/eeprom", whole):
            with self.assertRaises(OSError) as caught:
                pathlib.Path("/x/0-0050/eeprom").read_bytes()
            self.assertEqual(caught.exception.errno, errno.ENXIO)
            with self.assertRaises(OSError), open("/x/0-0050/eeprom", "rb") as eeprom:
                eeprom.read(128)
            pages, error = spd.read_pages("/x/0-0050/eeprom")
        self.assertEqual(pages, [whole[:128]] + [None] * 7)
        self.assertEqual(error.errno, errno.ENXIO)

    def test_a_chip_that_reads_whole(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp, "eeprom")
            path.write_bytes(bytes(range(256)) * 2)            # a DDR4's 512
            pages, error = spd.read_pages(path)
        self.assertIsNone(error)
        self.assertEqual(b"".join(pages), bytes(range(256)) * 2)


class TestOnAMachineThatBlocksTheSwitch(unittest.TestCase):

    def _snapshot(self):
        from silux.collector import Collector
        from tests.interval import second_snapshot
        from tests.test_nada_en_bruto import _con_permisos
        from tests.test_smbios import _end, _memory_array, _memory_device

        from tests.blocked_eeprom import blocked_past_page_zero

        with volcado.mounted(EQUIPOS / "i5-12450h") as raiz:
            (raiz / CHIP / "eeprom").write_bytes(construir_ddr5())
            sysroot.forget()
            with blocked_past_page_zero("0-0050/eeprom", construir_ddr5()):
                recolector = Collector()
                try:
                    f = second_snapshot(recolector)
                finally:
                    recolector.close()
        f = _con_permisos(f, _memory_array()
                          + _memory_device(configured_mts=4800, memory_type=0x22) + _end())
        # With the permissions, the provider attaches each SPD reading to its
        # module; here the firmware's table comes after the collection.
        import dataclasses
        from silux.providers.base import Draft
        from silux.providers.spd_modules import SpdModules
        borrador = Draft()
        borrador.modules = list(f.modules)
        SpdModules._merge(borrador, list(f.spd))
        return dataclasses.replace(f, modules=tuple(borrador.modules))

    def test_page_zero_is_used_and_the_rest_is_said_blocked(self):
        f = self._snapshot()
        self.assertEqual([(s.partial, s.jedec.speed_mts) for s in f.spd], [(True, 5600)])
        notas = [n for n in f.notes if n.path == "spd"]
        self.assertEqual([(n.key, n.need) for n in notas], [("prov.spd.partial", Need.HARDWARE)])
        self.assertIn("ENXIO", notas[0].detail)

    def test_on_the_memory_page(self):
        from tests import pantalla, qt
        f = self._snapshot()
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Memoria")
            pagina = ventana.stack.currentWidget()
            ficha = pagina._slot_grids[0]
            for clave in ("memory.field.chips", "memory.field.profiles", "memory.field.made"):
                with self.subTest(campo=clave):
                    self.assertFalse(ficha._values[_(clave)].isVisibleTo(pagina))
            self.assertEqual(ficha._values[_("memory.field.rated")].full_text(), "5600 MT/s")
            pie = pagina.spd_missing.text()
            # Its fast profiles are unknown, not absent.
            self.assertEqual(pagina.spd_note.toolTip(), _("memory.spd.note.partial"))
        self.assertIn(_("memory.na.spd.partial").split("{campos}")[1][:40], pie)


if __name__ == "__main__":
    unittest.main()
