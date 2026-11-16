"""La cabecera de Memoria sin permisos: a cuánto están catalogados, no a cuánto van.

El SPD de cada módulo se lee sin permisos y dice a qué velocidad puede ir. A
cuál va lo decide la BIOS, y eso está en la tabla del firmware, que sí los
pide. La cabecera decía «2 módulos leídos de su chip SPD a 3200 MT/s», que se
lee como la velocidad real; sin XMP activado van a 2133.

Con el volcado del i5-10400, que es justo ese caso: dos módulos de 3200 con
el SPD leído y sin permisos.
"""

import unittest

from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestLaCabeceraDeMemoria(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.foto = foto(EQUIPOS / "i5-10400")[0]

    def _pagina(self):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        theme.set_density("normal", "normal")
        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences().normalized())
        pagina.apply(self.foto)
        pagina.apply(self.foto)
        return pagina

    def test_el_volcado_es_el_caso(self):
        self.assertEqual([i.rated_mts for i in self.foto.spd], [3200, 3200])
        self.assertEqual(self.foto.modules, ())

    def test_dice_catalogados(self):
        pagina = self._pagina()             # guardada: sin dueño, Qt la borra
        texto = pagina.subtitle.text()
        self.assertIn("catalogados a 3200 MT/s", texto)
        self.assertNotIn("SPD a 3200", texto)

    def test_y_sigue_diciendo_lo_que_falta(self):
        from silux.i18n import _

        pagina = self._pagina()
        self.assertIn(_("memory.spd.needsroot").strip(" ·"), pagina.subtitle.text())

    def test_con_un_solo_modulo_va_en_singular(self):
        import dataclasses

        pagina = self._pagina()
        pagina.apply(dataclasses.replace(self.foto, spd=self.foto.spd[:1]))
        self.assertIn("catalogado a 3200 MT/s", pagina.subtitle.text())
        self.assertNotIn("catalogados", pagina.subtitle.text())


if __name__ == "__main__":
    unittest.main()
