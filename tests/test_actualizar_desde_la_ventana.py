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

    def start(self, v):
        # The window started as `main` starts it, without reading anything.
        with mock.patch.object(v.sampler, "start"):
            v.start()

    def test_on_by_default_it_checks_a_little_after_opening(self):
        v = self.ventana(welcome_shown=True)
        self.assertTrue(v.settings_page.check_updates.isChecked())
        # Built alone, as a capture builds it, it asks nothing.
        self.assertFalse(v._check_at_start.isActive())
        self.start(v)
        self.assertTrue(v._check_at_start.isActive())
        self.assertTrue(v.update_button.isHidden())

    def test_switched_off_it_does_not_check_on_opening(self):
        v = self.ventana(check_updates=False, welcome_shown=True)
        self.start(v)
        self.assertFalse(v._check_at_start.isActive())
        self.assertIsNone(v._tarea_de_red)

    def test_without_network_it_says_so_and_offers_nothing(self):
        # The real check, with the suite offline (tests/__init__.py).
        v = self.ventana()
        self.assertIs(v._buscar_version, updates.check)
        v.buscar_actualizacion()
        self.esperar(v)
        self.assertIn(_("updates.err.network"), v.settings_page.update_status.text())
        self.assertTrue(v.update_button.isHidden())
        self.assertTrue(v.settings_page.update_install_row.isHidden())

    def test_closing_while_github_is_slow_neither_waits_nor_aborts(self):
        # On by default, a check is under way in the first seconds of every
        # session. A QThread destroyed with the window aborted the process.
        import threading

        import shiboken6
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        answer = threading.Event()
        self.addCleanup(answer.set)
        qt.app()
        v = MainWindow(Preferences().normalized())
        v._buscar_version = lambda channel="stable": answer.wait(10) and None
        v.buscar_actualizacion()
        task = v._tarea_de_red
        v.close()
        shiboken6.delete(v)
        answer.set()
        self.assertTrue(task.wait(5000))
        qt.app().processEvents()

    def test_the_sidebar_notice_shows_with_the_bar_folded(self):
        v = self.ventana()
        v._version_nueva = NUEVA
        v.set_nav_folded(True)
        v._pintar_version_nueva()
        self.assertFalse(v.update_button.isHidden())
        self.assertEqual(v.update_button.text(), "↑")
        self.assertIn("99.0", v.update_button.toolTip())
        v.set_nav_folded(False)
        v._pintar_version_nueva()
        self.assertIn("99.0", v.update_button.text())

    def test_the_sidebar_notice_leads_to_the_updates_in_settings(self):
        v = self.ventana()
        v.resize(900, 680)
        v.show()
        qt.app().processEvents()
        v._version_nueva = NUEVA
        v._pintar_version_nueva()
        v._instalar_version = mock.Mock(side_effect=AssertionError("it only leads there"))
        v.update_button.click()
        for _turn in range(4):
            qt.app().processEvents()
        page = v.settings_page
        self.assertIs(v.stack.currentWidget(), page)
        self.assertTrue(page.update_install_row.isVisibleTo(page))
        self.assertIn("99.0", page.update_install.text())
        # Scrolled down to the group, its top in view.
        top = page.updates_card.mapTo(page.viewport(), page.updates_card.rect().topLeft()).y()
        self.assertGreater(page.verticalScrollBar().value(), 0)
        self.assertTrue(0 <= top < page.viewport().height() // 3, top)
        v._instalar_version.assert_not_called()

    def test_the_button_in_settings_installs(self):
        v = self.ventana()
        v._version_nueva = NUEVA
        v._pintar_version_nueva()
        with mock.patch.object(updates, "replaceable_path", return_value=None), \
                mock.patch("PySide6.QtWidgets.QMessageBox.information") as aviso:
            v.settings_page.update_install.click()
        self.assertIn(NUEVA.url, aviso.call_args[0][2])

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



class TestTheCompatibleOneOnAModernProcessor(unittest.TestCase):
    """A tester downloaded the compatible AppImage for a processor that runs
    the normal one: About says so, in one line, and only there."""

    def _about_note(self, build: str, cpuinfo: str):
        import pathlib
        import tempfile

        from silux.settings import Preferences
        from silux.ui import guarda
        from silux.ui.app import MainWindow

        qt.app()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = pathlib.Path(folder.name) / "cpuinfo"
        path.write_text(cpuinfo, encoding="utf-8")
        with mock.patch.object(updates, "build_id", return_value=build), \
                mock.patch.object(guarda, "CPUINFO", str(path)), \
                mock.patch.object(guarda.os, "uname", return_value=mock.Mock(machine="x86_64")):
            window = MainWindow(Preferences().normalized())
        self.addCleanup(window.close)
        note = window.settings_page.compat_note
        return note.text() if note is not None else None

    def test_it_says_the_normal_one_would_run(self):
        from tests.test_arranque import MODERNO
        text = self._about_note("20261123.a5b145b-compat", MODERNO)
        self.assertEqual(text, _("about.compat.normal").format(archivo=updates.NORMAL))

    def test_not_on_a_processor_without_v2_nor_on_the_normal_one(self):
        from tests.test_arranque import MODERNO, PHENOM_II
        self.assertIsNone(self._about_note("20261123.a5b145b-compat", PHENOM_II))
        self.assertIsNone(self._about_note("20261123.a5b145b", MODERNO))


if __name__ == "__main__":
    unittest.main()
