"""Why a card sold as «16 GB» shows 15.9 GiB.

A Radeon RX 9070 XT reads 15.9 GiB, as LACT's 16 304 MiB: the card carries
16 GiB and its firmware keeps 80 MiB before the driver sees it. Hovering the
total says so, with what is kept.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import GpuMemory
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados


class TestTheTip(unittest.TestCase):

    def test_the_9070_xt(self):
        gpu = next(g for g in shared_snapshot(EQUIPOS / "5800x3d").gpus if g.driver == "amdgpu")
        self.assertEqual(gpu.memory.total_bytes, 16304 * 1024 ** 2)
        self.assertEqual(render.vram_tip(gpu), _("gpu.tip.vram.kept").format(
            total=f"{render.thousands(16304)} MiB", chips=16, kept="80 MiB"))

    def test_on_its_page(self):
        qt.app()
        snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            from silux.ui.pages.graphics import GpuSection
            section = window.stack.currentWidget().findChildren(GpuSection)[0]
            shown = section.memory._values[_("gpu.vram.total")]
            self.assertIn(render.vram_tip(snapshot.gpus[0]), shown.toolTip())

    def test_nothing_to_say(self):
        gpu = shared_snapshot(EQUIPOS / "ryzen3-4100").gpus[0]
        self.assertEqual(gpu.memory.total_bytes, 2 * 1024 ** 3)      # a whole 2 GiB
        self.assertIsNone(render.vram_tip(gpu))
        whole = dataclasses.replace(gpu, memory=GpuMemory(total_bytes=3 * 1024 ** 3 - 1))
        self.assertIsNone(render.vram_tip(whole))                     # under a MiB

    def test_no_integrated_card_has_one(self):
        for folder in volcados():
            for gpu in shared_snapshot(folder).gpus:
                if gpu.integrated:
                    with self.subTest(folder.name, gpu=gpu.name):
                        self.assertIsNone(render.vram_tip(gpu))


if __name__ == "__main__":
    unittest.main()
