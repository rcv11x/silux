"""Ajustes: la maqueta aprobada el 18 de noviembre, con los cambios del autor.

Interruptores en vez de casillas; el estado del ayudante como insignia de
color y el botón que toca según ese estado (no se pide lo que ya está);
«1.0 s» con punto; la cuenta de piezas ARM la de la base de datos (en la
maqueta salía 0); la columna pegada a la izquierda; nada de «PROPUESTA», y
el grupo nuevo de integración con el escritorio, con su estado y el botón
de cada caso.
"""

import dataclasses
import os
import pathlib
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux import db, desktop, render
from silux.i18n import _
from silux.model import Need, Note, PrivilegedState
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton
except ImportError:                                    # pragma: no cover
    QApplication = None


def _pagina(app, **prefs):
    from silux.settings import Preferences
    from silux.ui import theme
    from silux.ui.pages.settings import SettingsPage

    pagina = SettingsPage(Preferences(**prefs).normalized(), theme.palette_for(app, "dark"))
    pagina.resize(1200, 900)
    pagina.show()
    app.processEvents()
    return pagina


def _textos(pagina):
    return [w.text() for w in pagina.findChildren(QLabel) + pagina.findChildren(QPushButton)
            if w.isVisibleTo(pagina)]


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaMaqueta(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self._tmp.name,
                                             "XDG_CONFIG_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def test_interruptores_y_no_casillas(self):
        from silux.ui.pages.settings import Interruptor

        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        self.assertEqual(pagina.findChildren(QCheckBox), [])
        self.assertIsInstance(pagina.all_features, Interruptor)
        self.assertIsInstance(pagina.fluid_charts, Interruptor)
        recibidas = []
        pagina.changed.connect(recibidas.append)
        pagina.all_features.click()
        self.assertTrue(recibidas[-1].show_all_features)

    def test_cada_interruptor_en_su_grupo(self):
        """Las gráficas fluidas son apariencia; las instrucciones de la CPU
        van con el muestreo, no con el idioma y las unidades."""
        from silux.ui.widgets import Card

        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)

        def grupo(control):
            padre = control.parentWidget()
            while not isinstance(padre, Card):
                padre = padre.parentWidget()
            return padre._title_label.text()

        self.assertEqual(grupo(pagina.fluid_charts), _("settings.card.appearance"))
        self.assertEqual(grupo(pagina.all_features), _("settings.card.sampling"))

    def test_el_intervalo_con_punto_aunque_el_sistema_vaya_en_español(self):
        anterior = QLocale()
        QLocale.setDefault(QLocale(QLocale.Language.Spanish, QLocale.Country.Spain))
        self.addCleanup(QLocale.setDefault, anterior)
        pagina = _pagina(self.app, interval_s=1.0)
        self.addCleanup(pagina.deleteLater)
        self.assertEqual(pagina.interval.text(), "1.0 s")

    def test_las_piezas_arm_son_las_de_la_base(self):
        """En la maqueta salía «0 piezas ARM»; la base tiene 198."""
        cuantas = db.load()["counts"]["arm_parts"]
        self.assertGreater(cuantas, 0)
        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        self.assertIn(f"{cuantas} piezas ARM", pagina.db_info.text())

    def test_each_number_of_the_table_says_where_it_comes_from(self):
        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        texto = pagina.db_info.text()
        datos = db.load()
        for numero, fuente in ((datos["counts"]["intel_family"], "Linux"),
                               (datos["counts"]["amd_models"], "amd.com"),
                               (datos["counts"]["cpuid_nodes"], "cpuid"),
                               (datos["counts"]["sockets"], "CPU-X")):
            with self.subTest(fuente=fuente):
                self.assertRegex(texto, rf"\b{numero} [^;]* {fuente}\b")
        self.assertNotIn("gen_cpu_db", texto)

    def test_the_switch_outline_is_one_sharp_pixel(self):
        """It was a blurred 2 px line: 1 px drawn between two rows of pixels."""
        from silux.ui import theme
        from silux.ui.pages.settings import Interruptor
        paleta = theme.palette_for(self.app, "dark")
        interruptor = Interruptor(paleta)
        self.addCleanup(interruptor.deleteLater)
        interruptor.resize(interruptor.sizeHint())
        imagen = interruptor.grab().toImage()
        contorno = paleta.q("muted")
        columna = imagen.width() // 2
        filas = [imagen.pixelColor(columna, y) for y in range(imagen.height() // 2)]
        cerca = [c for c in filas if max(abs(c.red() - contorno.red()), abs(c.green() - contorno.green()),
                                         abs(c.blue() - contorno.blue())) <= 8]
        self.assertEqual(len(cerca), 1, [c.name() for c in filas])

    def test_python_and_qt_with_the_versions_this_copy_runs(self):
        import platform

        from PySide6.QtCore import qVersion
        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        textos = _textos(pagina)
        self.assertIn(f"Python {platform.python_version()}", textos)
        self.assertTrue([t for t in textos if t.startswith("PySide6") and qVersion() in t])

    def test_sin_marcas_de_propuesta_y_claude_con_su_descripcion(self):
        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        textos = _textos(pagina)
        self.assertFalse([t for t in textos if "PROPUESTA" in t.upper()])
        self.assertIn(_("about.claude"), textos)

    def test_quitar_el_ayudante_solo_si_esta_instalado(self):
        """Antes solo se quitaba copiando una orden `sudo rm` del diálogo de
        permisos. Ahora es un botón, y solo sale si hay algo que quitar."""
        from silux.privileged.client import PrivilegedClient
        for instalado in (False, True):
            with self.subTest(instalado=instalado), \
                 mock.patch.object(PrivilegedClient, "instalado", return_value=instalado), \
                 mock.patch.object(PrivilegedClient, "necesita_reinstalar", return_value=False):
                pagina = _pagina(self.app)
                self.addCleanup(pagina.deleteLater)
                pagina.set_privileges(None)
                self.assertEqual(not pagina.remove_helper_button.isHidden(), instalado)
                if instalado:
                    pedidos = []
                    pagina.remove_helper_requested.connect(lambda: pedidos.append(1))
                    pagina.remove_helper_button.click()
                    self.assertEqual(pedidos, [1])

    def test_la_orden_de_quitarlo_es_el_desinstalador(self):
        from silux.ui.app import MainWindow
        from silux.privileged import client
        orden = MainWindow._orden_de_desinstalacion()
        self.assertIn(orden[0], client.PKEXEC_PATHS)
        self.assertEqual(orden[-1], "--uninstall")
        self.assertIn("silux-instalar.py", orden)

    def test_a_2560_la_columna_va_pegada_a_la_izquierda(self):
        from silux.ui import theme

        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        pagina.resize(2300, 1300)
        for _vez in range(3):
            self.app.processEvents()
        self.assertEqual(pagina.columna.x(), theme.METRICS.page_margin)
        self.assertLess(pagina.columna.width(), 2300 // 2 + 200)

    def test_los_desplegables_no_cortan_su_opcion(self):
        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        caja = pagina.network_box
        self.assertGreaterEqual(caja.width(), caja.sizeHint().width())
        anchos = {c.width() for c in (pagina.language_box, pagina.theme_box,
                                      pagina.network_box, pagina.interval)}
        self.assertEqual(len(anchos), 1, anchos)


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLosPermisos(unittest.TestCase):
    """La insignia y el botón, según lo que sabe la ventana del ayudante."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "i5-10400")[0]

    def _estado(self, privilegios, notas=None, instalado=False, viejo=False):
        from silux.privileged.client import PrivilegedClient

        pagina = _pagina(self.app)
        self.addCleanup(pagina.deleteLater)
        notas_de_la_foto = self.foto.notes if notas is None else tuple(
            n for n in self.foto.notes if n.need is not Need.ROOT)
        muestra = dataclasses.replace(self.foto, privileged=privilegios, notes=notas_de_la_foto)
        with mock.patch.object(PrivilegedClient, "instalado", return_value=instalado), \
             mock.patch.object(PrivilegedClient, "necesita_reinstalar", return_value=viejo):
            pagina.set_privileges(muestra)
        return pagina

    def test_el_volcado_tiene_algo_que_pedir(self):
        self.assertTrue(self.foto.permission_notes)

    def test_sin_conceder(self):
        p = self._estado(PrivilegedState(supported=True))
        self.assertEqual(p.permission_badge.text(), _("settings.perm.none"))
        self.assertEqual(p.permission_badge.tono, "muted")
        self.assertTrue(p.permission_button.isVisibleTo(p))
        self.assertTrue(p.explain_button.isVisibleTo(p))

    def test_concedidos_no_se_vuelven_a_pedir(self):
        p = self._estado(PrivilegedState(supported=True, connected=True), notas=(),
                         instalado=True)
        self.assertEqual(p.permission_badge.text(), _("settings.perm.installed.connected"))
        self.assertEqual(p.permission_badge.tono, "ok")
        self.assertFalse(p.permission_button.isVisibleTo(p))
        self.assertFalse(p.explain_button.isVisibleTo(p))

    def test_instalado_pide_la_contrasena_de_la_sesion(self):
        p = self._estado(PrivilegedState(supported=True), instalado=True)
        self.assertEqual(p.permission_badge.text(), _("settings.perm.installed"))
        self.assertTrue(p.permission_button.isVisibleTo(p))
        self.assertFalse(p.explain_button.isVisibleTo(p))
        pedidas = []
        p.elevation_requested.connect(lambda: pedidas.append(1))
        p.permission_button.click()
        self.assertEqual(pedidas, [1])

    def test_un_ayudante_de_otra_version_se_sustituye(self):
        p = self._estado(PrivilegedState(supported=True), instalado=True, viejo=True)
        self.assertEqual(p.permission_badge.tono, "warn")
        self.assertEqual(p.permission_button.text(), _("perm.replace.button"))
        sustituir = []
        p.permanent_requested.connect(lambda: sustituir.append(1))
        p.permission_button.click()
        self.assertEqual(sustituir, [1])

    def test_no_hacen_falta(self):
        p = self._estado(PrivilegedState(supported=True), notas=())
        self.assertEqual(p.permission_badge.text(), _("settings.perm.notneeded"))
        self.assertFalse(p.permission_button.isVisibleTo(p))

    def test_sin_pkexec(self):
        """Sin pkexec la foto no cuenta nada pendiente: no es «no hacen falta»."""
        p = self._estado(PrivilegedState(supported=False))
        self.assertEqual(p.permission_badge.text(), _("settings.perm.unsupported"))
        self.assertFalse(p.permission_button.isVisibleTo(p))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElEscritorio(unittest.TestCase):
    """El grupo nuevo, con la casa en una carpeta temporal."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        casa = pathlib.Path(self._tmp.name)
        (casa / "config").mkdir()
        (casa / "config" / "user-dirs.dirs").write_text(
            f'XDG_DESKTOP_DIR="{casa}/Escritorio"\n')
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(casa / "data"),
                                             "XDG_CONFIG_HOME": str(casa / "config")})
        patch.start()
        self.addCleanup(patch.stop)
        sin_ordenes = mock.patch.object(desktop, "refresh_caches")
        sin_ordenes.start()
        self.addCleanup(sin_ordenes.stop)
        self.pagina = _pagina(self.app)
        self.addCleanup(self.pagina.deleteLater)

    def _esperar(self):
        if self.pagina._tarea is not None:
            self.pagina._tarea.wait()
        for _vez in range(5):
            self.app.processEvents()

    def _visibles(self):
        p = self.pagina
        return {nombre for nombre, boton in (("add", p.desktop_add), ("fix", p.desktop_fix),
                                             ("remove", p.desktop_remove))
                if boton.isVisibleTo(p)}

    def test_sin_instalar_se_ofrece_anadir(self):
        self.assertEqual(self.pagina.desktop_state, "missing")
        self.assertEqual(self.pagina.desktop_badge.text(), _("settings.desktop.missing"))
        self.assertEqual(self._visibles(), {"add"})

    def test_desde_el_codigo_lo_dice(self):
        texto = self.pagina.desktop_row.explicacion.text()
        self.assertIn(render.home_path(desktop.ROOT), texto)
        self.assertIn("desarrollo", texto)

    def test_anadir_y_quitar_se_ven_en_la_misma_pagina(self):
        self.pagina.desktop_shortcut.setChecked(True)
        self.pagina.desktop_add.click()
        self._esperar()
        self.assertEqual(self.pagina.desktop_state, "current")
        self.assertEqual(self.pagina.desktop_badge.tono, "ok")
        self.assertEqual(self._visibles(), {"remove"})
        self.assertTrue(desktop.desktop_path("silux-dev").is_file())
        self.assertTrue(desktop.shortcut_path("silux-dev").is_file())
        self.pagina.desktop_remove.click()
        self._esperar()
        self.assertEqual(self.pagina.desktop_state, "missing")
        self.assertFalse(desktop.shortcut_path("silux-dev").exists())

    def test_una_entrada_rota_se_arregla(self):
        desktop.install()
        entrada = desktop.desktop_path("silux-dev")
        entrada.write_text(entrada.read_text().replace(
            "Path=", "Path=/home/ana/silux-que-ya-no-esta\nX-Path-Viejo="))
        self.pagina.refresh_desktop()
        self.assertEqual(self.pagina.desktop_state, "broken")
        self.assertEqual(self.pagina.desktop_badge.tono, "crit")
        self.assertEqual(self._visibles(), {"fix", "remove"})
        self.pagina.desktop_fix.click()
        self._esperar()
        self.assertEqual(self.pagina.desktop_state, "current")

    def test_lo_que_cambia_desde_fuera_se_ve_con_la_pagina_abierta(self):
        """Regla 9: instalada desde la terminal, la página lo dice con la
        foto siguiente, sin salir y volver."""
        desktop.install()
        self.pagina.apply(foto(EQUIPOS / "i5-10400")[0])
        self.assertEqual(self.pagina.desktop_state, "current")


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnLaVentana(unittest.TestCase):

    def test_la_ventana_le_da_la_foto_y_sus_botones_piden_permisos(self):
        """Sin ayudante instalado, que es el estado del que habla: lo fija,
        porque en un equipo con el ayudante puesto la página dice «installed»."""
        from silux.privileged.client import PrivilegedClient
        app = qt.app()
        f = foto(EQUIPOS / "i5-10400")[0]
        with mock.patch.object(PrivilegedClient, "instalado", return_value=False), \
             mock.patch.object(PrivilegedClient, "necesita_reinstalar", return_value=False), \
             pantalla.Ventana(f) as ventana:
            ventana.select_section("Ajustes")
            for _vez in range(3):
                app.processEvents()
            pagina = ventana.settings_page
            self.assertEqual(pagina.permission_state, "none")
            # Sin la regla de polkit puesta, antes se cuenta lo que dirá la
            # ventana de la contraseña; desde ahí se piden.
            pagina.permission_button.click()
            dialogo = ventana._dialogo_permisos
            self.assertTrue(dialogo.isVisible())
            with mock.patch.object(ventana.sampler, "request_elevation") as pedir:
                dialogo.grant_button.click()
            pedir.assert_called_once()
            self.assertFalse(pagina.permission_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
