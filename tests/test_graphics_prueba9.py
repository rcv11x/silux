"""What a Radeon's page says about its driver, caches and fan.

The version the libraries give is Mesa's, the userspace driver, not
amdgpu's; each library names its own Mesa driver; the L2 and the Infinity
Cache come from amdgpu's ioctl on RDNA 3 and later; a stopped fan says so
with its revolutions; the power limit in force goes with the factory one.
"""

import unittest

from silux import render
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados


class TestTheRadeon(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshot = shared_snapshot(EQUIPOS / "5800x3d")
        cls.gpu = cls.snapshot.gpus[0]

    def test_the_model(self):
        g = self.gpu
        self.assertEqual((g.driver, g.userspace_driver, g.isa), ("amdgpu", "Mesa", "gfx1201"))
        self.assertRegex(g.driver_version, r"^\d+\.\d+\.\d+$")
        self.assertEqual((g.l2_cache_bytes, g.infinity_cache_bytes), (8 * 1024**2, 64 * 1024**2))
        mesa = f"Mesa {g.driver_version}"
        self.assertEqual({a.name: render.api_driver(a, g) for a in g.apis},
                         {"Vulkan": f"radv ({mesa})", "OpenGL": f"radeonsi ({mesa})",
                          "OpenCL": f"rusticl ({mesa})"})

    def test_on_the_page(self):
        from silux.ui.pages.graphics import GpuSection

        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("Gráficos")
            section = window.stack.currentWidget().findChildren(GpuSection)[0]
            card, inventory = section.card._values, section.inventory._values
            self.assertEqual(card[_("gpu.field.driverver")].full_text(),
                             f"Mesa {self.gpu.driver_version}")
            self.assertEqual(card[_("gpu.field.l2")].full_text(), render.size(8 * 1024**2))
            self.assertEqual(inventory[_("gpu.field.isa")].full_text(), "gfx1201")
            # Its video BIOS's version and build date, from amdgpu's ioctl.
            self.assertEqual(inventory[_("gpu.field.vbiosver")].full_text(),
                             "023.008.000.068.000001 · 2024-12-04")
            fan = section.sensors._values[_("gpu.sensor.fan")]
            self.assertEqual(fan.full_text(), _("fan.stopped.rpm"))
            self.assertIn(_("gpu.tip.fan.zerorpm"), fan.toolTip())
            self.assertTrue(section.clocks._values[_("gpu.clock.memeff")].isHidden())
            limit = section.sensors._values[_("gpu.sensor.powercap")].full_text()
            self.assertTrue(limit.startswith("340 W · "), limit)
            # For experts: every DPM table with its step in use, the power
            # profile and OverDrive off, with how to turn it on.
            expert = section.expert._values
            self.assertRegex(expert[_("gpu.expert.fclk")].full_text(),
                             r"^313 · (\d+ · )*▸\d+( · \d+)* MHz$")
            self.assertEqual(expert[_("gpu.expert.sclk")].full_text(),
                             "500 · 2520 MHz · " + _("gpu.expert.now.asleep"))
            self.assertEqual(expert[_("gpu.expert.profile")].full_text(),
                             _("gpu.profile.bootup_default") + " (BOOTUP_DEFAULT)")
            self.assertEqual(expert[_("gpu.expert.overdrive")].full_text(), _("gpu.expert.off"))
            self.assertIn(_("gpu.expert.off.how"), section.expert_pie.text())
            self.assertTrue(expert[_("gpu.expert.vclk")].isHidden())

    def test_no_expert_section_without_amdgpu(self):
        from silux.ui.pages.graphics import GpuSection

        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i5-10400")) as window:
            window.select_section("Gráficos")
            section = window.stack.currentWidget().findChildren(GpuSection)[0]
            self.assertTrue(section.expert_fold.isHidden())


class TestEveryCard(unittest.TestCase):

    def test_mesa_named_where_it_is_mesa(self):
        for folder in volcados():
            snapshot = shared_snapshot(folder)
            for gpu in snapshot.gpus:
                if not gpu.driver_version:
                    continue
                with self.subTest(folder.name, card=gpu.name):
                    version = render.gpu_driver_version(gpu)
                    if gpu.driver == "nvidia":
                        self.assertFalse(version.startswith("Mesa"), version)
                    elif gpu.driver in ("amdgpu", "i915", "xe", "nouveau"):
                        self.assertTrue(version.startswith("Mesa "), version)

    def test_older_radeons_have_no_cache_figures(self):
        # The fields are gfx11 and later: a Polaris' are zero, not «0 B».
        gpu = shared_snapshot(EQUIPOS / "ryzen3-4100").gpus[0]
        self.assertEqual((gpu.l2_cache_bytes, gpu.infinity_cache_bytes), (None, None))


if __name__ == "__main__":
    unittest.main()
