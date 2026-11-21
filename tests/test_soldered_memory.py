"""Soldered memory has no SPD chip, which is not «could not be read».

The author's T14 Gen 2i: 8 GB soldered and a Kingston SODIMM in the slot,
the only SPD on its bus. With permissions its two modules come from SMBIOS
(as its report gave them); the soldered one has no chip, and the foot said
its chips, profiles and date «no se ha podido leer».
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.model import MemoryModule
from tests import qt
from tests.test_equipos import EQUIPOS, foto


def _page(modulos):
    from silux.settings import Preferences
    from silux.ui import theme
    from silux.ui.pages.memory import MemoryPage
    app = qt.app()
    f = foto(EQUIPOS / "i5-1135g7")[0]
    f = dataclasses.replace(f, modules=modulos(f.spd[0]))
    pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
    pagina.apply(f)
    return pagina


def _t14(lectura):
    comun = dict(populated=True, type="DDR4", size_bytes=8 << 30, speed_mts=3200,
                 configured_mts=3200, rank=1)
    return (MemoryModule(locator="Controller0-ChannelA", manufacturer="Samsung",
                         part_number="M471A1G44AB0-CWE", **comun),
            MemoryModule(locator="Controller1-ChannelA-DIMM0", manufacturer="Kingston",
                         part_number="9905711-049.A00G", spd=lectura, **comun))


class TestSolderedMemory(unittest.TestCase):

    def test_it_is_said_to_have_no_chip(self):
        pagina = _page(_t14)
        pie = pagina.spd_missing.text()
        self.assertIn(_("memory.na.soldered").split("{campos}")[1], pie)
        self.assertNotIn("no se ha podido leer", pie)

    def test_a_slot_without_its_spd_still_could_not_be_read(self):
        def dos_ranuras(lectura):
            sin, con = _t14(lectura)
            return (dataclasses.replace(sin, locator="Controller0-ChannelA-DIMM0"), con)
        pagina = _page(dos_ranuras)
        pie = pagina.spd_missing.text()
        self.assertNotIn(_("memory.na.soldered").split("{campos}")[1], pie)

    def test_hps_slot_names(self):
        self.assertTrue(MemoryModule(locator="Bottom-Slot 1(left)").in_a_slot)
        self.assertTrue(MemoryModule(locator="DIMM_A1").in_a_slot)
        self.assertFalse(MemoryModule(locator="Controller0-ChannelA").in_a_slot)


if __name__ == "__main__":
    unittest.main()
