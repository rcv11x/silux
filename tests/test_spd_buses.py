"""Which bus leads to the memory, and what to do when its SPD isn't read.

A laptop with no SPD chip registered anywhere was told to load ee1004: any
i2c bus that wasn't a graphics card's counted as the memory's, the
touchpad's DesignWare buses too. And with the permissions given, a chip
waiting for its driver showed «(needs permissions)» in the report.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import spd, sysroot, volcado
from silux.i18n import _
from silux.model import Need
from tests.test_equipos import EQUIPOS

SMBUS, DESIGNWARE, GPU = "0000:00:1f.4", "0000:00:15.0", "0000:00:02.0"


class _Tree:
    """/sys/bus/i2c/devices and the PCI classes, laid out as the kernel does."""

    def __init__(self, root: pathlib.Path):
        self.i2c, self.pci, self.devices = root / "i2c", root / "pci", root / "devices"
        for folder in (self.i2c, self.pci):
            folder.mkdir()
        for address, pci_class in ((SMBUS, "0x0c0500"), (DESIGNWARE, "0x0c8000"), (GPU, "0x030000")):
            (self.pci / address).mkdir()
            (self.pci / address / "class").write_text(pci_class)

    def bus(self, number: int, parent: str) -> None:
        folder = self.devices / "pci0000:00" / parent / f"i2c-{number}"
        folder.mkdir(parents=True)
        os.symlink(os.path.relpath(folder, self.i2c), self.i2c / f"i2c-{number}")

    def chip(self, bus: int, address: int, parent: str, name=None, bound=False) -> None:
        folder = self.devices / "pci0000:00" / parent / f"i2c-{bus}" / f"{bus}-00{address:02x}"
        folder.mkdir(parents=True)
        if name:
            (folder / "name").write_text(name + "\n")
        if bound:
            (folder / "hwmon").mkdir()
        os.symlink(os.path.relpath(folder, self.i2c), self.i2c / folder.name)

    def patches(self):
        return mock.patch.multiple(spd, SYS_I2C=self.i2c, SYS_PCI=self.pci)


class TestWhichBusLeadsToMemory(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = _Tree(pathlib.Path(self._tmp.name))
        self.tree.bus(1, f"{DESIGNWARE}/i2c_designware.0")      # the touchpad's
        self.tree.bus(3, GPU)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_touchpad_or_graphics_bus_is_not_the_memorys(self):
        self.tree.chip(1, 0x50, f"{DESIGNWARE}/i2c_designware.0", name="ee1004")
        with self.tree.patches():
            self.assertEqual(spd.memory_buses(), [])
            self.assertEqual(spd.unreadable_cause(), spd.CAUSE_NO_BUS)

    def test_a_memory_bus_with_no_chip_proposes_no_driver(self):
        self.tree.bus(8, SMBUS)
        with self.tree.patches():
            self.assertEqual(spd.memory_buses(), ["8"])
            self.assertEqual(spd.unreadable_cause(), spd.CAUSE_NO_CHIP)
            motivo, consejo = spd.diagnosis()
        self.assertEqual((motivo, consejo), (_("spd.nochip"), _("spd.nochip.hint")))
        self.assertNotIn("modprobe", consejo)

    def test_a_chip_without_its_driver_gets_that_driver(self):
        self.tree.bus(8, SMBUS)
        for address in (0x50, 0x52):
            self.tree.chip(8, address, SMBUS, name="ee1004")
        with self.tree.patches():
            self.assertEqual(spd.unreadable_cause(), spd.CAUSE_NO_DRIVER)
            _motivo, consejo = spd.diagnosis()
        self.assertEqual(consejo, _("spd.nodriver.load").format(orden="sudo modprobe ee1004"))

    def test_a_ddr3_chip_is_read_by_at24(self):
        self.tree.bus(8, SMBUS)
        self.tree.chip(8, 0x50, SMBUS, name="spd")
        with self.tree.patches():
            self.assertIn("sudo modprobe at24", spd.diagnosis()[1])

    def test_a_chip_without_a_name_gets_the_three_generations(self):
        self.tree.bus(8, SMBUS)
        self.tree.chip(8, 0x50, SMBUS)
        with self.tree.patches():
            self.assertEqual(spd.diagnosis()[1], _("spd.nodriver.hint"))

    def test_chips_with_their_driver_and_nothing_published(self):
        self.tree.bus(8, SMBUS)
        self.tree.chip(8, 0x50, SMBUS, name="spd5118", bound=True)
        with self.tree.patches():
            self.assertEqual(spd.unreadable_cause(), spd.CAUSE_NO_CONTENT)


def _without_driver(raiz: pathlib.Path) -> None:
    """The dump's two DDR4 chips registered by the SMBus driver, as the
    kernel names them, and ee1004 not loaded: no eeprom."""
    for address in ("10-0050", "10-0052"):
        chip = raiz / "sys/devices/pci0000:00/0000:00:1f.4/i2c-10" / address
        (chip / "eeprom").unlink()
        (chip / "name").write_text("ee1004\n")


class TestAChipWaitingForItsDriver(unittest.TestCase):

    def _snapshot(self):
        from silux.collector import Collector
        from tests.interval import second_snapshot
        from tests.test_nada_en_bruto import _con_permisos
        from tests.test_smbios import _end, _memory_array, _memory_device

        with volcado.montado(EQUIPOS / "i5-10400") as raiz:
            _without_driver(raiz)
            sysroot.forget()
            recolector = Collector()
            try:
                f = second_snapshot(recolector)
            finally:
                recolector.close()
        # And the permissions given: the firmware's table is read.
        return _con_permisos(f, _memory_array() + _memory_device() + _memory_device() + _end())

    def test_the_note_names_the_driver(self):
        nota = next(n for n in self._snapshot().notes if n.path == "spd")
        self.assertEqual((nota.need, nota.message, nota.hint),
                         (Need.DRIVER, _("spd.nodriver"),
                          _("spd.nodriver.load").format(orden="sudo modprobe ee1004")))

    def test_no_padlock_and_the_footnote_says_so_in_the_report(self):
        from silux.ui import full_report
        from tests import pantalla, qt

        f = self._snapshot()
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Memoria")
            pagina = ventana.stack.currentWidget()
            for ficha in pagina._slot_grids:
                for clave in ("memory.field.chips", "memory.field.profiles", "memory.field.made"):
                    with self.subTest(campo=clave):
                        self.assertFalse(ficha.is_locked(_(clave)))
            pie = pagina.spd_missing.text()
        self.assertIn(_("spd.nodriver")[1:40], pie)
        self.assertIn("sudo modprobe ee1004", pie)
        memoria = full_report.build(f).split("\n## Memoria\n", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn(f"({_('report.locked')})", memoria)
        self.assertIn("sudo modprobe ee1004", memoria)


if __name__ == "__main__":
    unittest.main()
