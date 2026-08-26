"""Sistema: reparto de memoria, tiempo encendido y lectura de /proc."""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from cpuz.model import Memory, System
from cpuz.providers import system as provider
from cpuz.providers.base import Draft

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Valores reales de un equipo con 16 GB, en kibibytes.
MEMINFO = """MemTotal:       16180744 kB
MemFree:         1138988 kB
MemAvailable:    6745896 kB
Buffers:             312 kB
Cached:          9488712 kB
SwapCached:        12345 kB
SReclaimable:     187284 kB
Shmem:           3728208 kB
SwapTotal:       8388604 kB
SwapFree:        6356580 kB
"""


class TestRepartoDeMemoria(unittest.TestCase):
    def _memory(self) -> Memory:
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = pathlib.Path(carpeta) / "meminfo"
            ruta.write_text(MEMINFO, encoding="utf-8")
            with mock.patch.object(provider, "MEMINFO", str(ruta)):
                return provider.SystemState._memory()

    def test_lee_los_campos(self):
        memory = self._memory()
        self.assertEqual(memory.total_bytes, 16180744 * 1024)
        self.assertEqual(memory.available_bytes, 6745896 * 1024)
        self.assertEqual(memory.reclaimable_bytes, 187284 * 1024)

    def test_usada_es_la_definicion_de_free(self):
        # `free` calcula la usada como total menos disponible.
        memory = self._memory()
        self.assertEqual(memory.used_bytes, (16180744 - 6745896) * 1024)

    def test_la_cache_recuperable_descuenta_la_compartida(self):
        memory = self._memory()
        self.assertEqual(memory.cache_bytes,
                         (9488712 + 187284 - 3728208) * 1024)

    def test_los_segmentos_de_la_barra_suman_el_total(self):
        """Si no suman, la barra miente: o se pasa o deja hueco falso."""
        memory = self._memory()
        suma = (memory.apps_bytes + memory.cache_bytes
                + memory.buffers_bytes + memory.free_bytes)
        self.assertEqual(suma, memory.total_bytes)

    def test_aplicaciones_es_menor_que_usada(self):
        # La diferencia es la caché que el kernel no puede devolver.
        memory = self._memory()
        self.assertLess(memory.apps_bytes, memory.used_bytes)

    def test_porcentajes(self):
        memory = self._memory()
        self.assertAlmostEqual(memory.used_percent, 58.3, places=1)
        self.assertAlmostEqual(memory.swap_used_percent, 24.2, places=1)

    def test_sin_swap_no_hay_division_por_cero(self):
        self.assertEqual(Memory(total_bytes=1024).swap_used_percent, 0.0)

    def test_memoria_vacia_no_revienta(self):
        vacia = Memory()
        self.assertEqual(vacia.used_percent, 0.0)
        self.assertEqual(vacia.apps_bytes, 0)


class TestTiempoEncendido(unittest.TestCase):
    def setUp(self):
        try:
            from cpuz.ui.pages.system import format_uptime
        except ImportError:                             # pragma: no cover
            self.skipTest("PySide6 no está instalado")
        self.formato = format_uptime

    def test_formatos(self):
        self.assertEqual(self.formato(90), "1 min")
        self.assertEqual(self.formato(3 * 3600 + 7 * 60), "3 h 07 min")
        self.assertEqual(self.formato(2 * 86400 + 14 * 3600 + 7 * 60), "2 d 14 h 07 min")

    def test_cero(self):
        self.assertEqual(self.formato(0), "0 min")


class TestLecturaDeProc(unittest.TestCase):
    def test_los_hilos_salen_del_cuarto_campo_de_loadavg(self):
        with mock.patch.object(provider, "read_text", return_value="1.02 1.47 1.34 2/1688 235202"):
            self.assertEqual(provider.SystemState._threads(), 1688)

    def test_loadavg_ilegible_da_cero(self):
        with mock.patch.object(provider, "read_text", return_value="basura"):
            self.assertEqual(provider.SystemState._threads(), 0)
        with mock.patch.object(provider, "read_text", return_value=None):
            self.assertEqual(provider.SystemState._threads(), 0)

    def test_ficheros_abiertos(self):
        with mock.patch.object(provider, "read_text", return_value="23125\t0\t9223372036854775807"):
            self.assertEqual(provider.SystemState._open_files(), 23125)


class TestRecoleccionReal(unittest.TestCase):
    def test_identidad(self):
        draft = Draft()
        provider.SystemIdentity().collect(draft)
        self.assertIn("system", draft.capabilities)
        self.assertTrue(draft.system.kernel)
        self.assertTrue(draft.system.architecture)
        self.assertTrue(draft.system.hostname)

    @unittest.skipUnless(os.path.exists("/proc/meminfo"), "sin /proc/meminfo")
    def test_estado_y_sensores_de_memoria(self):
        draft = Draft()
        provider.SystemIdentity().collect(draft)
        provider.SystemState().collect(draft)

        self.assertGreater(draft.system.memory.total_bytes, 0)
        self.assertGreater(draft.system.processes, 0)
        self.assertGreater(draft.system.uptime_seconds, 0)

        claves = {s.key for s in draft.sensors}
        self.assertIn("memory/ram", claves)


@unittest.skipUnless(__import__("importlib").util.find_spec("PySide6"), "sin PySide6")
class TestColumnasDelArbol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _tree(self):
        from cpuz.collector import Collector
        from cpuz.ui import theme
        from cpuz.ui.widgets import SensorTree

        tree = SensorTree(theme.DARK)
        tree.rebuild(Collector().sample().sensor_tree())
        return tree

    def test_la_ultima_columna_absorbe_el_ancho_sobrante(self):
        """Es lo que mantiene las cifras pegadas al nombre en pantalla completa."""
        tree = self._tree()
        tree.resize(1800, 800)
        tree.show()
        self.app.processEvents()

        nombres = tree.columnWidth(0)
        cifras = sum(tree.columnWidth(c) for c in range(1, 1 + tree.VALUE_COLUMNS))
        hueco = tree.columnWidth(len(tree.COLUMNS) - 1)

        self.assertLess(nombres + cifras, 700, "los datos deben quedarse a la izquierda")
        self.assertGreater(hueco, 900, "el sobrante va a la columna vacía")

    def test_todas_las_columnas_visibles_se_pueden_arrastrar(self):
        from PySide6.QtWidgets import QHeaderView

        tree = self._tree()
        tree.show()
        self.app.processEvents()
        header = tree.header()
        for column in range(len(tree.COLUMNS) - 1):
            with self.subTest(columna=tree.COLUMNS[column]):
                self.assertEqual(header.sectionResizeMode(column),
                                 QHeaderView.ResizeMode.Interactive)
        # La última se queda con el sobrante y no se arrastra.
        self.assertEqual(header.sectionResizeMode(len(tree.COLUMNS) - 1),
                         QHeaderView.ResizeMode.Stretch)

    def test_los_anchos_guardados_se_aplican(self):
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        tree.set_column_widths((300, 90, 70, 70, 80))
        self.assertEqual(tree.column_widths(), (300, 90, 70, 70, 80))

    def test_restablecer_vuelve_a_los_automaticos(self):
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        tree.set_column_widths((400, 200, 200, 200, 200))
        tree.reset_column_widths()
        self.assertLess(tree.columnWidth(1), 200)

    def test_el_ancho_automatico_tiene_topes(self):
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        self.assertGreaterEqual(tree.columnWidth(0), 150)
        self.assertLessEqual(tree.columnWidth(0), 460)

    def test_un_ancho_absurdo_no_borra_los_nombres(self):
        """Los anchos guardados con otra densidad dejaban la columna tan
        estrecha que el sangrado y el icono se comían la etiqueta entera."""
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        tree.set_column_widths((20, 5, 5, 5, 5))
        self.assertGreaterEqual(tree.columnWidth(0), tree.NAME_FLOOR)

    def test_si_no_caben_las_columnas_el_arbol_se_desplaza(self):
        """Antes se recortaba la última columna en silencio."""
        from cpuz.ui import theme

        theme.set_density("spacious")
        tree = self._tree()
        tree.reset_column_widths()
        tree.resize(420, 600)
        tree.show()
        self.app.processEvents()
        self.assertGreater(sum(tree.column_widths()), 420)
        self.assertTrue(tree.horizontalScrollBar().isVisible())
        theme.set_density("normal")

    def test_la_cabecera_avisa_de_que_se_puede_arrastrar(self):
        """Qt cambia el cursor sobre el separador, pero eso solo se descubre
        por accidente: hace falta una marca visible."""
        from cpuz.ui.widgets import ResizableHeader

        tree = self._tree()
        tree.show()
        self.app.processEvents()
        header = tree.header()
        self.assertIsInstance(header, ResizableHeader)

        borde = tree.columnWidth(0)
        self.assertEqual(header._divider_at(borde), 0)
        self.assertEqual(header._divider_at(borde // 2), -1)

    def test_la_densidad_amplia_deja_mas_aire_que_la_compacta(self):
        from cpuz.ui import theme

        anchos = {}
        for densidad in ("spacious", "compact"):
            theme.set_density(densidad)
            tree = self._tree()
            tree.show()
            self.app.processEvents()
            anchos[densidad] = sum(tree.column_widths())
        theme.set_density("normal")
        self.assertGreater(anchos["spacious"], anchos["compact"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(__import__("importlib").util.find_spec("PySide6"), "sin PySide6")
class TestReutilizacionDeWidgets(unittest.TestCase):
    """Actualizar textos, no rehacer widgets.

    Recrear las etiquetas en cada muestreo dejaba miles vivas y hacía crecer
    la memoria medio megabyte por minuto. Estas pruebas fijan que las piezas
    que se refrescan a menudo reutilicen lo que ya existe.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_la_fila_de_insignias_reescribe_en_vez_de_recrear(self):
        from cpuz.ui.widgets import ChipRow

        fila = ChipRow()
        fila.set_chips(["Usada 6.5 GB", "Caché 8.1 GB", "Libre 1.2 GB"])
        originales = list(fila._widgets)

        fila.set_chips(["Usada 6.6 GB", "Caché 8.0 GB", "Libre 1.1 GB"])
        self.assertEqual(fila._widgets, originales, "no debe crear insignias nuevas")
        self.assertEqual(originales[0].text(), "Usada 6.6 GB")

    def test_cambiar_el_numero_de_insignias_sí_rehace(self):
        from cpuz.ui.widgets import ChipRow

        fila = ChipRow()
        fila.set_chips(["A", "B"])
        fila.set_chips(["A", "B", "C"])
        self.assertEqual(len(fila._widgets), 3)

    def test_la_tabla_reescribe_las_celdas(self):
        from cpuz.ui.widgets import Table

        tabla = Table(("Perfil", "Velocidad"), numeric=(False, True))
        tabla.set_rows([["JEDEC", "3200 MT/s"], ["XMP 1", "3600 MT/s"]])
        celdas = [list(fila) for fila in tabla._cells]

        tabla.set_rows([["JEDEC", "3201 MT/s"], ["XMP 1", "3600 MT/s"]])
        self.assertEqual([list(f) for f in tabla._cells], celdas)
        self.assertEqual(celdas[0][1].full_text(), "3201 MT/s")

    def test_cambiar_el_numero_de_filas_sí_rehace(self):
        from cpuz.ui.widgets import Table

        tabla = Table(("A", "B"))
        tabla.set_rows([["1", "2"]])
        tabla.set_rows([["1", "2"], ["3", "4"]])
        self.assertEqual(len(tabla._cells), 2)

    def test_muchos_refrescos_no_dejan_widgets_vivos(self):
        from PySide6.QtWidgets import QWidget
        from cpuz.collector import Collector
        from cpuz.settings import Preferences
        from cpuz.ui import theme
        from cpuz.ui.app import MainWindow

        theme.set_density("normal")
        ventana = MainWindow(Preferences(theme="dark"))
        ventana.show()
        self.addCleanup(ventana.close)
        for seccion in ("Monitor", "Memoria", "Sistema"):
            ventana.select_section(seccion)
        colector = Collector()
        colector.snapshot()

        for _ in range(5):
            ventana._on_sample(colector.snapshot())
        self.app.processEvents()
        antes = len(ventana.findChildren(QWidget))

        for _ in range(40):
            ventana._on_sample(colector.snapshot())
        self.app.processEvents()
        despues = len(ventana.findChildren(QWidget))

        self.assertLessEqual(despues - antes, 2,
                             f"cuarenta refrescos crearon {despues - antes} widgets")
