"""La temperatura de una gráfica que no la publica: escondida y nombrada.

Una Intel no da su temperatura por ningún camino. En la ficha de Gráficos
era una ficha grande con un guion para siempre, en Inicio un hueco, y en
Sensores nada que dijera si faltaba o no se había encontrado. La regla 5 es
la misma en los tres sitios: lo que no existe en este hardware se esconde y
se nombra al pie.

Con los volcados de los dos equipos: la UHD 630 del i5-10400, que no la
publica, y la Radeon del 5800X3D, que sí.
"""

import os
import tempfile
import unittest
from unittest import mock

from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

INTEL, AMD = "i5-10400", "5800x3d"


class TestLoDiceElProveedor(unittest.TestCase):

    def test_la_intel_no_la_publica_y_la_radeon_si(self):
        intel = foto(EQUIPOS / INTEL)[0].gpus[0]
        self.assertTrue(intel.no_temperature_sensor)
        self.assertIsNone(intel.temp_c)
        radeon = foto(EQUIPOS / AMD)[0].gpus[0]
        self.assertFalse(radeon.no_temperature_sensor)
        self.assertIsNotNone(radeon.temp_c)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLasTresPaginas(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.fotos = {n: foto(EQUIPOS / n)[0] for n in (INTEL, AMD)}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana(self, nombre):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences(window_width=1440, window_height=880).normalized())
        ventana.resize(1440, 880)
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(self.fotos[nombre])
        ventana._on_sample(self.fotos[nombre])
        for _vez in range(4):
            self.app.processEvents()
        return ventana

    def _ficha_de_graficos(self, ventana):
        ventana.select_section("Gráficos")
        for _vez in range(4):
            self.app.processEvents()
        return ventana.graphics_page._sections[0]

    def test_en_graficos_no_hay_ficha_con_guion(self):
        from silux.i18n import _

        ficha = self._ficha_de_graficos(self._ventana(INTEL))
        self.assertFalse(ficha.tile_temp.isVisible())
        self.assertFalse(ficha.sensors._values[_("gpu.sensor.hotspot")].isVisible())
        # En esta integrada «Consumo y temperaturas» no tiene nada propio y
        # se va: su explicación queda debajo de la fila de tarjetas.
        self.assertTrue(ficha.sensors_outside.isVisible())
        self.assertIn(_("gpu.na.notemp"), ficha.sensors_outside.text())
        # Las otras fichas de una integrada siguen: uso, reloj y consumo.
        self.assertTrue(ficha.tile_clock.isVisible())

    def test_en_graficos_la_radeon_la_ensena(self):
        from silux.i18n import _

        ficha = self._ficha_de_graficos(self._ventana(AMD))
        self.assertTrue(ficha.tile_temp.isVisible())
        self.assertNotIn(_("gpu.na.notemp"), ficha.sensors_pie.text())

    def test_en_inicio_se_nombra_al_pie_de_las_temperaturas(self):
        from silux.i18n import _

        tarjeta = self._ventana(INTEL).home_page.temperaturas
        self.assertTrue(tarjeta.pie.isVisible())
        self.assertEqual(tarjeta.pie.text(), _("gpu.na.notemp"))
        self.assertNotIn(_("home.temp.gpu"), f"{tarjeta.nombre.text()} {tarjeta.cifras.text()}")
        self.assertNotIn("—", f"{tarjeta.nombre.text()} {tarjeta.cifras.text()}")

    def test_en_inicio_la_radeon_sale_con_su_cifra_y_sin_pie(self):
        from silux.i18n import _

        tarjeta = self._ventana(AMD).home_page.temperaturas
        self.assertFalse(tarjeta.pie.isVisible())
        self.assertIn(_("home.temp.gpu"), f"{tarjeta.nombre.text()} {tarjeta.cifras.text()}")

    def test_en_sensores_se_dice_que_no_hay_rama(self):
        ventana = self._ventana(INTEL)
        ventana.select_section("Sensores")
        for _vez in range(4):
            self.app.processEvents()
        pie = ventana.monitor_page.absent
        self.assertTrue(pie.isVisible())
        self.assertIn(self.fotos[INTEL].gpus[0].display_name, pie.text())

    def test_en_sensores_la_radeon_no_deja_nada_al_pie(self):
        ventana = self._ventana(AMD)
        ventana.select_section("Sensores")
        # Al pie puede haber otra cosa —las tensiones que el driver no
        # nombra—, pero no la gráfica.
        self.assertNotIn(self.fotos[AMD].gpus[0].display_name,
                         ventana.monitor_page.absent.text())


if __name__ == "__main__":
    unittest.main()
