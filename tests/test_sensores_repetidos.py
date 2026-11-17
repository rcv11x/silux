"""Lo que dos drivers leen del mismo chip se enseña una vez.

En el 5800X3D (Gigabyte X570) la placa salía con doce temperaturas y eran
seis: las del Super I/O (IT8688, por `it87`) y las mismas otra vez por
`gigabyte_wmi`, que no lee un chip suyo sino ese, a través del firmware.
"""

import dataclasses
import unittest

from silux import render
from silux.i18n import _
from silux.model import SensorKind
from silux.providers.hwmon import HwmonSensors
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _temperaturas(sensores, chip_empieza):
    return [s for s in sensores if s.chip.startswith(chip_empieza)
            and s.kind is SensorKind.TEMPERATURE]


class TestElProveedor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def test_el_volcado_trae_el_caso(self):
        wmi = _temperaturas(self.foto.sensors, "gigabyte_wmi")
        chip = _temperaturas(self.foto.sensors, "it8688")
        self.assertEqual((len(wmi), len(chip)), (6, 6))

    def test_las_del_wmi_quedan_marcadas_y_las_del_chip_no(self):
        wmi = _temperaturas(self.foto.sensors, "gigabyte_wmi")
        chip = _temperaturas(self.foto.sensors, "it8688")
        self.assertEqual({s.mirror_of for s in wmi}, {chip[0].chip})
        self.assertEqual({s.mirror_of for s in chip}, {None})
        # Y nada más en todo el equipo.
        self.assertEqual(sum(1 for s in self.foto.sensors if s.mirror_of), 6)

    def test_siguen_en_la_foto_pero_no_en_el_arbol(self):
        placa = self.foto.sensor_tree()[self.foto.board.display_name]["cat.temperature"]
        self.assertEqual([s.chip for s in placa if s.chip.startswith("gigabyte")], [])
        self.assertEqual(len([s for s in placa if s.chip.startswith("it8688")]), 6)
        self.assertEqual(len(_temperaturas(self.foto.sensors, "gigabyte_wmi")), 6)

    def _sin_marcar(self):
        return [dataclasses.replace(s, mirror_of=None) for s in self.foto.sensors]

    def test_si_no_marcan_lo_mismo_no_son_repetidas(self):
        """Otra placa podría cablear por WMI sondas que el Super I/O no ve."""
        primeras = sorted(x.order for x in self.foto.sensors if x.chip == "gigabyte_wmi")[:3]
        distintas = [dataclasses.replace(s, value=s.value + 9.0)
                     if s.chip == "gigabyte_wmi" and s.order in primeras
                     else s for s in self._sin_marcar()]
        salida = HwmonSensors()._sin_repetir(distintas)
        self.assertEqual([s for s in salida if s.mirror_of], [])

    def test_una_sonda_que_se_mueve_entre_las_dos_lecturas_no_lo_impide(self):
        """En el propio volcado la del zócalo marca 41 °C por un driver y 47
        por el otro: son la misma, leída con un instante de diferencia."""
        wmi = _temperaturas(self.foto.sensors, "gigabyte_wmi")
        chip = _temperaturas(self.foto.sensors, "it8688")
        lejos = [abs(a.value - b.value) for a, b in zip(wmi, chip)
                 if abs(a.value - b.value) > 2]
        self.assertEqual(len(lejos), 1, lejos)
        self.assertTrue(all(s.mirror_of for s in wmi))

    def test_si_no_son_las_mismas_sondas_tampoco(self):
        una_menos = self._sin_marcar()
        una_menos.remove(_temperaturas(una_menos, "gigabyte_wmi")[-1])
        salida = HwmonSensors()._sin_repetir(una_menos)
        self.assertEqual([s for s in salida if s.mirror_of], [])

    def test_una_vez_confirmado_no_se_desdice_con_un_salto(self):
        """Bajo carga, entre leer un driver y el otro una sonda se mueve más
        que el margen: el árbol no puede ganar y perder seis filas."""
        proveedor = HwmonSensors()
        self.assertEqual(sum(1 for s in proveedor._sin_repetir(self._sin_marcar())
                             if s.mirror_of), 6)
        salto = [dataclasses.replace(s, value=s.value + 5.0)
                 if s.chip == "gigabyte_wmi" else s for s in self._sin_marcar()]
        self.assertEqual(sum(1 for s in proveedor._sin_repetir(salto) if s.mirror_of), 6)

    def test_en_un_equipo_sin_ese_driver_no_se_marca_nada(self):
        intel = foto(EQUIPOS / "i5-10400")[0]
        self.assertEqual([s for s in intel.sensors if s.mirror_of], [])


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaPaginaDeSensores(unittest.TestCase):

    def test_seis_filas_y_un_renglon_que_dice_de_cual(self):
        from silux.settings import Preferences
        from silux.tracking import Tracker
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage

        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        pagina = MonitorPage(theme.palette_for(app, "dark"), Preferences().normalized(), Tracker())
        self.addCleanup(pagina.deleteLater)
        pagina.resize(1200, 900)
        pagina.show()
        pagina.apply(f)
        app.processEvents()

        placa = f.board.display_name
        rama = pagina.tree._rows[f"::{placa}/cat.temperature"]
        nombres = [rama.child(i).text(0) for i in range(rama.childCount())]
        # Seis del chip y las tres de relleno de ACPI: nueve, no quince.
        self.assertEqual(len(nombres), 9, nombres)
        self.assertFalse([n for n in nombres if "gigabyte" in n.lower()])
        for sensor in f.sensors:
            self.assertEqual(sensor.key in pagina.tree._rows, not sensor.mirror_of, sensor.key)

        pie = pagina.absent.text()
        self.assertIn(_("sensors.mirror").format(espejo="gigabyte_wmi", chip="it8688", n=6), pie)
        # El que se esconde no sale además como «numera sin decir dónde».
        sin_nombre = [l for l in pie.split("\n")
                      if l == _("sensors.unnamed.temps").format(chips="it8688")]
        self.assertEqual(len(sin_nombre), 1, pie)
        self.assertIn(str(sum(1 for s in f.sensors if not s.mirror_of)),
                      pagina._cuenta_completa)


if __name__ == "__main__":
    unittest.main()
