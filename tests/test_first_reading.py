"""On the first reading, what comes from two says «Calculando…», not «—».

Usage, power and transfer rates subtract two readings: the collector's first
snapshot has only the baseline, and the CPU page read «Uso —» and «Consumo
—», the dash of what can't be read. Each dump's first snapshot is what a
machine shows during its first second.
"""

import unittest
from collections import Counter

from silux import render, volcado
from silux.collector import Collector
from tests import pantalla, qt
from tests.interval import fake_clock, next_snapshot
from tests.per_dump import per_dump
from tests.test_equipos import EQUIPOS
from tests.test_interface_language import visible_texts

SECTIONS = ("Inicio", "CPU", "Gráficos", "Almacenamiento", "Red")


def _first_and_second(folder):
    with volcado.mounted(folder), fake_clock() as clock:
        collector = Collector()
        try:
            first = collector.snapshot()
            return first, next_snapshot(collector, clock)
        finally:
            collector.close()


class TestFirstReading(unittest.TestCase):

    # Each dump's pair, taken when a test asks for it: split by dump, a test
    # needs one, not nineteen.
    _pairs: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _pair(self, name: str):
        if name not in self._pairs:
            self._pairs[name] = _first_and_second(EQUIPOS / name)
        return self._pairs[name]

    def _texts(self, window, section):
        window.select_section(section)
        for _vez in range(3):
            self.app.processEvents()
        return visible_texts(window.stack.currentWidget())

    def _only_the_first_is_the_first(self, folder):
        first, second = self._pair(folder.name)
        self.assertEqual((first.first_reading, second.first_reading), (True, False))

    def _no_dash_where_a_figure_is_coming(self, folder):
        name = folder.name
        first, second = self._pair(name)
        with pantalla.Ventana(first) as window:
            before = {s: self._texts(window, s) for s in SECTIONS}
        with pantalla.Ventana(second) as window:
            after = {s: self._texts(window, s) for s in SECTIONS}
        for section in SECTIONS:
            if len(before[section]) != len(after[section]):
                continue
            for old, new in zip(before[section], after[section]):
                with self.subTest(name, section=section):
                    self.assertFalse(old == render.DASH and new != render.DASH,
                                     f"«—» before «{new}»")

    def test_the_cpu_tiles_and_home(self):
        first, second = self._pair("5800x3d")
        with pantalla.Ventana(first) as window:
            window.select_section("CPU")
            live = window.stack.currentWidget().live
            self.assertEqual(live.tile_usage.value.text(), render.calculating())
            self.assertEqual(live.tile_power.value.text(), render.calculating())
            window.select_section("Inicio")
            home = window.stack.currentWidget()
            self.assertEqual(home.red.cifras.text(), render.calculating())
            # The second reading takes «Calculando…» away.
            window._on_sample(second)
            for _vez in range(3):
                self.app.processEvents()
            self.assertNotIn(render.calculating(), visible_texts(home))
            window.select_section("CPU")
            self.assertNotEqual(live.tile_usage.value.text(), render.calculating())

    def test_after_the_first_the_page_is_as_with_the_second(self):
        """Rule 9: open with the first and given the second, each page reads
        as if opened with the second."""
        for name in ("5800x3d", "i5-1135g7", "qemu-kvm"):
            first, second = self._pair(name)
            with pantalla.Ventana(second) as window:
                fresh = {s: self._texts(window, s) for s in SECTIONS}
            with pantalla.Ventana(first) as window:
                for section in SECTIONS:
                    self._texts(window, section)
                window._on_sample(second)
                for section in SECTIONS:
                    # As a multiset: a notice created later comes later in
                    # Qt's list of children, not in the layout.
                    with self.subTest(name, section=section):
                        self.assertEqual(Counter(self._texts(window, section)),
                                         Counter(fresh[section]))


per_dump(TestFirstReading, "only_the_first_is_the_first", TestFirstReading._only_the_first_is_the_first)
per_dump(TestFirstReading, "no_dash_where_a_figure_is_coming",
         TestFirstReading._no_dash_where_a_figure_is_coming)


if __name__ == "__main__":
    unittest.main()
