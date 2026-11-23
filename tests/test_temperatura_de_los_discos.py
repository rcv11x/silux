"""La temperatura de un disco SATA que no la publica: candado o aviso, no «—».

Un NVMe trae su sensor bajo el propio controlador. Un SATA solo la da por dos
caminos: el módulo `drivetemp`, que casi ninguna distribución carga, o su
diagnóstico (SMART), que pide permisos. En el 5800X3D, con tres discos SATA y
sin ninguna de las dos cosas, la ficha de cada uno decía «Temperatura —»: el
mismo guion de «no lo sé» para un dato que está a un clic. Lo mismo las horas
de encendido, lo escrito y la vida restante, que salen del mismo diagnóstico.
"""

import dataclasses
import unittest

from silux.i18n import _
from silux.model import DiskHealth
from tests import qt
from tests.test_equipos import EQUIPOS, foto, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

DEL_DIAGNOSTICO = ("gpu.sensor.temp", "storage.field.hours", "storage.field.written",
                   "storage.field.life")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaFichaDeCadaDisco(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.amd = shared_snapshot(EQUIPOS / "5800x3d")
        cls.intel = shared_snapshot(EQUIPOS / "i5-10400")

    def _pagina(self, f):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.storage import StoragePage

        app = qt.app()
        pagina = StoragePage(theme.palette_for(app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(f)
        app.processEvents()
        return pagina

    def test_el_volcado_tiene_el_caso(self):
        sata = [d for d in self.amd.disks if d.kind != "NVMe"]
        self.assertEqual(len(sata), 3)
        self.assertTrue(all(d.temp_c is None for d in sata))
        self.assertIsNotNone(self.amd.permission_note("disks.health"))

    def test_sin_permisos_el_sata_lleva_candado_y_el_nvme_su_cifra(self):
        pagina = self._pagina(self.amd)
        temperatura = _("gpu.sensor.temp")
        for disco in self.amd.disks:
            rejilla = pagina._grids[disco.name]
            with self.subTest(disco=disco.name):
                self.assertEqual(rejilla.is_locked(temperatura), disco.temp_c is None)
                if disco.temp_c is not None:
                    self.assertIn("°C", rejilla._values[temperatura].text())
                else:
                    self.assertIn(self.amd.permission_note("disks.health").message,
                                  rejilla._candados[temperatura].toolTip())

    def test_lo_demas_del_diagnostico_tambien(self):
        pagina = self._pagina(self.amd)
        for disco in self.amd.disks:
            rejilla = pagina._grids[disco.name]
            for clave in DEL_DIAGNOSTICO[1:]:
                with self.subTest(disco=disco.name, campo=clave):
                    # La vida restante es de los SSD: en un disco de platos
                    # la fila no está (tests/test_estructura_de_almacenamiento.py).
                    if clave == "storage.field.life" and disco.rotational:
                        self.assertFalse(rejilla.is_locked(_(clave)))
                    else:
                        self.assertTrue(rejilla.is_locked(_(clave)))

    def test_la_tarjeta_vuelve_a_su_texto_si_el_diagnostico_se_pierde(self):
        """Con permisos de una sesión, al irse el ayudante la tarjeta seguía
        diciendo «leídos 2 de 5» con todos los discos otra vez sin leer."""
        pagina = self._pagina(self.amd)
        de_antes = pagina.elevation_text.text()
        a_medias = dataclasses.replace(self.amd, disks=tuple(
            dataclasses.replace(d, health=DiskHealth(power_on_hours=1200)) if i < 2 else d
            for i, d in enumerate(self.amd.disks)))
        pagina.apply(a_medias)
        self.assertNotEqual(pagina.elevation_text.text(), de_antes)
        pagina.apply(self.amd)
        self.assertEqual(pagina.elevation_text.text(), de_antes)

    def test_el_candado_pide_los_permisos(self):
        pagina = self._pagina(self.amd)
        pedidos = []
        pagina.elevation_requested.connect(lambda: pedidos.append(1))
        pagina._grids["sda"]._candados[_("gpu.sensor.temp")].clicked.emit()
        self.assertEqual(pedidos, [1])

    def test_en_la_tabla_el_guion_dice_por_que(self):
        pagina = self._pagina(self.amd)
        discos = [fila[0].text() for fila in pagina.disks._cells]
        celda = pagina.disks._cells[discos.index("sda")][5]
        self.assertIn("drivetemp", celda.toolTip())
        nvme = pagina.disks._cells[discos.index("nvme0n1")][5]
        self.assertNotIn("drivetemp", nvme.toolTip())

    def test_con_el_diagnostico_leido_el_candado_se_va(self):
        # Lo que deja el proveedor al leer el SMART: la salud de cada disco,
        # la temperatura que vino con ella y ninguna nota de permisos.
        leida = dataclasses.replace(
            self.amd,
            disks=tuple(dataclasses.replace(
                d, temp_c=d.temp_c if d.temp_c is not None else 31.0,
                health=DiskHealth(power_on_hours=1200)) for d in self.amd.disks),
            notes=tuple(n for n in self.amd.notes if n.path != "disks.health"))
        pagina = self._pagina(self.amd)
        pagina.apply(leida)
        rejilla = pagina._grids["sda"]
        self.assertFalse(rejilla.is_locked(_("gpu.sensor.temp")))
        self.assertEqual(rejilla._values[_("gpu.sensor.temp")].text(), "31.0 °C")
        self.assertFalse(rejilla.is_locked(_("storage.field.hours")))
        # Lo que ese disco no cuenta ni con permisos vuelve a ser un guion.
        self.assertFalse(rejilla.is_locked(_("storage.field.life")))

    def test_con_permisos_y_sin_temperatura_el_guion_dice_por_que(self):
        # Un SATA cuyo diagnóstico no trae temperatura: ya no hay nada que
        # abrir, y el guion explica el otro camino.
        leida = dataclasses.replace(
            self.amd,
            disks=tuple(dataclasses.replace(d, health=DiskHealth(power_on_hours=1200))
                        for d in self.amd.disks),
            notes=tuple(n for n in self.amd.notes if n.path != "disks.health"))
        pagina = self._pagina(leida)
        rejilla = pagina._grids["sda"]
        self.assertFalse(rejilla.is_locked(_("gpu.sensor.temp")))
        self.assertIn("drivetemp", rejilla._values[_("gpu.sensor.temp")].toolTip())

    def test_el_sata_del_intel_que_si_la_publica_no_cambia(self):
        pagina = self._pagina(self.intel)
        disco = self.intel.disks[0]
        self.assertIsNotNone(disco.temp_c)
        self.assertFalse(pagina._grids[disco.name].is_locked(_("gpu.sensor.temp")))


if __name__ == "__main__":
    unittest.main()
