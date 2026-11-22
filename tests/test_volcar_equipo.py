"""Lo que tapa el volcador (`silux/volcado.py`) y cómo se da cuenta de lo que no."""

import contextlib
import pathlib
import tempfile
import unittest

from silux import privacidad
from silux.model import CpuInfo, Disk, NetworkInterface, Partition, Snapshot
from tests.arbol import arbol

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


def _herramienta():
    from silux import volcado
    return volcado


volcar = _herramienta()


def _spd(tipo: int, largo: int) -> bytes:
    datos = bytearray(range(256)) * (largo // 256)
    datos[2] = tipo
    return bytes(datos)


class TestPiezasSinNumeroDeSerie(unittest.TestCase):

    def test_spd_ddr2_ddr3_ddr4_y_ddr5(self):
        for tipo, largo, (inicio, fin) in ((0x08, 256, (95, 99)), (0x0B, 256, (122, 126)),
                                           (0x0C, 512, (325, 329)), (0x12, 1024, (517, 521))):
            with self.subTest(tipo=hex(tipo)):
                datos = _spd(tipo, largo)
                limpio, serie = volcar._spd_without_serial(datos)
                self.assertEqual(serie, datos[inicio:fin])
                self.assertEqual(limpio[inicio:fin], bytes(fin - inicio))
                # Nada más cambia: el resto es lo que decodifica spd.py.
                self.assertEqual(limpio[:inicio] + limpio[fin:], datos[:inicio] + datos[fin:])

    def test_un_spd_que_no_se_conoce_se_deja(self):
        datos = _spd(0x01, 256)
        self.assertEqual(volcar._spd_without_serial(datos), (datos, b""))

    def test_no_dump_carries_a_module_serial(self):
        """The suite's dumps, each SPD chip: its serial is zeros."""
        from tests.test_equipos import EQUIPOS
        for eeprom in sorted(EQUIPOS.glob("*/sys/**/eeprom")):
            datos = eeprom.read_bytes()
            limpio, serie = volcar._spd_without_serial(datos)
            with self.subTest(chip=str(eeprom.relative_to(EQUIPOS))):
                self.assertEqual(serie, bytes(len(serie)))

    def test_the_ata_identify_keeps_its_model(self):
        from tests.test_storage import _identify

        palabras = _identify("KINGSTON SA400S37480G").split()
        serie = "50026B7784".ljust(20).encode()
        for i in range(10):
            palabras[10 + i] = f"{int.from_bytes(serie[2 * i:2 * i + 2], 'big'):04x}"
        limpio, quitado = volcar._identify_without_serial(" ".join(palabras))
        self.assertEqual(quitado, "50026B7784")
        self.assertNotIn("3530", limpio.split()[10:20])
        self.assertEqual(limpio.split()[27:47], palabras[27:47])

    def test_edid_con_la_suma_de_control_al_dia(self):
        bloque = bytearray(128)
        bloque[:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
        bloque[12:16] = b"\x12\x34\x56\x78"
        bloque[54:59] = b"\x00\x00\x00\xff\x00"
        bloque[59:72] = b"ABC123456789\n"
        bloque[127] = (-sum(bloque[:127])) % 256
        limpio = volcar._edid_without_serial(bytes(bloque))
        self.assertEqual(limpio[12:16], bytes(4))
        self.assertNotIn(b"ABC123", limpio)
        self.assertEqual(sum(limpio) % 256, 0)


class TestAnEdidStays(unittest.TestCase):
    """An EDID goes into the dump with only its serial covered, not taken
    out: a TV's was, as its «no number» (01 01 01 01) was taken for a
    serial and found in the EDID's unused standard timings."""

    def _dumped(self, raw: bytes):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        edid = root / "sys/devices/pci0000:00/0000:00:02.0/drm/card1/card1-HDMI-A-1/edid"
        edid.parent.mkdir(parents=True)
        edid.write_bytes(raw)
        cleaner = volcar._Anonymizer(root, {})
        cleaner.clean_contents()
        return edid.read_bytes(), volcar.found_in(root, cleaner.secrets, cleaner.raw_secrets,
                                                 own={})

    def _with_serial(self, raw: bytes, number: bytes, unused_timings: bool) -> bytes:
        block = bytearray(raw[:128])
        block[12:16] = number
        if unused_timings:
            # The last two standard timings unused, as most TVs leave them.
            block[50:54] = b"\x01\x01\x01\x01"
        block[127] = (-sum(block[:127])) % 256
        return bytes(block) + raw[128:]

    def test_every_real_edid_with_any_number(self):
        from silux import edid
        fixtures = pathlib.Path(__file__).parent / "fixtures" / "edid"
        for source in sorted(fixtures.glob("*.bin")):
            for number, unused in ((b"\x01\x01\x01\x01", True), (b"\x01\x01\x01\x01", False),
                                   (bytes(4), True), (b"\x8a\x3b\x01\x00", True)):
                with self.subTest(source.name, number=number.hex(), unused=unused):
                    raw = self._with_serial(source.read_bytes(), number, unused)
                    clean, findings = self._dumped(raw)
                    self.assertEqual(findings, [])
                    self.assertEqual(clean[12:16], bytes(4))
                    self.assertEqual(sum(clean[:128]) % 256, 0)
                    # Only the serial changed: the rest reads the same.
                    before, after = edid.parse(raw), edid.parse(clean)
                    self.assertEqual((after.model, after.native_width, after.width_mm),
                                     (before.model, before.native_width, before.width_mm))
                    self.assertEqual(clean[128:], raw[128:])

    def test_a_text_serial_is_looked_for_elsewhere(self):
        fixtures = pathlib.Path(__file__).parent / "fixtures" / "edid"
        block = bytearray((fixtures / "lg-27gl850-144hz.bin").read_bytes()[:128])
        block[90:108] = b"\x00\x00\x00\xff\x00" + b"SN12AB34567\n "
        block[127] = (-sum(block[:127])) % 256
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        (root / "edid").write_bytes(bytes(block))
        (root / "nota").write_text("SN12AB34567\n")
        cleaner = volcar._Anonymizer(root, {})
        cleaner.clean_contents()
        self.assertNotIn(b"SN12AB34567", (root / "edid").read_bytes())
        found = volcar.found_in(root, cleaner.secrets, cleaner.raw_secrets, own={})
        self.assertEqual([path for path, _kind, _what in found], ["nota"])


class TestLaComprobacionFinal(unittest.TestCase):

    def test_encuentra_un_dato_sustituido_y_unos_bytes_crudos(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            (raiz / "texto").write_text("gateway 203.0.113.7\n")
            (raiz / "binario").write_bytes(b"\x00\x01\xe9\x02\xe4\xc8\x00")
            self.assertEqual(volcar.check(raiz, set()), [])
            hallazgos = volcar.check(raiz, {"203.0.113.7"}, frozenset({b"\xe9\x02\xe4\xc8"}))
            self.assertEqual(len(hallazgos), 2, hallazgos)

    def test_una_direccion_de_verdad_no_pasa_y_el_bucle_local_si(self):
        def foto(*interfaces):
            return Snapshot(monotonic_ns=0, cpu=CpuInfo(), network=tuple(interfaces))

        local = NetworkInterface(name="lo", kind="loopback", ipv4="127.0.0.1",
                                 mac="00:00:00:00:00:00", ipv6=("::1",))
        self.assertEqual(volcar._what_anonymize_would_cover(foto(local)), [])
        casa = NetworkInterface(name="enp1s0", ipv4="198.51.100.20", mac=privacidad.MAC)
        self.assertEqual(volcar._what_anonymize_would_cover(foto(local, casa)),
                         ["network[1].ipv4"])


class TestLasDireccionesDeProc(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.limpio = volcar._Anonymizer(pathlib.Path(tmp.name), {})

    def test_la_puerta_de_enlace_de_proc_net_route(self):
        texto = ("Iface\tDestination\tGateway \tFlags\n"
                 "enp1s0\t00000000\t0100A8C0\t0003\n"
                 "enp1s0\t0000A8C0\t00000000\t0001\n")
        salida = self.limpio._network_path(texto)
        self.assertNotIn("0100A8C0", salida)
        self.assertNotIn("0000A8C0", salida)
        self.assertIn(volcar._ipv4_hex(privacidad.GATEWAY), salida)
        self.assertIn("0100A8C0", self.limpio.secrets)

    def test_whoever_built_the_kernel(self):
        # /proc/version names the builder: a list address in Debian, and
        # in a kernel someone compiled at home, theirs.
        # Split so that the privacy checker does not find it here.
        builder = "debian-kernel" + "@" + "lists.debian.org"
        texto = (f"Linux version 6.12.117+deb13-amd64 ({builder}) "
                 "(x86_64-linux-gnu-gcc-14 (Debian 14.2.0-19) 14.2.0) #1 SMP\n")
        salida = self.limpio._replace_text(texto)
        self.assertNotIn(builder, salida)
        self.assertIn("(usuario@example.org) (x86_64-linux-gnu-gcc-14", salida)
        self.assertIn(builder, self.limpio.secrets)

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
        proc = self.limpio.target / "proc"
        (proc / "self").mkdir(parents=True)
        (proc / "self" / "mounts").write_text(
            "/dev/sda2 / btrfs rw 0 0\n/dev/sdb1 /mnt/datos ext4 rw 0 0\n")
        (proc / "mounts").symlink_to("self/mounts")
        self.limpio.clean_contents()
        salida = (proc / "mounts").read_text()
        self.assertNotIn("datos", salida)
        self.assertIn("/dev/sdb1 /media/unidad1 ext4", salida)

    def test_a_mount_has_the_same_substitute_in_mounts_and_statvfs(self):
        # A desktop's second disk was /media/unidad1 in mounts and unidad2 in
        # statvfs: its path held something the text cover changes, and
        # statvfs was numbered after it. Replayed, the disk had no numbers.
        punto = f"{self.limpio.home}/discos/datos"
        self.limpio.recording = {"statfs": {"/": [1, 2, 3, 4], punto: [5, 6, 7, 8]}}
        salida = self.limpio._mounts(f"/dev/sda2 / btrfs rw 0 0\n/dev/sdb1 {punto} ext4 rw 0 0\n")
        self.assertIn("/dev/sdb1 /media/unidad1 ext4", salida)
        self.assertEqual(self.limpio.clean_recording()["statfs"],
                         {"/": [1, 2, 3, 4], "/media/unidad1": [5, 6, 7, 8]})


class TestLasFuentesAlternativas(unittest.TestCase):
    """El proveedor se queda con la primera fuente de frecuencia que contesta,
    y las demás no las abre: sin ellas en el volcado no se puede probar qué
    pasa en un kernel que no tiene la primera."""

    def test_con_una_fuente_van_las_demas_del_mismo_hilo(self):
        from silux.providers.sysfs_cpu import FREQUENCY_SOURCES

        carpeta = "/sys/devices/system/cpu/cpu3/cpufreq"
        leidos = {f"{carpeta}/{FREQUENCY_SOURCES[0]}", "/proc/stat"}
        self.assertEqual(volcar._alternatives(leidos),
                         {f"{carpeta}/{fuente}" for fuente in FREQUENCY_SOURCES})


class TestLasInterfacesEnSerie(unittest.TestCase):
    """Docker crea un puente por red y un `veth` por contenedor: con una de
    cada basta para ver cómo las trata la página de Red."""

    def test_queda_una_de_cada_familia_y_las_demas_enteras(self):
        nombres = ["lo", "enp5s0", "enp6s0", "docker0", "virbr0", "tailscale0",
                   "br-0123456789ab", "br-ba9876543210", "veth0a1b2c3", "veth4d5e6f7",
                   "veth8091a2b"]
        self.assertEqual(volcar._extra_in_series(nombres),
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
            limpio = volcar._Anonymizer(raiz, grabado)

            self.assertEqual(limpio.drop_serial_interfaces(), 2)

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
            self.assertEqual({c.partition(":")[0] for c in limpio.recording["ioctl_red"]}, quedan)


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
        self.limpio = volcar._Anonymizer(self.raiz, {})
        self.limpio.clean_contents()
        self.limpio.rename_interfaces()

    def test_no_queda_en_las_tablas_de_proc_net(self):
        for tabla in ("route", "if_inet6"):
            texto = (self.red / tabla).read_text()
            self.assertNotIn("AnaPC_wg0", texto, tabla)
            self.assertIn(privacidad.INTERFACE.format(1), texto, tabla)
        self.assertIn("enp1s0", (self.red / "route").read_text())

    def test_y_la_comprobacion_final_lo_busca_en_cada_byte(self):
        # Que un archivo nuevo lleve el nombre y nadie lo sustituya tiene que
        # parar el volcado, no depender de que alguien se acuerde de taparlo.
        self.assertEqual(volcar.check(self.raiz, self.limpio.secrets), [])
        (self.raiz / "proc/self/net/dev").write_text("AnaPC_wg0: 0 0\n")
        hallazgos = volcar.check(self.raiz, self.limpio.secrets)
        self.assertEqual(len(hallazgos), 1, hallazgos)
        self.assertIn("proc/self/net/dev", hallazgos[0])


class TestAnNvidiaCard(unittest.TestCase):
    """The first annex of the prueba2, from a laptop with an RTX 4050, did not
    come out: «anonimizar todavía encuentra qué tapar: gpus». NVML's UUID
    («GPU-» and a UUID) had its UUID zeroed by the dumper, and anonimizar
    still covered the rest. Any machine with an awake NVIDIA had no annex."""

    UUID = "GPU-5c2b6d0e-8f41-4a7d-b3e9-1f0c2a7d9e64"

    def _dump_with_the_card(self, tmp):
        import dataclasses
        import json
        import shutil
        from silux import nvml
        work = pathlib.Path(tmp) / "equipo"
        shutil.copytree(EQUIPOS / "qemu-kvm", work, symlinks=True)
        grabado = json.loads((work / "grabado.json").read_text())
        # As the NVIDIA provider records it: a dict per card, without serial.
        card = nvml.NvidiaGpu(
            pci_slot="0000:01:00.0", name="NVIDIA GeForce RTX 4050 Laptop GPU",
            vbios="95.07.2E.00.44", driver_version="550.163.01", uuid=self.UUID,
            cuda_cores=2560, memory_total_bytes=6 << 30, memory_bus_bits=96,
            power_cap_w=60.0, link_generation=1, link_width=8)
        nvml_recorded = {"abierta": True,
                         "tarjetas": [dict(dataclasses.asdict(card), serial=None,
                                           throttle_reasons=[])]}
        # Only NVML's goes through the dumper's cleaning: the rest of this
        # dump was cleaned when it was made.
        limpio = volcar._Anonymizer(work, {"nvml": nvml_recorded})
        grabado["nvml"] = limpio.clean_recording()["nvml"]
        (work / "grabado.json").write_text(json.dumps(grabado, indent=1))
        return work, limpio

    def test_its_uuid_is_covered_and_the_check_finds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, limpio = self._dump_with_the_card(tmp)
            photo = volcar.snapshot_of(work)
            self.assertIn("NVIDIA GeForce RTX 4050 Laptop GPU", [g.name for g in photo.gpus])
            self.assertEqual(volcar._what_anonymize_would_cover(photo), [])
            self.assertNotIn(self.UUID[4:], (work / "grabado.json").read_text())
            self.assertEqual(volcar.check(work, limpio.secrets), [])
            # And found anywhere else it went, byte by byte.
            (work / "proc" / "uuid-de-mas").write_text(self.UUID)
            self.assertTrue(volcar.check(work, limpio.secrets))

    def test_what_is_left_is_said_by_its_field_and_not_its_value(self):
        from silux.model import Gpu
        photo = Snapshot(monotonic_ns=0, cpu=CpuInfo(), gpus=(Gpu(name="x"), Gpu(unique_id=self.UUID)))
        quedan = volcar._what_anonymize_would_cover(photo)
        self.assertEqual(quedan, ["gpus[1].unique_id"])
        self.assertNotIn(self.UUID, " ".join(quedan))


class TestWhatPathlibLists(unittest.TestCase):
    """The providers list and look with pathlib. In Python 3.10 pathlib keeps
    its own `os.listdir` and `os.stat` (`_NormalAccessor`), taken when it is
    imported: the compat AppImage's annex lacked `/sys/bus/i2c/devices`,
    where the memory provider looks for the SPD chips."""

    def test_a_listed_folder_and_a_looked_at_file_are_noted(self):
        from silux import sysroot
        with arbol({"/sys/bus/i2c/devices/0-0050/name": "ee1004\n"}):
            with volcar._noting() as (_leidos, listados, mirados):
                carpeta = pathlib.Path(sysroot.path("/sys/bus/i2c/devices"))
                [entrada.name for entrada in carpeta.iterdir()]
                (carpeta / "0-0050" / "eeprom").exists()
        self.assertIn("/sys/bus/i2c/devices", listados)
        self.assertIn("/sys/bus/i2c/devices/0-0050/eeprom", mirados)

    def test_and_what_wakes_a_sleeping_card_is_not_read_with_it_either(self):
        # Path.read_text opened with that kept io.open: past the guard, the
        # compat's annex would wake a laptop's sleeping card.
        from silux import sysroot
        with _montado():
            dormidas = volcar._SleepingCards()
            with volcar._noting() as (leidos, _listados, _mirados), \
                    volcar._without_waking(dormidas):
                enlace = pathlib.Path(sysroot.path(f"{GRAFICA}/current_link_speed"))
                with self.assertRaises(FileNotFoundError):
                    enlace.read_text()
                self.assertEqual(pathlib.Path(sysroot.path(f"{GRAFICA}/vendor")).read_text(),
                                 "0x1002\n")
        self.assertIn(f"{GRAFICA}/vendor", leidos)


class TestAUsbMaker(unittest.TestCase):
    """A USB device's maker is a company, and its name is everywhere: a card
    reader says «Generic» (AMD's sound card is «HD-Audio Generic»), a
    network adapter «Realtek» (and so is the sound codec). Taken for a
    secret, the final check refused to write the dump of such a machine."""

    def test_it_goes_and_is_not_looked_for_elsewhere(self):
        for fabricante, modelo, sonido in (
                ("Generic", "USB3.0-CRW", "Codec: Generic HDMI\n"),
                ("Realtek", "USB 10/100/1000 LAN", "Codec: Realtek ALC1220\n")):
            with self.subTest(fabricante=fabricante), tempfile.TemporaryDirectory() as tmp:
                raiz = pathlib.Path(tmp)
                aparato = raiz / "sys/devices/pci0000:00/0000:00:08.1/usb1/1-3"
                aparato.mkdir(parents=True)
                (aparato / "manufacturer").write_text(fabricante + "\n")
                (aparato / "product").write_text(modelo + "\n")
                (raiz / "proc/asound/card0").mkdir(parents=True)
                (raiz / "proc/asound/card0/codec#0").write_text(sonido)
                limpio = volcar._Anonymizer(raiz, {})
                limpio.clean_contents()
                self.assertFalse((aparato / "manufacturer").exists())
                self.assertEqual(volcar.check(raiz, limpio.secrets), [])
                # The model does say what someone has plugged in: still looked for.
                self.assertIn(modelo, limpio.secrets)


class TestLosMontajesEnLaComprobacionFinal(unittest.TestCase):

    @staticmethod
    def _foto(*puntos):
        particiones = tuple(Partition(name=f"sda{n}", mountpoint=punto)
                            for n, punto in enumerate(puntos, 1))
        return Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                        disks=(Disk(name="sda", partitions=particiones),))

    def test_un_montaje_de_alguien_no_pasa(self):
        self.assertEqual(volcar._what_anonymize_would_cover(self._foto("/", "/mnt/datos")),
                         ["disks[0].partitions[1].mountpoint"])

    def test_uno_ya_sustituido_pasa_lleve_el_numero_que_lleve(self):
        # anonimizar numera por el orden de los discos y el volcado por el de
        # /proc/mounts: que no coincidan no es que quede algo por tapar.
        self.assertEqual(
            volcar._what_anonymize_would_cover(self._foto("/", "/media/unidad3", "/media/unidad2")),
            [])

    def test_un_numero_de_serie_sigue_sin_pasar(self):
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                        disks=(Disk(name="sda", serial="S4EWNX0M123456"),))
        self.assertEqual(volcar._what_anonymize_would_cover(foto), ["disks[0].serial"])




# Una RX 9070 XT tal como la publica el 5800X3D volcado: el puerto raíz, el
# conmutador que lleva la tarjeta dentro (subida y bajada), la gráfica y su
# audio HDMI en la misma ranura. Los valores son los de ese volcado. Lo que
# cambia es el estado de energía, que vale lo que el kernel escribe cuando la
# tarjeta duerme: `suspended` (Documentation/ABI/testing/sysfs-devices-power)
# y `D3cold` (Documentation/ABI/testing/sysfs-bus-pci, `power_state`, 5.11).
PUERTO = "/sys/devices/pci0000:00/0000:00:03.1"
SUBIDA = f"{PUERTO}/0000:0a:00.0"
BAJADA = f"{SUBIDA}/0000:0b:00.0"
GRAFICA = f"{BAJADA}/0000:0c:00.0"
AUDIO = f"{BAJADA}/0000:0c:00.1"


def _equipo_con_dedicada(estado: str, power_state: str):
    archivos = {}
    for puente in (PUERTO, SUBIDA, BAJADA):
        archivos.update({f"{puente}/class": "0x060400\n",
                         f"{puente}/current_link_speed": "16.0 GT/s PCIe\n",
                         f"{puente}/current_link_width": "16\n"})
    archivos.update({
        f"{GRAFICA}/vendor": "0x1002\n", f"{GRAFICA}/device": "0x7550\n",
        f"{GRAFICA}/class": "0x030000\n",
        f"{GRAFICA}/power/runtime_status": f"{estado}\n",
        f"{GRAFICA}/power_state": f"{power_state}\n",
        f"{GRAFICA}/power/control": "auto\n",
        f"{GRAFICA}/current_link_speed": "32.0 GT/s PCIe\n",
        f"{GRAFICA}/current_link_width": "16\n",
        f"{GRAFICA}/max_link_speed": "32.0 GT/s PCIe\n",
        f"{GRAFICA}/gpu_busy_percent": "0\n",
        f"{GRAFICA}/hwmon/hwmon3/name": "amdgpu\n",
        f"{GRAFICA}/hwmon/hwmon3/temp1_input": "38000\n",
        f"{AUDIO}/vendor": "0x1002\n", f"{AUDIO}/class": "0x040300\n",
        f"{AUDIO}/current_link_speed": "32.0 GT/s PCIe\n",
    })
    return archivos


@contextlib.contextmanager
def _montado(estado="suspended", power_state="D3cold"):
    with arbol(_equipo_con_dedicada(estado, power_state),
               carpetas=[f"{GRAFICA}/drm/card1", f"{GRAFICA}/drm/renderD128"]) as raiz:
        # Los enlaces que pone el núcleo de dispositivos: el del bus
        # (drivers/base/bus.c, `bus_add_device`), el de cada clase y el
        # `device` de vuelta (drivers/base/core.c, `device_add_class_symlinks`).
        enlaces = {
            "/sys/class/drm/card1": f"../..{GRAFICA[4:]}/drm/card1",
            f"{GRAFICA}/drm/card1/device": "../../../0000:0c:00.0",
            "/sys/class/hwmon/hwmon3": f"../..{GRAFICA[4:]}/hwmon/hwmon3",
            f"{GRAFICA}/hwmon/hwmon3/device": "../../../0000:0c:00.0",
        }
        for ranura, carpeta in (("0000:00:03.1", PUERTO), ("0000:0a:00.0", SUBIDA),
                                ("0000:0b:00.0", BAJADA), ("0000:0c:00.0", GRAFICA),
                                ("0000:0c:00.1", AUDIO)):
            enlaces[f"/sys/bus/pci/devices/{ranura}"] = f"../../..{carpeta[4:]}"
        for enlace, destino in enlaces.items():
            camino = raiz / enlace.lstrip("/")
            camino.parent.mkdir(parents=True, exist_ok=True)
            camino.symlink_to(destino)
        yield raiz


class TestUnaGraficaDormidaSeQuedaDormida(unittest.TestCase):
    """B-1: volcar un portátil no puede despertar la dedicada que duerme.

    Desde 6.18 leer `current_link_speed` la saca de D3cold
    (`pci_config_pm_runtime_get()`), y el volcado grabaría una tarjeta
    encendida por la herramienta.
    """

    def test_se_ve_dormida_por_cualquiera_de_los_dos_archivos(self):
        for estado, power_state in (("suspended", "D3cold"), ("suspended", "D0"),
                                    ("active", "D3hot")):
            with self.subTest(estado=estado, power_state=power_state), \
                    _montado(estado, power_state):
                self.assertEqual(volcar._SleepingCards().asleep, ["0000:0c:00.0"])
        with _montado("active", "D0"):
            self.assertFalse(volcar._SleepingCards())

    def test_de_ella_su_ranura_y_sus_puentes_solo_quien_es_y_como_esta(self):
        with _montado():
            dormidas = volcar._SleepingCards()
            for permitido in (f"{GRAFICA}/vendor", f"{GRAFICA}/class",
                              "/sys/bus/pci/devices/0000:0c:00.0/power/runtime_status",
                              f"{GRAFICA}/power_state", f"{AUDIO}/class"):
                self.assertFalse(dormidas.forbidden(permitido), permitido)
            for prohibido in (f"{GRAFICA}/current_link_speed",
                              "/sys/bus/pci/devices/0000:0c:00.0/gpu_busy_percent",
                              "/sys/class/hwmon/hwmon3/temp1_input",
                              f"{AUDIO}/current_link_speed",
                              f"{PUERTO}/current_link_speed",
                              "/dev/dri/renderD128", "/dev/dri/card1"):
                self.assertTrue(dormidas.forbidden(prohibido), prohibido)
            # Lo que no es de ella se lee como siempre.
            self.assertFalse(dormidas.forbidden("/proc/cpuinfo"))

    @staticmethod
    def _leidos_de_verdad(estado="suspended", power_state="D3cold"):
        """Lo que abre el Collector, con los enlaces resueltos."""
        import os

        from silux import sysroot

        with _montado(estado, power_state):
            dormidas = volcar._SleepingCards()
            leidos = volcar._collect(dormidas)[0]
            return dormidas, {sysroot.unrooted(os.path.realpath(sysroot.path(c))) for c in leidos}

    def test_el_collector_de_verdad_no_la_toca(self):
        _dormidas, leidos = self._leidos_de_verdad()
        suyos = {c for c in leidos if c.startswith(PUERTO)}
        # La encontró: sin esto, no tocarla no diría nada.
        self.assertIn(f"{GRAFICA}/vendor", suyos)
        seguros = {"vendor", "device", "class", "runtime_status", "power_state",
                   "subsystem_vendor", "subsystem_device", "revision", "control"}
        self.assertEqual(sorted(c for c in suyos if c.rsplit("/", 1)[-1] not in seguros), [])

    def test_despierta_se_lee_entera(self):
        dormidas, leidos = self._leidos_de_verdad("active", "D0")
        self.assertIn(f"{GRAFICA}/current_link_speed", leidos)
        self.assertEqual(dormidas.power_files(), {
            f"/sys/bus/pci/devices/0000:0c:00.0/{nombre}"
            for nombre in ("power/runtime_status", "power_state", "power/control")})


class TestMontarDesdeLaTerminal(unittest.TestCase):
    """`tools/montar_equipo.py` monta el volcado como lo montan los tests.

    Con `SILUX_SYSROOT` apuntando a la carpeta del repositorio faltan las
    carpetas vacías, que git no guarda: la integrada del i5-10400 salía sin
    sus unidades de ejecución en las capturas, y con ellas en los tests.
    """

    def _unidades(self, orden, entorno=None):
        import json
        import os
        import subprocess
        import sys

        raiz = pathlib.Path(__file__).resolve().parent.parent
        salida = subprocess.run(
            [sys.executable, *orden, sys.executable, "-m", "silux.cli", "--json"],
            cwd=raiz, capture_output=True, text=True, timeout=120,
            env={**os.environ, **(entorno or {})})
        self.assertEqual(salida.returncode, 0, salida.stderr[-400:])
        return json.loads(salida.stdout)["gpus"][0]["compute_units"]

    def test_la_orden_ve_lo_mismo_que_los_tests(self):
        self.assertEqual(self._unidades(["tools/montar_equipo.py", "i5-10400"]), 23)

    def test_que_es_justo_lo_que_la_variable_a_pelo_no_ve(self):
        raiz = pathlib.Path(__file__).resolve().parent
        carpeta = raiz / "fixtures" / "equipos" / "i5-10400"
        if (carpeta / "sys/devices/pci0000:00/0000:00:02.0/drm/renderD128").exists():
            self.skipTest("esta copia del repositorio conserva las carpetas vacías")
        self.assertIsNone(self._unidades(["-c", "import subprocess, sys; "
                                          "sys.exit(subprocess.run(sys.argv[1:]).returncode)"],
                                         {"SILUX_SYSROOT": str(carpeta)}))

    def test_sin_volcado_o_sin_orden_lo_dice(self):
        import subprocess
        import sys

        raiz = pathlib.Path(__file__).resolve().parent.parent
        for orden in (["no-existe", "true"], ["i5-10400"]):
            salida = subprocess.run([sys.executable, "tools/montar_equipo.py", *orden],
                                    cwd=raiz, capture_output=True, text=True, timeout=60)
            self.assertEqual(salida.returncode, 2, orden)


if __name__ == "__main__":
    unittest.main()
