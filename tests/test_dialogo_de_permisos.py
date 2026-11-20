"""«Qué hace esto»: lo que se le cuenta a alguien antes de pedirle la contraseña."""

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
class TestElDialogo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _dialogo(self, **kwargs):
        from silux.ui.dialogs import PermissionsDialog

        dialogo = PermissionsDialog(**kwargs)
        self.addCleanup(dialogo.close)
        return dialogo

    def test_cuenta_las_cuatro_cosas_en_poco(self):
        """Se lee justo antes de teclear una contraseña: cuatro párrafos
        cortos, qué lee, esta vez, para siempre y quién pide la contraseña."""
        textos = [p.text() for p in self._dialogo(permanente=False).paragraphs]
        self.assertEqual(len(textos), 4)
        self.assertIn("Solo lee", textos[0])
        self.assertIn("uso de la gráfica", textos[0])
        self.assertIn("mientras Silux esté abierto", textos[1])
        # What installing gives, and that the password is still asked.
        self.assertIn("ventana de la contraseña", textos[2])
        self.assertIn("se sigue pidiendo", textos[2])
        self.assertIn("no la ve", textos[3])
        self.assertLess(sum(len(t) for t in textos), 480)

    def test_sin_la_regla_dice_en_pequeno_lo_que_dira_la_ventana(self):
        """Sin la regla de polkit, la ventana de la contraseña enseña
        `python3 -c import linecache…`, y no se puede cambiar. Se dice en una
        línea pequeña bajo los botones y en el globo de «esta vez», y «Para
        siempre» es el botón principal."""
        dialogo = self._dialogo(permanente=True)
        dialogo.show()
        self.addCleanup(dialogo.close)
        self.assertEqual(len(dialogo.paragraphs), 4)
        self.assertTrue(dialogo.window_note.isVisible())
        self.assertIn("python3", dialogo.window_note.text())
        self.assertIn("python3", dialogo.grant_button.toolTip())
        self.assertTrue(dialogo.permanent_button.isDefault())
        self.assertFalse(dialogo.grant_button.isDefault())

    def test_con_la_regla_puesta_no_lo_cuenta(self):
        dialogo = self._dialogo(permanente=False)
        self.assertNotIn("python3", " ".join(p.text() for p in dialogo.paragraphs))
        self.assertTrue(dialogo.window_note.isHidden())
        self.assertTrue(dialogo.grant_button.isDefault())

    def test_la_orden_de_quitarlo_ya_no_esta_aqui(self):
        # Va en Ajustes, en un botón: copiar una orden `sudo rm` justo antes
        # de dar una contraseña era mucho que leer (test_ajustes).
        dialogo = self._dialogo()
        self.assertFalse(hasattr(dialogo, "command"))
        self.assertFalse([p for p in dialogo.paragraphs if "sudo" in p.text()])

    def test_cabe_en_la_ventana_compacta(self):
        dialogo = self._dialogo()
        dialogo.show()
        self.addCleanup(dialogo.close)
        self.app.processEvents()
        self.assertLessEqual(dialogo.width(), 760)

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

    def test_en_su_tamano_minimo_no_corta_ni_el_texto_ni_los_botones(self):
        """En Wayland el diálogo abre con su tamaño mínimo, y el mínimo que
        calcula Qt cuenta cada párrafo como una sola línea: 573x299 donde
        hacían falta 425 de alto. Sin pantalla abre con el tamaño bueno, así
        que aquí se le pone el mínimo a mano, que es lo que hace el
        compositor."""
        from silux.ui import theme
        from silux.settings import Preferences

        normales = Preferences().normalized()
        self.addCleanup(theme.apply, self.app, normales.theme, normales.density,
                        normales.font_scale)
        for letra in ("normal", "grande", "máximo"):
            for permanente in (True, False):
                with self.subTest(letra=letra, permanente=permanente):
                    theme.apply(self.app, normales.theme, normales.density, letra)
                    dialogo = self._dialogo(permanente=permanente)
                    dialogo.show()
                    dialogo.resize(dialogo.minimumSize())
                    for _vez in range(4):
                        self.app.processEvents()
                    cortados = [p.text()[:40] for p in dialogo.paragraphs
                                if p.height() < p.heightForWidth(p.width())]
                    self.assertEqual(cortados, [])
                    for boton in (dialogo.grant_button, dialogo.close_button):
                        self.assertLessEqual(boton.geometry().bottom(), dialogo.height())
                        self.assertLessEqual(boton.geometry().right(), dialogo.width())
                    dialogo.close()

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

    def test_sin_la_regla_dar_permisos_abre_antes_el_aviso(self):
        from silux.privileged.client import PrivilegedClient
        for instalado, al_dia in ((False, False), (True, False)):
            with self.subTest(instalado=instalado, al_dia=al_dia):
                ventana = self._ventana()
                with mock.patch.object(PrivilegedClient, "instalado", return_value=instalado), \
                     mock.patch.object(PrivilegedClient, "al_dia", return_value=al_dia), \
                     mock.patch.object(ventana.sampler, "request_elevation") as pedir:
                    ventana.home_page.permission_notice.grant_button.click()
                    pedir.assert_not_called()
                    dialogo = ventana._dialogo_permisos
                    self.assertTrue(dialogo.isVisible())
                    dialogo.grant_button.click()
                pedir.assert_called_once()

    def test_con_la_regla_al_dia_los_pide_sin_mas(self):
        from silux.privileged.client import PrivilegedClient
        ventana = self._ventana()
        with mock.patch.object(PrivilegedClient, "instalado", return_value=True), \
             mock.patch.object(PrivilegedClient, "al_dia", return_value=True), \
             mock.patch.object(ventana.sampler, "request_elevation") as pedir:
            ventana.home_page.permission_notice.grant_button.click()
        pedir.assert_called_once()
        self.assertIsNone(getattr(ventana, "_dialogo_permisos", None))

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


class TestConLosPermisosYaConcedidos(unittest.TestCase):
    """Con el ayudante ya conectado, «Dar permisos esta vez» no hace nada."""

    def setUp(self):
        qt.app()

    def test_no_se_ofrece(self):
        from silux.ui.dialogs import PermissionsDialog
        dialogo = PermissionsDialog(permanente=True, concedidos=True)
        self.addCleanup(dialogo.deleteLater)
        self.assertTrue(dialogo.grant_button.isHidden())
        self.assertFalse(dialogo.granted_label.isHidden())
        self.assertFalse(dialogo.permanent_button.isHidden())

    def test_la_ventana_lo_sabe_por_la_foto(self):
        import dataclasses
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        from tests import muestras
        ventana = MainWindow(Preferences().normalized())
        self.addCleanup(ventana.deleteLater)
        foto = muestras.foto_real()
        ventana._last_snapshot = dataclasses.replace(
            foto, privileged=dataclasses.replace(foto.privileged, connected=True))
        ventana._explicar_permisos()
        self.addCleanup(ventana._dialogo_permisos.deleteLater)
        self.assertTrue(ventana._dialogo_permisos.grant_button.isHidden())
