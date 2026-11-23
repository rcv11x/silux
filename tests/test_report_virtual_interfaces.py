"""The report carries the virtual interfaces, and the loopback as it is.

The author's T14 has a WireGuard tunnel (`interfaz1`): Red shows it folded,
Sensores lists it, and the report said nothing of it. And the anonymized
loopback read 192.168.1.120, the substitute every address got: 127.0.0.1
and ::1 are everyone's.
"""

import unittest

from silux import privacidad
from tests import qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot


class TestTheLoopbackIsNotCovered(unittest.TestCase):

    def test_it_keeps_its_address_and_the_rest_does_not(self):
        anonima = privacidad.anonymize(shared_snapshot(EQUIPOS / "i5-1135g7"))
        por_nombre = {i.name: i for i in anonima.network}
        self.assertEqual(por_nombre["lo"].ipv4, "127.0.0.1")
        self.assertEqual(por_nombre["wlan0"].ipv4, privacidad.IPV4)


class TestTheVirtualInterfacesInTheReport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        qt.app()
        from silux.ui import full_report
        cls.texto = full_report.build(shared_snapshot(EQUIPOS / "i5-1135g7"), sections=["Red"])

    def test_the_tunnel_is_there(self):
        self.assertIn("| interfaz1 |", self.texto)
        self.assertIn("### interfaz1", self.texto)

    def test_with_its_loopback_as_it_is(self):
        lo = self.texto[self.texto.index("### lo"):]
        self.assertIn("127.0.0.1", lo[:lo.index("### ", 4)])


if __name__ == "__main__":
    unittest.main()
