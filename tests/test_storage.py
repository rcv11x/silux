"""Los discos, contra un /sys/block falso.

Se montan a mano porque hace falta probar combinaciones que no se tienen
delante: un NVMe, un SSD SATA, un disco mecánico, uno externo y uno sin
particionar. La máquina donde corren los tests no tiene por qué llevar ninguno.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.model import Disk, DiskHealth, DiskIo, Partition
from silux.providers import storage
from silux.providers.base import Draft
from tests import qt


def _write(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


class BancoDeDiscos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "block").mkdir()
        parches = [
            mock.patch.object(storage, "SYS_BLOCK", self.root / "block"),
            mock.patch.object(storage, "PROC_MOUNTS", str(self.root / "mounts")),
            mock.patch.object(storage, "_usage", lambda punto: (1000, 4000)),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.addCleanup(self._tmp.cleanup)
        _write(self.root / "mounts", "")

    def disco(self, nombre, *, sectores=1000000, rotational="0", modelo="MODELO X",
              vendor=None, firmware="1.0", scheduler="none [mq-deadline] kyber",
              removable="0", logico="512", fisico="4096", stat=None,
              particiones=()) -> pathlib.Path:
        base = self.root / "block" / nombre
        _write(base / "size", str(sectores))
        _write(base / "queue" / "rotational", rotational)
        _write(base / "queue" / "scheduler", scheduler)
        _write(base / "queue" / "logical_block_size", logico)
        _write(base / "queue" / "physical_block_size", fisico)
        _write(base / "removable", removable)
        _write(base / "device" / "model", modelo)
        _write(base / "device" / "firmware_rev", firmware)
        if vendor:
            _write(base / "device" / "vendor", vendor)
        _write(base / "stat", stat or "104 0 22384 0 50 0 4096 0 0 0 0")
        for parte, tam in particiones:
            _write(base / parte / "size", str(tam))
            _write(base / parte / "partition", "1")
        return base

    def montar(self, *entradas) -> None:
        lineas = [f"/dev/{n} {punto} {fs} rw 0 0" for n, punto, fs in entradas]
        _write(self.root / "mounts", "\n".join(lineas))

    def recolectar(self, proveedor=None) -> Draft:
        draft = Draft()
        (proveedor or storage.Disks()).collect(draft)
        return draft


class TestTipos(BancoDeDiscos):
    """Qué disco es cada cosa, que no lo dice ningún campo."""

    def test_un_disco_mecanico(self):
        self.disco("sda", rotational="1", modelo="ST2000DM008")
        disco = self.recolectar().freeze().disks[0]
        self.assertEqual(disco.kind, "HDD")
        self.assertTrue(disco.rotational)

    def test_un_ssd_sata(self):
        self.disco("sdc", rotational="0", modelo="CT500MX500SSD1")
        self.assertEqual(self.recolectar().freeze().disks[0].kind, "SSD")

    def test_un_nvme_no_es_lo_mismo_que_un_ssd(self):
        # Los dos son «no rotatorios» y no se parecen en nada. El nombre del
        # dispositivo es lo que los separa.
        self.disco("nvme0n1", rotational="0", modelo="WD_BLACK SN850X")
        disco = self.recolectar().freeze().disks[0]
        self.assertEqual(disco.kind, "NVMe")
        self.assertEqual(disco.transport, "nvme")

    def test_sin_saber_si_gira_no_se_inventa(self):
        base = self.disco("sdz")
        (base / "queue" / "rotational").unlink()
        self.assertIsNone(self.recolectar().freeze().disks[0].kind)

    def test_el_fabricante_ata_no_es_un_fabricante(self):
        # Todos los discos SATA dicen «ATA» ahí; no aporta nada.
        self.disco("sda", vendor="ATA")
        self.assertIsNone(self.recolectar().freeze().disks[0].vendor)

    def test_los_dispositivos_que_no_son_discos_no_salen(self):
        for nombre in ("loop0", "ram0", "zram0", "dm-0", "sr0"):
            self.disco(nombre)
        self.disco("sda")
        discos = self.recolectar().freeze().disks
        self.assertEqual([d.name for d in discos], ["sda"])


class TestParticiones(BancoDeDiscos):
    def setUp(self):
        super().setUp()
        self.disco("sda", sectores=2000000,
                   particiones=(("sda1", 500000), ("sda2", 1500000)))
        self.montar(("sda1", "/boot", "vfat"), ("sda2", "/", "ext4"))

    def test_las_encuentra_con_su_sistema_de_archivos(self):
        disco = self.recolectar().freeze().disks[0]
        self.assertEqual([p.name for p in disco.partitions], ["sda1", "sda2"])
        self.assertEqual(disco.partitions[1].filesystem, "ext4")
        self.assertEqual(disco.partitions[1].mountpoint, "/")

    def test_una_particion_sin_montar_no_dice_cuanto_ocupa(self):
        self.montar(("sda1", "/boot", "vfat"))
        disco = self.recolectar().freeze().disks[0]
        sin_montar = disco.partitions[1]
        self.assertFalse(sin_montar.mounted)
        self.assertIsNone(sin_montar.used_bytes)

    def test_el_ocupado_del_disco_suma_sus_particiones(self):
        self.assertEqual(self.recolectar().freeze().disks[0].used_bytes, 2000)

    def test_los_sistemas_virtuales_no_son_particiones(self):
        _write(self.root / "mounts",
               "proc /proc proc rw 0 0\ntmpfs /tmp tmpfs rw 0 0\n"
               "/dev/sda1 /boot vfat rw 0 0")
        disco = self.recolectar().freeze().disks[0]
        self.assertEqual([p.mountpoint for p in disco.mounted_partitions], ["/boot"])


class TestRitmo(BancoDeDiscos):
    def test_la_primera_lectura_no_tiene_con_que_comparar(self):
        self.disco("sda")
        disco = self.recolectar().freeze().disks[0]
        self.assertIsNone(disco.io.read_rate_bps)
        self.assertEqual(disco.io.read_bytes, 22384 * 512)

    def test_la_segunda_ya_da_velocidad(self):
        # Con el reloj en la mano: entre una lectura y otra pasa un segundo
        # justo. Con el de verdad y un margen, el test fallaba cuando el
        # equipo iba cargado y entre las dos se colaban unos milisegundos.
        proveedor = storage.Disks()
        reloj = [1000.0]
        with mock.patch.object(storage.time, "monotonic", lambda: reloj[0]):
            self.disco("sda", stat="104 0 1000 0 50 0 500 0 0 0 0")
            self.recolectar(proveedor)
            reloj[0] += 1.0
            self.disco("sda", stat="104 0 3000 0 50 0 500 0 0 0 0")
            disco = self.recolectar(proveedor).freeze().disks[0]
        self.assertEqual(disco.io.read_rate_bps, 2000 * 512)

    def test_un_contador_reiniciado_no_da_ritmo_negativo(self):
        # Pasa al desconectar y volver a conectar un disco externo.
        proveedor = storage.Disks()
        self.disco("sda", stat="104 0 900000 0 50 0 500 0 0 0 0")
        self.recolectar(proveedor)
        self.disco("sda", stat="1 0 10 0 1 0 5 0 0 0 0")
        disco = self.recolectar(proveedor).freeze().disks[0]
        self.assertIsNone(disco.io.read_rate_bps)


class TestEnlacePcie(BancoDeDiscos):
    def test_un_disco_sata_no_tiene_enlace_propio(self):
        # Quien negocia PCIe es su controladora, que además la comparte con los
        # otros discos del mismo cable. Enseñarlo como del disco era mentir.
        self.disco("sda", rotational="1")
        self.assertIsNone(self.recolectar().freeze().disks[0].link)


class TestFormatoDeTamanos(unittest.TestCase):
    def test_los_discos_se_miden_en_terabytes(self):
        # Con la RAM nunca hizo falta, y un total de «8849.3 GB» no se lee.
        self.assertEqual(render.size(2 * 1024**4), "2 TB")
        self.assertEqual(render.size(int(1.8 * 1024**4)), "1.8 TB")
        self.assertEqual(render.size(500 * 1024**3), "500 GB")


class TestSalud(unittest.TestCase):
    def test_la_vida_restante_es_lo_contrario_del_desgaste(self):
        self.assertEqual(DiskHealth(percentage_used=7).life_left_percent, 93)
        self.assertIsNone(DiskHealth().life_left_percent)

    def test_un_disco_pasado_de_vuelta_no_baja_de_cero(self):
        # Los SSD siguen funcionando después del 100 % de desgaste.
        self.assertEqual(DiskHealth(percentage_used=130).life_left_percent, 0)

    def test_el_aviso_critico(self):
        self.assertTrue(DiskHealth(critical_warning=0).healthy)
        self.assertFalse(DiskHealth(critical_warning=1).healthy)
        self.assertIsNone(DiskHealth().healthy)



class TestLaCapturaAnonimaNoEnsenaDondeSeMonta(unittest.TestCase):
    """Un punto de montaje lleva el nombre de quien usa el equipo.

    Una memoria USB se monta en `/run/media/<usuario>/<etiqueta>`, y una
    partición de datos acaba a menudo en `/home/<usuario>/…`. El informe ya
    no los escribía; la página de Almacenamiento sí, y una captura con
    `--anonimo` los enseñaba igual. Los del sistema —`/`, `/boot/efi`,
    `/home`— no dicen nada de nadie y se quedan: son los que hacen falta para
    entender la tabla.
    """

    def _textos(self, foto):
        from PySide6.QtWidgets import QApplication, QLabel
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        app = qt.app()
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences())
        pagina.apply(foto)
        app.processEvents()
        textos = [w.text() for w in pagina.findChildren(QLabel)]
        textos += [w.toolTip() for w in pagina.findChildren(QLabel)]
        return "\n".join(textos)

    def _foto(self):
        from silux.model import CpuInfo, Disk, Partition, Snapshot, System

        particiones = (
            Partition(name="sda1", mountpoint="/boot/efi", filesystem="vfat",
                      size_bytes=600 * 1000**2, used_bytes=20 * 1000**2),
            Partition(name="sda2", mountpoint="/", filesystem="btrfs",
                      size_bytes=200 * 1000**3, used_bytes=90 * 1000**3),
            Partition(name="sdb1", mountpoint="/run/media/zoraida/FOTOS",
                      filesystem="exfat", size_bytes=64 * 1000**3,
                      used_bytes=10 * 1000**3),
            Partition(name="sda3", mountpoint="/home/zoraida/datos",
                      filesystem="ext4", size_bytes=100 * 1000**3,
                      used_bytes=5 * 1000**3),
        )
        disco = Disk(name="sda", model="Samsung SSD 870", kind="SSD",
                     size_bytes=500 * 1000**3, partitions=particiones)
        return Snapshot(monotonic_ns=0, cpu=CpuInfo(), disks=(disco,),
                        system=System(hostname="equipo-de-pruebas"))

    def test_anonima_no_sale_el_usuario(self):
        from silux import privacidad

        texto = self._textos(privacidad.anonymize(self._foto()))
        self.assertNotIn("zoraida", texto)
        self.assertIn("/boot/efi", texto)

    def test_sin_anonimizar_sale_tal_cual(self):
        self.assertIn("/run/media/zoraida/FOTOS", self._textos(self._foto()))


if __name__ == "__main__":
    unittest.main()


class TestDosDiscosIguales(unittest.TestCase):
    """Dos discos a la misma temperatura tumbaban la pestaña entera.

    El sitio más caliente se buscaba con `max()` sobre una lista de tuplas
    (temperatura, disco). Con temperaturas distintas la primera posición
    decide y no se llega a mirar la segunda; en cuanto dos coinciden, Python
    pasa a comparar los Disk y no hay forma de decir si uno es mayor que otro.

    Aparecía con el equipo llevando un rato encendido, que es cuando las
    temperaturas se estabilizan y coinciden.
    """

    def _pagina_con(self, temperaturas):
        from PySide6.QtWidgets import QApplication
        from silux.model import Disk, Snapshot, CpuInfo
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        app = qt.app()
        discos = tuple(
            Disk(name=f"nvme{i}n1", model=f"Disco {i}", temp_c=t,
                 size_bytes=500 * 1000**3, kind="NVMe")
            for i, t in enumerate(temperaturas)
        )
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences())
        pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(), disks=discos))
        return pagina

    def test_con_temperaturas_iguales_no_revienta(self):
        self._pagina_con([42.0, 42.0])

    def test_ni_con_tres(self):
        self._pagina_con([38.5, 38.5, 38.5])

    def test_y_sigue_eligiendo_el_mas_caliente(self):
        pagina = self._pagina_con([35.0, 51.0, 44.0])
        self.assertIn("51", pagina.tile_temp.value.text())


class TestRootsReserveIsReserved(unittest.TestCase):
    """ext4 keeps 5 % of itself for root by default, and that is neither
    used nor anybody's free space. Counted as used (f_blocks − f_bavail), a
    tester's laptop read «Ocupado 40.6 GB · Reservado 8.5 GB»: the reserved
    was only the tables, and the 23 GB for root were inside the used."""

    def test_any_ext4_with_its_default_reserve(self):
        # That laptop's root, 476.4 GB, as statvfs gives it: 4 KiB blocks,
        # 8.5 GB of tables outside f_blocks, 427.3 GB available, 5 % for root.
        bloque = 4096
        f_blocks = int((476.4 - 8.5) * 1e9) // bloque
        f_bavail = int(427.3e9) // bloque
        f_bfree = f_bavail + f_blocks * 5 // 100
        st = os.statvfs_result((bloque, bloque, f_blocks, f_bfree, f_bavail,
                                0, 0, 0, 0, 255))
        with mock.patch.object(storage.os, "statvfs", return_value=st):
            usados, libres = storage._usage("/")
        particion = Partition(name="nvme0n1p2", mountpoint="/", filesystem="ext4",
                              size_bytes=int(476.4e9), used_bytes=usados, free_bytes=libres)
        disco = Disk(name="nvme0n1", kind="NVMe", size_bytes=int(476.4e9),
                     partitions=(particion,))
        usado, libre, reservado, sin_montar = render.space((disco,))
        self.assertAlmostEqual(libre / 1e9, 427.3, delta=0.1)
        self.assertAlmostEqual(reservado / 1e9, 8.5 + (476.4 - 8.5) * 0.05, delta=0.1)
        self.assertAlmostEqual(usado / 1e9, 476.4 - 427.3 - reservado / 1e9, delta=0.1)
        self.assertEqual(sin_montar, 0)


class TestEspacioLibre(unittest.TestCase):
    """Lo que no está montado no está libre.

    En un equipo con Windows al lado, la barra decía «Libre 859.4 GB» de un
    disco de 931 con solo 359 en particiones montadas: restaba lo ocupado a
    la capacidad y daba por libre todo lo demás. El recuadro de al lado, que
    suma el hueco de las particiones montadas, decía 280.6 GB en la misma
    pantalla.
    """

    GB = 1000 ** 3

    def _pagina(self, particiones, capacidad):
        from PySide6.QtWidgets import QApplication
        from silux.model import CpuInfo, Disk, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        app = qt.app()
        # `used_bytes` y `mounted_partitions` son propiedades: salen de las
        # particiones, no se pasan.
        disco = Disk(name="sda", model="Samsung SSD 870", kind="SSD",
                     size_bytes=capacidad, partitions=tuple(particiones))
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences())
        pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(), disks=(disco,)))
        return pagina

    def _dual_boot(self):
        """Un disco de 931 GB con 359 en Linux y el resto en Windows."""
        from silux.model import Partition
        return [
            Partition(name="sda6", mountpoint="/efi", filesystem="vfat",
                      size_bytes=2 * self.GB, used_bytes=694 * 1000**2,
                      free_bytes=1300 * 1000**2),
            Partition(name="sda7", mountpoint="/", filesystem="ext4",
                      size_bytes=357 * self.GB, used_bytes=71 * self.GB,
                      free_bytes=279 * self.GB),
        ]

    def _trozos(self, pagina):
        return {s.label: s.value for s in pagina.total_bar._segments}

    def test_lo_libre_sale_de_las_particiones_montadas(self):
        trozos = self._trozos(self._pagina(self._dual_boot(), 931 * self.GB))
        self.assertLess(trozos["Libre"], 300 * self.GB,
                        "está contando como libre el disco sin montar")

    def test_y_el_resto_del_disco_se_dice_aparte(self):
        trozos = self._trozos(self._pagina(self._dual_boot(), 931 * self.GB))
        self.assertIn("Sin montar", trozos)
        self.assertGreater(trozos["Sin montar"], 500 * self.GB)

    def test_los_tres_trozos_suman_el_disco(self):
        trozos = self._trozos(self._pagina(self._dual_boot(), 931 * self.GB))
        self.assertAlmostEqual(sum(trozos.values()), 931 * self.GB,
                               delta=self.GB)

    def test_what_a_mounted_filesystem_keeps_is_not_unmounted(self):
        # A tester's laptop, its whole NVMe mounted: «Sin montar 8.6 GB» were
        # what ext4 keeps for itself (5 % for root, its tables).
        from silux.model import Partition
        GB = self.GB
        particiones = [
            Partition(name="nvme0n1p2", mountpoint="/boot/efi", filesystem="vfat",
                      size_bytes=512 * 1000 ** 2, used_bytes=8 * 1000 ** 2,
                      free_bytes=504 * 1000 ** 2),
            Partition(name="nvme0n1p3", mountpoint="/", filesystem="ext4",
                      size_bytes=476_400 * 1000 ** 2, used_bytes=38_600 * 1000 ** 2,
                      free_bytes=429_300 * 1000 ** 2),
        ]
        trozos = self._trozos(self._pagina(particiones, 476_912 * 1000 ** 2))
        self.assertNotIn("Sin montar", trozos)
        self.assertAlmostEqual(trozos["Reservado"], 8_500 * 1000 ** 2, delta=GB // 10)

    def test_un_disco_entero_montado_no_gana_un_trozo_de_mas(self):
        from silux.model import Partition
        entera = [Partition(name="sda1", mountpoint="/", filesystem="ext4",
                            size_bytes=500 * self.GB, used_bytes=200 * self.GB,
                            free_bytes=300 * self.GB)]
        trozos = self._trozos(self._pagina(entera, 500 * self.GB))
        self.assertNotIn("Sin montar", trozos)
        self.assertEqual(trozos["Libre"], 300 * self.GB)


class TestLaTemperaturaDelDiagnostico(unittest.TestCase):
    """El SMART se lee de tarde en tarde; su temperatura tiene que quedarse.

    El disco se reconstruye desde sysfs en cada muestreo, así que la
    temperatura que vino con el diagnóstico se pierde salvo que se guarde y se
    vuelva a poner. Sin esto salía un instante al desbloquear y en la muestra
    siguiente volvía a «—».
    """

    def setUp(self):
        self.cliente = mock.Mock()
        self.cliente.connected.return_value = True
        self.cliente.read_smart.return_value = (b"datos", "ata")
        self.proveedor = storage.Disks(client=self.cliente)

        self.salud = DiskHealth(power_on_hours=10)
        parches = [
            mock.patch.object(storage.smart_module, "parse",
                              return_value=self.salud),
            mock.patch.object(storage.smart_module, "ata_temperature",
                              return_value=38.0),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def _muestra(self, temp_c=None):
        draft = Draft()
        draft.disks = [Disk(name="sda", temp_c=temp_c)]
        self.proveedor._diagnosis(draft)
        return draft.disks[0]

    def test_la_primera_vez_la_trae_el_diagnostico(self):
        self.assertEqual(self._muestra().temp_c, 38.0)

    def test_y_sigue_ahi_en_la_muestra_siguiente(self):
        self._muestra()
        # Segunda vuelta: aún no toca releer el SMART, y aun así el dato está.
        self.assertEqual(self._muestra().temp_c, 38.0)
        self.assertEqual(self.cliente.read_smart.call_count, 1)

    def test_lo_que_publique_hwmon_manda(self):
        self._muestra()
        # Se relee en cada muestreo, así que es más fresca que la del SMART.
        self.assertEqual(self._muestra(temp_c=41.0).temp_c, 41.0)

    def test_pasado_el_intervalo_se_vuelve_a_preguntar(self):
        self._muestra()
        self.proveedor._read_at["sda"] -= storage.HEALTH_INTERVAL_S + 1
        self._muestra()
        self.assertEqual(self.cliente.read_smart.call_count, 2)

    def test_un_refresco_fallido_no_borra_lo_que_ya_se_sabia(self):
        self._muestra()
        self.proveedor._read_at["sda"] -= storage.HEALTH_INTERVAL_S + 1
        self.cliente.read_smart.side_effect = OSError("el disco no contesta")
        disco = self._muestra()
        self.assertEqual(disco.health, self.salud)
        self.assertEqual(disco.temp_c, 38.0)

    def test_un_disco_que_nunca_contesto_se_da_por_mudo(self):
        self.cliente.read_smart.side_effect = OSError("el disco no contesta")
        self.assertEqual(self._muestra().health, DiskHealth())
        self._muestra()
        # Y no se le vuelve a preguntar en cada muestreo.
        self.assertEqual(self.cliente.read_smart.call_count, 1)


class TestAvisosDeSalud(unittest.TestCase):
    """Lo que un disco dice de sí mismo y no salía en ninguna parte."""

    def _salud(self, **campos):
        from silux.model import DiskHealth

        return DiskHealth(**campos)

    def test_un_disco_sano_no_dice_nada(self):
        self.assertEqual(render.disk_warnings(
            self._salud(critical_warning=0, percentage_used=12)), [])

    def test_cada_bit_del_aviso_tiene_su_frase(self):
        """Están definidos por la especificación y significan lo mismo en
        todas las marcas."""
        avisos = render.disk_warnings(self._salud(critical_warning=0b1001))
        self.assertEqual(len(avisos), 2)
        self.assertTrue(all(nivel == "crítico" for nivel, _ in avisos))
        texto = " ".join(t for _, t in avisos)
        self.assertIn("reserva", texto)
        self.assertIn("solo lectura", texto)

    def test_un_bit_que_no_conocemos_se_dice_igual(self):
        """La especificación crece; callarse un aviso porque es nuevo sería lo
        peor que se puede hacer con este campo."""
        avisos = render.disk_warnings(self._salud(critical_warning=0b1000000))
        self.assertEqual(len(avisos), 1)
        self.assertIn("0x40", avisos[0][1])

    def test_los_datos_ilegibles_se_avisan(self):
        avisos = render.disk_warnings(
            self._salud(critical_warning=0, media_errors=47))
        self.assertEqual(avisos[0][0], "alto")
        self.assertIn("47", avisos[0][1])

    def test_la_vida_baja_se_avisa_antes_de_llegar_a_cero(self):
        """Decirlo al 0 % no sirve de nada: el aviso existe para que dé tiempo
        a hacer una copia."""
        self.assertTrue(render.disk_warnings(
            self._salud(critical_warning=0, percentage_used=95)))
        self.assertFalse(render.disk_warnings(
            self._salud(critical_warning=0, percentage_used=50)))

    def test_los_apagones_bruscos_no_son_un_aviso(self):
        """Cuentan cortes de luz y botones de reinicio: en un sobremesa son
        normales."""
        self.assertEqual(render.disk_warnings(
            self._salud(critical_warning=0, unsafe_shutdowns=120)), [])

    def test_sin_diagnostico_no_se_inventa_nada(self):
        self.assertEqual(render.disk_warnings(self._salud()), [])
        self.assertEqual(render.disk_warnings(None), [])


class TestElNombreDelBus(unittest.TestCase):
    """La ficha de cada disco pasaba a mayúsculas lo que da el kernel, y
    «nvme» salía «NVME» al lado de un «Tipo: NVMe» bien escrito."""

    def test_cada_bus_como_se_escribe(self):
        casos = {"nvme": "NVMe", "sata": "SATA", "usb": "USB", "mmc": "MMC"}
        for crudo, escrito in casos.items():
            with self.subTest(bus=crudo):
                self.assertEqual(render.disk_bus(crudo), escrito)
        self.assertEqual(render.disk_bus(None), render.DASH)
        # Uno que no esté en la tabla sale en mayúsculas, como hasta ahora.
        self.assertEqual(render.disk_bus("sas"), "SAS")

    def test_la_ficha_del_5800x3d_dice_nvme_bien_escrito(self):
        from silux.i18n import _
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(f)
        conexion = _("storage.field.bus")
        self.assertEqual(pagina._grids["nvme0n1"]._values[conexion].full_text(), "NVMe")
        self.assertEqual(pagina._grids["sda"]._values[conexion].full_text(), "SATA")

    def test_y_el_informe_no_lo_repite_ni_lo_deja_en_crudo(self):
        from silux import report
        from tests.test_equipos import EQUIPOS, foto

        texto = report.build(foto(EQUIPOS / "5800x3d")[0])
        self.assertIn("- Tipo: NVMe · 931.5 GB", texto)
        self.assertIn("- Tipo: HDD · SATA · ", texto)
        self.assertNotIn("· nvme", texto)


def _identify(modelo: str) -> str:
    """An ATA IDENTIFY as `ata_device/*/id` publishes it: 256 hex words, eight
    per line, the model in words 27 to 46, two characters per word."""
    palabras = [0] * 256
    texto = modelo.ljust(40).encode("ascii")
    for i in range(20):
        palabras[27 + i] = int.from_bytes(texto[2 * i:2 * i + 2], "big")
    lineas = [" ".join(f"{p:04x}" for p in palabras[i:i + 8]) for i in range(0, 256, 8)]
    return "\n".join(lineas)


class TestTheWholeModel(BancoDeDiscos):
    """sysfs cuts the model to 16 characters; the IDENTIFY has all of it."""

    def _sata(self, sysfs: str, entero: str) -> pathlib.Path:
        base = self.disco("sda", modelo=sysfs)
        puerto = self.root / "devices" / "pci0000:00" / "0000:00:17.0" / "ata3"
        dispositivo = puerto / "host2" / "target2:0:0" / "2:0:0:0"
        _write(dispositivo / "model", sysfs)
        _write(puerto / "link3" / "dev3.0" / "ata_device" / "dev3.0" / "id", _identify(entero))
        import shutil
        shutil.rmtree(base / "device")
        (base / "device").symlink_to(dispositivo)
        return base

    def test_from_the_identify(self):
        base = self._sata("KINGSTON SA400S3", "KINGSTON SA400S37480G")
        self.assertEqual(storage._ata_model(base), "KINGSTON SA400S37480G")

    def test_without_it_there_is_nothing_to_say(self):
        self.assertIsNone(storage._ata_model(self.disco("sda")))


class TestNotLessThanWhatItHolds(unittest.TestCase):
    """A tester's A400 had 316 GB on it and said 33 MB written in its life."""

    GB = 1000 ** 3
    A400 = [(241, 100, 68_446), (242, 100, 134_816), (231, 58, 58), (9, 100, 9_927)]

    def _diagnostico(self, modelo_entero):
        from tests.test_smart import tabla_ata

        cliente = mock.Mock()
        cliente.connected.return_value = True
        cliente.read_smart.return_value = (tabla_ata(self.A400), "ata")
        proveedor = storage.Disks(client=cliente)
        draft = Draft()
        draft.disks = [Disk(name="sda", model="KINGSTON SA400S3", partitions=(
            Partition(name="sda3", mountpoint="/", filesystem="ext4",
                      size_bytes=438 * self.GB, used_bytes=316 * self.GB,
                      free_bytes=94 * self.GB),))]
        with mock.patch.object(storage, "_ata_model", return_value=modelo_entero):
            proveedor._diagnosis(draft)
        return draft.disks[0].health

    def test_with_the_whole_model_the_unit_is_known(self):
        salud = self._diagnostico("KINGSTON SA400S37480G")
        self.assertEqual(salud.written_bytes, 68_446 * 1024 ** 3)
        self.assertFalse(salud.counters_unit_unknown)

    def test_without_it_the_impossible_figure_is_not_shown(self):
        # In 512-byte sectors it said 35 MB: less than the 316 GB it holds.
        salud = self._diagnostico(None)
        self.assertIsNone(salud.written_bytes)
        self.assertIsNone(salud.read_bytes)
        self.assertTrue(salud.counters_unit_unknown)
        self.assertEqual(salud.power_on_hours, 9_927)

    def test_on_the_page_the_row_hides_and_the_foot_says_why(self):
        from silux.i18n import _
        from silux.model import CpuInfo, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        app = qt.app()
        disco = Disk(name="sda", model="KINGSTON SA400S3", vendor="Kingston", kind="SSD", rotational=False,
                     size_bytes=480 * self.GB, health=self._diagnostico(None))
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(), disks=(disco,)))
        app.processEvents()
        grid = pagina._grids["sda"]
        self.assertFalse(grid._values[_("storage.field.written")].isVisibleTo(grid))
        pie = pagina._pies["sda"]
        self.assertTrue(pie.isVisibleTo(pagina))
        self.assertEqual(pie.text(), _("storage.na.written.unit"))

    def test_a_disk_whose_smart_does_not_count_it_says_so(self):
        # A WD Blue HDD's SMART, read with permissions: hours, no total written.
        from silux.i18n import _
        from silux.model import CpuInfo, DiskHealth, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        app = qt.app()
        disco = Disk(name="sdb", model="WDC WD10EZEX-21M", kind="HDD", rotational=True,
                     size_bytes=1000 * self.GB, health=DiskHealth(power_on_hours=10_938))
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(monotonic_ns=0, cpu=CpuInfo(), disks=(disco,)))
        app.processEvents()
        grid = pagina._grids["sdb"]
        self.assertFalse(grid._values[_("storage.field.written")].isVisibleTo(grid))
        self.assertIn(_("storage.na.written"), pagina._pies["sdb"].text())
