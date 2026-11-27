"""An Atheros AR242x declares the PCI class of an Ethernet controller: in
the Vostro A840 (Felix's prueba13 report) Placa base listed it as
«Ethernet». Its radio hangs from it (`ieee80211/`), and it is a Wi-Fi."""

import unittest

from tests.test_equipos import EQUIPOS, shared_snapshot


class TestWifiDeclaredEthernet(unittest.TestCase):
    def test_the_ar242x_is_a_wifi(self):
        snapshot = shared_snapshot(EQUIPOS / "celeron-560")
        atheros = next(d for d in snapshot.pci_devices if "AR242x" in (d.name or ""))
        self.assertEqual(atheros.kind, "wifi")
        self.assertEqual(sorted(d.kind for d in snapshot.pci_devices
                                if d.kind in ("wifi", "ethernet")), ["ethernet", "wifi"])


if __name__ == "__main__":
    unittest.main()
