"""An Intel GPU's clock over the interval, and sleep that is not 0 MHz.

`act_freq` reads 0 whenever the GPU is in RC6. With a 4K60 video on the
author's T14 (Iris Xe, i915) one reading a second went 0/1050/0/450/1100 MHz.
The figure is the mean of the readings that found it awake, read between
samples; asleep the whole interval it says «en reposo», never «0 MHz»; awake
part of the interval and never caught, the frequency the driver asked for.
The T14's dump, mounted, with its counters moving as they do.
"""

import pathlib
import unittest
from unittest import mock

from silux import volcado
from silux.collector import Collector
from silux.i18n import _
from tests import pantalla, qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"
GT = "sys/devices/pci0000:00/0000:00:02.0/drm/card1/gt/gt0"


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def photo(readings, asleep_ms, requested=None):
    """Two samples a second apart; between them `readings` of the actual
    frequency, the last one at the sample, and `asleep_ms` more of RC6."""
    reloj = _Clock()
    with volcado.montado(EQUIPOS / "i5-1135g7") as raiz, \
            mock.patch("silux.providers.drm.time.monotonic", reloj):
        gt = raiz / GT
        if requested is not None:
            (gt / "rps_cur_freq_mhz").write_text(f"{requested}\n")
        collector = Collector()
        try:
            collector.snapshot()
            rc6 = int((gt / "rc6_residency_ms").read_text())
            for mhz in readings[:-1]:
                (gt / "rps_act_freq_mhz").write_text(f"{mhz}\n")
                collector.between_samples()
            (gt / "rps_act_freq_mhz").write_text(f"{readings[-1]}\n")
            (gt / "rc6_residency_ms").write_text(f"{rc6 + asleep_ms}\n")
            reloj.now += 1.0
            return collector.snapshot()
        finally:
            collector.close()


def iris(snapshot):
    return next(g for g in snapshot.gpus if g.driver == "i915")


class TestTheClock(unittest.TestCase):

    def test_the_mean_of_when_it_was_awake(self):
        gpu = iris(photo([0, 1050, 0, 1100, 0], asleep_ms=820))
        self.assertEqual(gpu.clocks.core_hz, 1075 * 10**6)
        self.assertAlmostEqual(gpu.sleep_percent, 82.0)

    def test_asleep_the_whole_interval(self):
        self.assertEqual(iris(photo([0, 0, 0, 0, 0], asleep_ms=1000)).clocks.core_hz, 0)

    def test_awake_unseen_is_the_requested_frequency(self):
        gpu = iris(photo([0, 0, 0, 0, 0], asleep_ms=820, requested=1100))
        self.assertEqual(gpu.clocks.core_hz, 1100 * 10**6)


class TestOnThePage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()

    def _texts(self, snapshot):
        with pantalla.Ventana(snapshot) as ventana:
            ventana.select_section("Gráficos")
            return pantalla.textos_de(ventana.graphics_page)

    def test_asleep_is_a_word_not_zero_megahertz(self):
        textos = self._texts(photo([0, 0, 0, 0, 0], asleep_ms=1000))
        self.assertIn(_("gpu.clock.idle"), textos)
        self.assertFalse([t for t in textos if t.startswith("0 MHz") or t == "0"])

    def test_awake_it_says_how_long_it_slept(self):
        textos = self._texts(photo([0, 1050, 0, 1100, 0], asleep_ms=820))
        self.assertIn("1075", textos)
        self.assertIn(_("gpu.tile.asleep").format(pct="82.0 %"), textos)


if __name__ == "__main__":
    unittest.main()
