"""«Qué hace esto»: lo que se le cuenta a alguien antes de pedirle la contraseña."""

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


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElDialogo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _dialogo(self, **kwargs):
        from silux.ui.dialogs import PermissionsDialog

        dialogo = PermissionsDialog(**kwargs)
        self.addCleanup(dialogo.close)
        return dialogo

    def test_cuenta_las_cuatro_cosas(self):
        textos = [p.text() for p in self._dialogo().paragraphs]
        self.assertEqual(len(textos), 4)
        self.assertIn("Solo lee", textos[0])
        self.assertIn("mientras silux está abierto", textos[1])
        self.assertIn("/usr/local/libexec/silux", textos[2])
        self.assertIn("polkit", textos[3])
        self.assertIn("no la ve", textos[3])

    def test_la_orden_de_quitarlo_sirve_tambien_desde_el_appimage(self):
        # Decía «sudo python3 -m silux.privileged.instalar --uninstall», que
        # solo existe donde silux está instalado como paquete. Quien lo usa
        # desde el AppImage no tiene ese módulo, y es quien instaló el
        # ayudante desde la ventana. Borrar los dos archivos vale siempre.
        from silux.privileged import instalar

        de_siempre = self._dialogo().paragraphs[2].text()
        self.assertNotIn("Ajustes", de_siempre)
        self.assertNotIn("python3 -m", de_siempre)
        self.assertNotIn("{orden}", de_siempre)
        self.assertIn(f"sudo rm {instalar.DESTINO} {instalar.POLITICA}", de_siempre)

    def test_la_orden_borra_justo_lo_que_borra_el_desinstalador(self):
        import inspect

        from silux.privileged import instalar

        orden = instalar.orden_de_desinstalar().split()
        self.assertEqual(orden[:2], ["sudo", "rm"])
        self.assertEqual(set(orden[2:]), {str(instalar.DESTINO), str(instalar.POLITICA)})
        # Y el desinstalador no borra ningún archivo más que esos dos.
        fuente = inspect.getsource(instalar.desinstalar)
        self.assertIn("for ruta in (POLITICA, DESTINO)", fuente)

    def test_los_otros_parrafos_no_llevan_la_orden(self):
        textos = [p.text() for p in self._dialogo().paragraphs]
        self.assertEqual(sum("sudo rm" in t for t in textos), 1)

    def test_no_manda_a_tocar_cerrojos_del_sistema(self):
        todo = " ".join(p.text() for p in self._dialogo().paragraphs)
        self.assertNotIn("perf_event_paranoid", todo)

    def test_cada_boton_pide_lo_suyo_y_cierra(self):
        for boton, senal in (("grant_button", "grant_requested"),
                             ("permanent_button", "permanent_requested")):
            with self.subTest(boton=boton):
                dialogo = self._dialogo()
                dialogo.show()
                pedidos = []
                getattr(dialogo, senal).connect(lambda: pedidos.append(senal))
                getattr(dialogo, boton).click()
                self.assertEqual(pedidos, [senal])
                self.assertFalse(dialogo.isVisible())

    def test_cerrar_no_pide_nada(self):
        dialogo = self._dialogo()
        dialogo.show()
        pedidos = []
        dialogo.grant_requested.connect(lambda: pedidos.append("dar"))
        dialogo.permanent_requested.connect(lambda: pedidos.append("siempre"))
        dialogo.close_button.click()
        self.assertEqual(pedidos, [])
        self.assertFalse(dialogo.isVisible())

    def test_con_el_ayudante_ya_instalado_no_ofrece_instalarlo(self):
        dialogo = self._dialogo(permanente=False)
        dialogo.show()
        self.assertFalse(dialogo.permanent_button.isVisible())
        self.assertTrue(dialogo.grant_button.isVisible())


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestDesdeElAviso(unittest.TestCase):

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
        return ventana

    def test_el_aviso_lo_abre(self):
        ventana = self._ventana()
        ventana.home_page.permission_notice.explain_button.click()
        self.assertTrue(ventana._dialogo_permisos.isVisible())
        self.addCleanup(ventana._dialogo_permisos.close)

    def test_dar_permisos_desde_el_dialogo_los_pide(self):
        ventana = self._ventana()
        ventana.home_page.permission_notice.explain_button.click()
        with mock.patch.object(ventana.sampler, "request_elevation") as pedir:
            ventana._dialogo_permisos.grant_button.click()
        pedir.assert_called_once()

    def test_para_siempre_lanza_la_instalacion(self):
        ventana = self._ventana()
        ventana.home_page.permission_notice.explain_button.click()
        with mock.patch.object(type(ventana), "_on_permanent_requested") as instalar:
            # La señal se conectó al método de antes del parche: se reconecta.
            dialogo = ventana._dialogo_permisos
            dialogo.permanent_requested.disconnect()
            dialogo.permanent_requested.connect(ventana._on_permanent_requested)
            dialogo.permanent_button.click()
        instalar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
