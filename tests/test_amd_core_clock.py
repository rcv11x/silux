"""An AMD core's clock: a figure whenever the driver gives one, «en reposo»
only when it says the core is off.

On RDNA cards `pp_dpm_sclk` writes «S: 68Mhz *» when the clock falls under
half its lowest step: deep sleep, at that clock. Its line was skipped, no
step was marked and the expert row said «en reposo» beside «Núcleo: 1.61
GHz». «S: 0Mhz» is the core switched off (GFXOFF), and that is at rest
(smu_cmn.c, `smu_cmn_print_dpm_clk_levels`).

And `freq1_input` is an instant: on an RX 9070 XT it read 731, 645, 403 and
503 MHz a quarter of a second apart, and 0 when the core switched off. The
figure is the mean of the readings that found it on, read between samples;
off the whole interval, «en reposo».
"""

import pathlib
import unittest
from unittest import mock

from silux import render, volcado
from silux.collector import Collector
from silux.i18n import _
from tests import pantalla, qt

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"
CARD = "sys/devices/pci0000:00/0000:00:03.1/0000:0a:00.0/0000:0b:00.0/0000:0c:00.0"
FREQ = f"{CARD}/hwmon/hwmon3/freq1_input"


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def photo(readings_mhz, sclk=None):
    """Two samples a second apart; between them `readings_mhz` of the core
    clock, the last one at the sample."""
    clock = _Clock()
    with volcado.mounted(EQUIPOS / "5800x3d") as root, \
            mock.patch("silux.providers.drm.time.monotonic", clock):
        if sclk is not None:
            (root / CARD / "pp_dpm_sclk").write_text(sclk)
        collector = Collector()
        try:
            collector.snapshot()
            for mhz in readings_mhz[:-1]:
                (root / FREQ).write_text(f"{mhz * 1_000_000}\n")
                collector.between_samples()
            (root / FREQ).write_text(f"{readings_mhz[-1] * 1_000_000}\n")
            clock.now += 1.0
            return collector.snapshot()
        finally:
            collector.close()


def radeon(snapshot):
    return next(g for g in snapshot.gpus if g.driver == "amdgpu")


class TestTheDeepSleepLine(unittest.TestCase):
    def test_the_dump_has_it(self):
        text = (EQUIPOS / "5800x3d" / CARD / "pp_dpm_sclk").read_text()
        self.assertTrue(text.startswith("S: 68Mhz *"))

    def test_is_the_clock_in_use(self):
        levels = radeon(photo([1612])).clocks.core_levels
        sleeping = [level for level in levels if level.deep_sleep]
        self.assertEqual([(level.hz, level.active) for level in sleeping],
                         [(68_000_000, True)])
        row = render.dpm_levels(levels)
        self.assertNotIn(_("gpu.expert.now.asleep"), row)
        self.assertIn("68", row)

    def test_at_zero_the_core_is_off(self):
        levels = radeon(photo([0], sclk="S: 0Mhz *\n1: 500Mhz \n2: 2520Mhz \n")).clocks.core_levels
        self.assertIn(_("gpu.expert.now.asleep"), render.dpm_levels(levels))


class TestTheClockOverTheInterval(unittest.TestCase):
    def test_the_mean_of_the_readings(self):
        core = radeon(photo([731, 645, 403, 503])).clocks.core_hz
        self.assertEqual(core, round((731 + 645 + 403 + 503) / 4) * 1_000_000)

    def test_switched_off_part_of_the_interval_is_not_a_low_clock(self):
        core = radeon(photo([0, 41, 0, 85])).clocks.core_hz
        self.assertEqual(core, 63_000_000)

    def test_off_the_whole_interval_is_at_rest(self):
        snapshot = photo([0, 0, 0, 0])
        self.assertEqual(radeon(snapshot).clocks.core_hz, 0)
        qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            texts = pantalla.textos_de(window.graphics_page)
        self.assertIn(_("gpu.clock.idle"), texts)
        self.assertFalse([t for t in texts if t.startswith("0 MHz") or t == "0"])


class TestSensorsSaysTheSame(unittest.TestCase):
    """Graphics had the interval's clock and Sensors the last instant, and
    with the core off one said «en reposo» and the other «0.0 MHz»."""

    def row(self, snapshot) -> str:
        qt.app()
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Sensores")
            return window.monitor_page.tree._rows["amdgpu/freq1"].text(1)

    def test_the_interval_mean(self):
        snapshot = photo([731, 645, 403, 503])
        sclk = next(s for s in snapshot.sensors if s.key == "amdgpu/freq1")
        self.assertEqual(sclk.value * 1_000_000, radeon(snapshot).clocks.core_hz)

    def test_off_the_whole_interval(self):
        self.assertEqual(self.row(photo([0, 0, 0, 0])), _("gpu.clock.idle"))
