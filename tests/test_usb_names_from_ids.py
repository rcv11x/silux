"""A USB device that writes no name of its own, or a dump made before the
names were kept, is named by its ids in usb.ids, as PCI devices are by
pci.ids; one usb.ids doesn't have reads «Dispositivo USB 0bda:57b4». The
i7-4710hq's Devices listed only kinds: «Almacenamiento», «Video»."""

import unittest

from silux import render
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot
from tests.test_interface_language import visible_texts


class TestUsbNamesFromIds(unittest.TestCase):
    def test_the_dump_records_what_usb_ids_said(self):
        devices = {d.usb_id: d for d in shared_snapshot(EQUIPOS / "i7-4710hq").usb_devices}
        bluetooth = devices["04ca:2006"]
        self.assertIsNone(bluetooth.product)
        self.assertEqual((bluetooth.ids_vendor, bluetooth.ids_product),
                         ("Lite-On Technology Corp.", "Broadcom BCM43142A0 Bluetooth Device"))
        self.assertEqual(render.usb_name(bluetooth), "Broadcom BCM43142A0 Bluetooth Device")
        self.assertEqual(render.usb_name(devices["0bda:57b4"]), "Dispositivo USB 0bda:57b4")

    def test_on_the_devices_page(self):
        qt.app()
        with pantalla.Ventana(shared_snapshot(EQUIPOS / "i7-4710hq")) as window:
            window.select_section("Dispositivos")
            qt.app().processEvents()
            texts = visible_texts(window.stack.currentWidget())
        self.assertIn("Broadcom BCM43142A0 Bluetooth Device", texts)
        # The brand, not usb.ids' legal name, «Lite-On Technology Corp.».
        self.assertIn("Lite-On Technology", texts)
        self.assertNotIn("Lite-On Technology Corp.", texts)
        self.assertIn("Dispositivo USB 0bda:57b4", texts)

    def test_a_name_the_device_writes_comes_first(self):
        devices = shared_snapshot(EQUIPOS / "i5-10400").usb_devices
        self.assertEqual({render.usb_name(d) for d in devices}, {"NK65", "USB Optical Mouse"})
        self.assertTrue(all(d.ids_product is None for d in devices))


if __name__ == "__main__":
    unittest.main()
