"""Lanzar el ayudante desde dentro de un AppImage.

Un probador con Hyprland no conseguía elevar permisos: el botón devolvía
«Autorización cancelada o denegada» sin llegar a pedirle la contraseña. No era
su agente de polkit. Era que ejecutaba el AppImage, y desde ahí el ayudante no
se puede lanzar por dos motivos:

* El punto de montaje va con `nosuid`, y pkexec se niega a ejecutar nada de un
  sistema de archivos así. Deniega antes de preguntar, que es exactamente lo
  que se veía.
* El montaje es de FUSE y pertenece al usuario, así que root ni siquiera puede
  leer dentro. Aunque pkexec arrancara, no encontraría el ayudante.

Se prueba con el entorno simulado porque montar un AppImage de verdad dentro de
los tests exige FUSE, y la máquina que los ejecute no tiene por qué tenerlo.
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.privileged import client as mod
from silux.privileged.client import HelperUnavailable, PrivilegedClient


class TestDeteccion(unittest.TestCase):
    def test_fuera_de_un_appimage(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(mod.sys, "executable", "/usr/bin/python3"):
            self.assertFalse(PrivilegedClient().empaquetado())

    def test_por_la_variable_del_runtime(self):
        # El runtime de AppImage la exporta siempre.
        with mock.patch.dict(os.environ, {"APPIMAGE": "/home/x/silux.AppImage"}):
            self.assertTrue(PrivilegedClient().empaquetado())

    def test_por_la_ruta_del_interprete(self):
        # Por si alguien lo lanza de una forma que no exporte la variable.
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(mod.sys, "executable",
                               "/tmp/.mount_siluxAbC/usr/bin/python3"):
            self.assertTrue(PrivilegedClient().empaquetado())


class TestPreparacion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_sin_appimage_no_se_copia_nada(self):
        cliente = PrivilegedClient()
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: False)):
            interprete, ayudante = cliente._preparar()
        self.assertEqual(interprete, mod.sys.executable)
        self.assertEqual(ayudante, mod.HELPER)

    def test_con_appimage_se_usa_el_python_del_sistema(self):
        cliente = PrivilegedClient()
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: True)), \
             mock.patch.object(mod, "_cache_dir", lambda: self.cache), \
             mock.patch.object(mod, "SYSTEM_PYTHON", ("/usr/bin/python3",)):
            interprete, ayudante = cliente._preparar()
        self.assertEqual(interprete, "/usr/bin/python3")

    def test_el_ayudante_sale_del_montaje(self):
        cliente = PrivilegedClient()
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: True)), \
             mock.patch.object(mod, "_cache_dir", lambda: self.cache):
            _, ayudante = cliente._preparar()
        self.assertNotIn("/.mount_", str(ayudante))
        self.assertTrue(ayudante.is_file())
        # Y es el mismo ayudante, no uno recortado.
        self.assertEqual(ayudante.read_bytes(), mod.HELPER.read_bytes())

    def test_la_copia_se_rehace_en_cada_conexion(self):
        # Si el AppImage se actualiza, una copia vieja hablaría otro protocolo.
        cliente = PrivilegedClient()
        destino = self.cache / "helper.py"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("# versión antigua\n", encoding="utf-8")
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: True)), \
             mock.patch.object(mod, "_cache_dir", lambda: self.cache):
            _, ayudante = cliente._preparar()
        self.assertNotIn("versión antigua", ayudante.read_text(encoding="utf-8"))

    def test_la_copia_no_queda_legible_para_otros(self):
        cliente = PrivilegedClient()
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: True)), \
             mock.patch.object(mod, "_cache_dir", lambda: self.cache):
            _, ayudante = cliente._preparar()
        self.assertEqual(ayudante.stat().st_mode & 0o077, 0)

    def test_sin_python_del_sistema_se_explica(self):
        cliente = PrivilegedClient()
        with mock.patch.object(PrivilegedClient, "empaquetado", staticmethod(lambda: True)), \
             mock.patch.object(mod, "SYSTEM_PYTHON", ("/no/existe",)):
            with self.assertRaises(HelperUnavailable) as caso:
                cliente._preparar()
        self.assertIn("Python del sistema", str(caso.exception))


if __name__ == "__main__":
    unittest.main()
