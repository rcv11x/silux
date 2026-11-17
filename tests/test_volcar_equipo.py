"""Lo que tapa `tools/volcar_equipo.py` y cómo se da cuenta de lo que no."""

import importlib.util
import pathlib
import tempfile
import unittest

from silux import privacidad
from silux.model import CpuInfo, Disk, NetworkInterface, Partition, Snapshot


def _herramienta():
    ruta = pathlib.Path(__file__).resolve().parent.parent / "tools" / "volcar_equipo.py"
    spec = importlib.util.spec_from_file_location("volcar_equipo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


volcar = _herramienta()


def _spd(tipo: int, largo: int) -> bytes:
    datos = bytearray(range(256)) * (largo // 256)
    datos[2] = tipo
    return bytes(datos)


class TestPiezasSinNumeroDeSerie(unittest.TestCase):

    def test_spd_ddr4_y_ddr5(self):
        for tipo, largo, (inicio, fin) in ((0x0C, 512, (325, 329)), (0x12, 1024, (517, 521))):
            with self.subTest(tipo=hex(tipo)):
                datos = _spd(tipo, largo)
                limpio, serie = volcar._spd_sin_serie(datos)
                self.assertEqual(serie, datos[inicio:fin])
                self.assertEqual(limpio[inicio:fin], bytes(fin - inicio))
                # Nada más cambia: el resto es lo que decodifica spd.py.
                self.assertEqual(limpio[:inicio] + limpio[fin:], datos[:inicio] + datos[fin:])

    def test_un_spd_que_no_se_conoce_se_deja(self):
        datos = _spd(0x0B, 256)
        self.assertEqual(volcar._spd_sin_serie(datos), (datos, b""))

    def test_edid_con_la_suma_de_control_al_dia(self):
        bloque = bytearray(128)
        bloque[:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
        bloque[12:16] = b"\x12\x34\x56\x78"
        bloque[54:59] = b"\x00\x00\x00\xff\x00"
        bloque[59:72] = b"ABC123456789\n"
        bloque[127] = (-sum(bloque[:127])) % 256
        limpio = volcar._edid_sin_serie(bytes(bloque))
        self.assertEqual(limpio[12:16], bytes(4))
        self.assertNotIn(b"ABC123", limpio)
        self.assertEqual(sum(limpio) % 256, 0)


class TestLaComprobacionFinal(unittest.TestCase):

    def test_encuentra_un_dato_sustituido_y_unos_bytes_crudos(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            (raiz / "texto").write_text("gateway 203.0.113.7\n")
            (raiz / "binario").write_bytes(b"\x00\x01\xe9\x02\xe4\xc8\x00")
            self.assertEqual(volcar.comprobar(raiz, set()), [])
            hallazgos = volcar.comprobar(raiz, {"203.0.113.7"}, frozenset({b"\xe9\x02\xe4\xc8"}))
            self.assertEqual(len(hallazgos), 2, hallazgos)

    def test_una_direccion_de_verdad_no_pasa_y_el_bucle_local_si(self):
        def foto(*interfaces):
            return Snapshot(monotonic_ns=0, cpu=CpuInfo(), network=tuple(interfaces))

        local = NetworkInterface(name="lo", kind="loopback", ipv4="127.0.0.1",
                                 mac="00:00:00:00:00:00", ipv6=("::1",))
        self.assertEqual(volcar._lo_que_anonimizar_taparia(foto(local)), [])
        casa = NetworkInterface(name="enp1s0", ipv4="198.51.100.20", mac=privacidad.MAC)
        self.assertEqual(volcar._lo_que_anonimizar_taparia(foto(local, casa)),
                         ["network.enp1s0.ipv4"])


class TestLasDireccionesDeProc(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.limpio = volcar._Anonimizador(pathlib.Path(tmp.name), {})

    def test_la_puerta_de_enlace_de_proc_net_route(self):
        texto = ("Iface\tDestination\tGateway \tFlags\n"
                 "enp1s0\t00000000\t0100A8C0\t0003\n"
                 "enp1s0\t0000A8C0\t00000000\t0001\n")
        salida = self.limpio._ruta_de_red(texto)
        self.assertNotIn("0100A8C0", salida)
        self.assertNotIn("0000A8C0", salida)
        self.assertIn(volcar._ipv4_hex(privacidad.PUERTA), salida)
        self.assertIn("0100A8C0", self.limpio.secretos)

    def test_ipv6_menos_el_bucle_local(self):
        bucle = "0" * 31 + "1"
        texto = (f"fe800000000000000000000000000001 02 40 20 80 enp1s0\n"
                 f"{bucle} 01 80 10 80 lo\n")
        salida = self.limpio._ipv6(texto)
        self.assertNotIn("fe80", salida)
        self.assertIn(bucle, salida)

    def test_los_montajes_de_alguien(self):
        texto = ("/dev/sda2 / btrfs rw 0 0\n"
                 "/dev/sdb1 /run/media/ana/Fotos\\040viejas ext4 rw 0 0\n")
        salida = self.limpio._mounts(texto)
        self.assertIn(" / btrfs", salida)
        self.assertIn("/media/unidad1", salida)
        self.assertNotIn("ana", salida)

    def test_de_los_montajes_solo_queda_lo_que_es_de_un_disco(self):
        # Lo demás no lo lee nadie y lleva lo que hay abierto en la sesión:
        # el AppImage que se está usando, los contenedores, el usuario.
        texto = ("/dev/sda2 / btrfs rw 0 0\n"
                 "tmpfs /run/user/1000 tmpfs rw,uid=1000 0 0\n"
                 "Juego.AppImage /tmp/.mount_JuegoAbC fuse.Juego.AppImage ro,user_id=1000 0 0\n"
                 "overlay /var/lib/docker/rootfs/overlayfs/0123abcd overlay rw 0 0\n")
        self.assertEqual(self.limpio._mounts(texto), "/dev/sda2 / btrfs rw 0 0\n")

    def test_los_montajes_se_tapan_donde_estan_de_verdad(self):
        # /proc/mounts es un enlace a self/mounts: el archivo que se copia
        # está en otro sitio, y hay que reconocerlo ahí.
        proc = self.limpio.destino / "proc"
        (proc / "self").mkdir(parents=True)
        (proc / "self" / "mounts").write_text(
            "/dev/sda2 / btrfs rw 0 0\n/dev/sdb1 /mnt/datos ext4 rw 0 0\n")
        (proc / "mounts").symlink_to("self/mounts")
        self.limpio.contenidos()
        salida = (proc / "mounts").read_text()
        self.assertNotIn("datos", salida)
        self.assertIn("/dev/sdb1 /media/unidad1 ext4", salida)


class TestLasFuentesAlternativas(unittest.TestCase):
    """El proveedor se queda con la primera fuente de frecuencia que contesta,
    y las demás no las abre: sin ellas en el volcado no se puede probar qué
    pasa en un kernel que no tiene la primera."""

    def test_con_una_fuente_van_las_demas_del_mismo_hilo(self):
        from silux.providers.sysfs_cpu import FUENTES_DE_FRECUENCIA

        carpeta = "/sys/devices/system/cpu/cpu3/cpufreq"
        leidos = {f"{carpeta}/{FUENTES_DE_FRECUENCIA[0]}", "/proc/stat"}
        self.assertEqual(volcar._alternativas(leidos),
                         {f"{carpeta}/{fuente}" for fuente in FUENTES_DE_FRECUENCIA})


class TestLasInterfacesEnSerie(unittest.TestCase):
    """Docker crea un puente por red y un `veth` por contenedor: con una de
    cada basta para ver cómo las trata la página de Red."""

    def test_queda_una_de_cada_familia_y_las_demas_enteras(self):
        nombres = ["lo", "enp5s0", "enp6s0", "docker0", "virbr0", "tailscale0",
                   "br-0123456789ab", "br-ba9876543210", "veth0a1b2c3", "veth4d5e6f7",
                   "veth8091a2b"]
        self.assertEqual(volcar._sobrantes(nombres),
                         {"br-ba9876543210", "veth4d5e6f7", "veth8091a2b"})

    def test_lo_que_sobra_desaparece_de_todas_partes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            nombres = ("docker0", "br-0123456789ab", "br-ba9876543210",
                       "veth0a1b2c3", "veth4d5e6f7")
            (raiz / "sys/class/net").mkdir(parents=True)
            for nombre in nombres:
                carpeta = raiz / "sys/devices/virtual/net" / nombre
                (carpeta / "statistics").mkdir(parents=True)
                (carpeta / "mtu").write_text("1500\n")
                (raiz / "sys/class/net" / nombre).symlink_to(
                    f"../../devices/virtual/net/{nombre}")
            red = raiz / "proc/self/net"
            red.mkdir(parents=True)
            (red / "route").write_text(
                "Iface\tDestination\tGateway\n"
                + "".join(f"{n}\t000011AC\t00000000\n" for n in nombres))
            (red / "if_inet6").write_text(
                "".join(f"fe80000000000000000000000000000{i} 0{i} 40 20 80 {n}\n"
                        for i, n in enumerate(nombres)))
            grabado = {"ioctl_red": {f"{n}:0x8915": "198.51.100.1" for n in nombres}}
            limpio = volcar._Anonimizador(raiz, grabado)

            self.assertEqual(limpio.en_serie(), 2)

            quedan = {"docker0", "br-0123456789ab", "veth0a1b2c3"}
            self.assertEqual({e.name for e in (raiz / "sys/class/net").iterdir()}, quedan)
            self.assertEqual({e.name for e in (raiz / "sys/devices/virtual/net").iterdir()},
                             quedan)
            for archivo in ("route", "if_inet6"):
                texto = (red / archivo).read_text()
                self.assertNotIn("br-ba9876543210", texto)
                self.assertNotIn("veth4d5e6f7", texto)
                self.assertIn("veth0a1b2c3", texto)
            self.assertIn("Iface", (red / "route").read_text())
            self.assertEqual({c.partition(":")[0] for c in limpio.grabado["ioctl_red"]}, quedan)


class TestUnaInterfazConNombrePropio(unittest.TestCase):
    """Una interfaz de WireGuard llamada como su dueño sale en más sitios que
    su carpeta: también en las tablas de `/proc/net`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = pathlib.Path(tmp.name)
        (self.raiz / "sys/class/net").mkdir(parents=True)
        for nombre in ("enp1s0", "AnaPC_wg0"):
            carpeta = self.raiz / "sys/devices/virtual/net" / nombre
            carpeta.mkdir(parents=True)
            (carpeta / "mtu").write_text("1420\n")
            (self.raiz / "sys/class/net" / nombre).symlink_to(
                f"../../devices/virtual/net/{nombre}")
        self.red = self.raiz / "proc/self/net"
        self.red.mkdir(parents=True)
        (self.red / "route").write_text(
            "Iface\tDestination\tGateway\n"
            "enp1s0\t00000000\t0100A8C0\n"
            "AnaPC_wg0\t0000080A\t00000000\n")
        (self.red / "if_inet6").write_text(
            "fe800000000000000000000000000001 03 40 20 80 AnaPC_wg0\n")
        self.limpio = volcar._Anonimizador(self.raiz, {})
        self.limpio.contenidos()
        self.limpio.nombres()

    def test_no_queda_en_las_tablas_de_proc_net(self):
        for tabla in ("route", "if_inet6"):
            texto = (self.red / tabla).read_text()
            self.assertNotIn("AnaPC_wg0", texto, tabla)
            self.assertIn(privacidad.INTERFAZ.format(1), texto, tabla)
        self.assertIn("enp1s0", (self.red / "route").read_text())

    def test_y_la_comprobacion_final_lo_busca_en_cada_byte(self):
        # Que un archivo nuevo lleve el nombre y nadie lo sustituya tiene que
        # parar el volcado, no depender de que alguien se acuerde de taparlo.
        self.assertEqual(volcar.comprobar(self.raiz, self.limpio.secretos), [])
        (self.raiz / "proc/self/net/dev").write_text("AnaPC_wg0: 0 0\n")
        hallazgos = volcar.comprobar(self.raiz, self.limpio.secretos)
        self.assertEqual(len(hallazgos), 1, hallazgos)
        self.assertIn("proc/self/net/dev", hallazgos[0])


class TestLosMontajesEnLaComprobacionFinal(unittest.TestCase):

    @staticmethod
    def _foto(*puntos):
        particiones = tuple(Partition(name=f"sda{n}", mountpoint=punto)
                            for n, punto in enumerate(puntos, 1))
        return Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                        disks=(Disk(name="sda", partitions=particiones),))

    def test_un_montaje_de_alguien_no_pasa(self):
        self.assertEqual(volcar._lo_que_anonimizar_taparia(self._foto("/", "/mnt/datos")),
                         ["disks"])

    def test_uno_ya_sustituido_pasa_lleve_el_numero_que_lleve(self):
        # anonimizar numera por el orden de los discos y el volcado por el de
        # /proc/mounts: que no coincidan no es que quede algo por tapar.
        self.assertEqual(
            volcar._lo_que_anonimizar_taparia(self._foto("/", "/media/unidad3", "/media/unidad2")),
            [])

    def test_un_numero_de_serie_sigue_sin_pasar(self):
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                        disks=(Disk(name="sda", serial="S4EWNX0M123456"),))
        self.assertEqual(volcar._lo_que_anonimizar_taparia(foto), ["disks"])


if __name__ == "__main__":
    unittest.main()
