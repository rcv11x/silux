"""Los discos, contra un /sys/block falso.

Se montan a mano porque hace falta probar combinaciones que no se tienen
delante: un NVMe, un SSD SATA, un disco mecánico, uno externo y uno sin
particionar. La máquina donde corren los tests no tiene por qué llevar ninguno.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from silux import render
from silux.model import Disk, DiskHealth, DiskIo, Partition
from silux.providers import storage
from silux.providers.base import Draft


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
            mock.patch.object(storage, "_ocupacion", lambda punto: (1000, 4000)),
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
        proveedor = storage.Disks()
        self.disco("sda", stat="104 0 1000 0 50 0 500 0 0 0 0")
        self.recolectar(proveedor)
        proveedor._previo["sda"] = (proveedor._previo["sda"][0] - 1.0,
                                    1000 * 512, 500 * 512)
        self.disco("sda", stat="104 0 3000 0 50 0 500 0 0 0 0")
        disco = self.recolectar(proveedor).freeze().disks[0]
        self.assertAlmostEqual(disco.io.read_rate_bps, 2000 * 512, delta=5000)

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

        app = QApplication.instance() or QApplication([])
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

        app = QApplication.instance() or QApplication([])
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
        return {etiqueta: valor for etiqueta, valor, _ in pagina.total_bar._segments}

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
        self.proveedor._diagnostico(draft)
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
        self.proveedor._leido_en["sda"] -= storage.INTERVALO_SALUD + 1
        self._muestra()
        self.assertEqual(self.cliente.read_smart.call_count, 2)

    def test_un_refresco_fallido_no_borra_lo_que_ya_se_sabia(self):
        self._muestra()
        self.proveedor._leido_en["sda"] -= storage.INTERVALO_SALUD + 1
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
