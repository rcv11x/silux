"""A Radeon's memory clock as GPU-Z and TechPowerUp give it, the same in
the clock tile and in Clocks: the RX 9070 XT's tile read «memoria 2.50 GHz»
and its Clocks «1.26 GHz». amdgpu gives GDDR6's clock as its data rate over
16 (1258 MHz); GPU-Z, over 8 (2518 MHz, «20.1 Gbps effective»)."""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestTheRadeonsMemoryClock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")

    def test_on_its_page(self):
        gpu = self.snapshot.gpus[0]
        self.assertEqual((gpu.memory.kind, gpu.clocks.memory_hz), ("GDDR6", 1_258_000_000))
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("Gráficos")
            qt.app().processEvents()
            section = window.stack.currentWidget()._sections[0]
            clocks = section.clocks._values
            self.assertEqual(clocks[_("gpu.clock.memory")].full_text(),
                             _("gpu.clock.memrate").format(clock="2516 MHz", rate="20.1 Gbps"))
            self.assertEqual(clocks[_("gpu.clock.memmax")].full_text(), "2516 MHz")
            self.assertEqual(section.tile_clock.detail.full_text(),
                             _("gpu.tile.memclock").format(valor="2516 MHz"))

    def test_an_nvidia_stays_as_nvidia_smi_gives_it(self):
        gpu = next(g for g in shared_snapshot(EQUIPOS / "i7-12700kf").gpus
                   if g.vendor == "NVIDIA")
        self.assertEqual(render.gpu_memory_clock(gpu, gpu.clocks.memory_hz, rate=True),
                         render.hz(gpu.clocks.memory_hz))


if __name__ == "__main__":
    unittest.main()
