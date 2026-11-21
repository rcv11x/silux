"""The report carries the virtual interfaces, and the loopback as it is.

The author's T14 has a WireGuard tunnel (`interfaz1`): Red shows it folded,
Sensores lists it, and the report said nothing of it. And the anonymized
loopback read 192.168.1.120, the substitute every address got: 127.0.0.1
and ::1 are everyone's.
"""

import unittest

from silux import privacidad
from tests import qt
from tests.test_equipos import EQUIPOS, foto


class TestTheLoopbackIsNotCovered(unittest.TestCase):

    def test_it_keeps_its_address_and_the_rest_does_not(self):
        anonima = privacidad.anonimizar(foto(EQUIPOS / "i5-1135g7")[0])
        por_nombre = {i.name: i for i in anonima.network}
        self.assertEqual(por_nombre["lo"].ipv4, "127.0.0.1")
        self.assertEqual(por_nombre["wlan0"].ipv4, privacidad.IPV4)
