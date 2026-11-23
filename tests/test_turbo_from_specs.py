"""A processor without turbo hides it, and says so, instead of a dash.

Some parts without turbo declare the «cpb» flag anyway, and without a
frequency driver nothing in the kernel says otherwise: the Clocks card read
«Turbo: —» and «Máxima (silicio): —» on a part that has neither. AMD's
specifications list those models with a base clock and no boost.
"""

import unittest

from silux import db
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot


class TestTheSpecs(unittest.TestCase):

    def test_listed_without_boost_with_boost_and_not_listed(self):
        self.assertIs(db.amd_turbo("AMD Athlon 3000G with Radeon Vega Graphics"), False)
        self.assertIs(db.amd_turbo("AMD Ryzen 7 5800X3D 8-Core Processor"), True)
        self.assertIsNone(db.amd_turbo("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz"))


class TestAPartWithoutTurbo(unittest.TestCase):

    def test_its_clocks_card(self):
        f = shared_snapshot(EQUIPOS / "athlon-3000g")
        reloj = f.cpu.types[0].clocks
        self.assertIs(reloj.turbo_supported, False)
        qt.app()
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("CPU")
            pagina = ventana.stack.currentWidget()
            from silux.ui.pages.cpu import TypeSection
            seccion = pagina.findChildren(TypeSection)[0]
            for clave in ("cpu.clock.turbo", "cpu.clock.maxsilicon"):
                with self.subTest(campo=clave):
                    self.assertFalse(seccion.clocks._values[_(clave)].isVisibleTo(pagina))
            self.assertIn(_("cpu.clocks.noturbo"), seccion.clocks_foot.text())

    def test_a_part_whose_kernel_publishes_its_boost_is_untouched(self):
        reloj = shared_snapshot(EQUIPOS / "5800x3d").cpu.types[0].clocks
        self.assertIsNot(reloj.turbo_supported, False)
        self.assertIsNotNone(reloj.turbo_enabled)


class TestNoTurboIsNotATurboOff(unittest.TestCase):
    """intel_pstate's `no_turbo` reads 1 on a part without turbo, and the
    Clocks card said «Turbo desactivado», in orange, over «Este procesador
    no tiene turbo»."""

    def test_in_every_dump(self):
        from silux import render
        from tests.test_equipos import volcados
        qt.app()
        off = _("clock.turbo.off").split("{")[0]
        for folder in volcados():
            snapshot = shared_snapshot(folder)
            with self.subTest(folder.name):
                for cpu_type in snapshot.cpu.types:
                    clocks = cpu_type.clocks
                    if clocks.turbo_supported is False:
                        self.assertIsNone(clocks.turbo_enabled)
                        self.assertIsNone(render.turbo_note(clocks))
                with pantalla.Ventana(snapshot) as ventana:
                    ventana.select_section("CPU")
                    textos = pantalla.textos_de(ventana.stack.currentWidget())
                if _("cpu.clocks.noturbo") in " ".join(textos):
                    self.assertFalse([t for t in textos if t.startswith(off)])

    def test_its_case(self):
        clocks = shared_snapshot(EQUIPOS / "celeron-g3900").cpu.types[0].clocks
        self.assertEqual((clocks.turbo_supported, clocks.turbo_enabled), (False, None))


if __name__ == "__main__":
    unittest.main()
