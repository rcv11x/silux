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

    def test_por_debajo_sigue_entera(self):
        self.assertEqual(__version__.count("."), 2)

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
        if __version__.endswith(".0"):
            self.assertNotIn(_("app.version").format(v=__version__), etiquetas)


if __name__ == "__main__":
    unittest.main()
