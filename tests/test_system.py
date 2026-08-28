"""Sistema: reparto de memoria, tiempo encendido y lectura de /proc."""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.model import Memory, System
from silux.providers import system as provider
from silux.providers.base import Draft

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
            from silux.ui.pages.system import format_uptime
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
        from silux.collector import Collector
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        tree = SensorTree(theme.DARK)
        tree.rebuild(Collector().sample().sensor_tree())
        return tree

    def test_las_cifras_se_quedan_pegadas_al_nombre(self):
        """En pantalla completa, estirar las columnas de datos mandaría las
        cifras a un palmo del sensor que nombran. El sobrante va al final."""
        tree = self._tree()
        tree.resize(1800, 800)
        tree.show()
        self.app.processEvents()

        nombres = tree.columnWidth(0)
        cifras = sum(tree.columnWidth(c) for c in range(1, 1 + tree.VALUE_COLUMNS))
        self.assertLess(nombres + cifras, 700, "los datos deben quedarse a la izquierda")

    def test_la_curva_se_lleva_parte_del_sobrante(self):
        """En una pantalla de 2560 quedaban mil píxeles vacíos a la derecha
        mientras la curva se apretaba en ciento veinte. Crece hasta su tope y
        el resto se queda en la columna vacía, que es lo que sigue empujando
        las cifras hacia el nombre."""
        tree = self._tree()
        tree.resize(1800, 800)
        tree.show()
        self.app.processEvents()

        self.assertEqual(tree.columnWidth(tree.TREND_COLUMN), tree.TREND_MAX)
        self.assertGreater(tree.columnWidth(len(tree.COLUMNS) - 1), 400)

    def test_en_una_ventana_estrecha_la_curva_no_se_come_nada(self):
        """Solo se reparte lo que sobra: si no sobra, se queda como estaba."""
        tree = self._tree()
        tree.resize(700, 800)
        tree.show()
        self.app.processEvents()
        self.assertLess(tree.columnWidth(tree.TREND_COLUMN), tree.TREND_WIDTH + 20)

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
        """Lo que el usuario arrastró manda, siempre que quepa lo que hay."""
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        anchos = (300, 200, 190, 180, 170, 130)
        tree.set_column_widths(anchos)
        self.assertEqual(tree.column_widths(), anchos)

    def test_unos_anchos_de_antes_de_la_curva_se_completan(self):
        """Los guardados por una versión con una columna menos vienen cortos.

        Sin completarlos, la columna nueva se queda con lo que Qt tuviera
        puesto —cero hasta que alguien la mida— y la curva no se ve. Es el caso
        de cualquiera que actualice sin borrar sus preferencias.
        """
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        tree.set_column_widths((268, 111, 64, 72, 73))
        self.assertEqual(tree.columnWidth(tree.TREND_COLUMN), tree.TREND_WIDTH)

    def test_las_cifras_no_bajan_de_su_respiro(self):
        """Cuatro columnas de números alineados a la derecha y en
        monoespaciada, sin hueco entre ellas, se leen como un número largo, y
        la marca de arrastre de la cabecera acaba encima del último dígito.
        Los anchos guardados se respetan hacia arriba, nunca por debajo del
        contenido más su respiro."""
        tree = self._tree()
        tree.show()
        self.app.processEvents()
        tree.set_column_widths((300, 41, 41, 41, 41))
        for columna in range(1, 1 + tree.VALUE_COLUMNS):
            with self.subTest(columna=tree.COLUMNS[columna]):
                self.assertGreater(tree.columnWidth(columna), 41 + 10)

    def test_el_respiro_de_las_cifras_sigue_a_la_densidad(self):
        """Quien pide densidad compacta la pide también entre las cifras."""
        from silux.ui import theme

        tree = self._tree()
        previo = theme.METRICS
        try:
            theme.set_density("compact")
            estrecho = tree.RESPIRO_CIFRAS
            theme.set_density("spacious")
            ancho = tree.RESPIRO_CIFRAS
        finally:
            theme.METRICS = previo
        self.assertLess(estrecho, ancho)

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
        from silux.ui import theme

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
        from silux.ui.widgets import ResizableHeader

        tree = self._tree()
        tree.show()
        self.app.processEvents()
        header = tree.header()
        self.assertIsInstance(header, ResizableHeader)

        borde = tree.columnWidth(0)
        self.assertEqual(header._divider_at(borde), 0)
        self.assertEqual(header._divider_at(borde // 2), -1)

    def test_la_densidad_amplia_deja_mas_aire_que_la_compacta(self):
        from silux.ui import theme

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
        from silux.ui.widgets import ChipRow

        fila = ChipRow()
        fila.set_chips(["Usada 6.5 GB", "Caché 8.1 GB", "Libre 1.2 GB"])
        originales = list(fila._widgets)

        fila.set_chips(["Usada 6.6 GB", "Caché 8.0 GB", "Libre 1.1 GB"])
        self.assertEqual(fila._widgets, originales, "no debe crear insignias nuevas")
        self.assertEqual(originales[0].text(), "Usada 6.6 GB")

    def test_cambiar_el_numero_de_insignias_sí_rehace(self):
        from silux.ui.widgets import ChipRow

        fila = ChipRow()
        fila.set_chips(["A", "B"])
        fila.set_chips(["A", "B", "C"])
        self.assertEqual(len(fila._widgets), 3)

    def test_la_tabla_reescribe_las_celdas(self):
        from silux.ui.widgets import Table

        tabla = Table(("Perfil", "Velocidad"), numeric=(False, True))
        tabla.set_rows([["JEDEC", "3200 MT/s"], ["XMP 1", "3600 MT/s"]])
        celdas = [list(fila) for fila in tabla._cells]

        tabla.set_rows([["JEDEC", "3201 MT/s"], ["XMP 1", "3600 MT/s"]])
        self.assertEqual([list(f) for f in tabla._cells], celdas)
        self.assertEqual(celdas[0][1].full_text(), "3201 MT/s")

    def test_cambiar_el_numero_de_filas_sí_rehace(self):
        from silux.ui.widgets import Table

        tabla = Table(("A", "B"))
        tabla.set_rows([["1", "2"]])
        tabla.set_rows([["1", "2"], ["3", "4"]])
        self.assertEqual(len(tabla._cells), 2)

    def test_muchos_refrescos_no_dejan_widgets_vivos(self):
        from PySide6.QtWidgets import QWidget
        from silux.collector import Collector
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.app import MainWindow

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


class TestBuscadorDeSensores(unittest.TestCase):
    """El filtro del árbol. Con noventa y nueve sensores en ocho aparatos,
    encontrar «el de la VRAM» era plegar y desplegar ramas hasta dar con él."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _tree(self):
        from silux.collector import Collector
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        arbol = SensorTree(theme.DARK)
        arbol.rebuild(Collector().sample().sensor_tree())
        arbol.show()
        self.app.processEvents()
        return arbol

    def test_sin_texto_no_esconde_nada(self):
        arbol = self._tree()
        completos = arbol.coincidencias()
        arbol.set_filter("")
        self.assertEqual(arbol.coincidencias(), completos)

    def test_filtrar_deja_menos_de_lo_que_habia(self):
        arbol = self._tree()
        completos = arbol.coincidencias()
        arbol.set_filter("temperatura")
        self.assertLess(arbol.coincidencias(), completos)
        self.assertGreater(arbol.coincidencias(), 0)

    def test_el_nombre_del_aparato_tambien_busca(self):
        """La gente pide «los del 9070» tanto como «temperatura»."""
        from silux.collector import Collector

        arbol = self._tree()
        aparatos = list(Collector().sample().sensor_tree())
        if not aparatos:
            self.skipTest("esta máquina no publica sensores")
        arbol.set_filter(aparatos[0].split()[0].lower())
        self.assertGreater(arbol.coincidencias(), 0)

    def test_lo_que_no_casa_no_deja_nada_a_la_vista(self):
        """Cero es un resultado, no un fallo: hay que poder decirlo."""
        arbol = self._tree()
        arbol.set_filter("zzzz-no-existe")
        self.assertEqual(arbol.coincidencias(), 0)

    def test_quitar_el_filtro_lo_devuelve_todo(self):
        arbol = self._tree()
        completos = arbol.coincidencias()
        arbol.set_filter("temperatura")
        arbol.set_filter("")
        self.assertEqual(arbol.coincidencias(), completos)

    def test_buscar_abre_las_ramas(self):
        """Filtrar y dejar el resultado escondido dentro de una rama plegada
        no encuentra nada."""
        arbol = self._tree()
        for indice in range(arbol.topLevelItemCount()):
            arbol.topLevelItem(indice).setExpanded(False)
        arbol.set_filter("temperatura")
        visibles = [arbol.topLevelItem(i) for i in range(arbol.topLevelItemCount())]
        conresultados = [a for a in visibles if not a.isHidden()]
        self.assertTrue(conresultados)
        self.assertTrue(all(a.isExpanded() for a in conresultados))


class TestRamasRecordadas(unittest.TestCase):
    """Lo que el usuario dejó plegado sobrevive a cerrar el programa."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _tree(self, plegadas=None):
        from silux.collector import Collector
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        arbol = SensorTree(theme.DARK)
        arbol.set_collapsed(plegadas)
        arbol.rebuild(Collector().sample().sensor_tree())
        return arbol

    def test_sin_nada_guardado_se_abren_todas(self):
        """El primer arranque enseña de qué va la página sin tener que
        tocarla."""
        arbol = self._tree(None)
        for indice in range(arbol.topLevelItemCount()):
            self.assertTrue(arbol.topLevelItem(indice).isExpanded())

    def test_una_rama_guardada_como_plegada_nace_plegada(self):
        arbol = self._tree(None)
        if not arbol.topLevelItemCount():
            self.skipTest("esta máquina no publica sensores")
        clave = f"::{arbol.topLevelItem(0).text(0)}"

        otro = self._tree([clave])
        self.assertFalse(otro.topLevelItem(0).isExpanded())
        # Y las demás siguen abiertas: se guarda lo plegado, no lo abierto.
        if otro.topLevelItemCount() > 1:
            self.assertTrue(otro.topLevelItem(1).isExpanded())

    def test_lo_plegado_se_puede_recuperar_para_guardarlo(self):
        arbol = self._tree(None)
        if not arbol.topLevelItemCount():
            self.skipTest("esta máquina no publica sensores")
        arbol.topLevelItem(0).setExpanded(False)
        clave = f"::{arbol.topLevelItem(0).text(0)}"
        self.assertIn(clave, arbol.collapsed())


class TestRepartoDeLaRejillaDeNucleos(unittest.TestCase):
    """Cuántas celdas por fila. Con lo que cabe a secas, dieciséis hilos
    salían doce arriba y cuatro abajo, y ocho salían seis y dos."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _matriz(self, hilos: int, ancho: int):
        from silux.ui import theme
        from silux.ui.widgets import CoreMatrix

        matriz = CoreMatrix(theme.DARK)
        matriz.set_cores([{"name": f"CPU {i}", "detail": "", "usage": 0.0}
                          for i in range(hilos)])
        matriz.resize(ancho, 400)
        return matriz

    def _reparto(self, hilos: int, ancho: int) -> list[int]:
        columnas = self._matriz(hilos, ancho)._columns()
        return [min(columnas, hilos - i * columnas)
                for i in range((hilos + columnas - 1) // columnas)]

    def test_dieciseis_hilos_no_dejan_una_fila_de_cuatro(self):
        """Donde caben doce salían doce arriba y cuatro abajo. Dos filas de
        ocho se leen de un vistazo como los dos hilos por núcleo que casi
        siempre son."""
        self.assertEqual(self._reparto(16, 2000), [8, 8])

    def test_ocho_hilos_no_salen_seis_y_dos(self):
        """Cuánto se baja depende de lo ancha que sea la ventana; lo que no
        vale es dejar dos celdas sueltas debajo de seis."""
        reparto = self._reparto(8, 1200)
        self.assertGreaterEqual(reparto[-1] * 2, reparto[0], reparto)

    def test_la_ultima_fila_nunca_queda_casi_vacia(self):
        for hilos in (4, 6, 8, 12, 16, 20, 24, 32):
            for ancho in (700, 1100, 1500, 2000):
                with self.subTest(hilos=hilos, ancho=ancho):
                    reparto = self._reparto(hilos, ancho)
                    if len(reparto) > 1:
                        self.assertGreaterEqual(reparto[-1] * 2, reparto[0],
                                                f"{hilos} en {ancho}: {reparto}")

    def test_no_se_estrecha_mas_de_la_cuenta(self):
        """Quitar columnas ensancha las celdas: el reparto perfecto no vale a
        cualquier precio."""
        import math

        matriz = self._matriz(16, 1500)
        caben = max(1, int((matriz.width() + matriz.GAP)
                           // (matriz._cell_w + matriz.GAP)))
        self.assertGreaterEqual(matriz._columns(), math.ceil(caben * 0.6))

    def test_si_caben_todos_van_en_una_fila(self):
        self.assertEqual(self._reparto(4, 2400), [4])

    def test_una_ventana_estrechisima_sigue_dando_una_columna(self):
        self.assertGreaterEqual(self._matriz(16, 60)._columns(), 1)


class TestOrdenDelArbolDeSensores(unittest.TestCase):
    """Los aparatos salen como se buscan, no como los numeró el kernel.

    Sin ordenarlos van en el orden de los directorios de hwmon, que es un
    número arbitrario y cambia entre arranques: el procesador podía salir
    debajo de la tarjeta de red.
    """

    def _snapshot(self, dispositivos):
        from silux.model import (CpuInfo, CpuType, Disk, Gpu, Sensor,
                                 SensorKind, Snapshot)

        sensores = tuple(
            Sensor(key=f"k{i}", chip="c", device=nombre, label="l",
                   kind=SensorKind.TEMPERATURE, value=40.0)
            for i, nombre in enumerate(dispositivos)
        )
        return Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g",
                                       brand="AMD Ryzen 7 5800X3D"),)),
            gpus=(Gpu(index=0, name="Radeon RX 9070 XT"),),
            disks=(Disk(name="nvme0n1", model="Samsung SSD 970"),),
            sensors=sensores,
        )

    def test_el_procesador_va_primero_y_la_placa_detras(self):
        crudo = ["Red (enp6s0)", "Samsung SSD 970", "Gigabyte X570",
                 "AMD Ryzen 7 5800X3D", "Radeon RX 9070 XT", "Memoria"]
        orden = list(self._snapshot(crudo).sensor_tree())
        self.assertEqual(orden[0], "AMD Ryzen 7 5800X3D")
        self.assertEqual(orden[1], "Gigabyte X570")

    def test_la_red_va_al_final_y_los_discos_antes(self):
        crudo = ["Red (enp6s0)", "Samsung SSD 970", "AMD Ryzen 7 5800X3D"]
        orden = list(self._snapshot(crudo).sensor_tree())
        self.assertLess(orden.index("Samsung SSD 970"), orden.index("Red (enp6s0)"))

    def test_el_orden_no_depende_de_como_lleguen(self):
        uno = ["AMD Ryzen 7 5800X3D", "Memoria", "Red (enp6s0)"]
        otro = list(reversed(uno))
        self.assertEqual(list(self._snapshot(uno).sensor_tree()),
                         list(self._snapshot(otro).sensor_tree()))

    def test_la_bateria_y_el_puerto_usbc_van_al_final(self):
        crudo = ["Batería", "Puerto USB-C", "AMD Ryzen 7 5800X3D", "Memoria"]
        orden = list(self._snapshot(crudo).sensor_tree())
        self.assertEqual(orden[-2:], ["Batería", "Puerto USB-C"])


class TestQueLasCifrasQuepan(unittest.TestCase):
    """La columna se ensancha para lo que de verdad lleva escrito.

    Los relojes de núcleo salían como «4374.4 …»: la medida contaba el respiro
    entre columnas pero no el relleno de la celda, que va a los dos lados.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _tree(self):
        from silux.collector import Collector
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        arbol = SensorTree(theme.DARK)
        arbol.rebuild(Collector().sample().sensor_tree())
        arbol.resize(1800, 900)
        arbol.show()
        self.app.processEvents()
        return arbol

    def test_una_cifra_larga_ensancha_su_columna(self):
        from PySide6.QtGui import QFontMetrics

        from silux.ui import theme

        arbol = self._tree()
        clave = next(k for k in arbol._rows if not k.startswith("::"))
        texto = "4374.4 MHz"
        arbol.update_row(clave, [texto, "", "", ""])

        necesario = (QFontMetrics(arbol._value_font).horizontalAdvance(texto)
                     + theme.RELLENO_DE_CELDA * 2)
        self.assertGreaterEqual(arbol.columnWidth(1), necesario)

    def test_el_relleno_de_la_hoja_de_estilos_es_el_que_se_mide(self):
        """Escrito en dos sitios, subirlo en uno dejó las cifras cortadas."""
        from silux.ui import theme

        hoja = theme.stylesheet(theme.DARK)
        self.assertIn(f"{theme.RELLENO_DE_CELDA}px", hoja)


class TestEtiquetasRepetidas(unittest.TestCase):
    """Una placa Gigabyte publica sus temperaturas por el Super I/O y otra vez
    por su interfaz WMI, y las dos se llaman «Temperatura 1»."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _arbol_con(self, sensores):
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        arbol = SensorTree(theme.DARK)
        arbol.rebuild({"Placa": {"Temperaturas": tuple(sensores)}})
        return arbol

    def _sensor(self, chip, label, valor=40.0):
        from silux.model import Sensor, SensorKind

        return Sensor(key=f"{chip}/{label}", chip=chip, device="Placa",
                      label=label, kind=SensorKind.TEMPERATURE, value=valor)

    def _nombres(self, arbol):
        categoria = arbol.topLevelItem(0).child(0)
        return [categoria.child(i).text(0) for i in range(categoria.childCount())]

    def test_las_repetidas_dicen_de_qué_chip_son(self):
        arbol = self._arbol_con([self._sensor("it8688", "Temperatura 1"),
                                 self._sensor("gigabyte_wmi", "Temperatura 1")])
        self.assertEqual(self._nombres(arbol),
                         ["Temperatura 1 (it8688)",
                          "Temperatura 1 (gigabyte_wmi)"])

    def test_las_que_no_se_repiten_se_quedan_como_estaban(self):
        """El chip entre paréntesis en todas sería ruido."""
        arbol = self._arbol_con([self._sensor("it8688", "Temperatura 1"),
                                 self._sensor("it8688", "Temperatura 2")])
        self.assertEqual(self._nombres(arbol), ["Temperatura 1", "Temperatura 2"])


class TestElColorDeLasCeldas(unittest.TestCase):
    """Que una celda pida un color no significa que se pinte.

    Una hoja de estilos que declara `color` para `QTreeWidget::item` pisa el
    que cada celda pide por su cuenta, en silencio y sin error. Con él puesto
    no llegaba a la pantalla ni el rojo de un sensor pasado de vueltas ni el
    ámbar del que se está acercando: el árbol salía entero del mismo gris, y
    el fallo llevaba ahí desde que existen los avisos.

    Se comprueba en la hoja de estilos y no mirando píxeles: el árbol
    renderizado por su cuenta, fuera de la ventana, no se pinta como dentro de
    ella, así que una prueba de píxeles diría cosas que no pasan de verdad.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_la_hoja_de_estilos_no_declara_el_color_de_las_celdas(self):
        import re as _re

        from silux.ui import theme

        for paleta in (theme.DARK, theme.LIGHT):
            with self.subTest(tema=paleta.name if hasattr(paleta, "name") else "?"):
                bloque = _re.search(r"QTreeWidget::item \{(.*?)\}",
                                    theme.stylesheet(paleta), _re.S)
                self.assertIsNotNone(bloque)
                self.assertNotIn("color:", bloque.group(1))

    def _arbol(self):
        from silux.model import Sensor, SensorKind
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        arbol = SensorTree(theme.DARK)
        sensor = Sensor(key="t", chip="k", device="CPU", label="Tctl",
                        kind=SensorKind.TEMPERATURE, value=50.0)
        arbol.rebuild({"CPU": {"Temperaturas": [sensor]}})
        return arbol

    def _color(self, arbol, columna):
        return arbol._rows["t"].foreground(columna).color().name()

    def test_acercarse_al_umbral_cambia_el_color_de_la_celda(self):
        arbol = self._arbol()
        arbol.update_row("t", ["50.0 °C", "", "", ""], heat=0.0)
        frio = self._color(arbol, 1)
        arbol.update_row("t", ["80.9 °C", "", "", ""], heat=0.41)
        self.assertNotEqual(self._color(arbol, 1), frio)

    def test_el_maximo_se_tiñe_con_el_suyo_y_no_con_el_de_ahora(self):
        """Quien lanza una prueba de dos minutos mira después, con el actual
        ya frío: lo que sobrevive al pico es el máximo."""
        arbol = self._arbol()
        arbol.update_row("t", ["50.0 °C", "", "82.9", ""], heat=0.0, heat_max=0.47)
        self.assertNotEqual(self._color(arbol, 3), self._color(arbol, 1))

    def test_un_sensor_critico_pide_su_propio_color(self):
        from silux.ui import theme

        arbol = self._arbol()
        arbol.update_row("t", ["99.0 °C", "", "", ""], alarm="crítico")
        self.assertEqual(self._color(arbol, 1), theme.DARK.q("crit").name())
