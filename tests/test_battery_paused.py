"""A battery between its charge thresholds is paused, not held at the top.

The kernel says «Not charging» for both: at 70 % with a 65-80 % window the
laptop waits to drop under 65, which «held at the top» told wrong.
"""

import unittest

from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto


class TestBetweenItsThresholds(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        cls.snapshot = foto(EQUIPOS / "i5-8350u")[0]

    def test_the_status(self):
        battery = self.snapshot.batteries[0]
        self.assertEqual((battery.percent, battery.charge_start_percent,
                          battery.charge_end_percent), (70.0, 65, 80))
        self.assertEqual(battery.status, "bat.status.paused")
        self.assertTrue(battery.on_charger)

    def test_on_the_page(self):
        with pantalla.Ventana(self.snapshot) as window:
            window.select_section("Batería")
            text = " ".join(pantalla.textos_de(window.stack.currentWidget()))
        self.assertIn(_("bat.status.paused"), text)
        self.assertNotIn(_("bat.status.held"), text)
        self.assertIn(_("bat.left.oncharger"), text)


if __name__ == "__main__":
    unittest.main()
