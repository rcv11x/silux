"""Soldered memory has no SPD chip, which is not «could not be read».

The author's T14 Gen 2i: 8 GB soldered and a Kingston SODIMM in the slot,
the only SPD on its bus. With permissions its two modules come from SMBIOS
(as its report gave them, both with form factor SODIMM); the soldered one
has no chip, and the foot said its chips, profiles and date «no se ha
podido leer».

What is soldered: the SMBIOS form factor first, when it is one of memory
on the board (a row of chips); the name of its place otherwise, since many
laptops call soldered memory «ChannelA-DIMM0» and the T14 calls its
soldered memory a SODIMM.
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
    comun["form_factor"] = 0x0D          # SODIMM
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

    def test_a_row_of_chips_is_soldered_whatever_its_place_is_called(self):
        for formato in (0x0B, 0x05, 0x10):                  # row of chips, chip, die
            with self.subTest(formato=formato):
                self.assertFalse(MemoryModule(locator="ChannelA-DIMM0",
                                              form_factor=formato).in_a_slot)
        # A SODIMM does not settle it: the T14's soldered memory says so too.
        self.assertFalse(MemoryModule(locator="Controller0-ChannelA",
                                      form_factor=0x0D).in_a_slot)
        self.assertTrue(MemoryModule(locator="ChannelA-DIMM0",
                                     form_factor=0x0D).in_a_slot)

    def test_on_the_page_a_row_of_chips_has_no_chip(self):
        def soldada_con_nombre_de_ranura(lectura):
            sin, con = _t14(lectura)
            return (dataclasses.replace(sin, locator="ChannelA-DIMM0",
                                        form_factor=0x0B), con)
        pagina = _page(soldada_con_nombre_de_ranura)
        pie = pagina.spd_missing.text()
        self.assertIn(_("memory.na.soldered").split("{campos}")[1], pie)

    def test_the_code_decides_and_the_name_is_said_in_each_language(self):
        from silux import i18n, render
        modulo = MemoryModule(locator="ChannelA-DIMM0", form_factor=0x0B)
        nombres = {}
        for idioma in ("es", "en"):
            i18n.set_language(idioma)
            try:
                nombres[idioma] = (modulo.in_a_slot, render.memory_form_factor(modulo.form_factor))
            finally:
                i18n.set_language("es")
        self.assertEqual(nombres, {"es": (False, "Fila de chips"), "en": (False, "Row of chips")})


if __name__ == "__main__":
    unittest.main()
