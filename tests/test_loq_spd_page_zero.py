"""The LOQ's DDR5: page 0 of its SPD, read on the machine, and the rest blocked.

Its owner read page 0 with `dd bs=128 count=1`; pages 1 to 7 gave ENXIO, as
the machine blocks the page switch. The dump holds that page and answers the
other seven with their error. Read by hand: DDR5, SODIMM, 16 Gb chips x16,
tCK 416 ps (DDR5-4800), tAA, tRCD and tRP 16 ns, tRAS 32 ns, tRC 48 ns. In
clocks, with JEDEC's rounding and the CAS latencies the chip lists: CL40,
39, 39, 77, 116. The maker and the part are the firmware's.
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.model import MemoryModule
from silux.providers.base import Draft
from silux.providers.spd_modules import SpdModules
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

DUMP = EQUIPOS / "i5-12450h"


def _with_permissions(snapshot):
    """Its two SODIMM as its firmware's table lists them (its prueba8
    report), each SPD reading attached as the provider does."""
    modules = [MemoryModule(locator=f"Controller{n}-ChannelA-DIMM0", bank="BANK 0",
                            populated=True, size_bytes=8 << 30, type="DDR5", form_factor=0x0D,
                            speed_mts=4800, configured_mts=4800, manufacturer="Samsung",
                            part_number="M425R1GB4BB0-CQKOL", rank=1,
                            voltage_configured_mv=1100)
               for n in (0, 1)]
    draft = Draft()
    draft.modules = modules
    SpdModules._merge(draft, list(snapshot.spd))
    return dataclasses.replace(snapshot, modules=tuple(draft.modules))


class TestItsPageZero(unittest.TestCase):

    def test_exactly_what_it_says(self):
        reading, = foto(DUMP)[0].spd
        self.assertEqual((reading.dram_type, reading.module_type, reading.device_width,
                          reading.partial), ("DDR5", "SODIMM", 16, True))
        timings = reading.jedec
        self.assertEqual((timings.speed_mts, timings.cl, timings.trcd, timings.trp,
                          timings.tras, timings.trc), (4800, 40, 39, 39, 77, 116))
        # What page 0 doesn't hold is not made up.
        self.assertEqual((reading.manufacturer, reading.part_number, reading.ranks,
                          reading.capacity_bytes), (None,) * 4)

    def test_the_other_seven_said_blocked(self):
        notes = [n for n in foto(DUMP)[0].notes if n.path == "spd"]
        self.assertEqual([n.key for n in notes], ["prov.spd.partial"])
        self.assertIn("ENXIO", notes[0].detail)


class TestDumpedAgain(unittest.TestCase):
    """A machine like this one dumped: its `eeprom` is what read, page 0, and
    the other seven are recorded with their error."""

    def test_it_keeps_both(self):
        import json
        import pathlib
        import tempfile
        from silux import volcado
        with volcado.mounted(DUMP), tempfile.TemporaryDirectory() as out:
            folder = volcado.dump("otro", pathlib.Path(out), own={})
            eeprom = folder / "sys/devices/pci0000:00/0000:00:1f.4/i2c-0/0-0050/eeprom"
            page = eeprom.read_bytes()
            recorded = json.loads((folder / "grabado.json").read_text())["spd_pages"]
        self.assertEqual(page, (DUMP / "sys/devices/pci0000:00/0000:00:1f.4/i2c-0/0-0050"
                                / "eeprom").read_bytes())
        self.assertEqual(recorded, {"/sys/bus/i2c/devices/0-0050/eeprom":
                                    ["ok"] + ["ENXIO"] * 7})


class TestOnTheMemoryPage(unittest.TestCase):

    def test_with_the_firmwares_maker_and_part(self):
        qt.app()
        snapshot = _with_permissions(foto(DUMP)[0])
        self.assertEqual(snapshot.modules[0].spd.address, "0-0050")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Memoria")
            page = window.stack.currentWidget()
            card = page._slot_grids[0]
            values = {key: card._values[_(key)].full_text() for key in (
                "memory.field.vendor", "memory.field.part", "memory.field.type",
                "memory.field.rated", "memory.field.form")}
            # The timings sit in a card the test window doesn't lay out.
            texts = pantalla.textos_de(page)
        self.assertEqual(values, {"memory.field.vendor": "Samsung",
                                  "memory.field.part": "M425R1GB4BB0-CQKOL",
                                  "memory.field.type": "DDR5",
                                  "memory.field.rated": "4800 MT/s",
                                  "memory.field.form": "SODIMM"})
        row = texts.index(_("memory.module.n").format(n=1) + " · JEDEC")
        self.assertEqual(texts[row + 1:row + 8],
                         ["4800 MT/s", "40", "39", "39", "77", "116", "1.10 V"])


if __name__ == "__main__":
    unittest.main()
