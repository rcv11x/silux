"""Integración con el escritorio: icono y entrada de menú.

Se instala todo en un XDG_DATA_HOME temporal, y las órdenes que avisan al
escritorio no se lanzan: estos tests no tocan la configuración real ni la
sesión de quien los ejecuta.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from silux import desktop as installer  # noqa: E402
from tests import qt


def _hay_svg() -> bool:
    """Lo que dibuja los iconos: el complemento `qsvg` de Qt."""
    from PySide6.QtGui import QImageReader

    qt.app()
    return b"svg" in [bytes(f) for f in QImageReader.supportedImageFormats()]


HAS_SVG = _hay_svg()

APPIMAGE = "/home/ana/Aplicaciones/Silux x86_64.AppImage"
DEL_APPIMAGE = installer.current_launcher({"APPIMAGE": APPIMAGE})


def del_repositorio() -> installer.Launcher:
    return installer.current_launcher({})


class TestPlantillaDesktop(unittest.TestCase):
    def setUp(self):
        self.texto = installer.entry_text(DEL_APPIMAGE)

    def test_claves_obligatorias(self):
        for clave in ("Type=Application", "Name=Silux", "Exec=", "Icon=silux", "Categories="):
            with self.subTest(clave=clave):
                self.assertIn(clave, self.texto)

    def test_categorias_validas(self):
        # HardwareSettings exige que también esté Settings; como esto no es una
        # aplicación de ajustes, no debe aparecer.
        self.assertIn("Categories=System;Monitor;", self.texto)
        self.assertNotIn("HardwareSettings", self.texto)

    def test_icono_clase_y_archivo_dicen_lo_mismo(self):
        for lanzador in (DEL_APPIMAGE, del_repositorio()):
            with self.subTest(modo=lanzador.mode):
                texto = installer.entry_text(lanzador)
                self.assertIn(f"\nIcon={lanzador.app_id}\n", texto)
                self.assertIn(f"\nStartupWMClass={lanzador.app_id}\n", texto)
                self.assertEqual(installer.desktop_path(lanzador.app_id).stem, lanzador.app_id)

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "sin desktop-file-validate")
    def test_las_tres_pasan_el_validador(self):
        """El mismo que pasa `appimagetool` a la que va dentro del paquete."""
        with tempfile.TemporaryDirectory() as tmp:
            for lanzador in (DEL_APPIMAGE, del_repositorio(),
                             installer.Launcher("appimage", "silux", "Silux", "Silux", ("silux",))):
                ruta = pathlib.Path(tmp) / f"{lanzador.app_id}.desktop"
                ruta.write_text(installer.entry_text(lanzador))
                hecho = subprocess.run(["desktop-file-validate", str(ruta)],
                                       capture_output=True, text=True)
                self.assertEqual(hecho.returncode, 0, hecho.stdout + hecho.stderr)

    def test_sin_marcadores_por_rellenar(self):
        for lanzador in (DEL_APPIMAGE, del_repositorio()):
            self.assertNotIn("@", installer.entry_text(lanzador))


class TestDeDondeSeEjecuta(unittest.TestCase):
    """Cada forma de ejecutar silux tiene su entrada, y apunta a ella misma."""

    def test_desde_el_appimage_apunta_al_archivo_y_no_al_montaje(self):
        self.assertEqual(DEL_APPIMAGE.mode, "appimage")
        self.assertEqual(DEL_APPIMAGE.app_id, "silux")
        self.assertEqual(DEL_APPIMAGE.command, (APPIMAGE,))
        self.assertNotIn("Path=", installer.entry_text(DEL_APPIMAGE))

    def test_un_appimage_sin_su_ruta_no_se_puede_instalar(self):
        with mock.patch.object(installer.sys, "executable", "/tmp/.mount_SiluxAb12/usr/bin/python3"):
            lanzador = installer.current_launcher({})
        self.assertEqual(lanzador.mode, "appimage")
        self.assertEqual(lanzador.command, ())
        with self.assertRaises(installer.DesktopError):
            installer.write_desktop(lanzador)

    def test_desde_el_codigo_es_otra_entrada(self):
        lanzador = del_repositorio()
        self.assertEqual(lanzador.mode, "development")
        self.assertEqual(lanzador.app_id, "silux-dev")
        self.assertEqual(lanzador.name, "Silux (desarrollo)")
        self.assertEqual(lanzador.command[1:], ("-m", "silux.ui.app"))
        self.assertEqual(pathlib.Path(lanzador.working_dir), installer.ROOT)
        self.assertIn(f"\nPath={installer.ROOT}\n", installer.entry_text(lanzador))

    def test_desde_un_paquete_instalado_usa_su_ejecutable(self):
        with mock.patch.object(installer, "source_checkout", return_value=None), \
             mock.patch.object(installer.shutil, "which", return_value="/usr/bin/silux-gui"):
            lanzador = installer.current_launcher({})
        self.assertEqual((lanzador.mode, lanzador.app_id), ("package", "silux"))
        self.assertEqual(lanzador.command, ("/usr/bin/silux-gui",))


class TestLaOrden(unittest.TestCase):
    """`Exec=` con las reglas de comillas de la especificación."""

    def test_una_ruta_con_espacios_va_entre_comillas(self):
        self.assertEqual(installer.exec_line(("/home/ana/Mis apps/Silux.AppImage",)),
                         '"/home/ana/Mis apps/Silux.AppImage"')

    def test_una_ruta_normal_va_tal_cual(self):
        self.assertEqual(installer.exec_line(("/usr/bin/python3", "-m", "silux.ui.app")),
                         "/usr/bin/python3 -m silux.ui.app")

    def test_ida_y_vuelta(self):
        for orden in (
            ("/home/ana/Mis apps/Silux.AppImage",),
            ('/home/ana/"raro"/silux', "-m", "x"),
            ("/home/ana/$HOME/100%/silux",),
            ("/home/ana/con\\barra/silux",),
            ("/opt/silux/bin/silux-gui",),
        ):
            with self.subTest(orden=orden):
                self.assertEqual(installer.parse_exec(installer.exec_line(orden)), orden)

    def test_lee_la_que_escribe_otro_gestor(self):
        # Así las escribe AppManager, el gestor de AppImage de la oficina.
        self.assertEqual(installer.parse_exec('"/home/ana/AppImages/Silux" --no-sandbox %U'),
                         ("/home/ana/AppImages/Silux", "--no-sandbox"))


class _EnCasaFalsa(unittest.TestCase):
    def setUp(self):
        qt.app()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.casa = pathlib.Path(self._tmp.name)
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        # Sin tocar el escritorio de quien ejecuta los tests.
        sin_ordenes = mock.patch.object(installer, "refresh_caches")
        sin_ordenes.start()
        self.addCleanup(sin_ordenes.stop)

    def _escribir(self, relativa: str, texto: str = "x") -> pathlib.Path:
        ruta = self.casa / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto)
        return ruta


@unittest.skipUnless(HAS_SVG, "hace falta el complemento qsvg de Qt")
class TestInstalacion(_EnCasaFalsa):
    def test_el_svg_del_paquete_existe_y_se_lee(self):
        from PySide6.QtGui import QImage

        self.assertTrue(installer.SVG.exists(), installer.SVG)
        self.assertFalse(QImage(str(installer.SVG)).isNull())

    def test_instala_todos_los_tamanos(self):
        installer.render_icons()
        for size in installer.SIZES:
            with self.subTest(size=size):
                destino = installer.icon_path(size)
                self.assertTrue(destino.exists(), destino)
                self.assertGreater(destino.stat().st_size, 0)
        self.assertTrue(installer.scalable_path().exists())

    def test_los_png_salen_del_tamano_pedido_y_con_transparencia(self):
        from PySide6.QtGui import QImage

        installer.render_icons()
        for size in (16, 48, 256):
            imagen = QImage(str(installer.icon_path(size)))
            self.assertEqual((imagen.width(), imagen.height()), (size, size))
            self.assertEqual(imagen.pixelColor(0, 0).alpha(), 0)

    def test_la_entrada_de_menu_queda_completa(self):
        entrada = installer.write_desktop(DEL_APPIMAGE)
        texto = entrada.read_text(encoding="utf-8")
        self.assertNotIn("@", texto)
        self.assertTrue(texto.startswith("[Desktop Entry]"))
        self.assertTrue(os.access(entrada, os.X_OK))

    def test_desinstalar_lo_deja_limpio(self):
        installer.install(DEL_APPIMAGE)
        installer.uninstall(DEL_APPIMAGE)
        self.assertFalse(installer.desktop_path().exists())
        self.assertEqual(installer.icon_files("silux"), [])

    def test_la_del_appimage_y_la_del_codigo_conviven(self):
        """Quitar una no deja a la otra sin entrada ni icono."""
        installer.install(DEL_APPIMAGE)
        installer.install(del_repositorio())
        self.assertTrue(installer.desktop_path("silux").exists())
        self.assertTrue(installer.desktop_path("silux-dev").exists())
        installer.uninstall(del_repositorio())
        self.assertTrue(installer.desktop_path("silux").exists())
        self.assertTrue(installer.icon_path(48, "silux").exists())
        self.assertFalse(installer.icon_path(48, "silux-dev").exists())


@unittest.skipUnless(HAS_SVG, "hace falta el complemento qsvg de Qt")
class TestReinstalar(_EnCasaFalsa):
    """Reinstalar tiene que dejar lo mismo que instalar en limpio.

    En casa, con silux ya instalado de antes del cambio de logo, la barra de
    tareas seguía con el icono viejo; y en la oficina el menú conservaba la
    entrada de cuando el proyecto se llamaba cpuz, que no abre nada.
    """

    def test_quita_la_entrada_de_cuando_se_llamaba_cpuz(self):
        entrada = self._escribir("applications/cpuz.desktop",
                                 "[Desktop Entry]\nExec=/usr/bin/python3 -m cpuz.ui.app\n")
        iconos = [self._escribir(f"icons/hicolor/{t}/apps/cpuz.png") for t in ("16x16", "48x48")]
        iconos.append(self._escribir("icons/hicolor/scalable/apps/cpuz.svg"))
        installer.install(DEL_APPIMAGE)
        for ruta in (entrada, *iconos):
            self.assertFalse(ruta.exists(), ruta)

    def test_un_cpuz_que_no_es_nuestro_no_se_toca(self):
        ajena = self._escribir("applications/cpuz.desktop",
                               "[Desktop Entry]\nExec=wine cpuz_x64.exe\n")
        icono = self._escribir("icons/hicolor/48x48/apps/cpuz.png")
        installer.install(DEL_APPIMAGE)
        self.assertTrue(ajena.exists())
        self.assertTrue(icono.exists())

    def test_no_queda_ningun_tamano_de_la_version_anterior(self):
        viejo = self._escribir("icons/hicolor/1024x1024/apps/silux.png")
        installer.install(DEL_APPIMAGE)
        self.assertFalse(viejo.exists(), "un tamaño que ya no se genera se queda con el logo viejo")

    def test_los_iconos_son_archivos_nuevos_y_no_reescritos(self):
        """Con un enlace duro al viejo, y no comparando números de inodo: el
        sistema de archivos puede dar al nuevo el número que quedó libre (en
        el runner del CI pasó). Con el enlace vivo, ese inodo no se libera."""
        installer.install(DEL_APPIMAGE)
        viejo = self.casa / "icono-viejo.png"
        os.link(installer.icon_path(48), viejo)
        installer.install(DEL_APPIMAGE)
        self.assertFalse(os.path.samefile(installer.icon_path(48), viejo))

    def test_desinstalar_quita_tambien_lo_viejo(self):
        viejo = self._escribir("icons/hicolor/1024x1024/apps/silux.png")
        cpuz = self._escribir("applications/cpuz.desktop", "Exec=python3 -m cpuz.ui.app\n")
        installer.install(DEL_APPIMAGE)
        self._escribir("icons/hicolor/1024x1024/apps/silux.png")
        installer.uninstall(DEL_APPIMAGE)
        self.assertFalse(viejo.exists())
        self.assertFalse(cpuz.exists())

    def test_desde_el_codigo_quita_la_entrada_que_escribia_antes(self):
        """Antes el repositorio se instalaba como `silux.desktop`."""
        vieja = self._escribir("applications/silux.desktop",
                               "[Desktop Entry]\nExec=/usr/bin/python3 -m silux.ui.app\n"
                               "Path=/home/ana/silux\nIcon=silux\n")
        icono = self._escribir("icons/hicolor/48x48/apps/silux.png")
        installer.install(del_repositorio())
        self.assertFalse(vieja.exists())
        self.assertFalse(icono.exists())
        self.assertTrue(installer.desktop_path("silux-dev").exists())

    def test_desde_el_codigo_no_toca_la_del_appimage(self):
        installer.install(DEL_APPIMAGE)
        installer.install(del_repositorio())
        self.assertIn(APPIMAGE, installer.desktop_path("silux").read_text())


@unittest.skipUnless(HAS_SVG, "hace falta el complemento qsvg de Qt")
class TestElEstado(_EnCasaFalsa):
    """Lo que enseña Ajustes: qué hay instalado y qué botón toca."""

    def setUp(self):
        super().setUp()
        config = self.casa / "config"
        config.mkdir()
        (config / "user-dirs.dirs").write_text(f'XDG_DESKTOP_DIR="{self.casa}/Escritorio"\n')
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)})
        patch.start()
        self.addCleanup(patch.stop)

    def _estado(self, lanzador=DEL_APPIMAGE):
        return installer.status(lanzador).state

    def _cambiar_exec(self, orden):
        entrada = installer.desktop_path()
        texto = "\n".join(f"Exec={orden}" if l.startswith("Exec=") else l
                          for l in entrada.read_text().splitlines()) + "\n"
        entrada.write_text(texto)

    def test_sin_instalar(self):
        self.assertEqual(self._estado(), "missing")

    def test_recien_instalado_esta_al_dia(self):
        installer.install(DEL_APPIMAGE)
        self.assertEqual(self._estado(), "current")

    def test_desde_el_codigo_dice_donde_esta_el_repositorio(self):
        lanzador = del_repositorio()
        installer.install(lanzador)
        estado = installer.status(lanzador)
        self.assertEqual(estado.state, "current")
        self.assertEqual(pathlib.Path(estado.target), installer.ROOT)

    def test_un_appimage_que_no_dice_donde_esta(self):
        lanzador = installer.Launcher("appimage", "silux", "Silux", "Silux", ())
        self.assertEqual(self._estado(lanzador), "unsupported")

    def test_otra_copia_que_existe(self):
        installer.install(DEL_APPIMAGE)
        otra = self.casa / "Otra.AppImage"
        otra.write_text("")
        otra.chmod(0o755)
        self._cambiar_exec(str(otra))
        estado = installer.status(DEL_APPIMAGE)
        self.assertEqual((estado.state, estado.target), ("elsewhere", str(otra)))

    def test_una_copia_que_ya_no_existe(self):
        """Lo que se vio en casa: un acceso que no abre nada."""
        installer.install(DEL_APPIMAGE)
        self._cambiar_exec("/home/ana/AppImages/Silux-vieja.AppImage")
        self.assertEqual(self._estado(), "broken")

    def test_los_iconos_de_otra_version(self):
        installer.install(DEL_APPIMAGE)
        installer.scalable_path().write_text("<svg>el logo de antes</svg>")
        self.assertEqual(self._estado(), "outdated")

    def test_lo_que_dejo_una_version_vieja_tambien_cuenta(self):
        installer.install(DEL_APPIMAGE)
        self._escribir("applications/cpuz.desktop", "Exec=python3 -m cpuz.ui.app\n")
        self.assertEqual(self._estado(), "outdated")
        installer.install(DEL_APPIMAGE)
        self.assertEqual(self._estado(), "current")

    def test_el_acceso_del_escritorio(self):
        installer.install(DEL_APPIMAGE, on_desktop=True)
        acceso = self.casa / "Escritorio" / "silux.desktop"
        self.assertTrue(acceso.is_file())
        self.assertTrue(os.access(acceso, os.X_OK))
        self.assertTrue(installer.status(DEL_APPIMAGE).on_desktop)
        # Reinstalar sin decir nada lo conserva, y al día.
        installer.install(DEL_APPIMAGE)
        self.assertTrue(acceso.is_file())
        installer.install(DEL_APPIMAGE, on_desktop=False)
        self.assertFalse(acceso.exists())
        installer.install(DEL_APPIMAGE, on_desktop=True)
        installer.uninstall(DEL_APPIMAGE)
        self.assertFalse(acceso.exists())


class TestAvisoAlEscritorio(unittest.TestCase):
    def test_avisa_a_plasma_de_que_hay_iconos_nuevos(self):
        llamadas = []
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"XDG_DATA_HOME": tmp}), \
             mock.patch.object(installer.shutil, "which", side_effect=lambda orden: f"/usr/bin/{orden}"), \
             mock.patch.object(installer.subprocess, "run",
                               side_effect=lambda orden, **_k: llamadas.append(orden)):
            installer.refresh_caches()
        ordenes = [orden[0] for orden in llamadas]
        self.assertIn("kbuildsycoca6", ordenes)
        senal = [orden for orden in llamadas if orden[0] == "dbus-send"]
        self.assertEqual(len(senal), 1, ordenes)
        self.assertIn("/KIconLoader", senal[0])
        self.assertIn("org.kde.KIconLoader.iconChanged", senal[0])


class TestIconoDeLaVentana(unittest.TestCase):
    def test_hay_icono_aunque_no_este_instalado_en_el_tema(self):
        from PySide6.QtGui import QIcon
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



class TestTheAppImageFileIcon(unittest.TestCase):
    """The PNG the packager puts as `.DirIcon`: file managers read it for the
    AppImage file's own icon, and without it Dolphin showed a generic one."""

    def test_the_logo_at_256_px(self):
        import sys

        from PySide6.QtGui import QImage

        qt.app()
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
        import build_appimage

        with tempfile.TemporaryDirectory() as folder:
            png = installer.render_png(build_appimage.DIR_ICON_SIZE,
                                       pathlib.Path(folder) / "silux.png")
            self.assertEqual(build_appimage.png_size(png), (256, 256))
            image = QImage(str(png))
            # Something drawn, not a transparent square.
            self.assertTrue(any(image.pixelColor(x, y).alpha() > 0
                                for x in range(0, 256, 16) for y in range(0, 256, 16)))
            (pathlib.Path(folder) / "not.png").write_bytes(b"<svg/>")
            self.assertIsNone(build_appimage.png_size(pathlib.Path(folder) / "not.png"))


if __name__ == "__main__":
    unittest.main()
