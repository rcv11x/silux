"""A graphics card's memory chips by their maker's brand.

amdgpu writes the maker of the VRAM in lowercase, from its own list
(`mem_info_vram_vendor`, amdgpu_vram_mgr.c): Graphics showed «Chips: hynix»
and «samsung». And «unknown», its default, is no maker.
"""

import pathlib
import shutil
import tempfile
import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

# What the kernel writes, and the brand.
KERNEL = {"samsung": "Samsung", "infineon": "Infineon", "elpida": "Elpida",
          "etron": "Etron", "nanya": "Nanya", "hynix": "SK Hynix", "mosel": "Mosel Vitelic",
          "winbond": "Winbond", "esmt": "ESMT", "micron": "Micron"}


def chips(snapshot) -> str:
    qt.app()
    with pantalla.Ventana(snapshot) as window:
        window.select_section("Gráficos")
        return "\n".join(pantalla.textos_de(window.graphics_page))


class TestTheMakers(unittest.TestCase):
    def test_each_name_the_kernel_writes(self):
        for written, brand in KERNEL.items():
            with self.subTest(written=written):
                self.assertEqual(render.vram_maker(written), brand)

    def test_graphics_says_the_brand(self):
        for dump, brand, raw in (("5800x3d", "SK Hynix", "hynix"),
                                 ("ryzen5-9600x", "Samsung", "samsung")):
            with self.subTest(dump=dump):
                snapshot = shared_snapshot(EQUIPOS / dump)
                self.assertEqual(next(g.memory.vendor for g in snapshot.gpus
                                      if g.memory.vendor), raw)
                text = chips(snapshot)
                self.assertIn(brand, text)
                self.assertNotIn(f"\n{raw}\n", f"\n{text}\n")

    def test_unknown_is_no_maker(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = pathlib.Path(tmp) / "x3d"
            shutil.copytree(EQUIPOS / "5800x3d", copy, symlinks=True)
            vendor = next(copy.glob("sys/devices/**/mem_info_vram_vendor"))
            vendor.write_text("unknown\n")
            snapshot = foto(copy)[0]
        self.assertEqual([g.memory.vendor for g in snapshot.gpus if g.vendor == "AMD"], [None])
