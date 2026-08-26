"""Preferencias: validación, persistencia y tolerancia a ficheros rotos."""

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import settings


class TestPreferencias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def test_respeta_xdg_config_home(self):
        self.assertTrue(str(settings.config_path()).startswith(self._tmp.name))
        self.assertTrue(str(settings.config_path()).endswith("silux/settings.json"))

    def test_normaliza_valores_imposibles(self):
        p = settings.Preferences(
            interval_s=999, theme="marciano", temperature_unit="kelvin",
            density="gigante", window_width=1, window_height=99999,
        ).normalized()
        self.assertEqual(p.interval_s, 10.0)
        self.assertEqual(p.theme, "system")
        self.assertEqual(p.temperature_unit, "c")
        self.assertEqual(p.density, "normal")
        self.assertEqual(p.window_width, 380)
        self.assertEqual(p.window_height, 2160)

    def test_ida_y_vuelta(self):
        original = settings.Preferences(interval_s=2.5, theme="dark",
                                        temperature_unit="f", density="compact",
                                        show_all_features=True)
        self.assertTrue(settings.save(original))
        self.assertEqual(settings.load(), original.normalized())

    def test_fichero_corrupto_cae_a_los_valores_por_defecto(self):
        settings.config_dir().mkdir(parents=True, exist_ok=True)
        settings.config_path().write_text("{esto no es json", encoding="utf-8")
        self.assertEqual(settings.load(), settings.Preferences())

    def test_claves_desconocidas_se_ignoran(self):
        settings.config_dir().mkdir(parents=True, exist_ok=True)
        settings.config_path().write_text(
            json.dumps({"interval_s": 3.0, "una_opcion_del_futuro": True}), encoding="utf-8"
        )
        self.assertEqual(settings.load().interval_s, 3.0)

    def test_sin_fichero_devuelve_los_valores_por_defecto(self):
        self.assertEqual(settings.load(), settings.Preferences())

    def test_derivados(self):
        p = settings.Preferences(interval_s=1.5, temperature_unit="f")
        self.assertEqual(p.interval_ms, 1500)
        self.assertTrue(p.fahrenheit)

    def test_guardar_en_ruta_imposible_no_revienta(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/proc/no-escribible"}):
            self.assertFalse(settings.save(settings.Preferences()))


class TestRepartoDeColumnas(unittest.TestCase):
    """La aritmética del reparto adaptable, sin necesidad de Qt."""

    def setUp(self):
        try:
            from silux.ui.widgets import balanced_columns
        except ImportError:
            self.skipTest("PySide6 no está instalado")
        self.columnas = balanced_columns

    def test_reparto_exacto(self):
        self.assertEqual(self.columnas(4, 4), 4)
        self.assertEqual(self.columnas(12, 6), 6)

    def test_evita_dejar_una_huerfana(self):
        # 4 fichas en 3 columnas serían 3+1; 2+2 ocupa las mismas filas.
        self.assertEqual(self.columnas(4, 3), 2)

    def test_no_encoge_si_cuesta_filas(self):
        # 5 en 2 columnas son 3 filas; bajar a 1 serían 5. No compensa.
        self.assertEqual(self.columnas(5, 2), 2)
        self.assertEqual(self.columnas(5, 4), 4)

    def test_nunca_mas_columnas_que_elementos(self):
        self.assertEqual(self.columnas(2, 8), 2)

    def test_casos_degenerados(self):
        self.assertEqual(self.columnas(0, 4), 1)
        self.assertEqual(self.columnas(3, 0), 1)


if __name__ == "__main__":
    unittest.main()
