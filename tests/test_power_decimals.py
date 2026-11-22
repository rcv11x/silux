"""A power below 10 W has its decimal, and the same figure on every page.

An idle integrated card drew 0.4 W: Home said «0.4 W» and the Graphics tile
«0 W». Below 10 W a tenth still says something; above, it doesn't.
"""

import dataclasses
import re
import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, volcados
from tests.test_interface_language import visible_texts

try:
    from PySide6.QtWidgets import QLabel
except ImportError:                                    # pragma: no cover
    QLabel = None

SECTIONS = ("Inicio", "CPU", "Gráficos", "Batería")
# «3 W», «0 W»: a figure below 10 without its decimal, as a value («3 W»,
# «3 W de 60 W», «Consumo · 3 W»), not inside a sentence. A range's start
# («5–60 W») goes without the unit.
WHOLE_BELOW_TEN = re.compile(r"(?:^|[·(]\s?)\d W\b")


def _tiles_in_watts(page):
    from silux.ui.widgets import StatTile
    for tile in page.findChildren(StatTile):
        if tile.unit.text() == "W" and tile.value.isVisibleTo(page):
            yield tile.value.text()


class TestTheFormatter(unittest.TestCase):

    def test_one_decimal_below_ten(self):
        self.assertEqual(render.power_figure(0.4), "0.4")
        self.assertEqual(render.power_figure(8.44), "8.4")
        self.assertEqual(render.power_figure(9.96), "10")
        self.assertEqual(render.power_figure(54.0), "54")
        self.assertEqual(render.watts(0.4), "0.4 W")
        self.assertEqual(render.watts(67.5), "68 W")
        # A limit is the maker's number, and keeps its half watt.
        self.assertEqual(render.limit_watts(67.5), "67.5 W")
        self.assertEqual(render.limit_watts(54.0), "54 W")
        self.assertEqual(render.limit_watts(9.0), "9.0 W")


@unittest.skipIf(QLabel is None, "sin PySide6")
class TestEveryPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pages(self, snapshot):
        with pantalla.Ventana(snapshot) as window:
            for section in SECTIONS:
                if not window.select_section(section):
                    continue
                for _vez in range(3):
                    self.app.processEvents()
                page = window.stack.currentWidget()
                yield section, visible_texts(page), list(_tiles_in_watts(page))

    def test_no_whole_watt_below_ten(self):
        for folder in volcados():
            for section, texts, tiles in self._pages(foto(folder)[0]):
                with self.subTest(folder.name, section=section):
                    self.assertEqual([t for t in texts if WHOLE_BELOW_TEN.search(t)], [])
                    for figure in tiles:
                        if figure != render.DASH and float(figure) < 10:
                            self.assertIn(".", figure)

    def test_an_idle_integrated_card_on_home_and_graphics(self):
        snapshot = foto(EQUIPOS / "celeron-g3900")[0]
        gpu = dataclasses.replace(snapshot.gpus[0], power_w=0.4)
        snapshot = dataclasses.replace(snapshot, gpus=(gpu,))
        pages = {section: (texts, tiles) for section, texts, tiles in self._pages(snapshot)}
        self.assertEqual(pages["Gráficos"][1], ["0.4"])
        self.assertTrue(any("0.4 W" in t for t in pages["Inicio"][0]))


if __name__ == "__main__":
    unittest.main()
