"""A battery that gives neither `power_now` nor `current_now`, only `energy_now`.

Its power is how much the energy moved between two of the firmware's updates,
which come every few seconds: between two samples it mostly stays put. The
dump is a laptop whose battery publishes exactly that; here its firmware's
updates are played by writing `energy_now`.
"""

import unittest

from silux import volcado
from silux.collector import Collector
from silux.i18n import _
from tests.interval import fake_clock
from tests.test_equipos import EQUIPOS

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

BATTERY = "sys/class/power_supply/BAT1"


class _Laptop:
    """The dump mounted, its collector and its clock."""

    def __enter__(self):
        self._mounted = volcado.mounted(EQUIPOS / "i3-1115g4")
        self.root = self._mounted.__enter__()
        self._clock = fake_clock()
        self.clock = self._clock.__enter__()
        self.collector = Collector()
        return self

    def __exit__(self, *exc):
        self.collector.close()
        self._clock.__exit__(*exc)
        self._mounted.__exit__(*exc)

    def write(self, name: str, value: str) -> None:
        (self.root / BATTERY / name).write_text(value + "\n")

    def after(self, seconds: float, energy_uwh: int = None):
        if energy_uwh is not None:
            self.write("energy_now", str(energy_uwh))
        self.clock.advance(seconds)
        return self.collector.snapshot()


def _battery(snapshot):
    return snapshot.batteries[0]


class TestItsPowerFromItsEnergy(unittest.TestCase):

    def test_from_the_second_update_on(self):
        with _Laptop() as laptop:
            self.assertFalse((laptop.root / BATTERY / "power_now").exists())
            first = _battery(laptop.collector.snapshot())
            self.assertIsNone(first.power_w)
            self.assertTrue(first.power_settling)        # «Calculando…»
            # Unchanged: the firmware hasn't updated it yet.
            self.assertIsNone(_battery(laptop.after(1)).power_w)
            # Its first update: the window from the value it already had
            # would be too short.
            self.assertIsNone(_battery(laptop.after(4, 20_700_000)).power_w)
            # 20 mWh in 10 s.
            battery = _battery(laptop.after(10, 20_680_000))
            self.assertEqual(battery.power_w, 7.2)
            self.assertTrue(battery.power_from_energy)
            # Until its next update, the last window's.
            self.assertEqual(_battery(laptop.after(1)).power_w, 7.2)

    def test_energy_moving_the_other_way_is_no_rate(self):
        with _Laptop() as laptop:
            laptop.collector.snapshot()
            laptop.after(5, 20_700_000)
            # Discharging, and it rose: the charger went in between readings.
            self.assertIsNone(_battery(laptop.after(10, 20_720_000)).power_w)

    def test_a_new_state_starts_over(self):
        with _Laptop() as laptop:
            laptop.collector.snapshot()
            laptop.after(5, 20_700_000)
            self.assertEqual(_battery(laptop.after(10, 20_680_000)).power_w, 7.2)
            laptop.write("status", "Charging")
            self.assertIsNone(_battery(laptop.after(10, 20_700_000)).power_w)

    def test_a_short_window_is_no_rate(self):
        with _Laptop() as laptop:
            laptop.collector.snapshot()
            laptop.after(5, 20_700_000)
            # Less than half the sampling interval between the two updates.
            self.assertIsNone(_battery(laptop.after(0.2, 20_690_000)).power_w)


@unittest.skipIf(QApplication is None, "no PySide6")
class TestOnThePage(unittest.TestCase):

    def test_its_power_is_on_the_battery_page(self):
        from tests import pantalla, qt

        app = qt.app()
        with _Laptop() as laptop:
            laptop.collector.snapshot()
            laptop.after(5, 20_700_000)
            snapshot = laptop.after(10, 20_680_000)
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Batería")
            app.processEvents()
            from silux.ui.pages.battery import _SeccionBateria
            section = window.stack.currentWidget().findChild(_SeccionBateria)
            self.assertEqual(section.potencia.value.text(), "7.2")
            self.assertIn(_("bat.power.fromenergy"), section.potencia.toolTip())


if __name__ == "__main__":
    unittest.main()
