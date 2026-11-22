"""One family of units per block: binary for memory, decimal for disks.

A 1 TB disk read «931.5 GB», with «418.3 GiB used · 513.2 GiB free» under
it, and the sum didn't add up for whoever read it. Memory, video memory and
caches come in powers of two and say GiB, MiB, KiB; disks, partitions and
what crosses the network, in decimal as `df -H` writes them, with the GiB on
hover.
"""

import re
import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, volcados
from tests.test_interface_language import visible_texts

BINARY = re.compile(r"\d (?:KiB|MiB|GiB|TiB)\b")
# A rate («MB/s», «GB/s») is decimal everywhere, as networking writes it.
DECIMAL = re.compile(r"\d (?:kB|KB|MB|GB|TB)\b(?!/s)")


class TestTheFormatters(unittest.TestCase):

    def test_binary_and_decimal(self):
        self.assertEqual(render.size(16 * 1024**3), "16 GiB")
        self.assertEqual(render.cache_size(1280 * 1024), "1.25 MiB")
        self.assertEqual(render.decimal_size(1_000_204_886_016), "1.0 TB")


class TestEveryPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pages(self, folder):
        with pantalla.Ventana(foto(folder)[0]) as window:
            pages = {}
            for section in ("Inicio", "CPU", "Cachés", "Memoria", "Gráficos",
                            "Almacenamiento", "Red"):
                window.select_section(section)
                for _vez in range(3):
                    self.app.processEvents()
                page = window.stack.currentWidget()
                pages[section] = (page, " · ".join(visible_texts(page)))
            yield from pages.items()

    def test_disks_and_network_decimal_memory_and_caches_binary(self):
        for folder in volcados():
            for section, (page, text) in self._pages(folder):
                with self.subTest(folder.name, section=section):
                    if section in ("Almacenamiento", "Red"):
                        self.assertIsNone(BINARY.search(text))
                    elif section in ("CPU", "Cachés", "Memoria", "Gráficos"):
                        self.assertIsNone(DECIMAL.search(text))
                    else:
                        home = page
                        disks = " ".join(visible_texts(home.discos))
                        memory = " ".join(visible_texts(home.memoria))
                        self.assertIsNone(BINARY.search(disks))
                        self.assertIsNone(DECIMAL.search(memory))

    def test_the_gib_on_hover(self):
        snapshot = foto(EQUIPOS / "5800x3d")[0]
        nvme = next(d for d in snapshot.disks if d.name == "nvme0n1")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Almacenamiento")
            page = window.stack.currentWidget()
            row = [d.name for d in snapshot.disks].index("nvme0n1")
            self.assertEqual(page.disks._cells[row][3].toolTip(), render.size(nvme.size_bytes))
            self.assertEqual(page.title.toolTip(),
                             render.size(sum(d.size_bytes or 0 for d in snapshot.disks)))
            window.select_section("Inicio")
            home = window.stack.currentWidget()
            self.assertTrue(home.discos.nombre.toolTip().endswith("TiB"))


if __name__ == "__main__":
    unittest.main()
