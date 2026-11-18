"""Las páginas que no se ven no se repintan; lo que guarda historia, sí.

Aplicar cada foto entera a las catorce páginas reescribía tablas y árboles
que nadie miraba: con la ventana escondida era la tercera parte de lo que
gastaba silux. Ahora la foto entera va a la página que se ve; las que
guardan historia (las gráficas, los mínimos y máximos de Sensores, su
grabación) reciben lo suyo en cada muestreo, y las demás se ponen al día al
abrirlas o al volver a verse la ventana. La regla 9 sigue: lo que se abre
enseña la última foto.

Con el volcado del 5800X3D, para que haya de todo.
"""

import dataclasses
import unittest

from tests import qt
from tests.test_equipos import EQUIPOS, foto


class TestLasPaginasEscondidas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "5800x3d")[0]

    def ventana(self, pagina="Inicio"):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        ventana = MainWindow(Preferences().normalized())
        self.addCleanup(ventana.deleteLater)
        ventana.resize(1440, 900)
        ventana.show()
        ventana.select_section(pagina)
        for _vez in range(3):
            self.app.processEvents()
        return ventana

    def otra_foto(self, n):
        return dataclasses.replace(self.foto, monotonic_ns=self.foto.monotonic_ns + n * 10**9)

    def test_la_que_no_se_ve_no_se_repinta_y_al_abrirla_esta_al_dia(self):
        ventana = self.ventana("Inicio")
        llamadas = []
        original = ventana.board_page.apply
        ventana.board_page.apply = lambda f: (llamadas.append(f), original(f))
        for n in range(3):
            ventana._on_sample(self.otra_foto(n))
        self.assertEqual(llamadas, [], "escondida no se repinta")
        ventana.select_section("Placa base")
        self.assertEqual(len(llamadas), 1)
        self.assertIs(llamadas[0], ventana._last_snapshot, "con la última foto")

    def test_sensores_escondida_sigue_contando_y_no_cuenta_dos_veces(self):
        ventana = self.ventana("Inicio")
        clave = next(s.key for s in self.foto.sensors if s.value is not None)
        for n in range(4):
            ventana._on_sample(self.otra_foto(n))
        self.assertEqual(len(ventana._tracker.get(clave).history), 4,
                         "los mínimos, máximos e historial no se pierden")
        ventana.select_section("Sensores")
        self.assertEqual(len(ventana._tracker.get(clave).history), 4,
                         "abrirla no cuenta otra vez la última foto")
        self.assertIn(clave, ventana.monitor_page.tree._rows)

    def test_las_fichas_de_almacenamiento_tampoco(self):
        ventana = self.ventana("Inicio")
        for n in range(4):
            ventana._on_sample(self.otra_foto(n))
        grafica = ventana.storage_page.tile_read.chart
        self.assertEqual(len(grafica._values), 4)
        ventana.select_section("Almacenamiento")
        self.assertEqual(len(grafica._values), 4)
        self.assertTrue(ventana.storage_page.total_bar._segments, "y lo demás, pintado")

    def test_una_ventana_que_deja_de_verse_no_repinta_su_pagina(self):
        """Minimizada o en otro escritorio el compositor deja de enseñarla.
        Sin pantalla, eso se ve escondiéndola."""
        ventana = self.ventana("Memoria")
        ventana._se_ha_visto = True              # lo apunta el primer `Expose`
        ventana._on_sample(self.otra_foto(0))
        llamadas = []
        original = ventana.memory_page.apply
        ventana.memory_page.apply = lambda f: (llamadas.append(f), original(f))
        ventana.hide()
        self.app.processEvents()
        ventana._on_sample(self.otra_foto(1))
        self.assertEqual(llamadas, [])
        ventana.show()
        for _vez in range(3):
            self.app.processEvents()
        self.assertEqual(len(llamadas), 1, "al volver a verse, al día")
        self.assertIs(llamadas[0], ventana._last_snapshot)


class TestLaVentanaQueSeVa(unittest.TestCase):
    """Al recibir un `Expose`, la ventana se pone al día un instante después.
    Con `QTimer.singleShot(0, metodo)`, eso saltaba aunque la ventana ya se
    hubiera borrado: «Internal C++ object (MainWindow) already deleted», y
    en el CI, con PySide6 6.11, un `Segmentation fault` en otro test."""

    def test_un_expose_justo_antes_de_borrarla_no_salta_despues(self):
        import sys
        from unittest import mock

        import shiboken6
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtGui import QExposeEvent, QRegion

        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        app = qt.app()
        errores = []
        with mock.patch.object(sys, "excepthook", lambda *e: errores.append(e[1])):
            for _vez in range(5):
                ventana = MainWindow(Preferences().normalized())
                ventana.show()
                app.processEvents()
                QCoreApplication.sendEvent(ventana.windowHandle(), QExposeEvent(QRegion()))
                shiboken6.delete(ventana)
                app.processEvents()
        self.assertEqual(errores, [])


if __name__ == "__main__":
    unittest.main()
