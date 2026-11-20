"""La interfaz del actualizador, sin salir a la red.

Las funciones de buscar e instalar se sustituyen por falsas: lo que se
comprueba es lo que hace la ventana con lo que contestan.
"""

import dataclasses
import os
import unittest
from unittest import mock

from silux import __version__, updates
from silux.i18n import _
from tests import qt

NUEVA = updates.Release(version=(99, 0, 0), tag="v99.0.0",
                        url="https://github.com/rcv11x/silux/releases/tag/v99.0.0",
                        assets={updates.NORMAL: "https://example.invalid/a"})


class TestLaVentana(unittest.TestCase):
    def ventana(self, **prefs):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        qt.app()
        v = MainWindow(dataclasses.replace(Preferences(), **prefs).normalized())
        self.addCleanup(v.deleteLater)
        return v

    def esperar(self, v):
        v._tarea_de_red.wait(5000)
        qt.app().processEvents()

    def test_apagado_de_serie_y_sin_buscar_al_abrir(self):
        from silux.settings import Preferences
        self.assertFalse(Preferences().check_updates)
        v = self.ventana()
        self.assertTrue(v.settings_page.check_updates.isChecked() is False)
        self.assertIsNone(v._tarea_de_red)
        self.assertTrue(v.update_button.isHidden())

    def test_buscar_ahora_con_version_nueva_pone_el_aviso(self):
        v = self.ventana()
        v._buscar_version = lambda channel="stable": NUEVA
        v.settings_page.update_now.click()
        self.esperar(v)
        self.assertFalse(v.update_button.isHidden())
        # As the window writes every version: «99.0», «0.4-prueba3».
        self.assertIn("99.0", v.update_button.text())
        self.assertIn("99.0", v.settings_page.update_status.text())

    def test_sin_version_nueva_lo_dice_y_no_hay_aviso(self):
        v = self.ventana()
        # Una más antigua que cualquiera: la que corre puede ser de prueba
        # (0.4.0rc1), y una de prueba no es una release que se ofrezca.
        antigua = updates.Release(version=(0, 0, 0), tag="v0.0.0", url="u")
        v._buscar_version = lambda channel="stable": antigua
        v.buscar_actualizacion()
        self.esperar(v)
        self.assertTrue(v.update_button.isHidden())
        # Ahead of the latest published (a test version is): nothing newer,
        # and not «you have the latest», which would be another one.
        self.assertEqual(v.settings_page.update_status.text(), _("updates.none"))

    def test_the_latest_one_is_named_as_the_app_names_it(self):
        from silux import render
        v = self.ventana()
        v._buscar_version = lambda channel="stable": updates.Release(version=(0, 0, 0), tag="v0.0.0", url="u")
        with mock.patch.object(updates, "is_current", return_value=True):
            v.buscar_actualizacion()
            self.esperar(v)
        self.assertEqual(v.settings_page.update_status.text(),
                         _("updates.latest").format(version=render.version(__version__)))
        self.assertNotIn("rc", v.settings_page.update_status.text())

    def test_a_test_version_looks_in_the_test_channel(self):
        # Whoever runs the prueba2 gets the prueba3 with «Buscar ahora».
        from unittest import mock
        v = self.ventana()
        pedido = []
        prueba3 = updates.Release(version=(99, 0, 0), tag="99.0.0rc3", url="u", prerelease=3)
        v._buscar_version = lambda channel="stable": pedido.append(channel) or prueba3
        with mock.patch.object(updates, "__version__", "0.4.0rc2"), \
                mock.patch.object(updates, "channel_for",
                                  lambda pref, current="0.4.0rc2": updates.CHANNELS[1]
                                  if pref in ("", "testing") else "stable"):
            v.buscar_actualizacion()
            self.esperar(v)
        self.assertEqual(pedido, ["testing"])
        self.assertIn("99.0-prueba3", v.settings_page.update_status.text())

    def test_un_error_de_red_se_dice(self):
        v = self.ventana()
        def falla(channel="stable"):
            raise updates.UpdateError("network", "sin red")
        v._buscar_version = falla
        v.buscar_actualizacion()
        self.esperar(v)
        self.assertIn(_("updates.err.network"), v.settings_page.update_status.text())

    def test_desde_el_codigo_solo_avisa_y_no_baja_nada(self):
        v = self.ventana()
        v._version_nueva = NUEVA
        v._instalar_version = mock.Mock(side_effect=AssertionError("no debía bajar nada"))
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(updates, "replaceable_path", return_value=None), \
                mock.patch("PySide6.QtWidgets.QMessageBox.information") as aviso:
            os.environ.pop("APPIMAGE", None)
            v._actualizar()
        v._instalar_version.assert_not_called()
        self.assertIn(NUEVA.url, aviso.call_args[0][2])

    def test_desde_el_appimage_baja_y_ofrece_reiniciar(self):
        v = self.ventana()
        v._version_nueva = NUEVA
        destino = "/tmp/silux-x86_64.AppImage"
        v._instalar_version = mock.Mock(return_value=destino)
        with mock.patch.object(updates, "replaceable_path", return_value=destino), \
                mock.patch("PySide6.QtWidgets.QMessageBox.question",
                           return_value=__import__("PySide6.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.No) as pregunta:
            v._actualizar()
            self.esperar(v)
        v._instalar_version.assert_called_once_with(NUEVA, destino)
        pregunta.assert_called_once()
        self.assertTrue(v.update_button.isHidden())


if __name__ == "__main__":
    unittest.main()
