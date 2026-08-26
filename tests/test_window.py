"""La ventana: adaptación al ancho, ajustes en caliente y persistencia.

Se ejecuta con la plataforma «offscreen» de Qt, así que no hace falta
pantalla ni sesión gráfica: vale igual en un portátil que en integración
continua.
"""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:                                   # pragma: no cover
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 no está instalado")
class TestVentana(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from silux.ui import theme

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        theme.set_density("normal")
        self.addCleanup(theme.set_density, "normal")

    def _window(self, **kwargs):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        window = MainWindow(Preferences(**kwargs).normalized())
        window.show()
        self.addCleanup(window.close)
        return window

    # -- adaptación al ancho ------------------------------------------------

    def test_barra_lateral_se_esconde_en_ventanas_estrechas(self):
        from silux.ui.app import NAV_HIDE_BELOW

        window = self._window(window_width=900, window_height=680)
        self.app.processEvents()
        self.assertTrue(window.nav_panel.isVisible())
        self.assertFalse(window._compact_nav.isVisible())

        window.resize(NAV_HIDE_BELOW - 60, 620)
        self.app.processEvents()
        self.assertFalse(window.nav_panel.isVisible())
        self.assertTrue(window._compact_nav.isVisible())

    def test_el_selector_compacto_ofrece_solo_secciones_reales(self):
        from silux.ui.app import SECTIONS

        window = self._window()
        self.app.processEvents()
        disponibles = [name for name, enabled in SECTIONS if enabled]
        self.assertEqual(
            [window._compact_nav.itemText(i) for i in range(window._compact_nav.count())],
            disponibles,
        )

    def test_el_selector_compacto_cambia_de_seccion(self):
        window = self._window(window_width=470, window_height=620)
        self.app.processEvents()
        # Se busca por nombre, no por posición: añadir secciones no debe
        # romper el test.
        window._compact_nav.setCurrentIndex(window._compact_nav.findText("Ajustes"))
        self.app.processEvents()
        self.assertIs(window.stack.currentWidget(), window.settings_page)

    def test_todas_las_secciones_activas_tienen_pagina(self):
        from silux.ui.app import SECTIONS

        window = self._window()
        activas = sum(1 for _, enabled in SECTIONS if enabled)
        self.assertEqual(window.stack.count(), activas)
        for row in range(window.nav.count()):
            item = window.nav.item(row)
            if item.flags():                            # solo las habilitadas
                window.nav.setCurrentRow(row)
                self.app.processEvents()
                self.assertIsNotNone(window.stack.currentWidget())

    # -- ajustes en caliente ------------------------------------------------

    def test_cambiar_el_intervalo_no_reconstruye_la_interfaz(self):
        from dataclasses import replace

        window = self._window(interval_s=1.0)
        pagina = window.cpu_page
        window._on_preferences(replace(window.prefs, interval_s=2.5))
        self.assertIs(window.cpu_page, pagina)
        self.assertEqual(window.sampler._interval_ms, 2500)

    def test_cambiar_la_densidad_reconstruye_y_aplica_metricas(self):
        from dataclasses import replace
        from silux.ui import theme

        window = self._window(density="normal")
        pagina = window.cpu_page
        self.assertEqual(theme.METRICS, theme.NORMAL)

        window._on_preferences(replace(window.prefs, density="compact"))
        self.app.processEvents()
        self.assertEqual(theme.METRICS, theme.COMPACT)
        self.assertIsNot(window.cpu_page, pagina)

    def test_cambiar_de_tema_cambia_la_paleta(self):
        from dataclasses import replace
        from silux.ui import theme

        window = self._window(theme="light")
        self.assertEqual(window._palette, theme.LIGHT)
        window._on_preferences(replace(window.prefs, theme="dark"))
        self.assertEqual(window._palette, theme.DARK)

    def test_las_preferencias_se_guardan_al_cambiarlas(self):
        from dataclasses import replace
        from silux import settings

        window = self._window()
        window._on_preferences(replace(window.prefs, temperature_unit="f", interval_s=3.0))
        recargado = settings.load()
        self.assertEqual(recargado.temperature_unit, "f")
        self.assertEqual(recargado.interval_s, 3.0)

    def test_el_tamano_de_ventana_se_recuerda_al_cerrar(self):
        from silux import settings

        window = self._window(window_width=900, window_height=680)
        window.resize(760, 540)
        self.app.processEvents()
        window.close()
        recargado = settings.load()
        self.assertEqual((recargado.window_width, recargado.window_height), (760, 540))

    # -- tema ---------------------------------------------------------------

    def test_los_iconos_de_flecha_se_generan_y_se_cachean(self):
        from silux.ui import theme

        primera = theme._arrow_icon(theme.DARK.muted, True)
        self.assertTrue(os.path.exists(primera))
        self.assertIs(theme._arrow_icon(theme.DARK.muted, True).__class__, str)
        self.assertEqual(theme._arrow_icon(theme.DARK.muted, True), primera)
        # Distinto color o sentido, distinto fichero.
        self.assertNotEqual(theme._arrow_icon(theme.DARK.accent, True), primera)
        self.assertNotEqual(theme._arrow_icon(theme.DARK.muted, False), primera)

    def test_apply_deja_estilo_paleta_y_hoja(self):
        from silux.ui import theme

        from PySide6.QtGui import QColor, QPalette

        palette = theme.apply(self.app, "dark", "compact")
        self.assertEqual(palette, theme.DARK)
        self.assertEqual(theme.METRICS, theme.COMPACT)
        self.assertIn("QFrame#Card", self.app.styleSheet())
        # La QPalette importa tanto como la hoja: es de donde Qt saca los
        # colores que dibuja por su cuenta (flechas, selección, cursor).
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window),
            QColor(theme.DARK.bg),
        )
        theme.apply(self.app, "light", "normal")
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window),
            QColor(theme.LIGHT.bg),
        )

    # -- datos --------------------------------------------------------------

    def test_una_muestra_real_llena_la_pagina(self):
        from silux.collector import Collector

        window = self._window()
        window._on_sample(Collector().sample())
        self.app.processEvents()
        self.assertNotEqual(window.cpu_page.title.text(), "Leyendo el procesador…")
        self.assertIn("núcleos", window.cpu_page.subtitle.text())

    def test_la_pagina_de_caches_se_llena(self):
        from silux.collector import Collector

        window = self._window()
        window._on_sample(Collector().sample())
        self.app.processEvents()
        page = window.caches_page
        self.assertIn("caché en total", page.total.text())
        self.assertGreater(page.table._rows, 0)

    def test_la_ventana_no_baja_del_suelo_de_su_densidad(self):
        from silux.ui import theme

        for densidad, metrics in (("normal", theme.NORMAL), ("compact", theme.COMPACT)):
            with self.subTest(densidad=densidad):
                theme.set_density(densidad)
                window = self._window(density=densidad)
                window.resize(10, 10)
                self.app.processEvents()
                self.assertGreaterEqual(window.width(), metrics.min_window_w)
                self.assertGreaterEqual(window.height(), metrics.min_window_h)

    def test_el_contenido_cabe_en_el_suelo_sin_recortarse(self):
        """Ninguna página debe pedir más ancho del que hay en el tamaño mínimo.

        Con la barra de desplazamiento horizontal desactivada, un contenido
        más ancho que el viewport no se desplaza: se recorta en silencio. Es
        el fallo que se veía al encoger la ventana, y por eso se comprueba
        página a página y en las dos densidades.
        """
        from silux.collector import Collector
        from silux.ui import theme

        muestra = Collector().sample()
        for densidad, metrics in (("normal", theme.NORMAL), ("compact", theme.COMPACT)):
            theme.set_density(densidad)
            window = self._window(density=densidad)
            window.resize(metrics.min_window_w, metrics.min_window_h)
            window._on_sample(muestra)
            self.app.processEvents()

            for nombre in ("cpu_page", "monitor_page", "caches_page"):
                page = getattr(window, nombre)
                with self.subTest(densidad=densidad, pagina=nombre):
                    self.assertLessEqual(
                        page.widget().minimumSizeHint().width(),
                        page.viewport().width(),
                    )

    def test_fahrenheit_cambia_la_unidad_de_la_ficha(self):
        from dataclasses import replace
        from silux.collector import Collector

        window = self._window(temperature_unit="c")
        window._on_sample(Collector().sample())
        self.assertEqual(window.monitor_page.tile_temp.unit.text(), "°C")

        window._on_preferences(replace(window.prefs, temperature_unit="f"))
        window._on_sample(Collector().sample())
        self.assertEqual(window.monitor_page.tile_temp.unit.text(), "°F")

    def test_la_identificacion_y_el_monitor_estan_separados(self):
        """La página de CPU dice qué hay; Sensores dice qué está haciendo.

        La separación se llevó hasta el final a petición del autor: CPU ya no
        tiene ni las cuatro cifras vivas que le quedaban. Todo lo que cambia
        —gráficas, matriz de núcleos, temperatura, consumo— vive en Sensores, y
        tenerlo en dos sitios solo obligaba a mirar cuál de los dos iba primero.
        """
        window = self._window()
        for vivo in ("tile_temp", "cores"):
            self.assertTrue(hasattr(window.monitor_page, vivo))
            self.assertFalse(hasattr(window.cpu_page, vivo))
        for cifra in ("stat_temp", "stat_freq", "stat_usage", "stat_power"):
            self.assertFalse(hasattr(window.cpu_page, cifra))

    def test_los_extremos_sobreviven_a_un_cambio_de_tema(self):
        """Perder mínimos y máximos por cambiar de tema sería inaceptable."""
        from dataclasses import replace
        from silux.collector import Collector

        window = self._window(theme="light")
        window._on_sample(Collector().sample())
        window._on_sample(Collector().sample())
        seguidos = len(window._tracker)
        self.assertGreater(seguidos, 0)

        window._on_preferences(replace(window.prefs, theme="dark"))
        self.app.processEvents()
        self.assertIs(window.monitor_page._tracker, window._tracker)
        self.assertEqual(len(window._tracker), seguidos)


if __name__ == "__main__":
    unittest.main()
