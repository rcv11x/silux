"""El aviso de Inicio: lo que falta por permisos, junto, y cómo se aparta.

Con los volcados de los dos equipos, que son sin permisos: cinco datos en el
i5-10400 y tres en el 5800X3D. La foto «con permisos» es la misma sin sus
notas de permisos y con el ayudante conectado, que es lo que cambia cuando se
dan.
"""

import dataclasses
import os
import tempfile
import unittest
from unittest import mock

from silux.model import Need, PrivilegedState
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

INTEL, AMD = "i5-10400", "5800x3d"


def con_permisos(f):
    return dataclasses.replace(
        f, notes=tuple(n for n in f.notes if n.need is not Need.ROOT),
        privileged=PrivilegedState(supported=True, connected=True))


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElAvisoDeInicio(unittest.TestCase):

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

    def _ventana(self, **preferencias):
        from silux import settings
        from silux.ui.app import MainWindow

        guardadas = settings.load()
        ventana = MainWindow(dataclasses.replace(guardadas, **preferencias).normalized())
        ventana.show()
        self.addCleanup(ventana.close)
        return ventana

    def _aviso(self, ventana):
        return ventana.home_page.permission_notice

    def test_sale_con_lo_que_falta_en_cada_equipo(self):
        for nombre, cuantos in ((INTEL, 5), (AMD, 3)):
            with self.subTest(equipo=nombre):
                ventana = self._ventana()
                f = self.fotos[nombre]
                ventana._on_sample(f)
                aviso = self._aviso(ventana)
                self.assertFalse(aviso.isHidden())
                self.assertIn(str(cuantos), aviso.title.text())
                self.assertEqual([l.text() for l in aviso.lines],
                                 [n.what for n in f.permission_notes])

    def test_va_debajo_de_las_tarjetas_y_no_delante_del_equipo(self):
        # Arriba del todo eran 130 px de aviso antes del primer dato. Lo
        # primero de Inicio es el equipo; lo que falta lo señalan además el
        # candado de cada tarjeta y el enlace de la barra de estado.
        ventana = self._ventana()
        ventana._on_sample(self.fotos[AMD])
        self.app.processEvents()
        inicio = ventana.home_page
        aviso = self._aviso(ventana)
        self.assertFalse(aviso.isHidden())
        raiz = inicio.widget()
        def alto(widget):
            return widget.mapTo(raiz, widget.rect().topLeft()).y()
        self.assertEqual(alto(inicio.title.parentWidget()),
                         raiz.layout().contentsMargins().top())
        for tarjeta in (inicio.cpu, inicio.memoria, inicio.placa):
            self.assertGreater(alto(aviso), alto(tarjeta))

    def test_con_todo_leido_no_sale(self):
        ventana = self._ventana()
        ventana._on_sample(con_permisos(self.fotos[INTEL]))
        self.assertTrue(self._aviso(ventana).isHidden())

    def test_sin_ayudante_no_ofrece_lo_que_no_puede_dar(self):
        ventana = self._ventana()
        ventana._on_sample(dataclasses.replace(
            self.fotos[INTEL], privileged=PrivilegedState(supported=False)))
        self.assertTrue(self._aviso(ventana).isHidden())

    def test_desaparece_solo_al_dar_los_permisos(self):
        ventana = self._ventana()
        ventana._on_sample(self.fotos[INTEL])
        self.assertFalse(self._aviso(ventana).isHidden())
        ventana._on_sample(con_permisos(self.fotos[INTEL]))
        self.assertTrue(self._aviso(ventana).isHidden())

    def test_en_compacto_la_lista_es_un_renglon(self):
        ventana = self._ventana(density="compact")
        f = self.fotos[INTEL]
        ventana._on_sample(f)
        lineas = [l.text() for l in self._aviso(ventana).lines]
        self.assertEqual(len(lineas), 1)
        for nota in f.permission_notes:
            self.assertIn(nota.what, lineas[0])

    def test_dar_permisos_los_pide(self):
        ventana = self._ventana()
        ventana._on_sample(self.fotos[AMD])
        with mock.patch.object(ventana.sampler, "request_elevation") as pedir:
            self._aviso(ventana).grant_button.click()
        pedir.assert_called_once()
        # Mientras polkit pregunta no se puede pulsar otra vez…
        self.assertFalse(self._aviso(ventana).grant_button.isEnabled())
        # …y con la muestra siguiente vuelve, se hayan dado o no.
        ventana._on_sample(self.fotos[AMD])
        self.assertTrue(self._aviso(ventana).grant_button.isEnabled())

    def test_ahora_no_dura_lo_que_la_sesion(self):
        from dataclasses import replace

        ventana = self._ventana()
        ventana._on_sample(self.fotos[AMD])
        self._aviso(ventana).snooze_button.click()
        self.assertTrue(self._aviso(ventana).isHidden())
        ventana._on_sample(self.fotos[AMD])
        self.assertTrue(self._aviso(ventana).isHidden(), "volvió con la muestra siguiente")
        # Cambiar el tema rehace la página: el aviso no puede volver por eso.
        ventana._on_preferences(replace(ventana.prefs, theme="light"))
        ventana._on_sample(self.fotos[AMD])
        self.assertTrue(self._aviso(ventana).isHidden(), "volvió al rehacer la página")
        # En el arranque siguiente, sí.
        otra = self._ventana()
        otra._on_sample(self.fotos[AMD])
        self.assertFalse(self._aviso(otra).isHidden())

    def test_no_volver_a_mostrar_se_guarda(self):
        from silux import settings

        ventana = self._ventana()
        ventana._on_sample(self.fotos[AMD])
        self._aviso(ventana).dismiss_button.click()
        self.assertTrue(self._aviso(ventana).isHidden())
        self.assertTrue(settings.load().permission_notice_dismissed)
        otra = self._ventana()
        otra._on_sample(self.fotos[AMD])
        self.assertTrue(self._aviso(otra).isHidden())

    def test_si_deja_de_leerse_vuelve_aunque_se_hubiera_quitado(self):
        # Un ayudante que se cae a media sesión: lo que se estaba leyendo deja
        # de leerse. Eso es otro aviso, y «No volver a mostrar» no lo calla.
        ventana = self._ventana(permission_notice_dismissed=True)
        f = self.fotos[INTEL]
        ventana._on_sample(f)
        self.assertTrue(self._aviso(ventana).isHidden())
        ventana._on_sample(con_permisos(f))
        ventana._on_sample(f)
        aviso = self._aviso(ventana)
        self.assertFalse(aviso.isHidden())
        from silux.i18n import _
        self.assertEqual(aviso.title.text(), _("perm.notice.lost.many").format(n=5))
        # Y apartado, no insiste mientras dure.
        aviso.snooze_button.click()
        ventana._on_sample(f)
        self.assertTrue(aviso.isHidden())

    def test_repintar_no_crea_widgets(self):
        ventana = self._ventana()
        f = self.fotos[INTEL]
        ventana._on_sample(f)
        aviso = self._aviso(ventana)
        antes = len(aviso.findChildren(object))
        for _vez in range(10):
            ventana._on_sample(f)
        self.assertEqual(len(aviso.findChildren(object)), antes)


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLosAvisosDeLasPaginas(unittest.TestCase):
    """Los mismos dos botones en cada página, y apartan lo mismo que en Inicio.

    Apartar el aviso de Memoria y encontrárselo otra vez en Almacenamiento
    sería no haberlo apartado. Lo que falta sigue dicho donde falta, con su
    candado, y en el enlace de la barra de estado.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / INTEL)[0]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        parche = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        parche.start()
        self.addCleanup(parche.stop)

    def _ventana(self, **preferencias):
        from silux import settings
        from silux.ui.app import MainWindow

        ventana = MainWindow(dataclasses.replace(settings.load(), **preferencias).normalized())
        ventana.resize(1440, 880)
        ventana.show()
        self.addCleanup(ventana.close)
        ventana._on_sample(self.foto)
        ventana._on_sample(self.foto)
        for _vez in range(3):
            self.app.processEvents()
        return ventana

    def test_la_tarjeta_solo_tiene_dos_formas_de_apartarse(self):
        # «No volver a pedirla» (instalar el ayudante para siempre) iba al
        # lado de «Ahora no» y «No volver a mostrar» y se leía como una
        # tercera forma de quitar el aviso. Ahora está en «Qué hace esto».
        from PySide6.QtWidgets import QPushButton
        from silux.i18n import _
        from silux.privileged.client import PrivilegedClient

        # Sin un ayudante atrasado en el sistema, que añade su botón: si
        # quien ejecuta la suite tiene uno, este test no habla de eso.
        with mock.patch.object(PrivilegedClient, "necesita_reinstalar", return_value=False):
            ventana = self._ventana()
        for nombre, pagina in (("Memoria", ventana.memory_page),
                               ("Almacenamiento", ventana.storage_page)):
            ventana.select_section(nombre)
            self.app.processEvents()
            tarjeta = pagina.snooze_button.parentWidget()
            visibles = [b.text() for b in tarjeta.findChildren(QPushButton) if b.isVisible()]
            with self.subTest(pagina=nombre):
                self.assertEqual(visibles, [_("perm.read.button"), _("perm.notice.explain"),
                                            _("perm.notice.later"), _("perm.notice.never")])
                self.assertFalse([t for t in visibles if "pedirla" in t])

    def test_con_un_ayudante_atrasado_su_boton_va_en_otro_renglon_y_cabe(self):
        """En el 5800X3D, con el ayudante instalado de una versión anterior,
        «Actualizar el ayudante del sistema» iba en la fila de los otros
        cuatro botones: en compacto a 900 px la tarjeta pedía más ancho del
        que hay y Memoria y Almacenamiento salían cortadas por la derecha."""
        from PySide6.QtCore import QPoint
        from silux.privileged.client import PrivilegedClient
        from silux.ui import theme

        from silux.settings import Preferences

        normales = Preferences().normalized()
        self.addCleanup(theme.apply, self.app, normales.theme, normales.density,
                        normales.font_scale, normales.accent)
        # La densidad se aplica antes de montar la ventana, como al arrancar.
        theme.apply(self.app, normales.theme, "compact", normales.font_scale, normales.accent)
        with mock.patch.object(PrivilegedClient, "necesita_reinstalar", return_value=True):
            ventana = self._ventana(density="compact", window_width=900, window_height=680)
            ventana.resize(900, 680)
            for nombre, pagina in (("Memoria", ventana.memory_page),
                                   ("Almacenamiento", ventana.storage_page)):
                ventana.select_section(nombre)
                for _vez in range(5):
                    self.app.processEvents()
                with self.subTest(pagina=nombre):
                    boton = pagina.permanent_button
                    self.assertTrue(boton.isVisible())
                    def y(w):
                        return w.mapTo(ventana, QPoint(0, 0)).y()
                    self.assertGreater(y(boton), y(pagina.elevation_button))
                    for b in (boton, pagina.dismiss_button):
                        derecha = b.mapTo(ventana, QPoint(b.width(), 0)).x()
                        self.assertLessEqual(derecha, ventana.width(), b.text())
                    tarjeta = pagina.snooze_button.parentWidget()
                    self.assertLessEqual(
                        tarjeta.mapTo(ventana, QPoint(tarjeta.width(), 0)).x(), ventana.width())

    def test_que_hace_esto_abre_el_dialogo_desde_la_pagina(self):
        from silux.privileged.client import PrivilegedClient

        ventana = self._ventana()
        ventana.select_section("Memoria")
        # Sin ayudante instalado, que es cuando se ofrece: con uno al día en
        # el equipo de quien ejecuta la suite el botón no sale, y está bien.
        with mock.patch.object(PrivilegedClient, "instalado", return_value=False):
            ventana.memory_page.explain_button.click()
        self.assertTrue(ventana._dialogo_permisos.isVisible())
        self.addCleanup(ventana._dialogo_permisos.close)
        # Y ahí sigue estando darlos para siempre.
        self.assertTrue(ventana._dialogo_permisos.permanent_button.isVisible())

    @staticmethod
    def _avisos_con_boton(host):
        avisos = []
        for indice in range(host.count()):
            widget = host.itemAt(indice).widget()
            if widget is not None and getattr(widget, "action_button", None):
                avisos.append(widget)
        return avisos

    def _de_permisos(self, ventana):
        """Lo que cada página enseña para pedir permisos, visible o no."""
        ficha = ventana.graphics_page._sections[0]
        return {
            "CPU": bool(self._avisos_con_boton(ventana.cpu_page._notices_host)),
            "Gráficos": bool(self._avisos_con_boton(ficha._notices_host)),
            "Memoria": not ventana.memory_page.elevation.isHidden(),
            "Almacenamiento": not ventana.storage_page.elevation_card.isHidden(),
        }

    def test_las_cuatro_paginas_piden_permisos_y_llevan_los_dos_botones(self):
        from silux.i18n import _

        ventana = self._ventana()
        self.assertEqual(self._de_permisos(ventana),
                         {"CPU": True, "Gráficos": True, "Memoria": True,
                          "Almacenamiento": True})
        ficha = ventana.graphics_page._sections[0]
        portadores = (self._avisos_con_boton(ventana.cpu_page._notices_host)
                      + self._avisos_con_boton(ficha._notices_host)
                      + [ventana.memory_page, ventana.storage_page,
                         ventana.home_page.permission_notice])
        for portador in portadores:
            with self.subTest(donde=type(portador).__name__):
                self.assertEqual(portador.snooze_button.text(), _("perm.notice.later"))
                self.assertEqual(portador.dismiss_button.text(), _("perm.notice.never"))
                self.assertEqual(portador.snooze_button.objectName(), "TextButton")

    def test_ahora_no_en_una_pagina_los_aparta_todos(self):
        ventana = self._ventana()
        ventana.memory_page.snooze_button.click()
        self.assertEqual(set(self._de_permisos(ventana).values()), {False})
        self.assertTrue(ventana.home_page.permission_notice.isHidden())
        # Y con la muestra siguiente siguen apartados.
        ventana._on_sample(self.foto)
        self.assertEqual(set(self._de_permisos(ventana).values()), {False})

    def test_apartarlos_en_inicio_tambien_los_quita_de_las_paginas(self):
        ventana = self._ventana()
        ventana.home_page.permission_notice.snooze_button.click()
        self.assertEqual(set(self._de_permisos(ventana).values()), {False})

    def test_no_volver_a_mostrar_desde_una_pagina_se_guarda(self):
        from silux import settings

        ventana = self._ventana()
        aviso = self._avisos_con_boton(ventana.cpu_page._notices_host)[0]
        aviso.dismiss_button.click()
        self.assertTrue(settings.load().permission_notice_dismissed)
        otra = self._ventana()
        self.assertEqual(set(self._de_permisos(otra).values()), {False})

    def test_apartados_lo_que_falta_sigue_dicho(self):
        from silux.i18n import _

        ventana = self._ventana(permission_notice_dismissed=True)
        self.assertEqual(set(self._de_permisos(ventana).values()), {False})
        # El enlace de la barra, el candado del voltaje…
        self.assertFalse(ventana._blocked.isHidden())
        rejilla = next(iter(ventana.cpu_page._sections.values())).processor
        self.assertTrue(rejilla.is_locked(_("cpu.field.voltage")))
        # …y los avisos que no son de permisos, que no se apartan.
        self.assertIn("cpu.power", [n.path for n in self.foto.notes])
        host = ventana.cpu_page._notices_host
        self.assertGreater(host.count(), 0)

    def test_al_darlos_y_perderlos_vuelven_tambien_en_las_paginas(self):
        ventana = self._ventana(permission_notice_dismissed=True)
        ventana._on_sample(con_permisos(self.foto))
        ventana._on_sample(self.foto)
        ventana._on_sample(self.foto)
        self.assertTrue(self._de_permisos(ventana)["CPU"])
        self.assertTrue(self._de_permisos(ventana)["Almacenamiento"])
