"""The processor's package: from the CPU table, and else from the firmware's.

One generation's desktop and laptop chips share a codename; only the model
number tells them apart, so the table's rules look at it too.
"""

import re
import unittest
from unittest import mock

from silux import db
from silux.i18n import _
from silux.model import Need
from silux.privileged import smbios
from tests.test_equipos import EQUIPOS
from tests.test_referencias_cpu import _referencias, identificar
from tests.test_smbios import _end, _structure

# What a laptop's model number ends in, and a desktop's: K, S, T, P or none.
LAPTOP = re.compile(r"i[3579]-\d{4,5}(M|QM|MQ|HQ|XM|HK|H|U|Y|G\d)\s")
DESKTOP = re.compile(r"i[357]-[2-7]\d{3}[KSTP]?\s")


def _package(cpu: dict) -> str:
    codename, _node = identificar(cpu)
    return db.find_socket(cpu["vendor"], codename, cpu["brand"]) or ""


def _ivy_bridge(brand: str, cores: int) -> str:
    """The package the table gives an Ivy Bridge (06_3AH) with that brand."""
    ident = db.identify_x86(vendor_id="GenuineIntel", family=6, model=10, stepping=9,
                            ext_family=6, ext_model=58, cores=cores, brand=brand,
                            l2_kb=256, l3_kb=3072)
    return db.find_socket("GenuineIntel", ident.codename, brand)


def _processor(upgrade: int, populated: bool = True) -> bytes:
    """A type 4 structure: what matters is the status and the upgrade."""
    fields = bytearray(0x2A - 4)
    fields[0x04 - 4] = 1                    # string 1: socket designation
    fields[0x05 - 4] = 0x03                 # central processor
    fields[0x18 - 4] = 0x41 if populated else 0x00
    fields[0x19 - 4] = upgrade
    return _structure(4, bytes(fields), ["CPU 1"])


class TestTheTable(unittest.TestCase):

    def test_one_generation_on_a_desk_and_in_a_laptop(self):
        self.assertEqual(_ivy_bridge("Intel(R) Core(TM) i5-3330 CPU @ 3.00GHz", 4), "LGA 1155")
        self.assertIsNone(_ivy_bridge("Intel(R) Core(TM) i5-3210M CPU @ 2.50GHz", 2))
        self.assertEqual(_ivy_bridge("Intel(R) Core(TM) i5-3317U CPU @ 1.70GHz", 2),
                         "BGA (soldado)")

    def test_no_laptop_gets_a_desktop_socket(self):
        cpus = [c for c in _referencias() if c["vendor"] == "GenuineIntel"]
        laptops = [c for c in cpus if LAPTOP.search(c["brand"] + " ")]
        desktops = [c for c in cpus if DESKTOP.search(c["brand"] + " ")]
        self.assertGreater(len(laptops), 5)
        self.assertGreater(len(desktops), 10)
        for cpu in laptops:
            with self.subTest(cpu["brand"]):
                self.assertFalse(_package(cpu).startswith("LGA"), _package(cpu))
        for cpu in desktops:
            with self.subTest(cpu["brand"]):
                self.assertTrue(_package(cpu).startswith("LGA"), _package(cpu))


class TestTheFirmwareTable(unittest.TestCase):

    def _socket(self, *structures: bytes):
        return smbios.processor_socket(list(smbios.parse_table(b"".join(structures) + _end())))

    def test_the_specification_names_it_not_dmidecode(self):
        self.assertEqual(smbios.PROCESSOR_UPGRADES[0x24], "Socket LGA1155")
        self.assertEqual(self._socket(_processor(0x24)), "LGA 1155")
        self.assertEqual(self._socket(_processor(0x31)), "AM4")
        self.assertEqual(self._socket(_processor(0x21)), "rPGA 988B")

    def test_what_names_no_socket(self):
        for code in (0x01, 0x02, 0x06, 0xFE):
            with self.subTest(code=hex(code)):
                self.assertIsNone(self._socket(_processor(code)))

    def test_the_first_populated_socket(self):
        self.assertEqual(self._socket(_processor(0x2D, populated=False), _processor(0x32)),
                         "LGA 1151")


class _Helper:
    """The helper as the client sees it, handing over a table."""

    def __init__(self, table: bytes):
        self.table = table

    def supported(self):
        return True

    def connected(self):
        return True

    def connect(self):
        pass

    def smbios_table(self):
        return self.table

    def close(self):
        pass


def _collect(table=None):
    """The i5-3330's snapshot with a CPU table that lacks its package."""
    from silux import volcado
    from silux.collector import Collector
    from silux.providers.privileged_memory import PrivilegedMemory
    from tests.interval import second_snapshot

    with volcado.mounted(EQUIPOS / "i5-3330"), \
            mock.patch.object(db, "find_socket", return_value=None):
        collector = Collector()
        try:
            if table is not None:
                provider = next(p for p in collector.providers
                                if isinstance(p, PrivilegedMemory))
                provider.client = _Helper(table)
                provider.requested = True
            return second_snapshot(collector)
        finally:
            collector.close()


class TestOnTheCpuPage(unittest.TestCase):

    @staticmethod
    def _row(snapshot):
        from silux.ui.pages.cpu import TypeSection
        from tests import pantalla, qt

        qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("CPU")
            grid = window.cpu_page.findChildren(TypeSection)[0].processor
            name = _("cpu.field.package")
            return grid.is_locked(name), grid._values[name].full_text()

    def test_the_real_table_has_it(self):
        from silux import volcado

        snapshot = volcado.snapshot_of(EQUIPOS / "i5-3330")
        self.assertEqual(self._row(snapshot), (False, "LGA 1155"))

    def test_without_permissions_a_padlock(self):
        snapshot = _collect()
        note = next(n for n in snapshot.notes if n.path == "cpu.socket")
        self.assertIs(note.need, Need.ROOT)
        self.assertTrue(self._row(snapshot)[0])

    def test_with_permissions_the_firmware_says_it(self):
        snapshot = _collect(_processor(0x24) + _end())
        self.assertFalse(any(n.path == "cpu.socket" for n in snapshot.notes))
        self.assertEqual(self._row(snapshot), (False, "LGA 1155"))

    def test_with_permissions_and_a_firmware_that_does_not_say(self):
        snapshot = _collect(_processor(0x01) + _end())
        note = next(n for n in snapshot.notes if n.path == "cpu.socket")
        self.assertIs(note.need, Need.DATABASE)
        self.assertIn(_("prov.smbios.nosocket"), note.message)


if __name__ == "__main__":
    unittest.main()
