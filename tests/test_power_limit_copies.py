"""PL1 and PL2 from both of the processor's copies, read every sample.

Intel keeps each limit in its MSR and in the memory controller's registers
(intel-rapl-mmio), and enforces the lower. Laptop makers often lower only
one of them, and many change them when the charger is plugged in or out.
"""

import errno
import os
import unittest
from unittest import mock

from silux import render, sysroot, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.providers import base
from tests import pantalla, qt
from tests.interval import fake_clock, next_snapshot
from tests.test_equipos import EQUIPOS, foto

# The machine reported MSR 64 / 64 W and MMIO 20 / 64 W, the same on the
# charger and on battery; its PL4 is 121 W in both.
LAPTOP = EQUIPOS / "i5-1135g7"
MMIO = "sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0"
PL1_WINDOW_S = 27.983872


def _page_text(window) -> str:
    window.select_section("CPU")
    return "\n".join(pantalla.textos_de(window.stack.currentWidget()))


class TestTheLowerCopyIsEnforced(unittest.TestCase):

    def test_twenty_watts_not_sixty_four(self):
        power = foto(LAPTOP)[0].cpu.power
        self.assertEqual((power.limit_long_w, power.window_long_s, power.limit_long_other_w),
                         (20.0, PL1_WINDOW_S, 64.0))
        # PL2 is the same in both copies: nothing else to say.
        self.assertEqual((power.limit_short_w, power.limit_short_other_w), (64.0, None))

    def test_on_the_cpu_page(self):
        qt.app()
        with pantalla.Ventana(foto(LAPTOP)[0]) as window:
            text = _page_text(window)
        self.assertIn(render.power_limit(20.0, PL1_WINDOW_S) + " · "
                      + _("cpu.limit.lowest").format(otro=render.watts(64.0)), text)

    def test_without_the_mmio_copy_nothing_changes(self):
        from silux.providers.rapl import effective_limits
        msr = {"limit_long_w": 64.0, "window_long_s": 28.0}
        self.assertEqual(effective_limits(msr, {}), msr)

    def test_a_copy_that_only_the_mmio_has(self):
        from silux.providers.rapl import effective_limits
        self.assertEqual(effective_limits({}, {"limit_long_w": 20.0, "window_long_s": 28.0}),
                         {"limit_long_w": 20.0, "window_long_s": 28.0})


class TestReadEverySample(unittest.TestCase):
    """The firmware raising PL1 when the charger goes in, and lowering it
    back to where the MSR copy is."""

    def test_the_new_limit_on_the_open_page(self):
        qt.app()
        with volcado.montado(LAPTOP) as root, fake_clock() as clock:
            sysroot.olvidar()
            pl1 = root / MMIO / "constraint_0_power_limit_uw"
            collector = Collector()
            try:
                collector.snapshot()
                on_battery = next_snapshot(collector, clock)
                pl1.write_text("28000000\n")
                on_the_charger = next_snapshot(collector, clock)
                pl1.write_text("64000000\n")
                same_as_msr = next_snapshot(collector, clock)
            finally:
                collector.close()

        self.assertEqual(on_battery.cpu.power.limit_long_w, 20.0)
        self.assertEqual((on_the_charger.cpu.power.limit_long_w,
                          on_the_charger.cpu.power.limit_long_other_w), (28.0, 64.0))
        self.assertEqual((same_as_msr.cpu.power.limit_long_w,
                          same_as_msr.cpu.power.limit_long_other_w), (64.0, None))

        with pantalla.Ventana(on_battery) as window:
            window._on_sample(on_the_charger)
            charger_text = _page_text(window)
            window._on_sample(same_as_msr)
            msr_text = _page_text(window)
        self.assertIn(render.power_limit(28.0, PL1_WINDOW_S), charger_text)
        self.assertNotIn(render.power_limit(20.0, PL1_WINDOW_S), charger_text)
        # One copy again: the line about the other one goes.
        self.assertIn(render.power_limit(64.0, PL1_WINDOW_S), msr_text)
        self.assertNotIn(_("cpu.limit.lowest").format(otro=render.watts(64.0)), msr_text)


class TestThePeakHasNoWindow(unittest.TestCase):
    """The kernel answers ENODATA for PL4's time window in both copies: it
    has none, and that is not a failure."""

    def test_enodata_is_neither_a_failure_nor_a_note(self):
        real_open = open

        def kernel_open(path, *args, **kwargs):
            if os.fspath(path).endswith("constraint_2_time_window_us"):
                raise OSError(errno.ENODATA, os.strerror(errno.ENODATA), os.fspath(path))
            return real_open(path, *args, **kwargs)

        with volcado.montado(LAPTOP) as root, fake_clock() as clock:
            sysroot.olvidar()
            for zone in (MMIO, "sys/devices/virtual/powercap/intel-rapl/intel-rapl:0"):
                (root / zone / "constraint_2_time_window_us").write_text("")
            collector = Collector()
            try:
                with mock.patch.object(base, "open", kernel_open, create=True):
                    collector.snapshot()
                    snapshot = next_snapshot(collector, clock)
            finally:
                collector.close()

        self.assertEqual(snapshot.failures, ())
        self.assertFalse([n for n in snapshot.notes if n.key.startswith("cpu.power")])
        self.assertEqual((snapshot.cpu.power.limit_long_w, snapshot.cpu.power.window_long_s),
                         (20.0, PL1_WINDOW_S))


if __name__ == "__main__":
    unittest.main()
