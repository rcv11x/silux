"""An AMD card whose driver doesn't publish a reading hides it and says so.

The first Polaris in the suite (an RX 550) showed ten dashes: hotspot,
memory temperature, regulators, SoC and memory voltages, throttle state,
SoC clock, effective memory rate and its memory chips' maker. Older AMD
generations have no firmware telemetry: those never come, they aren't
unread. And its link ran at full speed with half the lanes, which the note
put down to idling.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto


def _section(f):
    from silux.ui.pages.graphics import GpuSection
    qt.app()
    gestor = pantalla.Ventana(f)
    ventana = gestor.__enter__()
    ventana.select_section("Gráficos")
    return gestor, ventana.stack.currentWidget().findChildren(GpuSection)[0]


class TestAPolaris(unittest.TestCase):

    def setUp(self):
        self.f = foto(EQUIPOS / "ryzen3-4100")[0]
        self.gpu = self.f.gpus[0]
        self.gestor, self.section = _section(self.f)

    def tearDown(self):
        self.gestor.__exit__(None, None, None)

    def test_what_its_driver_doesnt_publish_is_hidden_and_named(self):
        for tarjeta, claves in ((self.section.sensors, ("gpu.sensor.state", "gpu.sensor.hotspot",
                                                          "gpu.sensor.vrgfx", "gpu.sensor.vsoc",
                                                          "gpu.sensor.videouse")),
                                (self.section.clocks, ("SoC", "gpu.clock.memeff")),
                                (self.section.memory, ("gpu.vram.chips",))):
            for clave in claves:
                with self.subTest(campo=clave):
                    self.assertFalse(tarjeta._values[_(clave)].isVisibleTo(self.section))
        pie = self.section.sensors_pie.text()
        self.assertTrue(pie.startswith(_("gpu.na.amd.silent").split("{")[0]))
        for nombre in ("gpu.na.piece.hotspot", "gpu.na.piece.vrs", "gpu.na.piece.state"):
            self.assertIn(_(nombre), pie)
        # And what it does publish stays.
        for clave in ("gpu.sensor.fan", "gpu.sensor.voltage"):
            self.assertTrue(self.section.sensors._values[_(clave)].isVisibleTo(self.section))

    def test_a_link_at_full_speed_with_fewer_lanes_is_not_put_down_to_idling(self):
        self.assertTrue(self.gpu.link.fewer_lanes_at_full_speed)
        self.assertEqual(render.pcie_note(self.gpu.link), _("pcie.now.lanes").format(
            actual="PCIe 3.0 × 4", max="PCIe 3.0 × 8"))

    def test_a_zero_minimum_is_no_power_range(self):
        self.assertEqual(render.gpu_factory_power_limit(self.gpu), "35 W")


class TestAnAmdThatPublishesAll(unittest.TestCase):

    def test_nothing_hidden_nor_said(self):
        gestor, section = _section(foto(EQUIPOS / "5800x3d")[0])
        try:
            self.assertNotIn(_("gpu.na.amd.silent").split("{")[0], section.sensors_pie.text())
        finally:
            gestor.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
