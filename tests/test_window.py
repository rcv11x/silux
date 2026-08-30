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
        # Lo que enseña el selector es el nombre traducido; lo que hay en
        # SECTIONS son las claves.
        from silux.i18n import _

        disponibles = [_(name) for name, enabled in SECTIONS if enabled]
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

        # Escala explícita: las métricas de theme.NORMAL son las de la letra
        # sin escalar, y la de serie ya no lo está.
        window = self._window(density="normal", font_scale="normal")
        pagina = window.cpu_page
        self.assertEqual(theme.METRICS, theme.NORMAL)

        window._on_preferences(replace(window.prefs, density="compact"))
        self.app.processEvents()
        self.assertEqual(theme.METRICS, theme.COMPACT)
        self.assertIsNot(window.cpu_page, pagina)

    def test_cambiar_de_tema_cambia_la_paleta(self):
        from dataclasses import replace
        from silux.ui import theme

        # Contra la paleta ya teñida con el acento: comparar con theme.LIGHT
        # a secas solo funcionaba mientras el color de serie fuese el mismo
        # con el que están escritas las paletas base.
        window = self._window(theme="light")
        acento = window.prefs.accent
        self.assertEqual(window._palette,
                         theme.tinted(theme.LIGHT, acento, dark=False))
        window._on_preferences(replace(window.prefs, theme="dark"))
        self.assertEqual(window._palette,
                         theme.tinted(theme.DARK, acento, dark=True))

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
            theme.set_density(densidad, "normal")
            window = self._window(density=densidad, font_scale="normal")
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
        self.assertEqual(window.cpu_page.live.tile_temp.unit.text(), "°C")

        window._on_preferences(replace(window.prefs, temperature_unit="f"))
        window._on_sample(Collector().sample())
        self.assertEqual(window.cpu_page.live.tile_temp.unit.text(), "°F")

    def test_lo_que_hace_el_procesador_esta_en_la_pagina_del_procesador(self):
        """Las cifras vivas y la rejilla de núcleos viven en CPU, no en Sensores.

        Estuvieron en Sensores una temporada, con la idea de separar «qué hay»
        de «qué está haciendo». En la práctica no funcionó: quien abre la ficha
        del procesador quiere ver a cuánto va, y en Sensores ocupaban media
        pantalla dejando el árbol —que es lo propio de esa página— en una
        rendija.

        Sensores se queda con lo suyo: todos los sensores del equipo, con sus
        mínimos y máximos, que es lo que no cabe en ninguna otra parte.
        """
        window = self._window()
        for vivo in ("tile_temp", "tile_freq", "cores"):
            self.assertTrue(hasattr(window.cpu_page.live, vivo))
        for vivo in ("tile_temp", "cores"):
            self.assertFalse(hasattr(window.monitor_page, vivo),
                             f"{vivo} sigue en Sensores")
        self.assertTrue(hasattr(window.monitor_page, "tree"))

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


class TestLaSalidaParaLosDatosBloqueados(unittest.TestCase):
    """Decir que falta un dato por permisos y no ofrecer darlos.

    La barra de estado ya contaba «1 dato requiere permisos», y eso era todo:
    el único botón para darlos vivía dentro de Memoria, Gráficos y
    Almacenamiento. Un usuario con el consumo del procesador en blanco tenía el
    aviso delante y la salida en otra sección, que es la misma lección que ya
    estaba escrita para el aviso de Gráficos y que aquí faltaba por aplicar.

    Ahora el propio renglón es el botón, y la página de CPU lleva el suyo
    dentro del aviso.
    """

    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def _snapshot(self, con_nota):
        from silux.model import Need, Note, Snapshot

        notas = ()
        if con_nota:
            notas = (Note(path="cpu.power_w", need=Need.ROOT,
                          message="El consumo lo publica un registro del "
                                  "procesador que el kernel reserva al "
                                  "administrador.",
                          hint=""),)
        from silux.model import Board, Clocks, CpuInfo, CpuType, System

        # Con un tipo de núcleo: la página se planta antes de pintar los
        # avisos si no reconoce el procesador.
        cpu = CpuInfo(types=(CpuType(key="general", label="general",
                                     brand="AMD Ryzen 7 7445HS w/ Radeon 740M Graphics",
                                     cores=6, threads=12,
                                     clocks=Clocks(base_hz=3_200_000_000)),))
        return Snapshot(monotonic_ns=0, notes=notas, cpu=cpu,
                        board=Board(), system=System())

    def _window(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        window = MainWindow(Preferences().normalized())
        window.show()
        self.addCleanup(window.close)
        return window

    def test_sin_nada_bloqueado_no_hay_boton(self):
        window = self._window()
        window._on_sample(self._snapshot(False))
        self.app.processEvents()
        self.assertFalse(window._blocked.isVisible())

    def test_con_algo_bloqueado_sale_y_dice_cuantos(self):
        window = self._window()
        window._on_sample(self._snapshot(True))
        self.app.processEvents()
        self.assertTrue(window._blocked.isVisible())
        self.assertIn("1", window._blocked.text())

    def test_el_renglon_se_puede_pulsar_y_pide_los_permisos(self):
        """Lo que lo distingue del texto de antes."""
        window = self._window()
        window._on_sample(self._snapshot(True))
        self.app.processEvents()

        with mock.patch.object(window, "_on_elevation_requested") as pedir:
            window._blocked.clicked.disconnect()
            window._blocked.clicked.connect(pedir)
            window._blocked.click()
        pedir.assert_called_once()

    def test_la_pagina_de_cpu_puede_pedirlos_ella_sola(self):
        """Quien lee por qué falta el consumo es quien quiere arreglarlo."""
        window = self._window()
        self.assertTrue(hasattr(window.cpu_page, "elevation_requested"),
                        "la página de CPU no sabe pedir permisos")

    def test_el_aviso_de_cpu_trae_su_boton(self):
        from silux.model import Need

        window = self._window()
        window.cpu_page.apply(self._snapshot(True))
        self.app.processEvents()

        avisos = window.cpu_page._notices_host
        botones = []
        for indice in range(avisos.count()):
            widget = avisos.itemAt(indice).widget()
            if widget is not None and getattr(widget, "action_button", None):
                botones.append(widget.action_button)
        self.assertTrue(botones, "el aviso de permisos sale sin botón al lado")

    def test_los_avisos_salen_aunque_no_se_reconozca_el_procesador(self):
        """Que es cuando más falta hace decir por qué falta algo.

        La página se plantaba antes de pintarlos si `cpu.types` venía vacío, o
        sea justo en un equipo raro o en un ARM sin entrada en la base de
        datos: el usuario se quedaba mirando una pantalla vacía sin nada que
        le explicara qué había pasado.
        """
        from silux.model import Board, CpuInfo, Need, Note, Snapshot, System

        window = self._window()
        sin_cpu = Snapshot(
            monotonic_ns=0, cpu=CpuInfo(), board=Board(), system=System(),
            notes=(Note(path="cpu", need=Need.DATABASE,
                        message="Este procesador no está en la base de datos.",
                        hint=""),))
        window.cpu_page.apply(sin_cpu)
        self.app.processEvents()

        avisos = window.cpu_page._notices_host
        self.assertGreater(avisos.count(), 0,
                           "sin tipos de núcleo no se pinta ningún aviso")
