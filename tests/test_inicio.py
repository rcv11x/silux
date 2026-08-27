"""La portada: qué equipo es esto, en una pantalla.

El programa abría en la ficha del procesador, que responde a una pregunta que
nadie ha hecho todavía. Esta página contesta la primera: de qué equipo se
trata y si algo está caliente ahora mismo.
"""

import unittest

from PySide6.QtWidgets import QApplication

from silux import render
from silux.collector import Collector
from silux.settings import Preferences
from silux.ui import theme
from silux.ui.pages.home import HomePage


def _app():
    return QApplication.instance() or QApplication([])


class TestNombreCortoDeCpu(unittest.TestCase):
    """La cadena de marca trae coletillas que no distinguen un modelo de otro."""

    def test_quita_lo_que_no_dice_nada(self):
        for crudo, esperado in [
            ("AMD Ryzen 7 5800X3D 8-Core Processor", "AMD Ryzen 7 5800X3D"),
            ("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz", "Intel Core i5-10400"),
            ("Intel(R) Xeon(R) CPU E5-2650 v2 @ 2.60GHz", "Intel Xeon E5-2650 v2"),
            ("AMD Ryzen 7 7445HS w/ Radeon 740M Graphics", "AMD Ryzen 7 7445HS"),
        ]:
            self.assertEqual(render.cpu_short_name(crudo), esperado)

    def test_lo_que_ya_es_corto_no_se_toca(self):
        self.assertEqual(render.cpu_short_name("ARM Cortex-A76 r0p0"),
                         "ARM Cortex-A76 r0p0")

    def test_sin_marca_devuelve_el_guion(self):
        self.assertEqual(render.cpu_short_name(None), render.DASH)
        self.assertEqual(render.cpu_short_name(""), render.DASH)

    def test_nunca_deja_el_nombre_vacio(self):
        """Si al limpiar no queda nada, mejor la cadena original."""
        self.assertEqual(render.cpu_short_name("Processor"), "Processor")


class TestPagina(unittest.TestCase):
    def setUp(self):
        theme.set_density("normal", "normal")
        self.pagina = HomePage(theme.palette_for(_app(), "dark"),
                               Preferences(font_scale="normal").normalized())

    def test_pinta_este_equipo_sin_reventar(self):
        self.pagina.apply(Collector().sample())
        self.assertTrue(self.pagina.title.text())

    def test_las_cuatro_tarjetas_dicen_algo(self):
        self.pagina.apply(Collector().snapshot())
        for tarjeta in (self.pagina.cpu, self.pagina.gpu,
                        self.pagina.memoria, self.pagina.discos):
            self.assertTrue(tarjeta.nombre.text(),
                            f"{tarjeta._seccion} se ha quedado en blanco")

    def test_pulsar_una_tarjeta_pide_su_seccion(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        pedidas = []
        self.pagina.seccion_pedida.connect(pedidas.append)
        evento = QMouseEvent(QMouseEvent.Type.MouseButtonRelease,
                             QPoint(5, 5), Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.pagina.gpu.mouseReleaseEvent(evento)
        self.assertEqual(pedidas, ["Gráficos"])

    def test_un_equipo_sin_grafica_no_deja_la_tarjeta_muda(self):
        import dataclasses
        muestra = dataclasses.replace(Collector().snapshot(), gpus=())
        self.pagina.apply(muestra)
        self.assertIn("Sin gráfica", self.pagina.gpu.nombre.text())

    def test_ni_uno_sin_discos(self):
        import dataclasses
        muestra = dataclasses.replace(Collector().snapshot(), disks=())
        self.pagina.apply(muestra)
        self.assertIn("Sin unidades", self.pagina.discos.nombre.text())

    def test_repintar_muchas_veces_no_crea_widgets(self):
        """La regla de siempre: se reescribe el texto, no se rehace la tarjeta."""
        muestra = Collector().snapshot()
        self.pagina.apply(muestra)
        antes = len(self.pagina.findChildren(object))
        for _ in range(20):
            self.pagina.apply(muestra)
        self.assertEqual(len(self.pagina.findChildren(object)), antes)

    def tearDown(self):
        theme.set_density("normal", "normal")


if __name__ == "__main__":
    unittest.main()
