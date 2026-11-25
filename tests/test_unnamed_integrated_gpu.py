"""An AMD integrated GPU nobody names is not titled by its codename.

From a report: a Ryzen 9 7900 with an older pci.ids, which calls its
integrated GPU (1002:164e) just «Raphael», without the marketing name in
brackets. Its brand («AMD Ryzen 9 7900 12-Core Processor») names no Radeon,
and RADV calls the GPU by that brand. The card was titled «Raphael», with
its codename row saying neither its driver nor pci.ids gave one.
"""

import unittest
from unittest import mock

from silux import amdgpu
from silux.providers import derived, drm, gpu_apis, hwmon, pci
from silux.providers.base import Draft
from tests import qt
from tests.test_gpu import BancoDrm, _write

BRAND = "AMD Ryzen 9 7900 12-Core Processor"
# What the report's Vulkan listed for it.
VULKAN = {"name": f"{BRAND} (RADV RAPHAEL_MENDOCINO)", "api_version": "1.4.335",
          "instance_version": "1.4.341", "driver_version": 109051912,
          "vendor_id": 0x1002, "device_id": 0x164E, "kind": "integrada",
          "device_memory_bytes": 22172434432}


class TestTheRyzen9_7900(BancoDrm):

    def setUp(self):
        super().setUp()
        device = self.tarjeta(0, ranura="0000:0c:00.0", vendor="0x1002", device="0x164e",
                              subsystem_vendor="0x1043", subsystem_device="0x8877",
                              revision="0xc4", boot_vga="0", **{"class": "0x030000"})
        (self.root / "amdgpu").mkdir()
        (device / "driver").symlink_to(self.root / "amdgpu")
        _write(device / "drm" / "renderD128" / "dev", "226:128")
        # Its hwmon and usage, from the same annex.
        for name, value in (("name", "amdgpu"), ("temp1_label", "edge"),
                            ("temp1_input", "34000"), ("in0_label", "vddgfx"),
                            ("in0_input", "1310"), ("power1_label", "PPT"),
                            ("power1_input", "42133000")):
            _write(device / "hwmon" / "hwmon6" / name, value)
        (device / "hwmon" / "hwmon6" / "device").symlink_to(device.resolve())
        (self.root / "class_hwmon").mkdir()
        (self.root / "class_hwmon" / "hwmon6").symlink_to(device / "hwmon" / "hwmon6")
        _write(device / "gpu_busy_percent", "0")

    def _sensors(self) -> Draft:
        draft = self._collect()
        with mock.patch.object(hwmon, "HWMON", self.root / "class_hwmon"):
            drm.GpuState().collect(draft)
            hwmon.HwmonSensors().collect(draft)
            derived.DerivedSensors().collect(draft)
        return draft

    def _collect(self, pci_ids_name="Raphael") -> Draft:
        answer = amdgpu.DeviceInfo(device_id=0x164E, is_apu=True)
        real = drm.sysroot.recorded

        def ioctl(space, key, fn, *args, **kwargs):
            # Nothing reaches the GPU of whoever runs the suite.
            if space.startswith("amdgpu"):
                return answer if space == "amdgpu" else None
            return real(space, key, fn, *args, **kwargs)

        draft = Draft()
        draft.type_for("general")["brand"] = BRAND
        names = {(0x1002, 0x164E): ("Advanced Micro Devices, Inc. [AMD/ATI]", pci_ids_name)}
        with mock.patch.object(drm.sysroot, "recorded", ioctl), \
                mock.patch.object(drm.amdgpu, "render_node", return_value="/dev/dri/renderD128"), \
                mock.patch.object(drm.pciids, "lookup", return_value=names), \
                mock.patch.object(gpu_apis.gpuapi, "query", lambda: {"vulkan": [VULKAN]}), \
                mock.patch.object(pci, "DEVICES", str(self.root / "pci0000:00")):
            drm.DrmGpus().collect(draft)
            gpu_apis.GpuApis().collect(draft)
            pci.PciDevices().collect(draft)
        return draft

    def test_the_codename_is_a_codename(self):
        gpu = self._collect().gpus[0]
        self.assertTrue(gpu["integrated"])
        self.assertIsNone(gpu["name"])
        self.assertEqual(gpu["codename"], "Raphael")

    def test_nor_is_it_named_after_its_processor(self):
        snapshot = self._collect().freeze()
        self.assertNotIn(BRAND, snapshot.gpus[0].display_name or "")
        self.assertEqual(snapshot.gpus[0].apis[0].name, "Vulkan")

    def test_a_newer_pci_ids_names_it(self):
        gpu = self._collect(pci_ids_name="Raphael [Radeon 610M]").gpus[0]
        self.assertEqual((gpu["name"], gpu["codename"]), ("Radeon 610M", "Raphael"))

    def test_on_the_graphics_page(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = qt.app()
        page = GraphicsPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.apply(self._collect().freeze())
        section = page._sections[0]
        self.assertEqual(section.title.text(), _("gpu.unnamed").format(
            brand="AMD", kind=_("gpu.unnamed.integrated")))
        self.assertEqual(section.card.value_label(_("gpu.field.codename")).full_text(),
                         "Raphael")

    def test_sensors_call_it_the_same(self):
        from silux.i18n import _

        name = _("gpu.unnamed").format(brand="AMD", kind=_("gpu.unnamed.integrated"))
        devices = {(s.chip, s.device) for s in self._sensors().sensors
                   if s.device_key == "gpu:0000:0c:00.0"}
        # hwmon's chip and what derives from the driver, under one name.
        self.assertEqual(devices, {("amdgpu", name), ("drm", name)})

    def test_the_board_calls_it_the_same(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.board import BoardPage

        app = qt.app()
        page = BoardPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.apply(self._collect().freeze())
        rows = [[cell.full_text() for cell in cells] for cells in page.pci._cells]
        self.assertEqual([row[1] for row in rows], [_("gpu.unnamed").format(
            brand="AMD", kind=_("gpu.unnamed.integrated"))])


if __name__ == "__main__":
    unittest.main()
