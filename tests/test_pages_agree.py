"""The same measure says the same on every page that shows it.

Home said «DDR5-4800» where Memory said 6000 MT/s, and a Radeon's core was
«en reposo» on Graphics beside 0.261 V on Sensors: two pages, two answers.
Here, on every dump, what Graphics says of each card (core voltage, core
clock, edge temperature) against its rows in Sensors, and each drive's
temperature in Storage against its own in Sensors.
"""

import re
import unittest

from silux.i18n import _
from silux.model import DeviceKind, SensorKind
from tests import pantalla, qt
from tests.per_dump import per_dump
from tests.test_equipos import shared_snapshot

FIGURE = re.compile(r"(-?\d+(?:\.(\d+))?)\s*(GHz|MHz|V|°C|W)?")
SCALE = {"GHz": 1000.0}


def said(text: str):
    """What a cell says: «en reposo», or its figure in its base unit (MHz, V,
    °C) with half its last written digit, the precision it was written to."""
    if text.strip() == _("gpu.clock.idle"):
        return "idle"
    found = FIGURE.search(text.replace("\u202f", "").replace("\u00a0", ""))
    if not found:
        return None
    scale = SCALE.get(found.group(3), 1.0)
    decimals = len(found.group(2) or "")
    return float(found.group(1)) * scale, 0.5 * 10 ** -decimals * scale


class TestPagesAgree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def assert_same(self, one, other) -> None:
        """Both «en reposo», or the same figure to the precision of either."""
        if one == "idle" or other == "idle":
            self.assertEqual(one, other)
            return
        self.assertIsNotNone(one)
        self.assertIsNotNone(other)
        self.assertLessEqual(abs(one[0] - other[0]), max(one[1], other[1]) + 1e-9,
                             f"{one[0]} against {other[0]}")

    def _every_dump(self, folder):
        from silux.ui.pages.graphics import GpuSection

        snapshot = shared_snapshot(folder)
        with pantalla.Ventana(snapshot) as window:
            pages = dict(pantalla.recorrer(window))
            rows = window.monitor_page.tree._rows

            def in_sensors(sensor):
                row = rows.get(sensor.key)
                return said(row.text(1)) if row is not None else None

            sections = pages["nav.graphics"].findChildren(GpuSection)
            for gpu, section in zip(snapshot.gpus, sections):
                ours = [s for s in snapshot.sensors
                        if s.device_key == f"gpu:{gpu.pci_slot}"]
                rail = next((s for s in ours if s.gpu_core_rail), None)
                sclk = next((s for s in ours if s.kind is SensorKind.CLOCK
                             and (s.chip_label or "").lower() == "sclk"), None)
                edge = next((s for s in ours if s.kind is SensorKind.TEMPERATURE
                             and (s.chip_label or "").lower() == "edge"), None)
                pairs = (
                    ("voltage", rail, section.sensors.value_label(_("gpu.sensor.voltage"))),
                    ("clock", sclk, section.clocks.value_label(_("gpu.clock.core"))),
                )
                for what, sensor, label in pairs:
                    if sensor is None or label.isHidden():
                        continue
                    with self.subTest(gpu=gpu.name, what=what):
                        self.assert_same(said(label.full_text()), in_sensors(sensor))
                if edge is not None and gpu.temp_c is not None:
                    with self.subTest(gpu=gpu.name, what="edge"):
                        self.assert_same(said(section.tile_temp.figure_text()), in_sensors(edge))

            table = pages["nav.storage"].disks
            disks = {d.name: d for d in snapshot.disks}
            for cells in table._cells:
                unit = cells[0].full_text() if hasattr(cells[0], "full_text") else cells[0].text()
                temperature = cells[5].full_text() if hasattr(cells[5], "full_text") \
                    else cells[5].text()
                disk = disks.get(unit)
                if disk is None or said(temperature) is None:
                    continue
                composite = [s for s in snapshot.sensors
                             if s.device_kind == DeviceKind.DISK
                             and s.label == _("sensor.nvme.composite")
                             and s.device in (disk.model, f"{disk.model} ({unit})")]
                if len(composite) != 1:
                    continue
                with self.subTest(disk=unit):
                    self.assert_same(said(temperature), in_sensors(composite[0]))


per_dump(TestPagesAgree, "pages_agree", TestPagesAgree._every_dump)


if __name__ == "__main__":
    unittest.main()
