"""A battery whose firmware gives an impossible voltage, or nothing at all.

An old laptop's firmware gave 20.48 V for a pack of 14.8 V nominal, a byte
0x01 for its model and a charge of zero with no capacity: the card showed
an empty «Model:» and «Charge: — (0.0 Wh)». What a pack can't read is
dropped, and a battery left with nothing says so in one sentence.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux import report, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.providers import battery
from silux.providers.base import Draft
from tests import pantalla, qt
from tests.interval import fake_clock, next_snapshot
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

VOSTRO = EQUIPOS / "celeron-560"
BAT0 = "sys/devices/LNXSYSTM:00/LNXSYBUS:00/PNP0C0A:00/power_supply/BAT0"


def vostro_at_20_v():
    """The Vostro's dump with its battery as its prueba9 report read it,
    20.48 V for a pack of 14.8 V nominal; by the prueba13 it reads 0 V."""
    import shutil

    tmp = tempfile.mkdtemp(prefix="silux-vostro-")
    copy = pathlib.Path(tmp) / "celeron-560"
    shutil.copytree(VOSTRO, copy, symlinks=True)
    (copy / BAT0 / "voltage_now").write_text("20481000\n")
    return copy

# The same battery as its prueba7 report recorded it: no voltage at all.
BEFORE = {"charge_now": "0", "current_now": "1000", "cycle_count": "0",
          "manufacturer": "", "model_name": "\x01", "present": "1",
          "serial_number": "0", "status": "Not charging", "technology": "Unknown",
          "type": "Battery", "voltage_min_design": "0", "voltage_now": "0"}


def _read(**fields):
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        folder = root / "BAT0"
        folder.mkdir()
        for name, value in {"type": "Battery", "present": "1", **fields}.items():
            (folder / name).write_text(f"{value}\n", encoding="utf-8")
        with mock.patch.object(battery, "POWER_SUPPLY", root):
            draft = Draft()
            battery.Batteries().collect(draft)
    return draft.batteries[0]


class TestWhatAPackCanRead(unittest.TestCase):

    def test_a_voltage_no_pack_of_that_nominal_has_is_dropped(self):
        b = _read(voltage_now=20481000, voltage_min_design=14800000,
                  charge_now=0, current_now=1000)
        self.assertIsNone(b.voltage_v)
        self.assertEqual(b.impossible_voltage_v, 20.481)
        self.assertIsNone(b.power_w)
        b = _read(voltage_now=4000000, voltage_min_design=11100000)
        self.assertIsNone(b.voltage_v)

    def test_full_and_nearly_empty_are_possible(self):
        for now, nominal in ((16800000, 14800000), (12600000, 11100000),
                             (8400000, 7600000), (9600000, 14800000)):
            with self.subTest(now=now, nominal=nominal):
                b = _read(voltage_now=now, voltage_min_design=nominal)
                self.assertEqual(b.voltage_v, round(now / 1e6, 3))
                self.assertIsNone(b.impossible_voltage_v)

    def test_without_a_nominal_nothing_is_judged(self):
        self.assertEqual(_read(voltage_now=20481000).voltage_v, 20.481)

    def test_a_control_byte_is_no_model(self):
        b = _read(model_name="\x01", manufacturer="SMP")
        self.assertIsNone(b.model)
        self.assertEqual(b.manufacturer, "SMP")

    def test_a_zero_charge_with_nothing_to_set_it_against_is_no_charge(self):
        self.assertIsNone(_read(charge_now=0, voltage_min_design=14800000).now_wh)
        # With its capacity, zero is an empty battery.
        self.assertEqual(_read(charge_now=0, charge_full=4400000,
                               voltage_min_design=14800000).now_wh, 0)

    def test_the_vostro_has_no_data(self):
        b = foto(VOSTRO)[0].batteries[0]
        self.assertTrue(b.without_data)
        self.assertEqual((b.voltage_v, b.design_voltage_v), (None, 14.8))
        earlier = vostro_at_20_v()
        self.addCleanup(__import__("shutil").rmtree, earlier.parent)
        b = foto(earlier)[0].batteries[0]
        self.assertEqual((b.impossible_voltage_v, b.design_voltage_v), (20.481, 14.8))
        self.assertIn("- Tensión descartada: 20.48 V", report.build(foto(earlier)[0]))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnThePage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _page(self, snapshot):
        from tests.test_interface_language import visible_texts

        with pantalla.Ventana(snapshot) as window:
            window.select_section("Batería")
            for _turn in range(3):
                self.app.processEvents()
            return visible_texts(window.stack.currentWidget())

    def test_the_impossible_voltage_is_said_not_shown(self):
        earlier = vostro_at_20_v()
        self.addCleanup(__import__("shutil").rmtree, earlier.parent)
        texts = self._page(foto(earlier)[0])
        self.assertIn(_("bat.nodata.title"), texts)
        self.assertIn(_("bat.nodata.impossible").format(tension="20.48 V",
                                                        nominal="14.80 V"), texts)
        self.assertFalse([t for t in texts if "Wh" in t], texts)

    def test_the_battery_of_the_first_report_has_no_data_either(self):
        with volcado.mounted(VOSTRO) as root, fake_clock() as clock:
            folder = root / BAT0
            for name, value in BEFORE.items():
                (folder / name).write_text(f"{value}\n", encoding="utf-8")
            collector = Collector()
            try:
                collector.snapshot()
                snapshot = next_snapshot(collector, clock)
            finally:
                collector.close()
        self.assertIsNone(snapshot.batteries[0].impossible_voltage_v)
        texts = self._page(snapshot)
        self.assertIn(_("bat.nodata.title"), texts)
        self.assertIn(_("bat.nodata"), texts)


if __name__ == "__main__":
    unittest.main()
