"""An RTX 3070 on nouveau read 8.2 GiB of memory: with no NVML, it comes
from Vulkan, and NVK lists the CPU's 256 MiB window into VRAM as a heap of
its own besides the VRAM it maps (Mesa 25.0.7, `nvk_physical_device.c`).
Its BAR 1 is that window, in the PCI node's `resource`."""

import unittest

from silux import render
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestNouveauVram(unittest.TestCase):
    def test_the_3070_has_its_8_gib(self):
        gpu = next(g for g in shared_snapshot(EQUIPOS / "ryzen7-5800x-nouveau").gpus
                   if g.driver == "nouveau")
        self.assertEqual(gpu.memory.total_bytes, 8 * 1024 ** 3)
        self.assertEqual(render.size(gpu.memory.total_bytes), "8 GiB")


if __name__ == "__main__":
    unittest.main()
