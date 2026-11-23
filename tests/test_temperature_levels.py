"""Each temperature coloured by the limits its own part declares, the same
wherever it's shown.

Normal; amber from its max; red from its crit. Without a limit from the
hardware, no colour: Silux used to set its own for chips that declare none
(a Ryzen's Tctl turned amber at 80 °C), and a made-up limit paints a
machine's normal work as a warning. The temperatures here are the dumps'
own files raised by hand, as the parts would publish them hot.
"""

import unittest

from silux import thermal, volcado
from silux.collector import Collector
from tests.test_equipos import EQUIPOS

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

# The dumps' hwmon channels.
KIOXIA = "sys/class/hwmon/hwmon1/temp1_input"            # i5-10400: drivetemp, no limits
CORETEMP_PACKAGE = "sys/class/hwmon/hwmon2/temp1_input"  # i5-10400: max 84, crit 100
EVO_970 = "sys/class/hwmon/hwmon1/temp1_input"           # 5800x3d: max 84.85 = crit 84.85
SN850X = "sys/class/hwmon/hwmon2/temp1_input"            # 5800x3d: max 89.85, crit 93.85
TCTL = "sys/class/hwmon/hwmon5/temp1_input"              # 5800x3d: k10temp, no limits


def _collected(dump: str, **millidegrees):
    """The dump's first snapshot with those channels at those values: a
    temperature is a reading, and the second snapshot would take the dump's
    own second reading of them."""
    paths = {"kioxia": KIOXIA, "package": CORETEMP_PACKAGE, "evo": EVO_970,
             "sn850x": SN850X, "tctl": TCTL}
    with volcado.mounted(EQUIPOS / dump) as root:
        for name, value in millidegrees.items():
            (root / paths[name]).write_text(f"{value}\n")
        collector = Collector()
        try:
            return collector.snapshot()
        finally:
            collector.close()


def _disk(snapshot, model_start: str):
    return next(d for d in snapshot.disks if (d.model or "").startswith(model_start))


class TestTheModel(unittest.TestCase):

    def test_a_disk_without_limits_has_no_colour_however_hot(self):
        # A Kioxia EXCERIA SATA: no SCT, so drivetemp gives temp1 alone.
        snapshot = _collected("i5-10400", kioxia=70000)
        disk = _disk(snapshot, "KIOXIA")
        self.assertEqual(disk.temp_c, 70.0)
        self.assertEqual((disk.temp_high_c, disk.temp_critical_c), (None, None))
        self.assertEqual(disk.temp_level, thermal.OK)
        drivetemp = next(s for s in snapshot.sensors if s.chip == "drivetemp")
        self.assertEqual(drivetemp.alarm_level, thermal.OK)

    def test_max_and_crit_the_same_go_straight_to_red(self):
        evo = _disk(_collected("5800x3d", evo=84800), "Samsung")
        self.assertEqual((evo.temp_high_c, evo.temp_critical_c), (84.85, 84.85))
        self.assertEqual(evo.temp_level, thermal.OK)
        snapshot = _collected("5800x3d", evo=84850)
        self.assertEqual(_disk(snapshot, "Samsung").temp_level, thermal.CRITICAL)
        # Its other two sensors declare 0xFFFF K and 0 K: none.
        others = [s for s in snapshot.sensors if s.chip == "nvme" and s.label != "Del disco"]
        self.assertTrue(others)
        self.assertEqual({(s.high, s.critical) for s in others}, {(None, None)})

    def test_amber_from_its_max_red_from_its_crit(self):
        self.assertEqual(_disk(_collected("5800x3d", sn850x=89850), "WD").temp_level,
                         thermal.HIGH)
        self.assertEqual(_disk(_collected("5800x3d", sn850x=93850), "WD").temp_level,
                         thermal.CRITICAL)

    def test_a_ryzen_without_limits_has_no_colour(self):
        snapshot = _collected("5800x3d", tctl=95000)
        self.assertEqual(snapshot.cpu.temperature_c, 95.0)
        self.assertEqual(snapshot.cpu.temp_level, thermal.OK)
        self.assertFalse([s for s in snapshot.sensors
                          if s.chip == "k10temp" and s.alarm_level != thermal.OK])

    def test_coretemp_declares_its_own(self):
        self.assertEqual(_collected("i5-10400", package=84000).cpu.temp_level, thermal.HIGH)
        self.assertEqual(_collected("i5-10400", package=100000).cpu.temp_level,
                         thermal.CRITICAL)


@unittest.skipIf(QApplication is None, "no PySide6")
class TestEverywhereItIsShown(unittest.TestCase):
    """Sensors, Home's warning and its temperatures card, the CPU page, the
    drives' table, «Más caliente» and the disk's detail: one level each."""

    @classmethod
    def setUpClass(cls):
        from tests import qt
        cls.app = qt.app()

    def _page(self, window, section: str):
        window.select_section(section)
        for _turn in range(3):
            self.app.processEvents()
        return window.stack.currentWidget()

    def test_a_hot_970_evo_plus(self):
        from silux.i18n import _
        from silux.ui.pages.storage import COLUMNA_TEMPERATURA
        from tests import pantalla

        snapshot = _collected("5800x3d", evo=85000)
        evo = _disk(snapshot, "Samsung")
        row = snapshot.disks.index(evo)
        with pantalla.Ventana(snapshot) as window:
            storage = self._page(window, "Almacenamiento")
            self.assertEqual(storage.disks._cells[row][COLUMNA_TEMPERATURA].property("level"),
                             "critical")
            self.assertEqual(storage.tile_temp.value.property("level"), "critical")
            grid = storage._grids[evo.name]
            self.assertEqual(grid.value_label(_("gpu.sensor.temp")).property("level"),
                             "critical")
            # Max and crit the same: one limit, the critical one.
            self.assertEqual(grid.value_label(_("storage.field.templimits")).full_text(),
                             _("temp.limit.critical").format(v="85 °C"))

            home = self._page(window, "Inicio")
            self.assertEqual(home.temperaturas.nombre.property("level"), "critical")
            chips = [text for text, _loud in home.badges._chips]
            self.assertIn("⚠ " + _("home.alarm.crit.one").format(n=1), chips)

            sensors = self._page(window, "Sensores")
            composite = next(s for s in snapshot.sensors
                             if s.chip == "nvme" and s.label == "Del disco"
                             and s.critical == 84.85)
            self.assertEqual(sensors.tree._rows[composite.key].foreground(1).color().name(),
                             window._palette.q("crit").name())

    def test_a_hot_ryzen_and_a_cool_kioxia_have_no_colour(self):
        from silux.i18n import _
        from silux.ui.pages.storage import COLUMNA_TEMPERATURA
        from tests import pantalla

        for dump, hot in (("5800x3d", {"tctl": 95000}), ("i5-10400", {"kioxia": 70000})):
            snapshot = _collected(dump, **hot)
            with self.subTest(dump=dump), pantalla.Ventana(snapshot) as window:
                home = self._page(window, "Inicio")
                self.assertFalse([t for t, _loud in home.badges._chips if t.startswith("⚠")])
                self.assertEqual(home.temperaturas.nombre.property("level") or "", "")
                cpu = self._page(window, "CPU")
                self.assertEqual(cpu.live.tile_temp.value.property("level") or "", "")
                if dump == "i5-10400":
                    storage = self._page(window, "Almacenamiento")
                    cell = storage.disks._cells[0][COLUMNA_TEMPERATURA]
                    self.assertEqual(cell.property("level") or "", "")
                    self.assertEqual(cell.toolTip(), _("storage.tip.nolimits"))
                    grid = storage._grids["sda"]
                    self.assertFalse(grid.value_label(
                        _("storage.field.templimits")).isVisibleTo(storage))

    def test_the_cpu_tile_says_its_limits(self):
        from silux.i18n import _
        from tests import pantalla

        snapshot = _collected("i5-10400", package=85000)
        with pantalla.Ventana(snapshot) as window:
            cpu = self._page(window, "CPU")
            self.assertEqual(cpu.live.tile_temp.value.property("level"), "high")
            self.assertIn(_("temp.limit.critical").format(v="100 °C"),
                          cpu.live.tile_temp.toolTip())


if __name__ == "__main__":
    unittest.main()
