"""Integración con el escritorio: icono y entrada de menú.

Se instala todo en un XDG_DATA_HOME temporal, así que estos tests no tocan la
configuración real del usuario que los ejecuta.
"""

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import PySide6.QtSvg  # noqa: F401
    HAS_QT_SVG = True
except ImportError:                                     # pragma: no cover
    HAS_QT_SVG = False

import install_desktop as installer  # noqa: E402


class TestPlantillaDesktop(unittest.TestCase):
    def setUp(self):
        self.texto = installer.DESKTOP_TEMPLATE.read_text(encoding="utf-8")

    def test_claves_obligatorias(self):
        for clave in ("Type=Application", "Name=", "Exec=@EXEC@", "Icon=cpuz", "Categories="):
            with self.subTest(clave=clave):
                self.assertIn(clave, self.texto)

    def test_categorias_validas(self):
        # HardwareSettings exige que también esté Settings; como esto no es una
        # aplicación de ajustes, no debe aparecer.
        self.assertIn("Categories=System;Monitor;", self.texto)
        self.assertNotIn("HardwareSettings", self.texto)

    def test_wm_class_coincide_con_el_id(self):
        self.assertIn(f"StartupWMClass={installer.APP_ID}", self.texto)


@unittest.skipUnless(HAS_QT_SVG, "hace falta PySide6.QtSvg")
class TestInstalacion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def test_el_svg_del_paquete_existe_y_es_valido(self):
        from PySide6.QtSvg import QSvgRenderer

        self.assertTrue(installer.SVG.exists(), installer.SVG)
        self.assertTrue(QSvgRenderer(str(installer.SVG)).isValid())

    def test_instala_todos_los_tamanos(self):
        installer.render_icons()
        for size in installer.SIZES:
            with self.subTest(size=size):
                destino = installer.icon_path(size)
                self.assertTrue(destino.exists(), destino)
                self.assertGreater(destino.stat().st_size, 0)
        self.assertTrue(installer.scalable_path().exists())

    def test_los_png_salen_del_tamano_pedido(self):
        from PySide6.QtGui import QImage

        installer.render_icons()
        for size in (16, 48, 256):
            imagen = QImage(str(installer.icon_path(size)))
            self.assertEqual((imagen.width(), imagen.height()), (size, size))

    def test_la_entrada_de_menu_queda_completa(self):
        entrada = installer.write_desktop()
        texto = entrada.read_text(encoding="utf-8")
        self.assertNotIn("@EXEC@", texto)
        self.assertNotIn("@PATH@", texto)
        self.assertTrue(texto.startswith("[Desktop Entry]"))
        self.assertTrue(os.access(entrada, os.X_OK))

    def test_desinstalar_lo_deja_limpio(self):
        installer.render_icons()
        installer.write_desktop()
        installer.uninstall(quiet=True)
        self.assertFalse(installer.desktop_path().exists())
        self.assertFalse(installer.scalable_path().exists())
        for size in installer.SIZES:
            self.assertFalse(installer.icon_path(size).exists())

    def test_sin_ejecutable_instalado_se_fija_el_directorio(self):
        with mock.patch.object(installer.shutil, "which", return_value=None):
            comando, directorio = installer.resolve_exec()
        self.assertIn("-m cpuz.ui.app", comando)
        self.assertTrue(pathlib.Path(directorio).is_dir())


@unittest.skipUnless(HAS_QT_SVG, "hace falta PySide6.QtSvg")
class TestIconoDeLaVentana(unittest.TestCase):
    def test_hay_icono_aunque_no_este_instalado_en_el_tema(self):
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
        from cpuz.ui import app as ui_app

        QApplication.instance() or QApplication([])
        with mock.patch.object(QIcon, "fromTheme", return_value=QIcon()):
            icono = ui_app.application_icon()
        self.assertFalse(icono.isNull(), "debería recurrir al SVG del paquete")


if __name__ == "__main__":
    unittest.main()
