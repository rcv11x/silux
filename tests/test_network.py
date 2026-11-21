"""Las interfaces de red, contra un /sys falso.

Lo que más importa aquí es el cálculo del ritmo: los contadores del kernel son
totales desde que la interfaz se levantó, así que la velocidad sale de restar
dos lecturas. Eso tiene dos trampas —la primera vuelta no tiene con qué
comparar, y los contadores se reinician si la interfaz se cae— y las dos están
probadas.
"""

# Las direcciones son de la TEST-NET-1 (RFC 5737) y la MAC del bloque que la
# RFC 7042 reserva para documentación. No poner aquí las de la máquina en la
# que se escribe el test: acaban publicadas en el repositorio.

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
            # Sin él, los contadores salían de las interfaces del equipo que
            # ejecuta la suite, que también puede tener un enp6s0. Fuera de la
            # carpeta de las interfaces, o se leería como una más.
            mock.patch.object(network, "PROC_DEV", str(self.root) + "-proc-net-dev"),
            # Las direcciones IPv4 vienen de un ioctl, no de un fichero.
            mock.patch.object(network._Addresses, "ip", lambda self, n: self._falsas.get(n)),
            mock.patch.object(network._Addresses, "netmask", lambda self, n: "255.255.255.0"),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.addCleanup(self._tmp.cleanup)
        network._Addresses._falsas = {"enp6s0": "192.0.2.11"}

    def interfaz(self, nombre: str, *, operstate="up", carrier="1", speed="2500",
                 duplex="full", mtu="1500", mac="00:00:5e:00:53:af", tipo="1",
                 rx=1000, tx=500, fisica=True, **extra) -> None:
        base = self.root / nombre
        if fisica:
            # Una tarjeta de verdad cuelga de un bus. Sin este nodo el
            # proveedor la clasifica como virtual, que es lo correcto: así es
            # como se distingue una Realtek de un puente de libvirt.
            (base / "device").mkdir(parents=True, exist_ok=True)
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

    def ruta_por_defecto(self, interfaz: str, puerta_hex: str = "010200C0") -> None:
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
        # El dúplex llega como lo escribe el kernel; cómo se dice es cosa de
        # quien lo pinta.
        self.assertEqual(interfaz.duplex, "full")
        self.assertEqual(render.link_summary(interfaz), "2.5 Gb/s · dúplex completo")
        self.assertEqual(interfaz.mtu, 1500)

    def test_direccion_y_puerta_de_enlace(self):
        interfaz = self.recolectar().freeze().network[0]
        self.assertEqual(interfaz.ipv4, "192.0.2.11")
        # El kernel escribe la puerta en hexadecimal y del revés.
        self.assertEqual(interfaz.gateway, "192.0.2.1")
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
        # Con el reloj en la mano, como en el test de los discos: el de
        # verdad con un margen falla cuando el equipo va cargado.
        proveedor = network.NetworkInterfaces()
        reloj = [1000.0]
        with mock.patch.object(network.time, "monotonic", lambda: reloj[0]):
            self.interfaz("enp6s0", rx=1000, tx=500)
            self.recolectar(proveedor)
            # Un segundo después han entrado 100 KB más.
            reloj[0] += 1.0
            self.interfaz("enp6s0", rx=1000 + 102400, tx=500)
            interfaz = self.recolectar(proveedor).freeze().network[0]
        self.assertEqual(interfaz.traffic.rx_rate_bps, 102400)
        self.assertEqual(interfaz.traffic.tx_rate_bps, 0)

    def test_un_contador_que_se_reinicia_no_da_velocidad_negativa(self):
        # Pasa cuando la interfaz se cae y vuelve a levantarse.
        proveedor = network.NetworkInterfaces()
        self.interfaz("enp6s0", rx=1_000_000, tx=900_000)
        self.recolectar(proveedor)
        self.interfaz("enp6s0", rx=12, tx=8)
        interfaz = self.recolectar(proveedor).freeze().network[0]
        self.assertIsNone(interfaz.traffic.rx_rate_bps)


class TestContadoresDeUnaVez(BancoDeRed):
    """Con cuarenta interfaces (Docker crea un puente y un `veth` por red y
    por contenedor), leer de sysfs los ocho contadores de cada una eran 328
    archivos por muestreo. `/proc/net/dev` los trae todos en uno."""

    PROC = ("Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    "
            "packets errs drop fifo colls carrier compressed\n"
            "enp6s0: 5000 40 1 2 0 0 0 0 3000 30 3 4 0 0 0 0\n")

    def test_salen_de_proc_net_dev_sin_abrir_sysfs(self):
        import builtins
        self.interfaz("enp6s0", rx=1, tx=1)
        _write(pathlib.Path(network.PROC_DEV), self.PROC)
        self.addCleanup(pathlib.Path(network.PROC_DEV).unlink)
        abiertos = []
        original = builtins.open

        def abrir(ruta, *args, **kwargs):
            abiertos.append(str(ruta))
            return original(ruta, *args, **kwargs)

        with mock.patch.object(builtins, "open", abrir):
            trafico = self.recolectar().freeze().network[0].traffic
        self.assertEqual((trafico.rx_bytes, trafico.rx_packets, trafico.rx_errors,
                          trafico.rx_dropped), (5000, 40, 1, 2))
        self.assertEqual((trafico.tx_bytes, trafico.tx_packets, trafico.tx_errors,
                          trafico.tx_dropped), (3000, 30, 3, 4))
        self.assertEqual([r for r in abiertos if "/statistics/" in r], [])

    def test_lo_que_no_esta_ahi_sale_de_sysfs(self):
        self.interfaz("enp6s0", rx=1234, tx=99)
        trafico = self.recolectar().freeze().network[0].traffic
        self.assertEqual((trafico.rx_bytes, trafico.tx_bytes), (1234, 99))

    def test_lo_fijo_de_cada_interfaz_no_se_relee(self):
        import builtins
        proveedor = network.NetworkInterfaces()
        self.interfaz("enp6s0")
        _write(self.root / "enp6s0" / "ifindex", "2")
        self.recolectar(proveedor)
        abiertos = []
        original = builtins.open

        def abrir(ruta, *args, **kwargs):
            abiertos.append(str(ruta))
            return original(ruta, *args, **kwargs)

        with mock.patch.object(builtins, "open", abrir):
            self.recolectar(proveedor)
        self.assertEqual([r for r in abiertos if r.endswith("/type")], [])


class TestClases(BancoDeRed):
    def test_el_bucle_local_no_se_da_por_parado(self):
        # Su driver no informa del enlace y responde «unknown»; llamarlo parado
        # sería mentir sobre una interfaz que está trabajando.
        self.interfaz("lo", operstate="unknown", carrier="1", tipo="772",
                      speed=None, duplex=None, fisica=False)
        interfaz = self.recolectar().freeze().network[0]
        self.assertEqual(interfaz.kind, "loopback")
        self.assertTrue(interfaz.up)

    def test_un_puente_de_maquinas_virtuales(self):
        self.interfaz("virbr0", operstate="down", carrier="0", speed=None,
                      fisica=False)
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

    def test_lo_que_no_lleva_cable_no_se_queda_sin_cable(self):
        # Un puente de máquinas virtuales apagado está parado, no desenchufado.
        # Decir «sin cable» manda a alguien a mirar detrás del equipo.
        self.interfaz("virbr0", operstate="down", carrier="0", speed=None,
                      fisica=False)
        (self.root / "virbr0" / "bridge").mkdir(parents=True, exist_ok=True)
        interfaz = self.recolectar().freeze().network[0]
        self.assertEqual(render.interface_state(interfaz), "parada")


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
        activa = NetworkInterface(name="eth0", up=True, ipv4="192.0.2.2")
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
        resumen = render.link_summary
        self.assertEqual(resumen(NetworkInterface(name="a", speed_mbps=100)), "100 Mb/s")
        self.assertEqual(resumen(NetworkInterface(name="a", speed_mbps=2500, duplex="full")),
                         "2.5 Gb/s · dúplex completo")
        self.assertEqual(resumen(NetworkInterface(name="a", speed_mbps=100, duplex="half")),
                         "100 Mb/s · semidúplex")
        self.assertIsNone(resumen(NetworkInterface(name="a")))

    def test_la_palabra_del_kernel_no_llega_a_la_pantalla(self):
        # «2.5 Gb/s · full», con la interfaz en español. Y un dúplex que el
        # kernel no sabe —«unknown», sin cable— no es un dúplex que enseñar.
        for crudo in ("full", "half", "unknown"):
            texto = render.link_summary(NetworkInterface(name="a", speed_mbps=1000,
                                                         duplex=crudo))
            self.assertNotIn(crudo, texto)

    def test_y_en_ingles_se_dice_en_ingles(self):
        from silux import i18n

        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "es")
        self.assertEqual(render.link_summary(NetworkInterface(name="a", speed_mbps=2500,
                                                              duplex="full")),
                         "2.5 Gb/s · full duplex")


class TestElEnlaceEnLaPagina(unittest.TestCase):
    """Con el volcado del 5800X3D, que tiene una interfaz a 2,5 Gb/s."""

    def test_la_pagina_de_red_lo_dice_en_el_idioma_de_la_interfaz(self):
        try:
            from PySide6.QtWidgets import QLabel
        except ImportError:                            # pragma: no cover
            self.skipTest("sin PySide6")
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.network import NetworkPage
        from tests import qt
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        self.assertTrue([i for i in f.network if i.duplex == "full"],
                        "el volcado ya no tiene un enlace con dúplex")
        theme.set_density("normal", "normal")
        pagina = NetworkPage(theme.palette_for(app, "dark"), Preferences().normalized())
        pagina.apply(f)
        pagina.apply(f)
        textos = [e.text() for e in pagina.findChildren(QLabel)]
        textos += [getattr(e, "_full", "") for e in pagina.findChildren(QLabel)]
        self.assertTrue([t for t in textos if "dúplex completo" in t])
        self.assertFalse([t for t in textos if "· full" in t])


if __name__ == "__main__":
    unittest.main()
