"""La tabla de monitores no corta la resolución.

En el 5800X3D, con dos monitores, la tabla de salidas de Gráficos a 900 px
decía «2560 × 14…» y «semana 16 de 20…», con sitio de sobra para desplazarse.
Eran dos cosas:

- La tabla medía cada texto en píxeles enteros, redondeando hacia abajo, y
  quien decide si cabe usa el ancho de verdad: «2560 × 1440» medía 79 y
  ocupaba 79 y pico. La columna salía a 79 y la celda lo cortaba.
- El nombre del monitor llevaba la razón social entera del fabricante,
  «GIGA-BYTE TECHNOLOGY CO., LTD. AORUS FO27Q2», y se comía el ancho.

Con el volcado del 5800X3D, que tiene los dos monitores.
"""

import os
import tempfile
import unittest
from unittest import mock

from silux import render
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


class TestElNombreDelMonitor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monitores = [s.monitor for s in foto(EQUIPOS / "5800x3d")[0].gpus[0].displays
                         if s.monitor]

    def test_el_volcado_tiene_los_dos(self):
        self.assertEqual({m.model for m in self.monitores}, {"AORUS FO27Q2", "27GL850"})
        self.assertIn("GIGA-BYTE TECHNOLOGY CO., LTD.", {m.manufacturer for m in self.monitores})

    def test_sale_como_en_la_pegatina_y_no_con_la_razon_social(self):
        nombres = {render.monitor_name(m) for m in self.monitores}
        self.assertEqual(nombres, {"Gigabyte AORUS FO27Q2", "LG 27GL850"})

    def test_un_fabricante_que_no_se_conoce_se_deja_como_viene(self):
        import dataclasses

        raro = dataclasses.replace(self.monitores[0], manufacturer="Acme Displays", model="X1")
        self.assertEqual(render.monitor_name(raro), "Acme Displays X1")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaTabla(unittest.TestCase):

    def test_a_900_px_ninguna_cifra_sale_cortada(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.app import MainWindow

        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        prefs = Preferences(density="compact", window_width=900, window_height=680).normalized()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            theme.apply(app, "dark", "compact", prefs.font_scale, prefs.accent)
            self.addCleanup(theme.set_density, "normal", "normal")
            ventana = MainWindow(prefs)
            self.addCleanup(ventana.close)
            ventana.resize(900, 680)
            ventana.show()
            # Dos muestras y a mirar, como al abrir el programa: la tabla no
            # puede necesitar un tercer muestreo para medirse bien.
            ventana._on_sample(f)
            ventana._on_sample(f)
            ventana.select_section("Gráficos")
            for _vez in range(6):
                app.processEvents()
            tabla = ventana.graphics_page._sections[0].displays
            self.assertEqual(len(tabla._cells), 2)
            cortadas = [celda.full_text() for fila in tabla._cells for celda in fila[2:]
                        if celda.text() != celda.full_text()]
            self.assertEqual(cortadas, [])


if __name__ == "__main__":
    unittest.main()
