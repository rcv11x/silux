"""Idle states taken from the firmware's ACPI table are not the processor's.

A desktop i7-10700F (Comet Lake-S) read «C2 es el reposo más hondo de este
procesador», and the author's T14 «C3». Their states are «C1_ACPI» and
«C2_ACPI»: intel_idle took them from the board's _CST table
(intel_idle_init_cstates_acpi), and the number is ACPI's level.

A dump keeps one reading of cpuidle and the provider does not compute a
residency from it: here the states its dump enumerates, through the
provider's own residency, with two readings as a live machine makes them.
"""

import dataclasses
import pathlib
import unittest

from silux import render, volcado
from silux.i18n import _
from silux.model import IdleState
from silux.providers.cpuidle import CpuIdle
from tests import pantalla, qt
from tests.test_equipos import foto

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


def _residency(dump: str) -> list[IdleState]:
    with volcado.mounted(EQUIPOS / dump):
        estados = CpuIdle()._enumerate()
    antes = {(cpu, nombre): 0 for cpu, lista in estados.items() for _b, nombre, _d in lista}
    # In one second, 10 % in C1 and 80 % in the deepest, every thread alike.
    despues = {(cpu, nombre): {"C1_ACPI": 100_000, "C2_ACPI": 800_000}.get(nombre, 0)
               for cpu, nombre in antes}
    return CpuIdle.residency(antes, despues, 1.0, estados)


class TestTheBoardsAcpiStates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.estados = _residency("i7-10700f")

    def test_they_are_said_to_be_acpis(self):
        self.assertEqual(self.estados[-1].name, "C2_ACPI")
        self.assertEqual(render.idle_deepest(self.estados),
                         _("cpu.idle.deepest.acpi").format(nombre="C2", bajo="80", alto="80"))

    def test_on_the_cpu_page(self):
        f = foto(EQUIPOS / "i7-10700f")[0]
        f = dataclasses.replace(f, cpu=dataclasses.replace(f.cpu, idle_states=tuple(self.estados)))
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("CPU")
            self.app.processEvents()
            nota = ventana.cpu_page.idle_note.text()
        self.assertEqual(nota, _("cpu.idle.deepest.acpi").format(nombre="C2", bajo="80", alto="80"))

    def test_a_processors_own_states_keep_their_wording(self):
        estados = (IdleState(name="C1", percent=10, low=5, high=15),
                   IdleState(name="C10", percent=80, low=70, high=90))
        self.assertEqual(render.idle_deepest(estados),
                         _("cpu.idle.deepest").format(nombre="C10", bajo="70", alto="90"))


if __name__ == "__main__":
    unittest.main()
