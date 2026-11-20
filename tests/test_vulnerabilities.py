"""The System page's vulnerabilities, as two testers' reports showed them.

The list was titled «Las mitigadas» and listed «Vulnerable: No microcode»
too; and a status the kernel does not know («Unknown: No mitigations», in
a QEMU guest) counted nowhere: 17 known, 8 + 6 + 2 said.
"""

import unittest

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestTheVulnerabilities(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _page(self, equipo):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.system import SystemPage

        pagina = SystemPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        self.addCleanup(pagina.deleteLater)
        pagina.show()
        pagina.apply(foto(EQUIPOS / equipo)[0])
        self.app.processEvents()
        return pagina

    def test_the_list_is_not_called_the_mitigated_ones(self):
        pagina = self._page("qemu-kvm")
        self.assertNotIn("mitigadas", pagina.vuln_fold.boton.text().lower())

    def test_every_known_one_is_counted_somewhere(self):
        pagina = self._page("qemu-kvm")
        valores = pagina.security._values
        cuentas = [valores[_(k)].full_text() for k in
                   ("sys.vuln.unaffected", "sys.vuln.mitigated", "sys.vuln.open",
                    "sys.vuln.unknown")]
        numeros = [int(c) if c.isdigit() else 0 for c in cuentas]
        self.assertEqual(sum(numeros), int(valores[_("sys.vuln.known")].full_text()))
        self.assertEqual(numeros[3], 1)

    def test_without_unknown_ones_the_row_does_not_show(self):
        pagina = self._page("5800x3d")
        self.assertFalse(pagina.security._values[_("sys.vuln.unknown")]
                         .isVisibleTo(pagina.security))


if __name__ == "__main__":
    unittest.main()
