"""A USB network card: its model from usb.ids, and its USB port.

A USB Wi-Fi with rtl8192eu read «El kernel no publica modelo» while Devices
named it, and «Ranura PCI: 1-3:1.0», which is a USB interface. The report's
annex leaves out what's plugged into USB (its ids and names), so the dump is
mounted with the two ids the running system has.
"""

import re
import tempfile
import unittest
from unittest import mock

from silux import render, usbids, volcado
from silux.collector import Collector
from silux.i18n import _
from tests import pantalla, qt
from tests.interval import fake_clock, next_snapshot
from tests.test_equipos import EQUIPOS, foto, volcados
from tests.test_interface_language import visible_texts

DUMP = EQUIPOS / "celeron-g3900"
# The two lines of usb.ids that matter, as hwdata writes them.
USB_IDS = ("# a vendor before it\n0b95  ASIX Electronics Corp.\n\t1790  AX88179 Gigabit Ethernet\n"
           "0bda  Realtek Semiconductor Corp.\n\t8179  RTL8188EUS 802.11n Wireless Network Adapter\n"
           "\t818b  RTL8192EU 802.11b/g/n WLAN Adapter\n\t\t0001  an interface line\n"
           "0bdb  Ericsson Business Mobile Networks BV\n\t818b  not this one\n"
           "C 00  (Defined at Interface level)\n")
USB_INTERFACE = re.compile(r"\d+-[\d.]+:\d+\.\d+")


class _WithUsbIds(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = f"{tmp.name}/usb.ids"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(USB_IDS)
        patch = mock.patch.object(usbids, "CANDIDATE_PATHS", (path,))
        patch.start()
        self.addCleanup(patch.stop)


class TestTheDatabase(_WithUsbIds):

    def test_the_product_inside_its_vendor(self):
        self.assertEqual(usbids.lookup(0x0BDA, 0x818B),
                         ("Realtek Semiconductor Corp.", "RTL8192EU 802.11b/g/n WLAN Adapter"))
        self.assertIsNone(usbids.lookup(0x0BDA, 0x0001))
        self.assertIsNone(usbids.lookup(0x1234, 0x818B))


class TestTheCard(_WithUsbIds):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _snapshot(self, ids=True):
        with volcado.mounted(DUMP) as root, fake_clock() as clock:
            device = root / "sys/devices/pci0000:00/0000:00:14.0/usb1/1-3"
            if ids:
                (device / "idVendor").write_text("0bda\n")
                (device / "idProduct").write_text("818b\n")
            collector = Collector()
            try:
                collector.snapshot()
                return next_snapshot(collector, clock)
            finally:
                collector.close()

    def _card(self, snapshot):
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Red")
            for _vez in range(3):
                self.app.processEvents()
            page = window.stack.currentWidget()
            return visible_texts(page._cards["wlx00005e0053af"])

    def test_its_model_and_its_port(self):
        snapshot = self._snapshot()
        wifi = next(i for i in snapshot.network if i.driver == "rtl8192eu")
        self.assertEqual((wifi.pci_slot, wifi.usb_port), (None, "1-3"))
        self.assertEqual(wifi.model, "RTL8192EU 802.11b/g/n WLAN Adapter")
        texts = self._card(snapshot)
        self.assertIn(_("net.field.usbport"), texts)
        self.assertIn(render.usb_port("1-3"), texts)
        self.assertIn(render.with_maker(wifi.vendor, wifi.model), texts)
        self.assertNotIn(_("net.field.slot"), texts)
        self.assertFalse([t for t in texts if _("net.na.model") in t])

    def test_without_its_ids_still_a_usb_port(self):
        texts = self._card(self._snapshot(ids=False))
        self.assertIn(render.usb_port("1-3"), texts)
        self.assertNotIn(_("net.field.slot"), texts)


class TestEveryDump(unittest.TestCase):

    def test_no_usb_interface_as_a_pci_slot(self):
        for folder in volcados():
            for interface in foto(folder)[0].network:
                with self.subTest(folder.name, interface=interface.name):
                    self.assertFalse(USB_INTERFACE.fullmatch(interface.pci_slot or ""))


if __name__ == "__main__":
    unittest.main()
