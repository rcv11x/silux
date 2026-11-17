"""Almacenamiento: lo que se ve del TRIM, y el diagnóstico entero con permisos.

Las líneas de `/proc/mounts` y los valores de `discard_max_bytes` son los
del 5800X3D: dos NVMe, un SSD SATA y dos discos de platos, uno de ellos SMR.
"""

import dataclasses
import pathlib
import unittest

from silux import render
from silux.i18n import _
from silux.model import Disk, DiskHealth
from silux.providers import storage
from tests import pantalla, qt
from tests.arbol import arbol
from tests.test_al_momento import con_permisos
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

MONTAJES = (
    "/dev/nvme0n1p2 / btrfs rw,relatime,compress=zstd:3,ssd,discard=async,space_cache=v2 0 0\n"
    "/dev/nvme0n1p1 /boot vfat rw,relatime,fmask=0022 0 0\n"
    "/dev/nvme1n1p1 /mnt/juegos ext4 rw,relatime 0 0\n"
    "/dev/sdb1 /mnt/almacen ext4 rw,relatime 0 0\n"
    "tmpfs /tmp tmpfs rw,nosuid,nodev 0 0\n")


class TestLoQueSeLee(unittest.TestCase):

    def test_que_unidad_admite_descartes(self):
        archivos = {"/sys/block/nvme0n1/queue/discard_max_bytes": "2199023255040\n",
                    "/sys/block/sdb/queue/discard_max_bytes": "0\n"}
        with arbol(archivos) as raiz:
            self.assertIs(storage._admite_descartes(raiz / "sys/block/nvme0n1"), True)
            self.assertIs(storage._admite_descartes(raiz / "sys/block/sdb"), False)
            self.assertIsNone(storage._admite_descartes(raiz / "sys/block/no-existe"))

    def test_que_particiones_van_montadas_con_discard(self):
        with arbol({"/proc/mounts": MONTAJES}):
            self.assertEqual(storage._con_discard(), {"nvme0n1p2"})

    def test_una_opcion_que_solo_contiene_la_palabra_no_cuenta(self):
        with arbol({"/proc/mounts": "/dev/sda1 /x ext4 rw,nodiscard 0 0\n"}):
            self.assertEqual(storage._con_discard(), set())

    def test_el_temporizador(self):
        with arbol({storage.FSTRIM_ACTIVADO: ""}):
            self.assertTrue(storage._fstrim_activo())
        with arbol({"/proc/mounts": MONTAJES}):
            self.assertFalse(storage._fstrim_activo())


class TestLoQueSeDice(unittest.TestCase):

    def _disco(self, **campos):
        return Disk(name="x", **campos)

    def test_se_dice_lo_que_se_ve_y_no_un_si_a_secas(self):
        self.assertEqual(render.trim(self._disco(discard=True, discard_mounted=True,
                                                 fstrim_timer=True, rotational=False)),
                         "lo admite · montado con discard · fstrim.timer activado")
        self.assertEqual(render.trim(self._disco(discard=True, rotational=False)),
                         "lo admite · no se ve que se esté haciendo")

    def test_un_disco_de_platos_que_los_admite_es_un_smr(self):
        self.assertEqual(render.trim(self._disco(discard=True, rotational=True)),
                         "admite descartes (disco SMR)")

    def test_el_que_no_los_admite_no_ensena_la_fila(self):
        self.assertIsNone(render.trim(self._disco(discard=False, rotational=True)))
        self.assertIsNone(render.trim(self._disco()))

    def test_el_diagnostico_entero_en_filas(self):
        salud = DiskHealth(power_on_hours=1200, power_cycles=310, unsafe_shutdowns=12,
                           media_errors=0, spare_percent=100, critical_warning=0,
                           read_bytes=3 << 40,
                           attributes=((5, 100, 0), (199, 200, 3), (170, 98, 12)))
        filas = dict(render.smart_rows(salud))
        self.assertEqual(filas[_("smart.cycles")], "310")
        self.assertEqual(filas[_("smart.warning")], _("smart.warning.none"))
        self.assertEqual(filas[_("smart.spare")], "100 %")
        self.assertEqual(filas["199 · " + _("smart.attr.199")], "200 · en crudo 3")
        # El que no es de los comunes sale con su número, sin nombre inventado.
        self.assertEqual(filas["170 · " + _("smart.attr.other")], "98 · en crudo 12")

    def test_un_sata_guarda_su_tabla_de_atributos(self):
        from silux import smart
        from tests.test_smart import tabla_ata

        salud = smart.parse(tabla_ata([(9, 100, 1234), (5, 100, 0), (199, 200, 2)]), "ata")
        self.assertEqual(salud.attributes, ((5, 100, 0), (9, 100, 1234), (199, 200, 2)))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPagina(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        base = foto(EQUIPOS / "5800x3d")[0]
        # Lo que el proveedor dio en esa máquina para cada disco.
        visto = {"nvme0n1": (True, True), "nvme1n1": (True, False), "sda": (True, False),
                 "sdb": (False, False), "sdc": (True, False)}
        cls.foto = dataclasses.replace(base, disks=tuple(
            dataclasses.replace(d, discard=visto[d.name][0], discard_mounted=visto[d.name][1],
                                fstrim_timer=True) for d in base.disks))

    def _pagina(self, ventana):
        ventana.select_section("Almacenamiento")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.storage_page

    def test_el_trim_de_cada_disco_en_sus_detalles(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            fila = _("storage.field.trim")
            self.assertEqual(pagina._details["nvme0n1"]._values[fila].full_text(),
                             "lo admite · montado con discard · fstrim.timer activado")
            self.assertEqual(pagina._details["sda"]._values[fila].full_text(),
                             "admite descartes (disco SMR) · fstrim.timer activado")
            # El que no admite descartes no enseña la fila, ni con guion.
            pagina._folds["sdb"].boton.click()
            for _vez in range(3):
                self.app.processEvents()
            self.assertFalse(pagina._details["sdb"]._values[fila].isVisible())
            self.assertFalse(pagina._details["sdb"]._names[fila].isVisible())

    def test_el_diagnostico_completo_solo_con_permisos_y_sin_salir(self):
        with pantalla.Ventana(self.foto) as ventana:
            pagina = self._pagina(ventana)
            self.assertFalse(pagina._smart["nvme0n1"].isVisible())
            con = con_permisos(self.foto)
            con = dataclasses.replace(con, disks=tuple(
                dataclasses.replace(d, health=dataclasses.replace(
                    d.health, power_cycles=310, unsafe_shutdowns=12, media_errors=0,
                    critical_warning=0)) for d in con.disks))
            ventana._on_sample(con)
            for _vez in range(4):
                self.app.processEvents()
            pliegue = pagina._smart["nvme0n1"]
            self.assertTrue(pliegue.isVisible())
            rejilla = pliegue.body.itemAt(0).widget()
            self.assertEqual(rejilla._values[_("smart.cycles")].full_text(), "310")
            self.assertEqual(rejilla._values[_("smart.unsafe")].full_text(), "12")
            # Y si se pierden, se va.
            ventana._on_sample(self.foto)
            for _vez in range(4):
                self.app.processEvents()
            self.assertFalse(pagina._smart["nvme0n1"].isVisible())


if __name__ == "__main__":
    unittest.main()
