"""The package power's tooltip in Sensors names where it comes from in plain
words: the kernel's RAPL (powercap). The kernel calls the framework
«intel-rapl» on AMD too, and «intel-rapl · rapl/package_w» on a Ryzen read
like a mistake. The only dump whose RAPL reads without permissions is an
Intel's; the tooltip is the same on any processor."""

import unittest

from silux.i18n import _
from tests import geometry, pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot


class TestRaplSource(unittest.TestCase):
    def test_the_package_power_says_rapl_without_its_kernel_name(self):
        app = qt.app()
        snapshot = shared_snapshot(EQUIPOS / "i7-6700k")
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Sensores")
            geometry.settle(app)
            rows = window.monitor_page.tree._rows
            key = next(k for k in rows if k.endswith("rapl/package_w"))
            tip = rows[key].toolTip(0)
            self.assertIn(_("sensors.source.rapl"), tip)
            self.assertNotIn("intel-rapl", tip)
            self.assertNotIn("rapl/", tip)


if __name__ == "__main__":
    unittest.main()
