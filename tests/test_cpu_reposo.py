"""CPU: residencia en los estados de reposo, y los límites de potencia a la vista.

Los nombres y descripciones de los estados son los del 5800X3D (kernel
7.3.4): POLL, C1 y C2. Los microsegundos son dos lecturas con un segundo
entre medias, como las da `cpuidle/stateN/time`.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import IdleState
from silux.providers.base import Draft
from silux.providers.cpuidle import CpuIdle
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

BASE = "/sys/devices/system/cpu/cpu{}/cpuidle/state{}/"
ESTADOS = (("POLL", "CPUIDLE CORE POLL IDLE"), ("C1", "ACPI FFH MWAIT 0x0"),
           ("C2", "ACPI IOPORT 0x414"))


def _equipo(tiempos: dict) -> dict:
    """`tiempos`: hilo → (µs en POLL, en C1, en C2)."""
    archivos = {}
    for cpu, micros in tiempos.items():
        for n, ((nombre, descripcion), valor) in enumerate(zip(ESTADOS, micros)):
            archivos[BASE.format(cpu, n) + "name"] = nombre + "\n"
            archivos[BASE.format(cpu, n) + "desc"] = descripcion + "\n"
            archivos[BASE.format(cpu, n) + "time"] = f"{valor}\n"
    return archivos


class TestLaResidencia(unittest.TestCase):

    def test_sale_de_restar_dos_lecturas(self):
        estados = {0: [("", n, d) for n, d in ESTADOS], 1: [("", n, d) for n, d in ESTADOS]}
        antes = {(0, "POLL"): 100, (0, "C1"): 1_000_000, (0, "C2"): 9_000_000,
                 (1, "POLL"): 0, (1, "C1"): 2_000_000, (1, "C2"): 5_000_000}
        despues = {(0, "POLL"): 100, (0, "C1"): 1_100_000, (0, "C2"): 9_800_000,
                   (1, "POLL"): 0, (1, "C1"): 2_300_000, (1, "C2"): 5_500_000}
        salida = CpuIdle.residency(antes, despues, 1.0, estados)
        self.assertEqual(salida, [
            IdleState("POLL", "CPUIDLE CORE POLL IDLE", 0.0, 0.0, 0.0),
            IdleState("C1", "ACPI FFH MWAIT 0x0", 20.0, 10.0, 30.0),
            IdleState("C2", "ACPI IOPORT 0x414", 65.0, 50.0, 80.0)])

    def test_la_primera_lectura_solo_pone_la_referencia(self):
        """Con el equipo de quien ejecuta la suite, si tiene cpuidle: no se
        exige ningún estado concreto, solo la forma."""
        import time

        proveedor = CpuIdle()
        if not proveedor.available():
            self.skipTest("este equipo no publica cpuidle")
        draft = Draft()
        proveedor.collect(draft)
        self.assertNotIn("idle_states", draft.cpu_extra)
        time.sleep(0.05)
        draft = Draft()
        proveedor.collect(draft)
        estados = draft.cpu_extra.get("idle_states", [])
        self.assertTrue(all(0.0 <= e.percent <= 100.0 and e.low <= e.high for e in estados))

    def test_en_un_equipo_volcado_no_sale_porque_solo_hay_una_lectura(self):
        proveedor = CpuIdle()
        with arbol(_equipo({0: (0, 1_000_000, 9_000_000)})):
            self.assertTrue(proveedor.available())
            for _vuelta in range(2):
                draft = Draft()
                proveedor.collect(draft)
            self.assertNotIn("idle_states", draft.cpu_extra)

    def test_un_contador_que_retrocede_no_da_porcentajes_negativos(self):
        estados = {0: [("", "C2", None)]}
        salida = CpuIdle.residency({(0, "C2"): 9_000_000}, {(0, "C2"): 100}, 1.0, estados)
        self.assertEqual(salida, [])

    def test_sin_cpuidle_no_esta_disponible(self):
        with arbol({"/proc/uptime": "1 1\n"}):
            self.assertFalse(CpuIdle().available())

    def test_la_barra_suma_cien_y_lo_activo_es_lo_que_sobra(self):
        estados = (IdleState("POLL", None, 0.0, 0.0, 0.0), IdleState("C1", None, 16.0, 10.0, 25.0),
                   IdleState("C2", None, 63.0, 45.0, 73.0))
        tramos = render.idle_segments(estados)
        self.assertEqual([(s.key, s.label, s.value) for s in tramos],
                         [("active", _("cpu.idle.active"), 21.0), ("C1", "C1", 16.0),
                          ("C2", "C2", 63.0)])
        self.assertAlmostEqual(sum(s.value for s in tramos), 100.0)
        self.assertEqual(render.idle_deepest(estados),
                         "C2 es el reposo más hondo de este procesador: entre el 45 % y el "
                         "73 % del tiempo, según el hilo.")

    def test_sin_la_etiqueta_que_el_kernel_pone_a_lo_que_saca_del_firmware(self):
        """Así los publica el i5-10400 de la oficina (kernel 7.3).

        `intel_idle` no tiene tabla propia para Comet Lake-S y toma los
        estados de la del firmware (ACPI `_CST`), y a esos les pone
        «_ACPI» detrás. En la barra salía «C2_ACPI».
        """
        estados = (IdleState("POLL", "CPUIDLE CORE POLL IDLE", 0.0, 0.0, 0.0),
                   IdleState("C1_ACPI", "ACPI FFH MWAIT 0x0", 3.0, 1.0, 5.0),
                   IdleState("C2_ACPI", "ACPI FFH MWAIT 0x33", 94.0, 66.0, 100.0))
        self.assertEqual([s.label for s in render.idle_segments(estados)],
                         [_("cpu.idle.active"), "C1", "C2"])
        # And they are said to be the board's, not this processor's.
        self.assertEqual(render.idle_deepest(estados),
                         _("cpu.idle.deepest.acpi").format(
                             nombre="C2", tiempo=_("cpu.idle.share.range").format(
                                 bajo="66", alto="100").capitalize()))
        # Lo que no es esa etiqueta se queda como está.
        self.assertEqual(render.idle_name("C1E"), "C1E")
        self.assertEqual(render.idle_name("C6"), "C6")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.amd = shared_snapshot(EQUIPOS / "5800x3d")
        cls.intel = shared_snapshot(EQUIPOS / "i5-10400")
        cls.reposo = (IdleState("POLL", "CPUIDLE CORE POLL IDLE", 0.0, 0.0, 0.0),
                      IdleState("C1", "ACPI FFH MWAIT 0x0", 16.0, 10.0, 25.0),
                      IdleState("C2", "ACPI IOPORT 0x414", 63.0, 45.0, 73.0))

    def _pagina(self, ventana):
        ventana.select_section("CPU")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.stack.currentWidget()

    def test_pl1_y_pl2_del_volcado_de_intel(self):
        self.assertEqual((self.intel.cpu.power.limit_long_w, self.intel.cpu.power.limit_short_w),
                         (65.0, 115.0))
        with pantalla.Ventana(self.intel) as ventana:
            pagina = self._pagina(ventana)
            self.assertTrue(pagina.energy_card.isVisible())
            self.assertEqual(pagina.limits._values[_("cpu.limit.pl1")].full_text(),
                             render.watts(65.0))
            self.assertEqual(pagina.limits._values[_("cpu.limit.pl2")].full_text(),
                             render.watts(115.0))
            self.assertFalse(pagina.energy_pie.isVisible())

    def test_en_amd_no_hay_limites_y_se_dice(self):
        con_reposo = dataclasses.replace(self.amd, cpu=dataclasses.replace(
            self.amd.cpu, idle_states=self.reposo))
        with pantalla.Ventana(con_reposo) as ventana:
            pagina = self._pagina(ventana)
            self.assertTrue(pagina.energy_card.isVisible())
            self.assertFalse(pagina.limits.isVisible())
            self.assertEqual(pagina.energy_pie.text(), _("cpu.limit.amd"))
            self.assertTrue(pagina.idle_bar.isVisible())
            self.assertIn("C2", pagina.idle_note.text())
            self.assertIn("73", pagina.idle_note.text())

    def test_el_reposo_llega_con_la_pagina_abierta(self):
        """La primera muestra no lo trae: sale en la segunda, sin salir."""
        with pantalla.Ventana(self.intel) as ventana:
            pagina = self._pagina(ventana)
            self.assertFalse(pagina.idle_bar.isVisible())
            ventana._on_sample(dataclasses.replace(self.intel, cpu=dataclasses.replace(
                self.intel.cpu, idle_states=self.reposo)))
            for _vez in range(4):
                self.app.processEvents()
            self.assertTrue(pagina.idle_bar.isVisible())
            self.assertTrue(pagina.idle_note.isVisible())


if __name__ == "__main__":
    unittest.main()
