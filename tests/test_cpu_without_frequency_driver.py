"""Without cpufreq the processor's frequency is not fixed.

An Athlon 3000G without a frequency driver: with permissions its base,
3.50 GHz, comes from the P-state registers, and with no turbo and no kernel
minimum the frequency tile read «fija en 3.50 GHz» while its threads ran
between 2.3 and 3.5. Those come from /proc/cpuinfo: the effective frequency
the processor measures (APERF/MPERF) on a busy thread, the nominal one on an
idle thread.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


def _with_permissions(snapshot, base_hz: int):
    """As with permissions: the base from the P-state registers, which are
    then the frequency (`msr_pstate`), and no turbo, so the base is the
    highest (`turbo`)."""
    types = tuple(dataclasses.replace(t, clocks=dataclasses.replace(
        t.clocks, base_hz=base_hz, max_turbo_hz=base_hz, current_from="msr"))
        for t in snapshot.cpu.types)
    return dataclasses.replace(snapshot, cpu=dataclasses.replace(snapshot.cpu, types=types))


class TestTheAthlon(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshot = _with_permissions(shared_snapshot(EQUIPOS / "athlon-3000g"),
                                         3_500_000_000)

    def test_the_dump_is_the_case(self):
        clocks = shared_snapshot(EQUIPOS / "athlon-3000g").cpu.types[0].clocks
        self.assertEqual(clocks.current_from, "cpuinfo")
        self.assertIs(clocks.turbo_supported, False)

    def test_not_fixed_and_where_each_threads_comes_from(self):
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("CPU")
            page = window.stack.currentWidget()
            detail = page.live.tile_freq.detail.text()
            texts = pantalla.textos_de(page)
        self.assertEqual(detail, _("cpu.tile.upto").format(valor=render.hz(3_500_000_000)))
        self.assertTrue(any(_("cpu.clocks.nodriver.msr") in t for t in texts))
        for key in ("cpu.clocks.nodriver.msr", "cpu.clocks.nodriver.cpuinfo"):
            self.assertIn("APERF/MPERF", _(key))


if __name__ == "__main__":
    unittest.main()
