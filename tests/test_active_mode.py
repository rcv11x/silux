"""A screen's resolution is the mode it runs at, not the one it prefers.

A Sony TV preferred 1360 × 768 and ran at 1920 × 1080, and the monitors
table said 1360 × 768: that was the EDID's preferred mode. The running mode
comes from the kernel's modesetting (`drmmode`), recorded in the dumps; the
preferred one goes apart, and says so where it's all there is.
"""

import ctypes
import json
import unittest
from unittest import mock

from silux import drmmode, render, sysroot, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.model import Display
from silux.providers import drm
from tests import pantalla, qt
from tests.interval import fake_clock, next_snapshot
from tests.test_equipos import EQUIPOS, foto
from tests.test_interface_language import visible_texts


class TestTheIoctls(unittest.TestCase):
    """The structures and numbers of include/uapi/drm/drm.h and drm_mode.h."""

    def test_as_the_kernel_has_them(self):
        self.assertEqual([ctypes.sizeof(s) for s in (drmmode._CardResources, drmmode._ModeInfo,
                                                      drmmode._Crtc, drmmode._Encoder,
                                                      drmmode._Connector)],
                         [64, 68, 104, 20, 80])
        self.assertEqual([drmmode.GETRESOURCES, drmmode.GETCRTC, drmmode.GETENCODER,
                          drmmode.GETCONNECTOR],
                         [0xC04064A0, 0xC06864A1, 0xC01464A6, 0xC05064A7])
        self.assertEqual(drmmode.CONNECTOR_TYPES[11], "HDMI-A")
        self.assertEqual(drmmode.CONNECTOR_TYPES[14], "eDP")

    def test_the_refresh_from_the_pixel_clock(self):
        mode = drmmode._ModeInfo(clock=148500, htotal=2200, vtotal=1125, vrefresh=60)
        self.assertEqual(drmmode._refresh(mode), 60.0)
        ntsc = drmmode._ModeInfo(clock=148352, htotal=2200, vtotal=1125, vrefresh=60)
        self.assertEqual(drmmode._refresh(ntsc), 59.94)


class TestTheText(unittest.TestCase):

    TV = Display(connector="HDMI-A-1", connected=True, width=1360, height=768,
                 active_width=1920, active_height=1080, active_refresh_hz=60.0)
    SAME = Display(connector="DP-1", connected=True, width=2560, height=1440,
                   active_width=2560, active_height=1440)
    UNKNOWN = Display(connector="DP-2", connected=True, width=2560, height=1440)

    def test_the_cell_is_the_running_mode(self):
        self.assertEqual(render.display_resolution(self.TV), "1920 × 1080")
        # Unknown, the preferred one, named so.
        self.assertEqual(render.display_resolution(self.UNKNOWN),
                         _("gpu.display.preferred.only").format(res="2560 × 1440"))

    def test_the_foot_says_what_the_cell_is(self):
        self.assertEqual(render.displays_resolution_note([self.TV, self.SAME]),
                         _("gpu.displays.prefers").format(salida="HDMI-A-1", res="1360 × 768"))
        self.assertEqual(render.displays_resolution_note([self.SAME, self.UNKNOWN]),
                         _("gpu.displays.preferred.only").format(salidas="DP-2"))
        self.assertIsNone(render.displays_resolution_note([self.SAME]))

    def test_one_line_says_both(self):
        self.assertIn(_("gpu.display.preferred").format(res="1360 × 768"),
                      render.display_mode(self.TV))
        self.assertEqual(render.display_mode(self.UNKNOWN).split(" · ")[0],
                         _("gpu.display.preferred.only").format(res="2560 × 1440"))


class TestOnTheGraphicsPage(unittest.TestCase):
    """Its dump has no EDID (it carried the TV's serial) and no recorded
    mode: mounted with what the kernel answers on that machine."""

    def test_the_tv_at_its_running_mode(self):
        qt.app()
        with volcado.mounted(EQUIPOS / "celeron-g3900") as root, fake_clock() as clock:
            path = root / "grabado.json"
            recorded = json.loads(path.read_text())
            recorded["drm_modes"] = {"card1": {"HDMI-A-1": {
                "width": 1920, "height": 1080, "refresh_hz": 60.0}}}
            path.write_text(json.dumps(recorded))
            sysroot.forget()
            collector = Collector()
            try:
                collector.snapshot()
                snapshot = next_snapshot(collector, clock)
            finally:
                collector.close()
        tv = next(d for g in snapshot.gpus for d in g.displays if d.connected)
        self.assertEqual((tv.active_width, tv.active_height), (1920, 1080))
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            texts = visible_texts(window.stack.currentWidget())
        self.assertIn("1920 × 1080", texts)
        # No preferred to set apart, and nothing unknown to say.
        self.assertFalse([t for t in texts if t.startswith(
            _("gpu.displays.preferred.only").split("{")[0])])

    def test_a_dump_without_the_running_mode_says_so(self):
        qt.app()
        folder = EQUIPOS / "i5-10400"
        self.assertNotIn("drm_modes", json.loads((folder / "grabado.json").read_text()))
        snapshot = foto(folder)[0]
        connected = [d.connector for g in snapshot.gpus for d in g.displays if d.connected]
        self.assertTrue(connected)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Gráficos")
            texts = visible_texts(window.stack.currentWidget())
        self.assertIn(_("gpu.displays.preferred.only").format(
            salidas=render.enumeration(connected)), texts)

    def test_a_card_asleep_is_not_asked(self):
        with mock.patch.object(drmmode, "active_modes") as asked:
            with volcado.mounted(EQUIPOS / "celeron-g3900"):
                drm._outputs("card1", ask_modes=False)
                asked.assert_not_called()
                drm._outputs("card1")
                asked.assert_called_once_with("card1")


if __name__ == "__main__":
    unittest.main()
