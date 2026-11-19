"""La versión como se enseña: «0.4» y no «0.4.0»; «0.4.1» solo en arreglos.

Por debajo sigue siendo x.y.z: `silux.__version__`, pyproject, la etiqueta,
el informe y `--version`.
"""

import unittest

from silux import __version__, render


class TestLaVersion(unittest.TestCase):
    def test_sin_el_cero_del_final(self):
        self.assertEqual(render.version("0.4.0"), "0.4")
        self.assertEqual(render.version("1.0.0"), "1.0")

    def test_un_arreglo_lleva_su_numero(self):
        self.assertEqual(render.version("0.4.1"), "0.4.1")
        self.assertEqual(render.version("0.4.10"), "0.4.10")

    def test_una_de_prueba_lleva_su_nombre(self):
        from silux import i18n
        self.addCleanup(i18n.set_language, i18n.actual())
        i18n.set_language("es")
        self.assertEqual(render.version("0.4.0rc1"), "0.4-prueba1")
        self.assertEqual(render.version("0.4.1rc2"), "0.4.1-prueba2")
        i18n.set_language("en")
        self.assertEqual(render.version("0.4.0rc1"), "0.4-test1")

    def test_por_debajo_sigue_entera(self):
        # x.y.z, y como mucho «rcN» detrás: la versión de prueba de PEP 440.
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+(rc\d+)?$")

    def test_la_ventana_la_enseña_corta(self):
        from tests import qt
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        from silux.i18n import _
        qt.app()
        ventana = MainWindow(Preferences().normalized())
        self.addCleanup(ventana.deleteLater)
        from PySide6.QtWidgets import QLabel
        etiquetas = [l.text() for l in ventana.findChildren(QLabel)]
        corta = _("app.version").format(v=render.version(__version__))
        self.assertIn(corta, etiquetas)
        if __version__.endswith(".0") or "rc" in __version__:
            self.assertNotIn(_("app.version").format(v=__version__), etiquetas)


if __name__ == "__main__":
    unittest.main()
