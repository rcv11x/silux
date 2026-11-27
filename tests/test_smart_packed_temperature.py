"""A SMART temperature packed in its raw value (194 and 190), shown as
smartctl reads it by default: the office's KIOXIA-EXCERIA S read
«72 · en crudo 176 094 576 668» where smartctl says «27 (Min/Max 14/41)».

The raw value is Silux's reading of the drive; smartctl's 27 was another
moment (the lowest and highest agree). The SanDisk SSD PLUS over USB in
Felix's reports packs the same way: 29 °C, as its temperature said.
"""

import unittest

from silux import render

KIOXIA_194 = 176_094_576_668


class TestPackedTemperature(unittest.TestCase):
    def test_as_smartctl_reads_it(self):
        self.assertEqual(render.smart_temperature(KIOXIA_194), "28 °C, mín 14, máx 41")
        self.assertEqual(render.smart_temperature(240_518_758_429), "29 °C, mín 9, máx 56")
        # Only the current one when the drive keeps no lowest and highest.
        self.assertEqual(render.smart_temperature(73_014_444_079), "47 °C")


# The KIOXIA's attributes as its diagnosis read them: (id, normalized, raw).
KIOXIA = [(9, 100, 4_181), (12, 100, 1_503), (192, 100, 134), (194, 72, KIOXIA_194),
          (241, 100, 915_316)]


class TestTheSameTemperatureEverywhere(unittest.TestCase):
    """The diagnosis said «194 · Temperatura 28 °C», and a page should never
    say «—» for that drive's temperature nor that no drive gives one: the
    drive's card, the table and the hottest tile take the same 28."""

    def _disk(self):
        from unittest import mock

        from silux.model import Disk
        from silux.providers import storage
        from silux.providers.base import Draft
        from tests.test_smart import tabla_ata

        client = mock.Mock()
        client.connected.return_value = True
        client.read_smart.return_value = (tabla_ata(KIOXIA), "ata")
        draft = Draft()
        draft.disks = [Disk(name="sda", model="KIOXIA-EXCERIA SATA SSD", kind="SSD",
                            rotational=False, size_bytes=480 * 1000 ** 3)]
        storage.Disks(client=client)._diagnosis(draft)
        return draft.disks[0]

    def test_the_provider_gives_it_to_the_drive(self):
        disk = self._disk()
        self.assertEqual(disk.temp_c, 28.0)
        self.assertEqual(dict((a, r) for a, _n, r in disk.health.attributes)[194], KIOXIA_194)

    def test_on_the_page(self):
        from silux.i18n import _
        from silux.model import CpuInfo, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage
        from tests import qt

        app = qt.app()
        page = StoragePage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(page.deleteLater)
        page.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(), disks=(self._disk(),)))
        app.processEvents()
        self.assertEqual(page._grids["sda"]._values[_("gpu.sensor.temp")].full_text(),
                         render.temperature(28.0))
        self.assertEqual(page.tile_temp.value.text(), "28")
        self.assertEqual(page.tile_temp.detail.full_text(), "sda")


if __name__ == "__main__":
    unittest.main()
