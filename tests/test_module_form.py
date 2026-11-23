"""A module's form reads the same with permissions as without.

Without permissions the form came from the module's SPD («UDIMM»); with
them, from the firmware's table, which only says «DIMM».
"""

import dataclasses
import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados

# What the firmware's table calls each SPD type (SMBIOS form factor codes).
DIMM, SODIMM = 0x09, 0x0D


def _as_the_firmware_says(module):
    form = SODIMM if "SO" in module.spd.module_type else DIMM
    return dataclasses.replace(module, form_factor=form)


def _from_the_firmware(snapshot):
    """Its modules as the firmware's table lists them with permissions, each
    with its SPD attached."""
    from silux.model import MemoryModule
    return tuple(_as_the_firmware_says(MemoryModule(
        locator=f"ChannelA-DIMM{n}", populated=True, type=info.dram_type, spd=info))
        for n, info in enumerate(snapshot.spd))


class TestTheForm(unittest.TestCase):

    def test_with_and_without_permissions_in_every_dump(self):
        for folder in volcados():
            snapshot = shared_snapshot(folder)
            for info, module in zip(snapshot.spd, _from_the_firmware(snapshot)):
                if not info.module_type:
                    continue
                with self.subTest(folder.name, module=info.address):
                    self.assertEqual(render.module_form(module), info.module_type)

    def test_on_the_memory_page(self):
        qt.app()
        snapshot = shared_snapshot(EQUIPOS / "celeron-g3900")
        self.assertFalse(snapshot.modules)
        with_permissions = dataclasses.replace(snapshot, modules=_from_the_firmware(snapshot))
        texts = {}
        for name, photo in (("without", snapshot), ("with", with_permissions)):
            with pantalla.Ventana(photo) as window:
                window.select_section("Memoria")
                texts[name] = pantalla.textos_de(window.stack.currentWidget())
        for name in texts:
            with self.subTest(name):
                self.assertIn("UDIMM", texts[name])
                self.assertNotIn("DIMM", texts[name])


if __name__ == "__main__":
    unittest.main()
