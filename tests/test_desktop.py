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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import PySide6.QtSvg  # noqa: F401
    HAS_QT_SVG = True
except ImportError:                                     # pragma: no cover
    HAS_QT_SVG = False

from silux import desktop as installer  # noqa: E402
from tests import qt


class TestPlantillaDesktop(unittest.TestCase):
    def setUp(self):
        self.texto = installer.DESKTOP_TEMPLATE

    def test_claves_obligatorias(self):
        for clave in ("Type=Application", "Name=", "Exec=@EXEC@", "Icon=silux", "Categories="):
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
        # Antes de que el instalador cree su QGuiApplication: en un proceso
        # solo cabe una, y los tests de interfaz que vengan detrás necesitan
        # que sea la de widgets. Con esta ya creada, el instalador la reutiliza.
        qt.app()
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
        installer.uninstall()
        self.assertFalse(installer.desktop_path().exists())
        self.assertFalse(installer.scalable_path().exists())
        for size in installer.SIZES:
            self.assertFalse(installer.icon_path(size).exists())

    def test_sin_ejecutable_instalado_se_fija_el_directorio(self):
        with mock.patch.object(installer.shutil, "which", return_value=None):
            comando, directorio = installer.resolve_exec()
        self.assertIn("-m silux.ui.app", comando)
        self.assertTrue(pathlib.Path(directorio).is_dir())


@unittest.skipUnless(HAS_QT_SVG, "hace falta PySide6.QtSvg")
class TestReinstalar(unittest.TestCase):
    """Reinstalar tiene que dejar lo mismo que instalar en limpio.

    En casa, con silux ya instalado de antes del cambio de logo, la barra de
    tareas seguía con el icono viejo; y en la oficina el menú conservaba la
    entrada de cuando el proyecto se llamaba cpuz, que no abre nada.
    """

    def setUp(self):
        qt.app()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.casa = pathlib.Path(self._tmp.name)
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        # Sin tocar el escritorio de quien ejecuta los tests.
        sin_ordenes = mock.patch.object(installer.shutil, "which", return_value=None)
        sin_ordenes.start()
        self.addCleanup(sin_ordenes.stop)

    def _escribir(self, relativa: str, texto: str = "x") -> pathlib.Path:
        ruta = self.casa / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto)
        return ruta

    def test_quita_la_entrada_de_cuando_se_llamaba_cpuz(self):
        entrada = self._escribir("applications/cpuz.desktop",
                                 "[Desktop Entry]\nExec=/usr/bin/python3 -m cpuz.ui.app\n")
        iconos = [self._escribir(f"icons/hicolor/{t}/apps/cpuz.png") for t in ("16x16", "48x48")]
        iconos.append(self._escribir("icons/hicolor/scalable/apps/cpuz.svg"))
        installer.install()
        for ruta in (entrada, *iconos):
            self.assertFalse(ruta.exists(), ruta)

    def test_un_cpuz_que_no_es_nuestro_no_se_toca(self):
        ajena = self._escribir("applications/cpuz.desktop",
                               "[Desktop Entry]\nExec=wine cpuz_x64.exe\n")
        icono = self._escribir("icons/hicolor/48x48/apps/cpuz.png")
        installer.install()
        self.assertTrue(ajena.exists())
        self.assertTrue(icono.exists())

    def test_no_queda_ningun_tamano_de_la_version_anterior(self):
        viejo = self._escribir("icons/hicolor/1024x1024/apps/silux.png")
        installer.install()
        self.assertFalse(viejo.exists(), "un tamaño que ya no se genera se queda con el logo viejo")

    def test_los_iconos_son_archivos_nuevos_y_no_reescritos(self):
        installer.install()
        antes = installer.icon_path(48).stat().st_ino
        installer.install()
        self.assertNotEqual(antes, installer.icon_path(48).stat().st_ino)

    def test_avisa_a_plasma_de_que_hay_iconos_nuevos(self):
        llamadas = []
        with mock.patch.object(installer.shutil, "which", side_effect=lambda orden: f"/usr/bin/{orden}"), \
             mock.patch.object(installer.subprocess, "run",
                               side_effect=lambda orden, **_k: llamadas.append(orden)):
            installer.install()
        ordenes = [orden[0] for orden in llamadas]
        self.assertIn("kbuildsycoca6", ordenes)
        senal = [orden for orden in llamadas if orden[0] == "dbus-send"]
        self.assertEqual(len(senal), 1, ordenes)
        self.assertIn("/KIconLoader", senal[0])
        self.assertIn("org.kde.KIconLoader.iconChanged", senal[0])

    def test_desinstalar_quita_tambien_lo_viejo(self):
        viejo = self._escribir("icons/hicolor/1024x1024/apps/silux.png")
        cpuz = self._escribir("applications/cpuz.desktop", "Exec=python3 -m cpuz.ui.app\n")
        installer.install()
        self._escribir("icons/hicolor/1024x1024/apps/silux.png")
        installer.uninstall()
        self.assertFalse(viejo.exists())
        self.assertFalse(cpuz.exists())


@unittest.skipUnless(HAS_QT_SVG, "hace falta PySide6.QtSvg")
class TestIconoDeLaVentana(unittest.TestCase):
    def test_hay_icono_aunque_no_este_instalado_en_el_tema(self):
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
        from silux.ui import app as ui_app

        qt.app()
        with mock.patch.object(QIcon, "fromTheme", return_value=QIcon()):
            icono = ui_app.application_icon()
        self.assertFalse(icono.isNull(), "debería recurrir al SVG del paquete")

    def test_el_icono_del_tema_no_gana_al_del_paquete(self):
        """Un icono «silux» instalado en el tema puede ser de una versión vieja.

        En casa la barra de tareas de Plasma enseñaba el logo anterior con la
        aplicación nueva abierta: la ventana se presentaba con el icono que
        encontraba en el tema, el de la última instalación, mientras la barra
        lateral pintaba el del paquete. El del paquete es siempre el de esta
        versión.
        """
        from PySide6.QtGui import QIcon, QPixmap
        from silux.ui import app as ui_app

        qt.app()
        viejo = QPixmap(16, 16)
        viejo.fill()
        with mock.patch.object(QIcon, "fromTheme", return_value=QIcon(viejo)) as tema:
            icono = ui_app.application_icon()
        tema.assert_not_called()
        self.assertFalse(icono.isNull())


if __name__ == "__main__":
    unittest.main()
