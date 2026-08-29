"""La portada: qué equipo es esto, en una pantalla.

El programa abría en la ficha del procesador, que responde a una pregunta que
nadie ha hecho todavía. Esta página contesta la primera: de qué equipo se
trata y si algo está caliente ahora mismo.
"""

import unittest

from PySide6.QtWidgets import QApplication

from silux import render
from silux.collector import Collector
from silux.settings import Preferences
from silux.ui import theme
from silux.ui.pages.home import HomePage


def _app():
    return QApplication.instance() or QApplication([])


class TestNombreCortoDeCpu(unittest.TestCase):
    """La cadena de marca trae coletillas que no distinguen un modelo de otro."""

    def test_quita_lo_que_no_dice_nada(self):
        for crudo, esperado in [
            ("AMD Ryzen 7 5800X3D 8-Core Processor", "AMD Ryzen 7 5800X3D"),
            ("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz", "Intel Core i5-10400"),
            ("Intel(R) Xeon(R) CPU E5-2650 v2 @ 2.60GHz", "Intel Xeon E5-2650 v2"),
            ("AMD Ryzen 7 7445HS w/ Radeon 740M Graphics", "AMD Ryzen 7 7445HS"),
        ]:
            self.assertEqual(render.cpu_short_name(crudo), esperado)

    def test_lo_que_ya_es_corto_no_se_toca(self):
        self.assertEqual(render.cpu_short_name("ARM Cortex-A76 r0p0"),
                         "ARM Cortex-A76 r0p0")

    def test_sin_marca_devuelve_el_guion(self):
        self.assertEqual(render.cpu_short_name(None), render.DASH)
        self.assertEqual(render.cpu_short_name(""), render.DASH)

    def test_nunca_deja_el_nombre_vacio(self):
        """Si al limpiar no queda nada, mejor la cadena original."""
        self.assertEqual(render.cpu_short_name("Processor"), "Processor")


class TestPagina(unittest.TestCase):
    def setUp(self):
        theme.set_density("normal", "normal")
        self.pagina = HomePage(theme.palette_for(_app(), "dark"),
                               Preferences(font_scale="normal").normalized())

    def test_pinta_este_equipo_sin_reventar(self):
        self.pagina.apply(Collector().sample())
        self.assertTrue(self.pagina.title.text())

    def test_las_cuatro_tarjetas_dicen_algo(self):
        self.pagina.apply(Collector().snapshot())
        for tarjeta in (self.pagina.cpu, self.pagina.gpu,
                        self.pagina.memoria, self.pagina.discos):
            self.assertTrue(tarjeta.nombre.text(),
                            f"{tarjeta._seccion} se ha quedado en blanco")

    def test_pulsar_una_tarjeta_pide_su_seccion(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        pedidas = []
        self.pagina.seccion_pedida.connect(pedidas.append)
        evento = QMouseEvent(QMouseEvent.Type.MouseButtonRelease,
                             QPoint(5, 5), Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.pagina.gpu.mouseReleaseEvent(evento)
        self.assertEqual(pedidas, ["Gráficos"])

    def test_un_equipo_sin_grafica_no_deja_la_tarjeta_muda(self):
        import dataclasses
        muestra = dataclasses.replace(Collector().snapshot(), gpus=())
        self.pagina.apply(muestra)
        self.assertIn("Sin gráfica", self.pagina.gpu.nombre.text())

    def test_ni_uno_sin_discos(self):
        import dataclasses
        muestra = dataclasses.replace(Collector().snapshot(), disks=())
        self.pagina.apply(muestra)
        self.assertIn("Sin unidades", self.pagina.discos.nombre.text())

    def test_repintar_muchas_veces_no_crea_widgets(self):
        """La regla de siempre: se reescribe el texto, no se rehace la tarjeta."""
        muestra = Collector().snapshot()
        self.pagina.apply(muestra)
        antes = len(self.pagina.findChildren(object))
        for _ in range(20):
            self.pagina.apply(muestra)
        self.assertEqual(len(self.pagina.findChildren(object)), antes)

    def tearDown(self):
        theme.set_density("normal", "normal")


if __name__ == "__main__":
    unittest.main()


class TestTarjetaDeGraficaEnLaPortada(unittest.TestCase):
    """La ficha de la gráfica tiene que decir algo, aunque falte casi todo.

    De una captura ajena: un portátil con una UHD Graphics G4 enseñaba el
    nombre de la tarjeta y debajo un guion, nada más. No era un fallo de
    lectura sino de qué se elige enseñar: en una Intel el uso y los vatios
    salen de contadores del kernel que piden permisos, y la temperatura no
    existe por ningún camino. Sin las tres, la ficha se quedaba vacía.

    El reloj del motor gráfico sí está en sysfs y se lee sin pedir nada.
    """

    def setUp(self):
        theme.set_density("normal", "normal")
        self.pagina = HomePage(theme.palette_for(_app(), "dark"),
                               Preferences(font_scale="normal").normalized())

    @staticmethod
    def _foto(**campos):
        """Una foto con una sola gráfica, la que se quiera describir."""
        import dataclasses

        from silux.model import Gpu

        base = Collector().snapshot()
        return dataclasses.replace(base, gpus=(Gpu(**campos),))

    def test_una_intel_sin_permisos_ensena_su_reloj(self):
        from silux.model import GpuClocks

        foto = self._foto(
            name="UHD Graphics G4", vendor="Intel", integrated=True,
            clocks=GpuClocks(core_hz=1_100_000_000, core_max_hz=1_300_000_000))
        self.pagina.apply(foto)
        cifras = self.pagina.gpu.cifras.text()
        self.assertTrue(cifras, "la ficha se quedó sin ninguna cifra")
        self.assertIn("Hz", cifras)

    def test_y_dice_que_es_integrada_en_vez_de_dejar_el_hueco(self):
        foto = self._foto(name="UHD Graphics G4", integrated=True)
        self.pagina.apply(foto)
        self.assertTrue(self.pagina.gpu.detalle.text())

    def test_un_dato_que_falta_no_se_cuela_en_la_linea_de_detalle(self):
        """«— · PCIe 1.0 × 16» se lee como si sobrara algo. Y sobraba."""
        from silux.model import GpuMemory, PcieLink

        foto = self._foto(
            name="GeForce GTX 1660 Ti",
            memory=GpuMemory(total_bytes=6 * 1024**3),   # sin tipo: NVML no lo da
            link=PcieLink(current_speed_gts=2.5, current_width=16))
        self.pagina.apply(foto)
        detalle = self.pagina.gpu.detalle.text()
        self.assertFalse(detalle.startswith(render.DASH), detalle)
        self.assertNotIn(f"{render.DASH} ·", detalle)


class TestCopiarUnValor(unittest.TestCase):
    """Un clic en el valor lo deja en el portapapeles.

    Los que uno copia todo el rato son los que no se pueden teclear de
    memoria: la referencia de un módulo de memoria, el identificador único de
    una gráfica, la firma CPUID. Seleccionarlos a mano dentro de una tarjeta
    es incómodo justo en esos, que son los largos.
    """

    def setUp(self):
        from PySide6.QtWidgets import QApplication

        theme.set_density("normal", "normal")
        _app()
        QApplication.clipboard().clear()

    @staticmethod
    def _clic(widget):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        evento = QMouseEvent(QMouseEvent.Type.MouseButtonRelease,
                             QPoint(2, 2), Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        widget.mouseReleaseEvent(evento)

    def test_el_valor_de_una_ficha_se_copia(self):
        from PySide6.QtWidgets import QApplication

        from silux.ui.widgets import InfoGrid

        rejilla = InfoGrid()
        etiqueta = rejilla.add("Identificador único", "0123456789abcdef")
        self._clic(etiqueta)
        self.assertEqual(QApplication.clipboard().text(), "0123456789abcdef")

    def test_se_copia_entero_aunque_en_pantalla_salga_recortado(self):
        """Es justo el caso en el que copiar sirve para algo."""
        from PySide6.QtWidgets import QApplication

        from silux.ui.widgets import InfoGrid

        largo = "Intel(R) Xeon(R) CPU E5-2650 v2 @ 2.60GHz"
        rejilla = InfoGrid()
        etiqueta = rejilla.add("Especificación", largo)
        # `resize` es lo que dispara el recorte: el ancho disponible se mira
        # en `resizeEvent`, no al asignar el texto.
        # Sin pantalla no llega el `resizeEvent` que recorta, así que se
        # reescribe el texto después de estrecharlo para forzar el cálculo.
        etiqueta.resize(40, etiqueta.height())
        etiqueta.set_full_text(largo + " ")
        etiqueta.set_full_text(largo)
        self.assertNotEqual(etiqueta.text(), largo,
                            "no llegó a recortarse, la prueba no vale")
        self._clic(etiqueta)
        self.assertEqual(QApplication.clipboard().text(), largo)

    def test_un_dato_que_falta_no_se_copia(self):
        """Un guion en el portapapeles no le sirve a nadie."""
        from PySide6.QtWidgets import QApplication

        from silux.ui.widgets import InfoGrid

        rejilla = InfoGrid()
        self._clic(rejilla.add("Microcódigo", "—"))
        self.assertEqual(QApplication.clipboard().text(), "")

    def test_el_nombre_del_campo_no_se_copia_solo(self):
        """Se copia el dato, no la palabra con la que se le llama."""
        from PySide6.QtWidgets import QApplication

        from silux.ui.widgets import InfoGrid

        rejilla = InfoGrid()
        rejilla.add("Fabricante", "AMD")
        self._clic(rejilla._names["Fabricante"])
        self.assertEqual(QApplication.clipboard().text(), "")

    def test_las_celdas_de_una_tabla_tambien_se_copian(self):
        """Ahí están los modelos de disco y las direcciones de red."""
        from PySide6.QtWidgets import QApplication

        from silux.ui.widgets import Table

        tabla = Table(("Unidad", "Modelo"))
        tabla.set_rows([("nvme0n1", "WD_BLACK SN850X HS 1000GB")])
        self._clic(tabla._cells[0][1])
        self.assertEqual(QApplication.clipboard().text(),
                         "WD_BLACK SN850X HS 1000GB")


class TestTarjetaDePuntuacion(unittest.TestCase):
    """La cifra comparable y su barra, en la página de Rendimiento.

    Dos huecos distintos, y cada uno se explica en vez de dejar la tarjeta a
    medias: una prueba que no se hizo con la duración canónica no tiene cifra,
    y una pieza de la que no hay medidas no tiene con qué compararse.
    """

    def setUp(self):
        from silux.settings import Preferences
        from silux.ui.pages.performance import PerformancePage

        theme.set_density("normal", "normal")
        self.pagina = PerformancePage(
            theme.palette_for(_app(), "dark"),
            Preferences(font_scale="normal").normalized())

    def _prueba(self, segundos, cpu="Procesador de prueba"):
        from silux import history, score

        tabla = score.referencias()
        if not tabla:
            self.skipTest("la escala está pendiente de rehacer")
        hilos = tabla["patron"]["hilos"]
        scores = {f"{c}/1": v for c, v in tabla["un_hilo"].items()}
        scores |= {f"{c}/{hilos}": v for c, v in tabla["multihilo"].items()}
        return history.Entry(timestamp=0, cpu=cpu, threads=hilos,
                             seconds=segundos, scores=scores)

    def test_una_prueba_de_otra_duracion_tiene_cifra_pero_no_barra(self):
        """Una sola puntuación en pantalla, y se dice hasta dónde llega.

        Antes salían dos cifras distintas de la misma prueba: la nueva arriba
        y la suma vieja en el historial. Ahora la cifra es siempre la misma y
        lo que cambia es con qué se puede comparar.
        """
        self.pagina._pintar_puntuacion(self._prueba(30.0))
        self.assertFalse(self.pagina.score_card.isHidden())
        self.assertTrue(self.pagina.score_value.text())
        self.assertIsNone(self.pagina.score_bar._comparacion)
        self.assertTrue(self.pagina.score_range.text(),
                        "tiene que decir por qué no hay barra")

    def test_con_la_duracion_canonica_sale_la_cifra(self):
        from silux import score

        self.pagina._pintar_puntuacion(self._prueba(score.SEGUNDOS_CANONICOS))
        self.assertFalse(self.pagina.score_card.isHidden())
        self.assertTrue(self.pagina.score_value.text())

    def test_sin_medidas_de_esa_pieza_no_hay_barra_pero_sí_explicación(self):
        from silux import score

        self.pagina._pintar_puntuacion(self._prueba(score.SEGUNDOS_CANONICOS))
        self.assertIsNone(self.pagina.score_bar._comparacion)
        self.assertTrue(self.pagina.score_range.text(),
                        "el hueco tiene que explicarse")

    def test_con_medidas_suficientes_aparece_la_barra(self):
        import unittest.mock as mock

        from silux import score

        tabla = dict(score.referencias())
        if not tabla:
            self.skipTest("la escala está pendiente de rehacer")
        tabla["piezas"] = {"Procesador de prueba": {
            "hilos": tabla["patron"]["hilos"],
            "un_hilo": [900, 1000, 1100], "multihilo": [900, 1000, 1100]}}
        with mock.patch.object(score, "referencias", lambda: tabla):
            self.pagina._pintar_puntuacion(
                self._prueba(score.SEGUNDOS_CANONICOS))
        self.assertIsNotNone(self.pagina.score_bar._comparacion)
        self.assertEqual(self.pagina.score_bar._comparacion.muestras, 3)


class TestTodasLasPaginasRecibenElMuestreo(unittest.TestCase):
    """Una página fuera del reparto no se entera de nada, y no se nota.

    La de rendimiento estaba fuera. No enseña cifras del muestreo, así que a
    simple vista daba igual, pero de ahí sacaba una sola cosa: contra qué
    procesador se está midiendo. Sin ella guardaba todas las pruebas con «?»
    en vez del nombre, y eso deja el historial sin poder distinguir dos
    equipos y la puntuación sin pieza con la que compararse.
    """

    def test_ninguna_pagina_se_queda_sin_snapshot(self):
        import ast
        import pathlib

        fuente = (pathlib.Path(__file__).resolve().parent.parent
                  / "silux" / "ui" / "app.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)

        # Las páginas que la ventana construye…
        construidas = {n.targets[0].attr for n in ast.walk(arbol)
                       if isinstance(n, ast.Assign) and len(n.targets) == 1
                       and isinstance(n.targets[0], ast.Attribute)
                       and n.targets[0].attr.endswith("_page")}
        # …y las que reciben el muestreo.
        repartidas = set()
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.FunctionDef)
                    and nodo.name == "_distribute"):
                repartidas = {n.attr for n in ast.walk(nodo)
                              if isinstance(n, ast.Attribute)
                              and n.attr.endswith("_page")}
        # Ajustes no enseña ni un dato del equipo: preferencias y poco más.
        # Es la única que puede quedarse fuera, y se dice aquí para que
        # añadir otra a la lista sea una decisión y no un descuido.
        sin_datos_del_equipo = {"settings_page"}

        self.assertTrue(construidas and repartidas)
        self.assertEqual(construidas - repartidas - sin_datos_del_equipo, set(),
                         "estas páginas no reciben el snapshot")

    def test_la_pagina_de_rendimiento_sabe_de_que_cpu_habla(self):
        from silux.collector import Collector
        from silux.settings import Preferences
        from silux.ui.pages.performance import PerformancePage

        theme.set_density("normal", "normal")
        pagina = PerformancePage(theme.palette_for(_app(), "dark"),
                                 Preferences(font_scale="normal").normalized())
        pagina.apply(Collector().sample())
        self.assertNotEqual(pagina._cpu_actual, "?")
