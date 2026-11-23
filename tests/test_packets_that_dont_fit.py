"""Packets that can't be the wire's aren't shown as a figure.

A USB Wi-Fi with rtl8192eu read «2.0 GB received in 31 074 packets»: 64 kB
a packet, with an MTU of 1500. Its driver counts aggregated frames, or
miscounts; the page says so instead of a count nobody can trust.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import FRAME_OVERHEAD, NetworkInterface, NetworkTraffic
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot, volcados
from tests.test_interface_language import visible_texts


class TestTheRule(unittest.TestCase):

    def test_up_to_a_full_frame_fits(self):
        full = 1500 + FRAME_OVERHEAD
        card = NetworkInterface(name="eth0", kind="ethernet", mtu=1500,
                                traffic=NetworkTraffic(rx_bytes=10 * full, rx_packets=10))
        self.assertTrue(card.received_packets_fit)
        card = dataclasses.replace(card, traffic=NetworkTraffic(rx_bytes=10 * full + 1,
                                                                rx_packets=10))
        self.assertFalse(card.received_packets_fit)
        # The kernel's own aggregated packets cross a bridge or a veth as one.
        bridge = dataclasses.replace(card, kind="puente")
        self.assertTrue(bridge.received_packets_fit)


class TestOnTheNetworkPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _texts(self, snapshot):
        with pantalla.Ventana(snapshot) as window:
            window.select_section("Red")
            for _vez in range(3):
                self.app.processEvents()
            return visible_texts(window.stack.currentWidget())

    def test_in_every_dump(self):
        for folder in volcados():
            snapshot = shared_snapshot(folder)
            texts = self._texts(snapshot)
            for interface in snapshot.network:
                why = render.packets_misfit(interface)
                with self.subTest(folder.name, interface=interface.name):
                    if why is None:
                        continue
                    self.assertIn(why, " ".join(texts))
                    count = render.thousands(interface.traffic.rx_packets
                                             + interface.traffic.tx_packets)
                    self.assertNotIn(count, texts)

    def test_its_case(self):
        snapshot = shared_snapshot(EQUIPOS / "celeron-g3900")
        wifi = next(i for i in snapshot.network if i.driver == "rtl8192eu")
        self.assertFalse(wifi.received_packets_fit)
        texts = self._texts(snapshot)
        self.assertIn(_("net.packets.misfit"), texts)
        self.assertIn(_("net.packets.misfit.short"), texts)
        self.assertNotIn(_("net.packets2").format(n=render.thousands(wifi.traffic.rx_packets)),
                         texts)
        self.assertIn("rtl8192eu", render.packets_misfit(wifi))
        # Its Ethernet, without a cable, has nothing that doesn't add up.
        ethernet = next(i for i in snapshot.network if i.driver == "r8169")
        self.assertIsNone(render.packets_misfit(ethernet))


if __name__ == "__main__":
    unittest.main()
