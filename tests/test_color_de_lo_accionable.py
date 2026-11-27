"""Lo que falta y tiene arreglo va en azul; el ámbar es la marca.

El ámbar es el acento y el color del logo: es lo seleccionado y lo que se
pulsa. Mientras lo accionable también fue ámbar, la banda de un aviso, un
candado y el botón principal eran del mismo color.
"""

import os
import tempfile
import unittest
from unittest import mock

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElColorDeLoAccionable(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences().normalized())
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(self.foto)
        self.app.processEvents()
        return ventana

    def test_el_acento_es_el_ambar_de_la_marca(self):
        from silux.ui import theme

        self.assertEqual(theme.DARK.accent, theme.ACCENTS["amber"]["dark"][0])
        self.assertEqual(theme.LIGHT.accent, theme.ACCENTS["amber"]["light"][0])

    def test_los_candados_no_son_del_color_del_acento_ni_del_aviso(self):
        from silux.ui.widgets import LockMark

        ventana = self._ventana()
        paleta = ventana._palette
        self.assertNotEqual(paleta.info, paleta.accent)
        for seccion in ("Inicio", "CPU", "Almacenamiento"):
            ventana.select_section(seccion)
            self.app.processEvents()
            candados = [c for c in ventana.stack.currentWidget().findChildren(LockMark)
                        if c.isVisible()]
            with self.subTest(pagina=seccion):
                self.assertTrue(candados)
                for candado in candados:
                    self.assertEqual(candado._color.name().lower(), paleta.info.lower())

    def test_el_aviso_de_inicio_y_el_enlace_de_la_barra_van_en_azul(self):
        from silux.ui import theme

        ventana = self._ventana()
        self.assertEqual(ventana.home_page.permission_notice.property("tone"), "action")
        hoja = theme.stylesheet(ventana._palette)
        self.assertIn(f'QFrame#Notice[tone="action"] {{ border-left-color: {ventana._palette.info}; }}',
                      hoja)
        # The rule that names it, alone or with others that share its look.
        regla = next(cuerpo for selectores, cuerpo in
                     (bloque.split("{", 1) for bloque in hoja.split("}") if "{" in bloque)
                     if any(selector.strip().endswith("QPushButton#StatusAction")
                            for selector in selectores.split(",")))
        self.assertIn(f"color: {ventana._palette.info};", regla)

    def test_el_interruptor_encendido_va_en_el_acento_y_no_en_azul(self):
        # Encendido es algo que el usuario ha elegido, como una casilla
        # marcada o la sección abierta: ámbar. El azul dice que falta algo
        # que tiene arreglo, y un interruptor encendido no le falta nada.
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QWidget

        from silux.ui import theme
        from silux.ui.pages.settings import Interruptor

        for paleta in (theme.DARK, theme.LIGHT):
            interruptor = Interruptor(paleta)
            self.addCleanup(interruptor.deleteLater)
            interruptor.setChecked(True)
            interruptor.resize(interruptor.sizeHint())
            lienzo = QPixmap(interruptor.size())
            lienzo.fill(paleta.q("surface"))
            interruptor.render(lienzo, renderFlags=QWidget.RenderFlag.DrawChildren)
            imagen = lienzo.toImage()
            colores = {imagen.pixelColor(x, y).name().lower()
                       for x in range(imagen.width()) for y in range(imagen.height())}
            with self.subTest(acento=paleta.accent):
                self.assertIn(paleta.accent.lower(), colores)
                self.assertNotIn(paleta.info.lower(), colores)

    def test_un_aviso_de_un_disco_sigue_siendo_un_aviso(self):
        # Eso no es una tarea del usuario: es un estado del equipo.
        from silux.ui.widgets import Notice

        self.assertEqual(Notice("t", "b").property("tone"), "warn")


if __name__ == "__main__":
    unittest.main()
