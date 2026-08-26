"""Quitarle a una foto del equipo lo que señala a quien la sacó.

Existe porque las capturas del repositorio llevaban dentro el nombre del
equipo y el número de serie de la gráfica del autor. Una captura acaba en un
foro o en un README igual que el informe de fallos, y el informe ya se
cuidaba de esto desde el principio.
"""

import unittest

from silux import privacidad
from silux.model import (CpuInfo, Gpu, GpuMemory, NetworkInterface,
                        Snapshot, System)


def _foto() -> Snapshot:
    return Snapshot(
        monotonic_ns=0, cpu=CpuInfo(),
        system=System(distribution="CachyOS", kernel="Linux 7.2.0",
                      hostname="milkshake", desktop="KDE"),
        gpus=(Gpu(index=0, name="Radeon RX 9070 XT", vendor="AMD",
                  unique_id="d718956bebe9d407",
                  memory=GpuMemory(total_bytes=16 * 1024**3)),),
        network=(NetworkInterface(name="enp6s0", up=True, ipv4="192.168.96.11",
                                  ipv6=("fe80::59e7:c2c7:a19c:a2b4",),
                                  gateway="192.168.96.1",
                                  mac="74:fe:ce:6c:d6:43", speed_mbps=2500),),
    )


class TestLoQueSeTapa(unittest.TestCase):
    def setUp(self):
        self.limpia = privacidad.anonimizar(_foto())

    def test_el_nombre_del_equipo(self):
        self.assertEqual(self.limpia.system.hostname, "equipo")

    def test_el_numero_de_serie_de_la_grafica(self):
        self.assertNotEqual(self.limpia.gpus[0].unique_id, "d718956bebe9d407")

    def test_la_direccion_ip_y_la_puerta_de_enlace(self):
        interfaz = self.limpia.network[0]
        self.assertEqual(interfaz.ipv4, "192.0.2.11")
        self.assertEqual(interfaz.gateway, "192.0.2.1")

    def test_la_direccion_fisica(self):
        self.assertEqual(self.limpia.network[0].mac, "00:00:5e:00:53:af")

    def test_y_la_ipv6(self):
        self.assertEqual(self.limpia.network[0].ipv6, ("2001:db8::11",))

    def test_no_queda_ni_un_rastro_en_la_foto_entera(self):
        """El barrido que se hizo a mano antes de publicar, automatizado."""
        texto = repr(self.limpia)
        for real in ("milkshake", "d718956bebe9d407", "192.168.96",
                     "74:fe:ce:6c:d6:43", "fe80::59e7"):
            self.assertNotIn(real, texto, f"se ha colado {real}")


class TestLoQueNoSeToca(unittest.TestCase):
    def setUp(self):
        self.limpia = privacidad.anonimizar(_foto())

    def test_el_hardware_sigue_entero(self):
        """La gracia de una captura es que enseñe el programa de verdad."""
        self.assertEqual(self.limpia.gpus[0].name, "Radeon RX 9070 XT")
        self.assertEqual(self.limpia.system.distribution, "CachyOS")
        self.assertEqual(self.limpia.network[0].speed_mbps, 2500)

    def test_lo_tapado_mide_lo_mismo(self):
        """Si cambiara el largo, la ventana se recolocaría al ocultarlo."""
        self.assertEqual(len(self.limpia.gpus[0].unique_id),
                         len("d718956bebe9d407"))

    def test_una_foto_sin_nada_que_tapar_se_devuelve_igual(self):
        vacia = Snapshot(monotonic_ns=0, cpu=CpuInfo())
        self.assertIs(privacidad.anonimizar(vacia), vacia)

    def test_no_inventa_una_ip_donde_no_habia(self):
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(), network=(
            NetworkInterface(name="lo", up=True),))
        self.assertIsNone(privacidad.anonimizar(foto).network[0].ipv4)


if __name__ == "__main__":
    unittest.main()
