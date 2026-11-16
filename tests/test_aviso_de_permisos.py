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

    def test_va_antes_que_la_cabecera(self):
        ventana = self._ventana()
        ventana._on_sample(self.fotos[AMD])
        self.app.processEvents()
        self.assertLess(self._aviso(ventana).geometry().top(),
                        ventana.home_page.title.parentWidget().geometry().top())

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
