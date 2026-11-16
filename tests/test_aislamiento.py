"""La suite no escribe en la configuración ni en los datos de quien la ejecuta.

Dos módulos montaban la ventana sin aislar `XDG_CONFIG_HOME`, y la ventana
guarda sus preferencias al cerrarse: cada `unittest discover` reescribía el
`~/.config/silux/settings.json` de quien desarrolla con los valores por
defecto. Los que montan la página de Rendimiento, además, leían su historial
de pruebas real. Lo destapó la quinta auditoría al ver cambiar de fecha ese
archivo en mitad de una sesión de solo lectura.
"""

import os
import pathlib
import unittest

import tests
from tests import qt


class TestLaSuiteVaEnSuCaja(unittest.TestCase):

    def _caja(self) -> pathlib.Path:
        caja = getattr(tests, "CAJA", None)
        self.assertIsNotNone(caja, "tests/__init__.py no prepara ninguna caja")
        return pathlib.Path(caja)

    def test_preferencias_historial_y_cache_caen_dentro(self):
        from silux import history, registro, settings

        caja = self._caja()
        for nombre, ruta in (("preferencias", settings.config_dir()),
                             ("historial", history.history_path()),
                             ("registro", registro.carpeta()),
                             ("caché", pathlib.Path(os.environ.get("XDG_CACHE_HOME", "")))):
            with self.subTest(nombre=nombre):
                self.assertTrue(pathlib.Path(ruta).is_relative_to(caja),
                                f"{nombre} va a {ruta}")

    @unittest.skipUnless(__import__("importlib").util.find_spec("PySide6"), "sin PySide6")
    def test_cerrar_la_ventana_no_toca_la_configuracion_de_casa(self):
        """El efecto, y no solo la variable: se abre y se cierra una ventana
        de verdad y se mira el archivo de la carpeta personal. Solo se lee su
        fecha; si no existe, que siga sin existir."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        de_casa = pathlib.Path.home() / ".config" / "silux" / "settings.json"
        antes = de_casa.stat().st_mtime_ns if de_casa.exists() else None

        qt.app()
        ventana = MainWindow(Preferences())
        ventana.close()

        despues = de_casa.stat().st_mtime_ns if de_casa.exists() else None
        self.assertEqual(antes, despues, f"la ventana ha escrito en {de_casa}")


if __name__ == "__main__":
    unittest.main()
