"""Las interfaces de red, contra un /sys falso.

Lo que más importa aquí es el cálculo del ritmo: los contadores del kernel son
totales desde que la interfaz se levantó, así que la velocidad sale de restar
dos lecturas. Eso tiene dos trampas —la primera vuelta no tiene con qué
comparar, y los contadores se reinician si la interfaz se cae— y las dos están
probadas.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.model import NetworkInterface, NetworkTraffic
from silux.providers import network
from silux.providers.base import Draft


def _write(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


class BancoDeRed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        parches = [
            mock.patch.object(network, "SYS_NET", str(self.root)),
            mock.patch.object(network, "PROC_ROUTE", str(self.root / "route")),
            mock.patch.object(network, "PROC_IPV6", str(self.root / "if_inet6")),
            # Las direcciones IPv4 vienen de un ioctl, no de un fichero.
            mock.patch.object(network._Direcciones, "ip", lambda self, n: self._falsas.get(n)),
            mock.patch.object(network._Direcciones, "mascara", lambda self, n: "255.255.255.0"),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.addCleanup(self._tmp.cleanup)
        network._Direcciones._falsas = {"enp6s0": "192.168.96.11"}

    def interfaz(self, nombre: str, *, operstate="up", carrier="1", speed="2500",
                 duplex="full", mtu="1500", mac="74:fe:ce:6c:d6:43", tipo="1",
                 rx=1000, tx=500, **extra) -> None:
        base = self.root / nombre
        for campo, valor in (("operstate", operstate), ("carrier", carrier),
                             ("speed", speed), ("duplex", duplex), ("mtu", mtu),
                             ("address", mac), ("type", tipo)):
            if valor is not None:
                _write(base / campo, valor)
        estadisticas = {"rx_bytes": rx, "tx_bytes": tx, "rx_packets": 10,
                        "tx_packets": 5, "rx_errors": 0, "tx_errors": 0,
                        "rx_dropped": 0, "tx_dropped": 0}
        estadisticas.update(extra)
        for campo, valor in estadisticas.items():
            _write(base / "statistics" / campo, str(valor))

    def ruta_por_defecto(self, interfaz: str, puerta_hex: str = "0160A8C0") -> None:
        _write(self.root / "route",
               "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
               f"{interfaz}\t00000000\t{puerta_hex}\t0003\t0\t0\t100\t00000000")

    def recolectar(self, proveedor=None) -> Draft:
        draft = Draft()
        (proveedor or network.NetworkInterfaces()).collect(draft)
        return draft


class TestLectura(BancoDeRed):
    def setUp(self):
        super().setUp()
        self.interfaz("enp6s0")
        self.ruta_por_defecto("enp6s0")

    def test_datos_del_enlace(self):
        interfaz = self.recolectar().freeze().network[0]
        self.assertEqual(interfaz.name, "enp6s0")
        self.assertTrue(interfaz.up)
        self.assertEqual(interfaz.speed_mbps, 2500)
        self.assertEqual(interfaz.link_summary, "2.5 Gb/s · full")
        self.assertEqual(interfaz.mtu, 1500)

    def test_direccion_y_puerta_de_enlace(self):
        interfaz = self.recolectar().freeze().network[0]
        self.assertEqual(interfaz.ipv4, "192.168.96.11")
        # El kernel escribe la puerta en hexadecimal y del revés.
        self.assertEqual(interfaz.gateway, "192.168.96.1")
        self.assertTrue(interfaz.default_route)

    def test_esta_activa(self):
        self.assertTrue(self.recolectar().freeze().network[0].active)


class TestRitmo(BancoDeRed):
    """La velocidad sale de restar dos lecturas de los contadores."""

    def test_la_primera_vuelta_no_tiene_con_que_comparar(self):
        self.interfaz("enp6s0", rx=1000, tx=500)
        interfaz = self.recolectar().freeze().network[0]
        # Y eso no es cero: es que todavía no se sabe.
        self.assertIsNone(interfaz.traffic.rx_rate_bps)
        self.assertEqual(interfaz.traffic.rx_bytes, 1000)

    def test_la_segunda_ya_da_velocidad(self):
        proveedor = network.NetworkInterfaces()
        self.interfaz("enp6s0", rx=1000, tx=500)
        self.recolectar(proveedor)
        # Un segundo después han entrado 100 KB más.
        proveedor._previo["enp6s0"] = (proveedor._previo["enp6s0"][0] - 1.0, 1000, 500)
        self.interfaz("enp6s0", rx=1000 + 102400, tx=500)
        interfaz = self.recolectar(proveedor).freeze().network[0]
        self.assertAlmostEqual(interfaz.traffic.rx_rate_bps, 102400, delta=2000)
        self.assertAlmostEqual(interfaz.traffic.tx_rate_bps, 0, delta=100)

    def test_un_contador_que_se_reinicia_no_da_velocidad_negativa(self):
        # Pasa cuando la interfaz se cae y vuelve a levantarse.
        proveedor = network.NetworkInterfaces()
        self.interfaz("enp6s0", rx=1_000_000, tx=900_000)
        self.recolectar(proveedor)
        self.interfaz("enp6s0", rx=12, tx=8)
        interfaz = self.recolectar(proveedor).freeze().network[0]
        self.assertIsNone(interfaz.traffic.rx_rate_bps)


class TestClases(BancoDeRed):
    def test_el_bucle_local_no_se_da_por_parado(self):
        # Su driver no informa del enlace y responde «unknown»; llamarlo parado
        # sería mentir sobre una interfaz que está trabajando.
        self.interfaz("lo", operstate="unknown", carrier="1", tipo="772",
                      speed=None, duplex=None)
        interfaz = self.recolectar().freeze().network[0]
        self.assertEqual(interfaz.kind, "loopback")
        self.assertTrue(interfaz.up)

    def test_un_puente_de_maquinas_virtuales(self):
        self.interfaz("virbr0", operstate="down", carrier="0", speed=None)
        (self.root / "virbr0" / "bridge").mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.recolectar().freeze().network[0].kind, "puente")

    def test_una_interfaz_wifi(self):
        self.interfaz("wlan0")
        (self.root / "wlan0" / "wireless").mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.recolectar().freeze().network[0].kind, "wifi")

    def test_una_interfaz_caida_no_declara_velocidad(self):
        # `speed` devuelve -1 cuando no hay enlace, que no es una velocidad.
        self.interfaz("enp5s0", operstate="down", carrier="0", speed="-1")
        interfaz = self.recolectar().freeze().network[0]
        self.assertIsNone(interfaz.speed_mbps)
        self.assertFalse(interfaz.up)
        self.assertEqual(render.interface_state(interfaz), "sin cable")


class TestRender(unittest.TestCase):
    def test_ritmos_en_bytes(self):
        self.assertEqual(render.rate(0), "0 B/s")
        # El kilo va en minúscula, como manda el sistema internacional.
        self.assertEqual(render.rate(2150), "2.1 kB/s")
        self.assertEqual(render.rate(5.5e6), "5.5 MB/s")
        self.assertEqual(render.rate(None), render.DASH)

    def test_ritmos_en_bits(self):
        self.assertEqual(render.rate(2150, bits=True), "17.2 kb/s")
        self.assertEqual(render.rate(None, bits=True), render.DASH)

    def test_las_dos_unidades_cuadran_con_un_test_de_velocidad(self):
        # El caso que motivó tener las dos: un enlace que un gestor de
        # descargas enseña como 116 MB/s es el que speedtest llama 931 Mb/s.
        medido = 116.4e6
        self.assertEqual(render.rate(medido), "116.4 MB/s")
        self.assertEqual(render.rate(medido, bits=True), "931.2 Mb/s")

    def test_van_en_potencias_de_mil_no_de_1024(self):
        # En redes la convención es decimal: un gigabit son mil millones de
        # bits. Con 1024 las dos unidades no cuadrarían entre sí.
        self.assertEqual(render.rate(1e9), "1.0 GB/s")
        self.assertEqual(render.rate(125e6, bits=True), "1.0 Gb/s")

    def test_estado_de_una_interfaz(self):
        activa = NetworkInterface(name="eth0", up=True, ipv4="10.0.0.2")
        self.assertEqual(render.interface_state(activa), "activa")
        sin_ip = NetworkInterface(name="eth0", up=True, carrier=True)
        self.assertEqual(render.interface_state(sin_ip), "sin dirección")
        parada = NetworkInterface(name="eth0", up=False, carrier=None)
        self.assertEqual(render.interface_state(parada), "parada")

    def test_totales_y_problemas(self):
        trafico = NetworkTraffic(rx_bytes=1000, tx_bytes=500, rx_errors=2, tx_dropped=3)
        self.assertEqual(trafico.total_bytes, 1500)
        self.assertEqual(trafico.problems, 5)

    def test_el_ritmo_total_suma_los_dos_sentidos(self):
        self.assertIsNone(NetworkTraffic().total_rate_bps)
        self.assertEqual(NetworkTraffic(rx_rate_bps=100.0, tx_rate_bps=50.0)
                         .total_rate_bps, 150.0)

    def test_velocidades_del_enlace(self):
        self.assertEqual(NetworkInterface(name="a", speed_mbps=100).link_summary,
                         "100 Mb/s")
        self.assertEqual(NetworkInterface(name="a", speed_mbps=2500,
                                          duplex="full").link_summary, "2.5 Gb/s · full")
        self.assertIsNone(NetworkInterface(name="a").link_summary)


if __name__ == "__main__":
    unittest.main()
