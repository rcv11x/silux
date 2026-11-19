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


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestInstaladaYUtilizable(unittest.TestCase):
    """El título dice la memoria instalada y la que queda para usar.

    Decía «15.4 GB de memoria» en un equipo con dos módulos de 8 GB: es
    `MemTotal`, lo instalado menos lo que se quedan el firmware y el kernel,
    y parecía que faltaba memoria. La instalada sale de los módulos o del SPD;
    sin ninguno de los dos no se adivina.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _titulo(self, carpeta):
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        f = foto(EQUIPOS / carpeta)[0]
        theme.set_density("normal", "normal")
        self.pagina = MemoryPage(theme.palette_for(self.app, "dark"),
                                 Preferences().normalized())
        self.pagina.apply(f)
        return f, self.pagina.title.text()

    def test_con_el_spd_dice_las_dos(self):
        from silux import render
        f, titulo = self._titulo("i5-10400")
        self.assertEqual(titulo, "16 GB instalados · "
                         f"{render.size(f.system.memory.total_bytes)} utilizables")
        self.assertEqual(render.size(f.system.memory.total_bytes), "15.4 GB")

    def test_sin_modulos_ni_spd_solo_la_utilizable(self):
        from silux import render
        f, titulo = self._titulo("5800x3d")
        self.assertEqual((f.modules, f.spd), ((), ()))
        self.assertEqual(titulo, f"{render.size(f.system.memory.total_bytes)} utilizables")

    def test_con_la_tabla_del_firmware_manda_la_suma_de_los_modulos(self):
        import dataclasses
        from silux.model import MemoryModule
        f, _titulo = self._titulo("i5-10400")
        modulos = (MemoryModule(populated=True, size_bytes=16 * 1024**3),
                   MemoryModule(populated=True, size_bytes=16 * 1024**3),
                   MemoryModule(populated=False))
        self.assertEqual(dataclasses.replace(f, modules=modulos).installed_memory_bytes,
                         32 * 1024**3)


if __name__ == "__main__":
    unittest.main()
