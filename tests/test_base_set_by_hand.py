"""A Ryzen 7 5800X with its base set to 4.2 GHz in the BIOS and Core
Performance Boost off (Felix's prueba13 report).

The firmware took the `cpb` flag away and `cpufreq/boost` reads 0: turbo
is off, not missing, since AMD lists a 4.7 GHz boost for the model. And
amd-pstate worked its maximum out from the firmware's base (4200 × 166 /
130 = 5.36 GHz): no maximum the kernel derives from a base set by hand is
the processor's, so neither shows and a note says the base, AMD's, and
AMD's boost.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestBaseSetByHand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = shared_snapshot(EQUIPOS / "ryzen7-5800x")
        cls.clocks = cls.snapshot.cpu.types[0].clocks

    def test_turbo_is_off_not_missing(self):
        self.assertIs(self.clocks.turbo_supported, True)
        self.assertIs(self.clocks.turbo_enabled, False)
        self.assertEqual(render.turbo(self.clocks), _("board.off"))
        self.assertNotIn(_("cpu.clocks.noturbo"), render.clocks_footnote(self.clocks) or "")

    def test_no_maximum_worked_out_from_that_base(self):
        self.assertEqual(self.clocks.base_hz, 4_200_000_000)
        self.assertIsNone(self.clocks.max_hz)
        self.assertIsNone(self.clocks.max_turbo_hz)
        note = next(n for n in self.snapshot.notes if n.key == "prov.cppc.basechanged")
        for figure in ("4.20 GHz", "3.80 GHz"):
            self.assertIn(figure, note.message)
        for figure in ("5.36 GHz", "4.70 GHz"):
            self.assertIn(figure, note.hint)

    def test_on_the_page_and_the_card_to_share(self):
        from silux.ui import tarjeta
        from tests.test_interface_language import visible_texts

        app = qt.app()
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("CPU")
            geometry.settle(app)
            texts = " ".join(visible_texts(window.stack.currentWidget()))
        # Only the note names the kernel's figure, to say what it is.
        self.assertNotIn("– 5.36", texts)
        self.assertNotIn(_("cpu.clock.maxkernel"), texts)
        self.assertNotIn(_("cpu.clock.maxsilicon"), texts)
        self.assertNotIn(_("cpu.clocks.noturbo"), texts)
        self.assertIn(_("cpu.clock.turbo"), texts)
        rows = " ".join(" ".join(row) for row in tarjeta._fila(self.snapshot))
        self.assertNotIn("5.36", rows)

    def test_the_base_row_says_it_was_set_in_the_bios(self):
        # «Base 4.20 GHz» alone read as the processor's own base.
        self.assertEqual((self.clocks.factory_base_hz, self.clocks.factory_boost_hz),
                         (3_800_000_000, 4_700_000_000))
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("CPU")
            geometry.settle(qt.app())
            section = next(iter(window.stack.currentWidget()._sections.values()))
            base = section.clocks._values[_("cpu.clock.base")].full_text()
        self.assertEqual(base, _("cpu.clock.base.set").format(
            base=render.clock_and_multiplier(4_200_000_000, self.clocks.base_multiplier),
            factory="3.80 GHz"))

    def test_a_base_as_amd_lists_it_keeps_its_maximums(self):
        clocks = shared_snapshot(EQUIPOS / "5800x3d").cpu.types[0].clocks
        self.assertEqual(round(clocks.max_turbo_hz / 1e7), 455)
        self.assertIsNone(clocks.factory_base_hz)
        self.assertEqual(render.base_clock(clocks),
                         render.clock_and_multiplier(clocks.base_hz, clocks.base_multiplier))


if __name__ == "__main__":
    unittest.main()
