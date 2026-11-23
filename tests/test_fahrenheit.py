"""In Fahrenheit, every temperature shown is in °F and coloured as in °C.

A temperature's level is decided in °C (`thermal`); only showing it
converts, and every figure goes through `render`'s temperature functions.
Pages that converted by hand left a «°C» behind: Home's chart kept its
Celsius figures under «°F», and a sensor's limits on hover kept the model's
unit.
"""

import unittest

from silux import render
from tests.test_equipos import foto, volcados

try:
    from PySide6.QtWidgets import (QApplication, QLabel, QTreeWidget,
                                   QTreeWidgetItemIterator, QWidget)
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestTheFormats(unittest.TestCase):

    def test_a_limit_is_whole_converted_then_rounded(self):
        # 358 K: 84.85 °C, 184.73 °F.
        self.assertEqual(render.temperature_whole(84.85), "85 °C")
        self.assertEqual(render.temperature_whole(84.85, fahrenheit=True), "185 °F")
        self.assertEqual(render.temperature_whole(93.85), "94 °C")

    def test_the_limits_line(self):
        self.assertTrue(render.temperature_limits(89.85, 93.85).endswith("94 °C"))
        self.assertIn("90 °C", render.temperature_limits(89.85, 93.85))
        self.assertIn("194 °F", render.temperature_limits(89.85, 93.85, fahrenheit=True))

    def test_a_difference_has_no_32(self):
        self.assertEqual(render.temperature_difference(5), "5 °C")
        self.assertEqual(render.temperature_difference(5, fahrenheit=True), "9 °F")
        self.assertEqual(render.temperature_difference(None), render.DASH)

    def test_a_reading(self):
        self.assertEqual(render.temperature(85.0, fahrenheit=True), "185.0 °F")
        self.assertEqual(render.in_temperature_unit(100.0, fahrenheit=True), 212.0)


def _window(snapshot, fahrenheit: bool):
    from silux.settings import Preferences
    from silux.ui.app import MainWindow

    window = MainWindow(Preferences(temperature_unit="f" if fahrenheit else "c").normalized())
    window.resize(1300, 900)
    window.show()
    window._on_sample(snapshot)
    return window


def _walk(snapshot, fahrenheit: bool) -> dict:
    """Each section: its texts and tooltips, and the levels its figures are
    painted with, in the widgets' order."""
    from tests import pantalla

    seen = {}
    window = _window(snapshot, fahrenheit)
    try:
        for name, page in pantalla.recorrer(window):
            QApplication.processEvents()
            texts = pantalla.textos_de(page) + [w.toolTip() for w in page.findChildren(QWidget)
                                               if w.toolTip()]
            # A tree's tooltips hang from its rows, not from a widget.
            for tree_widget in page.findChildren(QTreeWidget):
                row = QTreeWidgetItemIterator(tree_widget)
                while row.value() is not None:
                    texts += [row.value().toolTip(column)
                              for column in range(tree_widget.columnCount())]
                    row += 1
            levels = [label.property("level") or "" for label in page.findChildren(QLabel)]
            tree = getattr(page, "tree", None)
            if tree is not None:
                levels += [row.foreground(1).color().name() + row.foreground(3).color().name()
                           for _key, row in sorted(tree._rows.items())]
            seen[name] = (texts, levels)
    finally:
        window.close()
    return seen


@unittest.skipIf(QApplication is None, "no PySide6")
class TestEveryPageInFahrenheit(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tests import qt
        cls.app = qt.app()

    def _check(self, snapshot, name: str):
        from silux.i18n import _

        celsius, fahrenheit = _walk(snapshot, False), _walk(snapshot, True)
        # The Settings option that names the other unit is its name, not a figure.
        allowed = {_("opt.temp.celsius")}
        for section, (texts, levels) in fahrenheit.items():
            with self.subTest(dump=name, section=section):
                left = [t for t in texts if "°C" in t and t not in allowed]
                self.assertEqual(left, [])
                self.assertEqual(levels, celsius[section][1])

    def test_hot_parts_are_coloured_the_same(self):
        from tests.test_temperature_levels import _collected

        for dump, hot in (("5800x3d", {"evo": 85000, "sn850x": 90000, "tctl": 95000}),
                          ("i5-10400", {"package": 100000, "kioxia": 70000})):
            snapshot = _collected(dump, **hot)
            self.assertTrue(any(s.alarm for s in snapshot.sensors))
            self._check(snapshot, dump)


def _per_dump(folder):
    def test(self):
        self._check(foto(folder)[0], folder.name)
    return test


# One test per dump, so the suite spreads them over its processes.
for _folder in volcados():
    setattr(TestEveryPageInFahrenheit, f"test_{_folder.name.replace('-', '_')}",
            _per_dump(_folder))
del _folder


if __name__ == "__main__":
    unittest.main()
