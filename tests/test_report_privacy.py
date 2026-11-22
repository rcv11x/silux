"""A new report carries no module serial number, from the SPD or SMBIOS.

The annex of a report is a dump of the machine (`python -m silux.annex`,
`volcado.dump`). Run as root, the Collector reads the raw SMBIOS table
itself; on any machine the SPD chips hold the module's serial. Neither may
reach the annex, nor the report's pages, nor the loader cache.
"""

import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from silux import annex, volcado
from silux.privileged import smbios
from tests.test_equipos import EQUIPOS
from tests.test_smbios import _end, _memory_array, _memory_device

SPD = "sys/devices/pci0000:00/0000:00:1f.3/i2c-8/8-0052/eeprom"
MODULE_SERIAL = "0x12345678"           # what `_memory_device` writes
SPD_SERIAL = b"\x07\x82\x70\xe4"


class TestANewReport(unittest.TestCase):
    """The i5-3330 (DDR3) with a serial put back in its SPD, a loader cache
    and an SMBIOS table, dumped as a report does it, as root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(cls.tmp.name)
        machine = base / "i5-3330"
        shutil.copytree(EQUIPOS / "i5-3330", machine, symlinks=True)
        eeprom = machine / SPD
        data = bytearray(eeprom.read_bytes())
        data[122:126] = SPD_SERIAL
        eeprom.write_bytes(bytes(data))
        (machine / "etc" / "ld.so.cache").write_bytes(b"ld.so-1.7.0" + bytes(64))
        tables = machine / "sys/firmware/dmi/tables"
        tables.mkdir(parents=True)
        cls.table = _memory_array() + _memory_device() + _end()
        (tables / "DMI").write_bytes(cls.table)
        with volcado.mounted(machine), \
                mock.patch("silux.providers.privileged_memory.already_root", return_value=True):
            cls.dump = volcado.dump("equipo", base / "out")
            cls.snapshot = volcado.snapshot_of(machine)
        cls.annex = annex.to_text(cls.dump)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_case_is_there(self):
        # Read as root, the table gave its module: the serial was there to leak.
        self.assertIn(MODULE_SERIAL, self.table.decode(errors="replace"))
        self.assertEqual(len(smbios.memory_devices(list(smbios.parse_table(self.table)))), 1)

    def test_no_spd_serial(self):
        for eeprom in self.dump.rglob("eeprom"):
            with self.subTest(str(eeprom.relative_to(self.dump))):
                self.assertEqual(volcado._spd_without_serial(eeprom.read_bytes())[1],
                                 bytes(len(volcado._spd_without_serial(eeprom.read_bytes())[1])))
        self.assertNotIn(SPD_SERIAL.hex(" "), self.annex)
        self.assertNotIn(SPD_SERIAL.hex(), self.annex)

    def test_no_raw_firmware_table_nor_loader_cache(self):
        self.assertFalse((self.dump / "sys/firmware/dmi/tables/DMI").exists())
        self.assertFalse((self.dump / "etc/ld.so.cache").exists())
        self.assertNotIn(MODULE_SERIAL, self.annex)

    def test_no_module_serial_on_the_pages(self):
        from silux.ui import full_report
        from tests import qt

        qt.app()
        modules = [m for m in self.snapshot.modules if m.populated]
        self.assertTrue(modules)
        text = full_report.build(self.snapshot, anonymous=True)
        self.assertNotIn(MODULE_SERIAL, text)


class TestEveryDumpOfTheSuite(unittest.TestCase):

    def test_no_raw_firmware_table(self):
        for prefix in volcado.NEVER_COPIED:
            found = [p for p in EQUIPOS.glob(f"*/{prefix.strip('/')}/*")]
            self.assertEqual(found, [], prefix)


if __name__ == "__main__":
    unittest.main()
