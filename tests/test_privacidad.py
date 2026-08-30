"""Quitarle a una foto del equipo lo que señala a quien la sacó.

Existe porque las capturas del repositorio llevaban dentro el nombre del
equipo y el número de serie de la gráfica del autor. Los datos de entrada de
aquí abajo son inventados, de los rangos de documentación: escribir un caso
de prueba copiando lo que uno tiene delante es justo como llegaron los otros
al repositorio. Una captura acaba en un
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
                      hostname="portatil-de-ana", desktop="KDE"),
        gpus=(Gpu(index=0, name="Radeon RX 9070 XT", vendor="AMD",
                  unique_id="fedcba9876543210",
                  memory=GpuMemory(total_bytes=16 * 1024**3)),),
        network=(NetworkInterface(name="enp6s0", up=True, ipv4="203.0.113.7",
                                  ipv6=("2001:db8:1::7",),
                                  gateway="203.0.113.1",
                                  mac="00:00:5e:00:53:0b", speed_mbps=2500),),
    )


class TestLoQueSeTapa(unittest.TestCase):
    def setUp(self):
        self.limpia = privacidad.anonimizar(_foto())

    def test_el_nombre_del_equipo(self):
        self.assertEqual(self.limpia.system.hostname, "equipo")

    def test_el_numero_de_serie_de_la_grafica(self):
        self.assertNotEqual(self.limpia.gpus[0].unique_id, "fedcba9876543210")

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
        for real in ("portatil-de-ana", "fedcba9876543210", "203.0.113",
                     "00:00:5e:00:53:0b", "2001:db8:1::7"):
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
                         len("fedcba9876543210"))

    def test_una_foto_sin_nada_que_tapar_se_devuelve_igual(self):
        vacia = Snapshot(monotonic_ns=0, cpu=CpuInfo())
        self.assertIs(privacidad.anonimizar(vacia), vacia)

    def test_no_inventa_una_ip_donde_no_habia(self):
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(), network=(
            NetworkInterface(name="lo", up=True),))
        self.assertIsNone(privacidad.anonimizar(foto).network[0].ipv4)


if __name__ == "__main__":
    unittest.main()


class TestLaMarcaDeLasCapturas(unittest.TestCase):
    """Una captura se publica igual que un informe, y no se puede leer igual.

    El comprobador de privacidad busca texto en lo versionado, y eso no sirve
    para un PNG: la dirección física que se ve en pantalla no está escrita en
    ninguna parte del archivo. Estuvo dando por buena una captura con la MAC de
    la máquina y su IPv6 pública a la vista.

    Como no se puede leer lo que enseña la imagen, se comprueba cómo se hizo:
    el programa escribe dentro del PNG si tapó los identificadores o no, y el
    comprobador exige esa marca.
    """

    def _comprobador(self):
        import importlib.util
        import pathlib

        ruta = pathlib.Path(__file__).resolve().parent.parent / "tools" / "comprobar_privacidad.py"
        spec = importlib.util.spec_from_file_location("comprobar_privacidad", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_el_valor_de_la_marca_no_lleva_tildes(self):
        """Con «sí», Qt lo escribe en Latin-1 y quien busque UTF-8 no lo ve.

        Es un metadato que lee un script, no texto de ventana, así que en
        ASCII no hay dos formas de escribirlo. La primera versión de esto
        buscaba «sí» en UTF-8 y no encontraba nunca la marca que sí estaba.
        """
        self.assertTrue(self._comprobador().ANONIMA.isascii())

    def test_quien_escribe_la_marca_y_quien_la_busca_dicen_lo_mismo(self):
        """Si divergen, el comprobador avisa de todas o de ninguna."""
        import pathlib

        fuente = (pathlib.Path(__file__).resolve().parent.parent
                  / "silux" / "ui" / "app.py").read_text(encoding="utf-8")
        marca = self._comprobador().ANONIMA.decode("ascii")
        clave, valor = marca.split("\x00")
        self.assertIn(f'"{clave}"', fuente,
                      "la captura no escribe la clave que el comprobador busca")
        self.assertIn(f'"{valor}"', fuente,
                      "la captura no escribe el valor que el comprobador busca")

    def test_las_capturas_publicadas_estan_marcadas(self):
        """Las del repositorio van al README, o sea a un sitio público."""
        avisos = self._comprobador()._capturas_delatoras()
        self.assertEqual(avisos, [], "hay capturas sin hacer con --anonimo")


class TestElNombreDelEquipoSeColabaPorLaRed(unittest.TestCase):
    """El nombre no vive solo en su campo.

    Una interfaz de Tailscale, de ZeroTier o un puente hecho a mano se llaman
    como la máquina. Tapando `system.hostname` el informe seguía enseñando
    «alex_portatil (virtual)» en la lista de red, y eso es un archivo pensado
    para pegar en público. Se vio en el primer informe de un portátil.
    """

    def _foto(self, equipo="alex_portatil", interfaz="alex_portatil"):
        from silux.model import (Board, CpuInfo, NetworkInterface, Snapshot,
                                 System)

        return Snapshot(monotonic_ns=0, cpu=CpuInfo(), board=Board(),
                        system=System(hostname=equipo),
                        network=(NetworkInterface(name=interfaz, up=False),
                                 NetworkInterface(name="wlan0", up=True)))

    def test_la_interfaz_que_se_llama_como_el_equipo_se_tapa(self):
        tapada = privacidad.anonimizar(self._foto())
        self.assertNotIn("alex_portatil", [i.name for i in tapada.network])

    def test_las_demas_conservan_su_nombre(self):
        tapada = privacidad.anonimizar(self._foto())
        self.assertIn("wlan0", [i.name for i in tapada.network])

    def test_también_cuando_el_nombre_va_dentro(self):
        """`docker-alex_portatil` o `br-alex_portatil-0`."""
        tapada = privacidad.anonimizar(
            self._foto(interfaz="br-alex_portatil-0"))
        self.assertNotIn("alex_portatil", tapada.network[0].name)

    def test_un_nombre_de_equipo_muy_corto_no_arrasa_con_todo(self):
        """Con un equipo llamado «pc», tapar esas dos letras destrozaría
        «enp5s0» y media lista sin motivo."""
        tapada = privacidad.anonimizar(self._foto(equipo="pc", interfaz="pcie0"))
        self.assertEqual(tapada.network[0].name, "pcie0")
