"""What a Radeon's driver gives as zero when it measures nothing.

From a report: an RX 5500 XT (Navi 14) whose firmware table and hwmon give
0 for the memory's temperature and the three regulators'. The Graphics page
read «Memory chips: 0.0 °C» and three regulators at 0.0 °C. At rest its core's
rail is switched off and reads 6 mV, which the page showed as «0.006 V».
"""

import unittest
from unittest import mock

from silux import amdgpu, gpumetrics
from silux.providers import drm
from silux.providers.base import Draft
from tests import qt
from tests.test_gpu import BancoDrm, _write, _write_bytes

# The card's gpu_metrics (v1.3) as the report's annex dumped it, byte by byte.
RX_5500_XT_METRICS = bytes.fromhex(
    "78000103 2a002b00 00000000 00000000"
    "00000100 ffff0300 ffffffff ffffffff"
    "b8c80dc7 9d0a0000 00003100 6300ffff"
    "ffffffff ffff0000 fa016400 00000000"
    "ffffffff 00000000 00000800 5000ffff"
    "ffffffff ffffffff ffffffff ffffffff"
    "ffffffff ffffffff ffffffff ffffffff"
    "00000000 00000000")

# Its hwmon, from the same annex.
RX_5500_XT_HWMON = {
    "name": "amdgpu", "temp1_label": "edge", "temp1_input": "42000",
    "temp1_crit": "110000", "temp2_label": "junction", "temp2_input": "43000",
    "temp2_crit": "105000", "temp3_label": "mem", "temp3_input": "0",
    "temp3_crit": "105000", "in0_label": "vddgfx", "in0_input": "6",
    "fan1_input": "0", "pwm1": "0", "pwm1_max": "255",
    "power1_label": "PPT", "power1_average": "3000000", "power1_cap": "121000000",
    "freq1_label": "sclk", "freq1_input": "0",
}


class TestTheFirmwareTable(unittest.TestCase):

    def test_its_zeros_are_no_temperature(self):
        metrics = gpumetrics.parse(RX_5500_XT_METRICS)
        self.assertEqual(metrics.version, "1.3")
        self.assertEqual((metrics.temp_edge_c, metrics.temp_hotspot_c), (42.0, 43.0))
        self.assertEqual((metrics.temp_memory_c, metrics.temp_vr_gfx_c,
                          metrics.temp_vr_soc_c, metrics.temp_vr_mem_c),
                         (None, None, None, None))

    def test_but_its_other_zeros_are_readings(self):
        # The same table at rest: the engine idle and the fan stopped.
        metrics = gpumetrics.parse(RX_5500_XT_METRICS)
        self.assertEqual(metrics.gfx_activity_percent, 0.0)
        self.assertEqual(metrics.memory_activity_percent, 1.0)
        self.assertEqual(metrics.fan_rpm, 0)
        self.assertEqual(metrics.socket_power_w, 3.0)


class TestTheRx5500xt(BancoDrm):

    def setUp(self):
        super().setUp()
        device = self.tarjeta(0, ranura="0000:03:00.0", vendor="0x1002", device="0x7340",
                              subsystem_vendor="0x148c", subsystem_device="0x2401",
                              revision="0xc5", boot_vga="1", **{"class": "0x030000"})
        (self.root / "amdgpu").mkdir()
        (device / "driver").symlink_to(self.root / "amdgpu")
        _write(device / "drm" / "renderD128" / "dev", "226:128")
        for name, value in RX_5500_XT_HWMON.items():
            _write(device / "hwmon" / "hwmon3" / name, value)
        _write_bytes(device / "gpu_metrics", RX_5500_XT_METRICS)

    def _collect(self) -> Draft:
        answer = amdgpu.DeviceInfo(device_id=0x7340, is_apu=False)
        real = drm.sysroot.recorded

        def ioctl(space, key, fn, *args, **kwargs):
            # Nothing reaches the GPU of whoever runs the suite.
            if space.startswith("amdgpu"):
                return answer if space == "amdgpu" else None
            return real(space, key, fn, *args, **kwargs)

        draft = Draft()
        with mock.patch.object(drm.sysroot, "recorded", ioctl), \
                mock.patch.object(drm.amdgpu, "render_node", return_value="/dev/dri/renderD128"):
            drm.DrmGpus().collect(draft)
            drm.GpuState().collect(draft)
        return draft

    def test_its_idle_engine_is_at_0_percent(self):
        gpu = self._collect().gpus[0]
        self.assertEqual(gpu["busy_percent"], 0.0)
        self.assertEqual(gpu["fan_rpm"], 0)

    def test_no_zero_degrees(self):
        gpu = self._collect().gpus[0]
        self.assertEqual((gpu["temp_c"], gpu["hotspot_c"]), (42.0, 43.0))
        for field in ("memory_temp_c", "vr_gfx_c", "vr_soc_c", "vr_memory_c"):
            with self.subTest(field):
                self.assertIsNone(gpu[field])

    def test_the_page_hides_them_and_says_so(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = qt.app()
        page = GraphicsPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        page.apply(self._collect().freeze())
        section = page._sections[0]
        for row in ("gpu.sensor.memtemp", "gpu.sensor.vrgfx", "gpu.sensor.vrsoc",
                    "gpu.sensor.vrmem"):
            with self.subTest(row):
                self.assertTrue(section.sensors.value_label(_(row)).isHidden())
        self.assertFalse(section.sensors.value_label(_("gpu.sensor.hotspot")).isHidden())
        foot = section.sensors_pie.text()
        self.assertIn(_("gpu.na.piece.memtemp"), foot)
        self.assertIn(_("gpu.na.piece.vrs"), foot)

    def test_its_switched_off_rail_is_at_rest(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.graphics import GraphicsPage

        app = qt.app()
        page = GraphicsPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(page.deleteLater)
        snapshot = self._collect().freeze()
        # The reading stays as the driver gave it; only how it is said changes.
        self.assertEqual(snapshot.gpus[0].voltage_v, 0.006)
        page.apply(snapshot)
        self.assertEqual(
            page._sections[0].sensors.value_label(_("gpu.sensor.voltage")).full_text(),
            _("gpu.clock.idle"))


class TestTheCoreVoltage(unittest.TestCase):

    def test_a_working_core_shows_its_voltage(self):
        from silux import render

        # An RX 9070 XT and an RX 550 at rest, from our dumps.
        self.assertEqual(render.gpu_voltage(0.693), "0.693 V")
        self.assertEqual(render.gpu_voltage(0.781), "0.781 V")
        self.assertEqual(render.gpu_voltage(None), render.DASH)


class TestOnTheSensorsPage(unittest.TestCase):
    """Sensors read «Core · 0.006 V» while Graphics said at rest."""

    def _row(self, millivolts: str, label: str = "vddgfx") -> str:
        import os
        import pathlib
        import tempfile

        from silux import sysroot
        from silux.providers.hwmon import HwmonSensors
        from silux.settings import Preferences
        from silux.tracking import Tracker
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = pathlib.Path(tmp.name) / "sys/class/hwmon/hwmon3"
        for name, value in {**RX_5500_XT_HWMON, "in0_input": millivolts,
                            "in0_label": label}.items():
            _write(folder / name, value)
        draft = Draft()
        with mock.patch.dict(os.environ, {"SILUX_SYSROOT": tmp.name}):
            sysroot.forget()
            self.addCleanup(sysroot.forget)
            HwmonSensors().collect(draft)
        app = qt.app()
        page = MonitorPage(theme.palette_for(app, "dark"), Preferences().normalized(),
                           Tracker())
        self.addCleanup(page.deleteLater)
        page.apply(draft.freeze())
        return page.tree._rows["amdgpu/in0"].text(1)

    def test_its_switched_off_rail_is_at_rest(self):
        from silux.i18n import _

        self.assertEqual(self._row("6"), _("gpu.clock.idle"))

    def test_a_working_one_shows_its_voltage(self):
        self.assertEqual(self._row("781").strip(), "0.781 V")

    def test_whichever_label_names_the_core(self):
        """hwmon names «vddc» the core as it does «vddgfx» (`GPU_LABELS`)."""
        from silux.i18n import _

        self.assertEqual(self._row("6", label="vddc"), _("gpu.clock.idle"))
        # The northbridge's is not the core's.
        self.assertEqual(self._row("6", label="vddnb").strip(), "0.006 V")


if __name__ == "__main__":
    unittest.main()
