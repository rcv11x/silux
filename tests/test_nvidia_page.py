"""An NVIDIA's page, from what NVML answered for a tester's RTX 4060.

About twenty rows read «—»: what NVML does not publish on a GeForce and what
an NVIDIA does not have. The card is the one in that report: AD107, 3072
CUDA cores, 8 GB on a 128-bit bus, 37 °C, its fan stopped, 115 W of limit.
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.model import Gpu, GpuClocks, GpuMemory, PcieLink
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def rtx_4060() -> Gpu:
    return Gpu(index=0, vendor="NVIDIA", name="GeForce RTX 4060", codename="AD107",
               driver="nvidia", driver_version="595.104.02", vendor_id=0x10DE,
               device_id=0x2882, pci_slot="0000:01:00.0", drm_node="card0",
               integrated=False, primary=True, compute_units=3072,
               temp_c=37.0, fan_percent=0.0, power_cap_w=115.0, throttled=False,
               busy_percent=0.0, memory_busy_percent=2.0,
               memory=GpuMemory(total_bytes=8188 * 1024 ** 2, used_bytes=1296 * 1024 ** 2,
                                bus_bits=128),
               clocks=GpuClocks(core_hz=210_000_000, core_max_hz=3_105_000_000,
                                memory_hz=405_000_000, memory_max_hz=8_501_000_000),
               link=PcieLink(current_speed_gts=2.5, current_width=8,
                             max_speed_gts=8.0, max_width=8))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestTheNvidiaPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _section(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        f = dataclasses.replace(foto(EQUIPOS / "5800x3d")[0], gpus=(rtx_4060(),))
        pagina = GraphicsPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(f)
        self.app.processEvents()
        return pagina._sections[0]

    def test_what_nvml_does_not_publish_is_said_not_dashed(self):
        seccion = self._section()
        for grid, clave in ((seccion.card, "gpu.field.rops"), (seccion.memory, "gpu.vram.type"),
                            (seccion.clocks, "SoC"), (seccion.sensors, "gpu.sensor.vrgfx"),
                            (seccion.sensors, "gpu.sensor.voltage")):
            with self.subTest(fila=clave):
                self.assertFalse(grid._values[_(clave)].isVisibleTo(grid))
        self.assertIn(_("gpu.na.nvidia.sensors"), seccion.sensors_pie.text())
        self.assertIn(_("gpu.na.nvidia.memory"), seccion.memory_pie.text())

    def test_what_it_does_publish_stays(self):
        seccion = self._section()
        for grid, clave in ((seccion.card, "gpu.field.compute"), (seccion.memory, "gpu.vram.bus"),
                            (seccion.clocks, "gpu.clock.coremax"), (seccion.sensors, "gpu.sensor.fan")):
            with self.subTest(fila=clave):
                self.assertTrue(grid._values[_(clave)].isVisibleTo(grid))


if __name__ == "__main__":
    unittest.main()
