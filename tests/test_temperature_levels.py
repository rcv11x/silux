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
from tests.test_equipos import EQUIPOS, shared_snapshot

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

    def test_a_zen_3_warns_from_its_sheet_and_never_turns_red(self):
        # k10temp declares nothing; AMD's sheet gives the 5800X3D 90 °C.
        for millidegrees, level in ((89000, thermal.OK), (91000, thermal.HIGH),
                                    (120000, thermal.HIGH)):
            with self.subTest(millidegrees=millidegrees):
                snapshot = _collected("5800x3d", tctl=millidegrees)
                self.assertEqual(snapshot.cpu.temp_level, level)
                self.assertEqual((snapshot.cpu.temp_high_c, snapshot.cpu.temp_critical_c,
                                  snapshot.cpu.temp_sheet_high_c), (None, None, 90))
                tctl = next(s for s in snapshot.sensors if s.chip_label == "Tctl")
                self.assertEqual((tctl.high, tctl.critical, tctl.sheet_high), (None, None, 90))
                self.assertEqual(tctl.alarm_level, level)

    def test_from_zen_2_on_only(self):
        from silux import db

        # AMD lists 95 °C for the Athlon 3000G, a Zen 1 part: the family
        # leaves it out, not a missing row.
        self.assertEqual(db.amd_model("AMD Athlon 3000G with Radeon Vega Graphics")["tjmax_c"], 95)
        for dump, expected in (("athlon-3000g", None), ("ryzen3-4100", 95),
                               ("ryzen5-5600g", 95), ("i5-10400", None)):
            with self.subTest(dump=dump):
                snapshot = shared_snapshot(EQUIPOS / dump)
                self.assertEqual(snapshot.cpu.temp_sheet_high_c, expected)
                self.assertEqual({s.sheet_high for s in snapshot.sensors
                                  if s.chip == "k10temp"} or {None}, {expected})

    def test_declared_limits_win_over_the_sheet(self):
        self.assertEqual(thermal.level(91, 95, 100, sheet_high=90), thermal.OK)
        self.assertEqual(thermal.level(150, None, None, sheet_high=90), thermal.HIGH)
        self.assertEqual(thermal.level(150, None, None, sheet_high=0), thermal.OK)

    def test_coretemp_declares_its_own(self):
        self.assertEqual(_collected("i5-10400", package=84000).cpu.temp_level, thermal.HIGH)
        self.assertEqual(_collected("i5-10400", package=100000).cpu.temp_level,
                         thermal.CRITICAL)


LOQ_MODULE = "sys/devices/pci0000:00/0000:00:1f.4/i2c-0/0-0050/hwmon/hwmon5/temp1_input"
LOQ_NVME = "sys/devices/pci0000:00/0000:00:06.0/0000:06:00.0/nvme/nvme0/hwmon2"


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheLoq(unittest.TestCase):
    """spd5118 declares 55 and 85 °C for the DDR5; the SK hynix declares
    85.85 and 86.85 for its composite and 0xFFFF K for its other two."""

    def test_the_nvmes_garbage_limits_go(self):
        from tests.test_equipos import shared_snapshot

        nvme = {s.chip_label: (s.high, s.critical)
                for s in shared_snapshot(EQUIPOS / "i5-12450h").sensors if s.chip == "nvme"}
        self.assertEqual(nvme, {"Composite": (85.85, 86.85), "Sensor 1": (None, None),
                                "Sensor 2": (None, None)})

    def test_the_modules_temperature_on_the_memory_page(self):
        from silux.i18n import _
        from tests import pantalla, qt

        qt.app()
        for millidegrees, level in ((50000, ""), (60000, "high"), (86000, "critical")):
            with volcado.mounted(EQUIPOS / "i5-12450h") as root:
                (root / LOQ_MODULE).write_text(f"{millidegrees}\n")
                collector = Collector()
                try:
                    snapshot = collector.snapshot()
                finally:
                    collector.close()
            with self.subTest(millidegrees=millidegrees), pantalla.Ventana(snapshot) as window:
                window.select_section("Memoria")
                page = window.stack.currentWidget()
                label = page._slot_grids[0].value_label(_("memory.field.temp"))
                self.assertEqual(label.property("level") or "", level)
                self.assertIn("85 °C", label.toolTip())


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

    def test_a_ryzen_under_its_sheet_and_a_cool_kioxia_have_no_colour(self):
        from silux.i18n import _
        from silux.ui.pages.storage import COLUMNA_TEMPERATURA
        from tests import pantalla

        for dump, hot in (("5800x3d", {"tctl": 88000}), ("i5-10400", {"kioxia": 70000})):
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

    def test_a_ryzen_over_its_sheet_is_amber_and_says_where_it_comes_from(self):
        from silux.i18n import _
        from tests import pantalla

        snapshot = _collected("5800x3d", tctl=95000)
        with pantalla.Ventana(snapshot) as window:
            cpu = self._page(window, "CPU")
            self.assertEqual(cpu.live.tile_temp.value.property("level"), "high")
            self.assertEqual(cpu.live.tile_temp.toolTip(),
                             _("temp.limits.sheet").format(v="90 °C"))
            home = self._page(window, "Inicio")
            self.assertEqual(home.temperaturas.nombre.property("level"), "high")
            sensors = self._page(window, "Sensores")
            tctl = next(s for s in snapshot.sensors if s.chip_label == "Tctl")
            row = sensors.tree._rows[tctl.key]
            self.assertEqual(row.foreground(1).color().name(), window._palette.q("warn").name())
            self.assertIn(_("sensors.limit.sheet").format(v="90 °C"), row.toolTip(0))
            self.assertIn(_("sensors.alarm.sheet"), row.toolTip(0))

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
