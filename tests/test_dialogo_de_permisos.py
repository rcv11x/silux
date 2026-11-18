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

        dialogo = self._dialogo()
        de_siempre = dialogo.paragraphs[2].text()
        self.assertNotIn("Ajustes", de_siempre)
        self.assertNotIn("python3 -m", de_siempre)
        self.assertNotIn("{orden}", de_siempre)
        self.assertEqual(dialogo.command_text,
                         f"sudo rm {instalar.DESTINO} {instalar.POLITICA}")
        # Lo que se ve, pegado en un terminal, es esa misma orden: la barra
        # al final del renglón la continúa.
        visto = dialogo.command.toPlainText()
        self.assertEqual(" ".join(visto.replace("\\\n", " ").split()), dialogo.command_text)

    def test_la_orden_va_en_su_campo_entera_y_no_partida_en_el_parrafo(self):
        # En el párrafo, con ajuste de línea, se partía a mitad de una ruta:
        # ni se leía ni se podía copiar de un golpe.
        dialogo = self._dialogo()
        dialogo.show()
        self.addCleanup(dialogo.close)
        self.app.processEvents()
        campo = dialogo.command
        self.assertFalse([p for p in dialogo.paragraphs if "sudo" in p.text()])
        self.assertTrue(campo.isReadOnly())
        # De ancho fijo. Se mide: `QFontInfo.fixedPitch` dice que no de una
        # «Noto Sans Mono» que sí lo es.
        medida = campo.fontMetrics()
        self.assertEqual(medida.horizontalAdvance("iiii"), medida.horizontalAdvance("MMMM"))
        # Una ruta por renglón, y ninguna partida.
        renglones = campo.toPlainText().split("\n")
        self.assertEqual(len(renglones), 2)
        self.assertTrue(renglones[0].endswith("silux-helper \\"))
        self.assertTrue(renglones[1].strip().endswith(".policy"))
        # Caben enteros, a lo ancho y a lo alto: nada que desplazar.
        self.assertGreaterEqual(
            campo.viewport().width(),
            max(medida.horizontalAdvance(r) for r in renglones))
        self.assertGreaterEqual(campo.viewport().height(), 2 * medida.lineSpacing())
        # El diálogo se deja crecer hasta lo que pide: con un tope más
        # estrecho que la orden, el campo se salía por la derecha y los
        # párrafos se quedaban sin altura.
        self.assertGreaterEqual(dialogo.maximumWidth(),
                                dialogo.layout().minimumSize().width())
        self.assertGreaterEqual(dialogo.width(), dialogo.layout().minimumSize().width())
        for parrafo in dialogo.paragraphs:
            self.assertGreaterEqual(parrafo.height(),
                                    parrafo.heightForWidth(parrafo.width()))
        # Y va justo debajo del párrafo que habla de quitarlo.
        self.assertGreater(campo.mapTo(dialogo, campo.rect().topLeft()).y(),
                           dialogo.paragraphs[2].mapTo(
                               dialogo, dialogo.paragraphs[2].rect().topLeft()).y())
        self.assertLess(campo.mapTo(dialogo, campo.rect().topLeft()).y(),
                        dialogo.paragraphs[3].mapTo(
                            dialogo, dialogo.paragraphs[3].rect().topLeft()).y())

    def test_el_boton_la_copia(self):
        from PySide6.QtWidgets import QApplication

        dialogo = self._dialogo()
        dialogo.show()
        self.addCleanup(dialogo.close)
        QApplication.clipboard().setText("otra cosa")
        dialogo.copy_button.click()
        self.assertEqual(QApplication.clipboard().text(), dialogo.command_text)
        self.assertNotIn("\n", QApplication.clipboard().text())
        self.assertEqual(dialogo.copy_button.text(), _("app.copied"))

    def test_cabe_en_la_ventana_compacta(self):
        dialogo = self._dialogo()
        dialogo.show()
        self.addCleanup(dialogo.close)
        self.app.processEvents()
        self.assertLessEqual(dialogo.width(), 760)

    def test_la_orden_borra_justo_lo_que_borra_el_desinstalador(self):
        import inspect

        from silux.privileged import instalar

        orden = instalar.orden_de_desinstalar().split()
        self.assertEqual(orden[:2], ["sudo", "rm"])
        self.assertEqual(set(orden[2:]), {str(instalar.DESTINO), str(instalar.POLITICA)})
        # Y el desinstalador no borra ningún archivo más que esos dos.
        fuente = inspect.getsource(instalar.desinstalar)
        self.assertIn("for ruta in (POLITICA, DESTINO)", fuente)

    def test_ningun_parrafo_lleva_la_orden(self):
        textos = [p.text() for p in self._dialogo().paragraphs]
        self.assertEqual(sum("sudo rm" in t for t in textos), 0)

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
