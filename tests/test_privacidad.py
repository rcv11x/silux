"""Quitarle a una foto del equipo lo que señala a quien la sacó.

Existe porque las capturas del repositorio llevaban dentro el nombre del
equipo y el número de serie de la gráfica del autor. Los datos de entrada de
aquí abajo son inventados, de los rangos de documentación: escribir un caso
de prueba copiando lo que uno tiene delante es justo como llegaron los otros
al repositorio. Una captura acaba en un
foro o en un README igual que el informe de fallos, y el informe ya se
cuidaba de esto desde el principio.
"""

import dataclasses
import re
import unittest

from silux import privacidad
from silux.model import (Battery, CpuInfo, Disk, Display, Edid, Gpu,
                         GpuMemory, NetworkInterface, Partition, Sensor,
                         SensorKind, Snapshot, System)

# Lo que no puede quedar en ninguna parte de la foto anonimizada. Ninguno
# coincide con lo que `privacidad` pone en su lugar: si coincidieran, el
# barrido no distinguiría tapado de sin tapar.
SECRETOS = ("portatil-de-ana", "fedcba9876543210", "203.0.113",
            "00:00:5e:00:53:0b", "2001:db8:1::7", "MON7Q2X91",
            "S5GXNX0R123456", "BAT998877", "/run/media/ana", "ana_wg0")


def _foto() -> Snapshot:
    """Una foto con todo lo que puede llevar algo de quien la saca.

    La anterior traía el sistema, una gráfica y una interfaz, y el test que
    dice barrer «la foto entera» no podía ver el número de serie de un
    monitor, el de un disco, el de una batería, un punto de montaje ni una
    interfaz con nombre propio, porque no venían.
    """
    monitor = Display(connector="DP-1", connected=True,
                      monitor=Edid(manufacturer_id="GBT", model="FO27Q2",
                                   serial="MON7Q2X91"))
    return Snapshot(
        monotonic_ns=0, cpu=CpuInfo(),
        system=System(distribution="CachyOS", kernel="Linux 7.2.0",
                      hostname="portatil-de-ana", desktop="KDE"),
        gpus=(Gpu(index=0, name="Radeon RX 9070 XT", vendor="AMD",
                  unique_id="fedcba9876543210",
                  memory=GpuMemory(total_bytes=16 * 1024**3),
                  displays=(monitor,)),),
        network=(NetworkInterface(name="enp6s0", up=True, ipv4="203.0.113.7",
                                  ipv6=("2001:db8:1::7",),
                                  gateway="203.0.113.1",
                                  mac="00:00:5e:00:53:0b", speed_mbps=2500),
                 NetworkInterface(name="ana_wg0", kind="virtual", up=True)),
        disks=(Disk(name="nvme0n1", model="Samsung SSD 990 PRO",
                    serial="S5GXNX0R123456",
                    partitions=(Partition(name="nvme0n1p2", mountpoint="/"),
                                Partition(name="sda1",
                                          mountpoint="/run/media/ana/USB"))),),
        batteries=(Battery(name="BAT0", serial="BAT998877",
                           manufacturer="SMP", model="5B10W13930"),),
        sensors=(Sensor(key="net/ana_wg0/rx", chip="net",
                        device="Red (ana_wg0)", label="Bajada",
                        kind=SensorKind.NETWORK, value=0.0),
                 Sensor(key="acpitz/1", chip="acpitz",
                        device="portatil-de-ana-acpi", label="temp1",
                        kind=SensorKind.TEMPERATURE, value=40.0)),
    )


class TestLoQueSeTapa(unittest.TestCase):
    def setUp(self):
        self.limpia = privacidad.anonimizar(_foto())

    def test_el_nombre_del_equipo(self):
        self.assertEqual(self.limpia.system.hostname, "silux-pc")

    def test_el_numero_de_serie_de_la_grafica(self):
        self.assertNotEqual(self.limpia.gpus[0].unique_id, "fedcba9876543210")

    def test_la_direccion_ip_y_la_puerta_de_enlace(self):
        interfaz = self.limpia.network[0]
        self.assertEqual(interfaz.ipv4, "192.168.1.120")
        self.assertEqual(interfaz.gateway, "192.168.1.1")

    def test_la_direccion_fisica(self):
        self.assertEqual(self.limpia.network[0].mac, "00:00:5e:00:53:af")

    def test_dos_tarjetas_distintas_no_acaban_con_la_misma_direccion(self):
        # Con la misma falsa en todas, la captura enseñaba dos tarjetas con
        # una sola dirección física, que es justo lo que no puede pasar.
        f = _foto()
        red = (dataclasses.replace(f.network[0], name="enp5s0", mac="00:00:5e:00:53:0b"),
               dataclasses.replace(f.network[0], name="enp6s0", mac="00:00:5e:00:53:0c"),
               # Un puente lleva la de la tarjeta que tiene debajo: la misma
               # de verdad sigue siendo la misma al taparla.
               dataclasses.replace(f.network[0], name="br0", mac="00:00:5e:00:53:0b"),
               dataclasses.replace(f.network[0], name="lo", mac="00:00:00:00:00:00"))
        limpia = privacidad.anonimizar(dataclasses.replace(f, network=red))
        macs = [i.mac for i in limpia.network]
        self.assertEqual(macs[0], privacidad.MAC)
        self.assertNotEqual(macs[0], macs[1])
        self.assertEqual(macs[0], macs[2])
        self.assertEqual(macs[3], "00:00:00:00:00:00")
        for mac in macs[:3]:
            self.assertRegex(mac, r"^00:00:5e:00:53:[0-9a-f]{2}$")
            self.assertNotIn(mac, ("00:00:5e:00:53:0b", "00:00:5e:00:53:0c"))

    def test_la_pagina_de_red_las_ensena_distintas(self):
        from PySide6.QtWidgets import QLabel
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.network import NetworkPage
        from tests import qt

        app = qt.app()
        f = _foto()
        red = (dataclasses.replace(f.network[0], name="enp5s0", mac="00:00:5e:00:53:0b"),
               dataclasses.replace(f.network[0], name="enp6s0", mac="00:00:5e:00:53:0c"))
        pagina = NetworkPage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(privacidad.anonimizar(dataclasses.replace(f, network=red)))
        app.processEvents()
        texto = "\n".join(e.text() for e in pagina.findChildren(QLabel))
        self.assertEqual(len(set(re.findall(r"00:00:5e:00:53:[0-9a-f]{2}", texto))), 2, texto)

    def test_y_la_ipv6(self):
        self.assertEqual(self.limpia.network[0].ipv6, ("2001:db8::11",))

    def test_no_queda_ni_un_rastro_en_la_foto_entera(self):
        """El barrido que se hizo a mano antes de publicar, automatizado."""
        texto = repr(self.limpia)
        for real in SECRETOS:
            self.assertNotIn(real, texto, f"se ha colado {real}")

    def test_y_el_barrido_ve_lo_que_busca(self):
        """Sin tapar, cada secreto está en la foto: si no, no se buscaba nada."""
        texto = repr(_foto())
        for real in SECRETOS:
            self.assertIn(real, texto)


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
        tapada = privacidad.anonimizar(self._foto(equipo="pc", interfaz="enp5s0"))
        self.assertEqual(tapada.network[0].name, "enp5s0")


class TestElNombreDelEquipoSeBuscaComoNombre(unittest.TestCase):
    """Sin distinguir mayúsculas, y como palabra entera.

    Se buscaba como subcadena exacta: «PORTATIL-ANA» se escapaba si el
    hostname era «portatil-ana», que es lo mismo para cualquier persona y
    para el propio sistema; y con un hostname de pocas letras se destrozaban
    nombres que no tenían nada que ver: «lan» convertía `wlan0` en
    `wequipo0`. Por debajo de tres letras ni se intentaba, así que un equipo
    llamado «pc» no se tapaba en ninguna parte.
    """

    def _foto(self, equipo, *, red=(), aparato=None, aviso=None):
        from silux.model import (CpuInfo, Need, NetworkInterface, Note, Sensor,
                                 SensorKind, Snapshot, System)

        return Snapshot(
            monotonic_ns=0, cpu=CpuInfo(), system=System(hostname=equipo),
            network=tuple(NetworkInterface(name=n, up=True) for n in red),
            sensors=((Sensor(key="x/1", chip="acpitz", device=aparato,
                             label="temp1", kind=SensorKind.TEMPERATURE,
                             value=40.0),) if aparato else ()),
            notes=((Note(path="x", need=Need.HARDWARE, message=aviso),)
                   if aviso else ()))

    def test_da_igual_como_vaya_escrito(self):
        tapada = privacidad.anonimizar(self._foto(
            "portatil-ana", aparato="PORTATIL-ANA-acpi",
            aviso="El equipo Portatil-Ana no publica su ventilador."))
        self.assertEqual(tapada.sensors[0].device, f"{privacidad.EQUIPO}-acpi")
        self.assertNotIn("ana", tapada.notes[0].message.lower())

    def test_un_nombre_corto_no_se_come_trozos_de_otros(self):
        tapada = privacidad.anonimizar(self._foto(
            "lan", red=("wlan0",), aparato="Red (wlan0)",
            aviso="La placa lanza un aviso."))
        self.assertEqual(tapada.network[0].name, "wlan0")
        self.assertEqual(tapada.sensors[0].device, "Red (wlan0)")
        self.assertEqual(tapada.notes[0].message, "La placa lanza un aviso.")

    def test_ni_el_de_una_interfaz_del_sistema(self):
        tapada = privacidad.anonimizar(self._foto("dock", red=("docker0",)))
        self.assertEqual(tapada.network[0].name, "docker0")

    def test_un_nombre_ya_tapado_no_se_vuelve_a_buscar(self):
        # Los volcados de antes del 19 de noviembre se llaman «equipo», que es
        # además una palabra: se tapaba «Este equipo no publica…».
        aviso = "Este equipo no publica su ventilador."
        tapada = privacidad.anonimizar(self._foto("equipo", aviso=aviso))
        self.assertEqual(tapada.notes[0].message, aviso)

    def test_pero_un_nombre_corto_entero_si_se_tapa(self):
        tapada = privacidad.anonimizar(self._foto("pc", aparato="pc (ACPI)"))
        self.assertEqual(tapada.sensors[0].device, f"{privacidad.EQUIPO} (ACPI)")


if __name__ == "__main__":
    unittest.main()
