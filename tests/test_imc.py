"""El contador del controlador de memoria: lo que la RAM mueve ahora mismo.

Es un sensor y no una prueba, y de ahí salen la mitad de estos tests: no lo
provoca nadie, así que la cifra solo vale si la conversión es exacta. El
contador cuenta líneas de caché y el factor lo publica el kernel; equivocarse
en ese paso no da un error, da una cifra creíble y falsa.

Las cifras de más abajo no son inventadas: salen de medir el uncore de un
i5-10400 contra tráfico de tamaño conocido —diez gibibytes leídos a
propósito— y comprobar que el contador veía esos mismos diez.
"""

import unittest

from silux.model import MemoryTraffic, Need, SensorKind
from silux.privileged import helper, protocol
from silux.privileged.client import HelperError, LecturaImc, PmuUnsupported
from silux.providers.base import Draft
from silux.providers.imc import ImcTraffic

BYTES_POR_CUENTA = 64
ESCALA = 6.103515625e-05          # MiB por cuenta, tal y como la publica el kernel
GiB = 1 << 30


def _cuentas(bytes_movidos):
    return bytes_movidos // BYTES_POR_CUENTA


def _lectura(reloj_ns, leido, escrito, nucleos=None, *, pmu="uncore_imc",
             unidad="MiB", truncado=False, nombres=("data_reads", "data_writes")):
    """Una respuesta del ayudante con el tráfico ya convertido a cuentas."""
    contadores = {pmu: {nombres[0]: _cuentas(leido), nombres[1]: _cuentas(escrito)}}
    if nucleos is not None:
        contadores[pmu]["ia_requests"] = _cuentas(nucleos)
    escalas = {pmu: {e: ESCALA for e in contadores[pmu]}}
    unidades = {pmu: {e: unidad for e in contadores[pmu]}}
    return LecturaImc(reloj_ns, contadores, escalas, unidades, truncado)


class ClienteFalso:
    """Un ayudante de mentira que devuelve los contadores que se le digan."""

    def __init__(self, respuestas, conectado=True):
        self._respuestas = list(respuestas)
        self._conectado = conectado
        self.llamadas = 0

    def connected(self):
        return self._conectado

    def imc(self):
        self.llamadas += 1
        siguiente = self._respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


class TestElContratoDelAyudante(unittest.TestCase):
    """Lo que el ayudante deja abrir, que es lo que corre como root."""

    def test_es_una_accion_del_contrato(self):
        self.assertIn(protocol.ACTION_IMC, protocol.ACTIONS)

    def test_los_patrones_del_contrato_y_del_ayudante_coinciden(self):
        # Si se separan, el cliente pediría cosas que el ayudante rechaza.
        self.assertEqual(protocol.PMU_IMC, helper.PMU_IMC.pattern)
        self.assertEqual(protocol.PMU_IMC_EVENT, helper.PMU_IMC_EVENT.pattern)

    def test_la_version_subio_al_anadir_la_accion(self):
        # Una copia instalada en /usr/local/libexec no se actualiza sola, y
        # una que no sepa esta acción tiene que declararse vieja.
        self.assertEqual(helper.VERSION, protocol.VERSION_REQUERIDA)
        self.assertGreaterEqual(helper.VERSION, 3)

    def test_el_patron_admite_los_tres_nombres_que_usa_intel(self):
        for bueno in ("uncore_imc", "uncore_imc_0", "uncore_imc_free_running_0"):
            with self.subTest(pmu=bueno):
                self.assertTrue(helper.PMU_IMC.match(bueno))

    def test_el_patron_no_deja_salirse_del_directorio(self):
        for malo in ("..", "../../etc", "uncore_imc/../cpu", "cpu", "i915",
                     "intel_pt", "kprobe", "tracepoint", "msr", "uncore_cbox_0",
                     "uncore_arb", "amd_umc_0", "uncore_imcx"):
            with self.subTest(nombre=malo):
                self.assertIsNone(helper.PMU_IMC.match(malo))

    def test_solo_entran_los_contadores_que_se_han_comprobado(self):
        for bueno in ("data_reads", "data_writes", "data_read", "data_write",
                      "cas_count_read", "cas_count_write", "ia_requests"):
            with self.subTest(evento=bueno):
                self.assertTrue(helper.PMU_IMC_EVENT.match(bueno))

    def test_gt_requests_e_io_requests_se_quedan_fuera(self):
        """Los dos existen, los dos suman y ninguno de los dos se sostiene.

        Medidos en el i5-10400: `io_requests` marcó la misma cifra —0,93
        GiB/s— en reposo y bajo carga de memoria, que no es lo que hace un
        contador de tráfico; y `gt_requests` marcó 4,6 GiB/s con una sola
        pantalla de 1080p conectada, diez veces lo que puede mover su
        refresco. Que sumen con el total no los hace atribuibles.
        """
        for malo in ("gt_requests", "io_requests"):
            with self.subTest(evento=malo):
                self.assertIsNone(helper.PMU_IMC_EVENT.match(malo))

    def test_el_ayudante_decide_solo_que_abre(self):
        # El cliente manda una familia y nada más: ni nombres de PMU ni
        # números de evento viajan por el protocolo.
        self.assertEqual(helper._pmu_admitido(helper.FAMILIA_IMC, "uncore_imc"),
                         helper.PMU_IMC_EVENT)
        self.assertIsNone(helper._pmu_admitido(helper.FAMILIA_IMC, "i915"))
        self.assertIsNone(helper._pmu_admitido(helper.FAMILIA_GPU, "uncore_imc"))


class TestUnaMaquinaSinContadores(unittest.TestCase):
    """La rama que se ejecuta en cualquier AMD, vista fallar de verdad."""

    def test_el_ayudante_contesta_unsupported_y_no_un_error(self):
        """La diferencia entre «no lo tiene» y «se rompió»: gris contra rojo."""
        import tempfile

        original = helper.PMU_ROOT
        fds, fallos = dict(helper._PMU_FDS), dict(helper._PMU_FALLO)
        helper._PMU_FDS.clear()
        helper._PMU_FALLO.clear()

        def restaurar():
            helper.PMU_ROOT = original
            helper._PMU_FDS.clear()
            helper._PMU_FDS.update(fds)
            helper._PMU_FALLO.clear()
            helper._PMU_FALLO.update(fallos)

        self.addCleanup(restaurar)
        with tempfile.TemporaryDirectory() as sin_pmu:
            helper.PMU_ROOT = sin_pmu
            respuesta = helper.read_imc()

        self.assertFalse(respuesta["ok"])
        self.assertEqual(respuesta["error"], "unsupported")
        self.assertIn("controlador de memoria", respuesta["message"])


class TestLaDerivada(unittest.TestCase):
    """De cuentas acumuladas a bytes por segundo, que es donde se falla."""

    def _proveedor(self, respuestas):
        proveedor = ImcTraffic(client=ClienteFalso(respuestas))
        proveedor._forzar_disponible = True
        return proveedor

    def _recoge(self, proveedor, veces=2):
        borrador = Draft()
        for _vuelta in range(veces):
            proveedor.collect(borrador)
        return borrador

    def setUp(self):
        # El proveedor mira sysfs para saber si esta máquina tiene el PMU, y
        # eso depende de quién ejecute los tests. Aquí se comprueba la cuenta,
        # así que se responde que sí y se deja el sysfs en paz.
        import silux.providers.imc as modulo
        self._original = modulo.hay_controlador
        modulo.hay_controlador = lambda: True
        self.addCleanup(setattr, modulo, "hay_controlador", self._original)

    def test_diez_gibibytes_en_un_segundo_son_diez_gibibytes(self):
        """La comprobación de la que salió todo, con sus números.

        Diez GiB leídos a propósito en una ventana de un segundo tienen que
        salir a 10,74 GB/s, que es lo que son diez GiB en unidades decimales.
        """
        borrador = self._recoge(self._proveedor([
            _lectura(0, 0, 0),
            _lectura(1_000_000_000, 10 * GiB, 0),
        ]))
        self.assertIsNotNone(borrador.memory_traffic)
        self.assertAlmostEqual(borrador.memory_traffic.read_bytes_s / 1e9,
                               10.74, places=1)

    def test_la_ventana_manda_y_no_el_segundo_redondo(self):
        # Medio segundo con los mismos bytes es el doble de ritmo.
        borrador = self._recoge(self._proveedor([
            _lectura(0, 0, 0),
            _lectura(500_000_000, 10 * GiB, 0),
        ]))
        self.assertAlmostEqual(borrador.memory_traffic.read_bytes_s / 1e9,
                               21.47, places=1)

    def test_la_primera_vuelta_solo_fija_la_referencia(self):
        proveedor = self._proveedor([_lectura(0, 5 * GiB, 5 * GiB)])
        borrador = self._recoge(proveedor, veces=1)
        self.assertIsNone(borrador.memory_traffic,
                          "un contador acumulado no da ritmo con una sola lectura")

    def test_lectura_escritura_y_nucleos_van_a_su_campo(self):
        borrador = self._recoge(self._proveedor([
            _lectura(0, 0, 0, 0),
            _lectura(1_000_000_000, 4 * GiB, 2 * GiB, 3 * GiB),
        ]))
        trafico = borrador.memory_traffic
        self.assertAlmostEqual(trafico.read_bytes_s / 1e9, 4.29, places=1)
        self.assertAlmostEqual(trafico.write_bytes_s / 1e9, 2.15, places=1)
        self.assertAlmostEqual(trafico.cpu_bytes_s / 1e9, 3.22, places=1)
        self.assertAlmostEqual(trafico.total_bytes_s / 1e9, 6.44, places=1)

    def test_sin_ia_requests_el_campo_se_queda_a_none(self):
        """Un guion, no un cero: no todas las generaciones lo publican."""
        borrador = self._recoge(self._proveedor([
            _lectura(0, 0, 0),
            _lectura(1_000_000_000, GiB, GiB),
        ]))
        self.assertIsNone(borrador.memory_traffic.cpu_bytes_s)

    def test_los_canales_de_un_servidor_se_suman(self):
        """Cada canal tiene su PMU y su contador; el tráfico es la suma."""
        def dos_canales(reloj, por_canal):
            contadores = {f"uncore_imc_{n}": {"cas_count_read": _cuentas(por_canal),
                                              "cas_count_write": 0}
                          for n in (0, 1)}
            escalas = {p: {e: ESCALA for e in ev} for p, ev in contadores.items()}
            unidades = {p: {e: "MiB" for e in ev} for p, ev in contadores.items()}
            return LecturaImc(reloj, contadores, escalas, unidades, False)

        borrador = self._recoge(self._proveedor([
            dos_canales(0, 0), dos_canales(1_000_000_000, 5 * GiB)]))
        self.assertAlmostEqual(borrador.memory_traffic.read_bytes_s / 1e9,
                               10.74, places=1)

    def test_un_contador_que_retrocede_no_publica_nada(self):
        """Reiniciado o recién abierto: restar daría un número negativo."""
        borrador = self._recoge(self._proveedor([
            _lectura(0, 10 * GiB, 10 * GiB),
            _lectura(1_000_000_000, 1 * GiB, 1 * GiB),
        ]))
        self.assertIsNone(borrador.memory_traffic)

    def test_una_unidad_desconocida_no_se_convierte(self):
        """Si el kernel dejara de contar en MiB, la cifra sería otra cosa.

        Es el mismo cuidado que con las versiones de `gpu_metrics`: antes que
        multiplicar por un factor que ya no corresponde, no se enseña nada.
        """
        borrador = self._recoge(self._proveedor([
            _lectura(0, 0, 0, unidad="KiB"),
            _lectura(1_000_000_000, 10 * GiB, 10 * GiB, unidad="KiB"),
        ]))
        self.assertIsNone(borrador.memory_traffic)

    def test_una_lista_incompleta_de_canales_no_publica_una_suma_corta(self):
        borrador = self._recoge(self._proveedor([
            _lectura(0, 0, 0, truncado=True),
            _lectura(1_000_000_000, 10 * GiB, 0, truncado=True),
        ]))
        self.assertIsNone(borrador.memory_traffic)
        motivos = [n.need for n in borrador.notes if n.path == "memory.traffic"]
        self.assertIn(Need.ERROR, motivos,
                      "un tope nuestro que recorta la cifra es un fallo nuestro")

    def test_una_maquina_sin_contadores_deja_de_preguntar(self):
        proveedor = self._proveedor([PmuUnsupported("no hay")])
        self._recoge(proveedor, veces=1)
        self.assertTrue(proveedor._mudo)
        self.assertFalse(proveedor.available())
        self.assertEqual(proveedor.unavailable_reason()[1], Need.HARDWARE,
                         "que no exista no se arregla con permisos")

    def test_un_fallo_suelto_no_da_nada_por_perdido(self):
        """La tubería puede cortarse y el usuario volver a autorizar."""
        proveedor = self._proveedor([HelperError("se cortó"),
                                     _lectura(0, 0, 0),
                                     _lectura(1_000_000_000, GiB, GiB)])
        borrador = self._recoge(proveedor, veces=3)
        self.assertFalse(proveedor._mudo)
        self.assertIsNotNone(borrador.memory_traffic)


class TestPorQueFaltaCuandoFalta(unittest.TestCase):
    """Las dos respuestas, que no son la misma y se pintan de otro color."""

    def test_con_contador_y_sin_permisos_pide_permisos(self):
        import silux.providers.imc as modulo
        original = modulo.hay_controlador
        modulo.hay_controlador = lambda: True
        self.addCleanup(setattr, modulo, "hay_controlador", original)

        proveedor = ImcTraffic(client=None)
        ruta, motivo, _mensaje, _pista = proveedor.unavailable_reason()
        self.assertEqual(ruta, "memory.traffic")
        self.assertEqual(motivo, Need.ROOT)

    def test_sin_contador_no_se_pide_nada(self):
        """En un Ryzen, pedir la contraseña para no enseñar nada sería peor."""
        import silux.providers.imc as modulo
        original = modulo.hay_controlador
        modulo.hay_controlador = lambda: False
        self.addCleanup(setattr, modulo, "hay_controlador", original)

        proveedor = ImcTraffic(client=None)
        self.assertEqual(proveedor.unavailable_reason()[1], Need.HARDWARE)

    def test_el_buscador_de_pmu_lee_el_sysfs_de_verdad(self):
        """Sin exigir resultado: esta máquina puede no tener ninguno."""
        from silux.providers.imc import hay_controlador
        self.assertIsInstance(hay_controlador(), bool)


class TestElTraficoEnPantalla(unittest.TestCase):
    """Que se vea. Un dato que llega al modelo y no tiene celda no está hecho.

    Es la lección del voltaje del núcleo, que se midió, se guardó y se quedó
    sin fila con la suite entera en verde.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _pagina(self, trafico, modulos=()):
        from silux.model import CpuInfo, CpuType, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
            modules=tuple(modulos),
            memory_traffic=trafico,
        ))
        self.app.processEvents()
        self._viva = pagina          # sin referencia viva, Qt borra los widgets
        return pagina

    @staticmethod
    def _celda(pagina, clave):
        from silux.i18n import _
        from silux.ui.widgets import InfoGrid
        for grid in pagina.findChildren(InfoGrid):
            if _(clave) in grid._values:
                return grid._values[_(clave)]
        return None

    def test_la_ficha_tiene_donde_pintarlo(self):
        pagina = self._pagina(MemoryTraffic(1, 1))
        for clave in ("memory.traffic.now", "memory.traffic.read",
                      "memory.traffic.write", "memory.traffic.cpu"):
            with self.subTest(fila=clave):
                self.assertIsNotNone(self._celda(pagina, clave),
                                     f"{clave} no tiene fila en la ficha")

    def test_la_cifra_llega_a_la_celda(self):
        pagina = self._pagina(MemoryTraffic(read_bytes_s=4_030_000_000,
                                            write_bytes_s=3_320_000_000))
        self.assertIn("4.0", self._celda(pagina, "memory.traffic.read")._full)
        self.assertIn("3.3", self._celda(pagina, "memory.traffic.write")._full)
        self.assertIn("7.3", self._celda(pagina, "memory.traffic.now")._full)

    def test_con_modulos_conocidos_sale_la_fraccion_del_teorico(self):
        """Dos módulos a 2666 MT/s son 42,7 GB/s teóricos."""
        from silux.model import MemoryModule
        modulos = [MemoryModule(populated=True, locator="DIMM 0", bank="CHANNEL A",
                                size_bytes=8 << 30, configured_mts=2666),
                   MemoryModule(populated=True, locator="DIMM 1", bank="CHANNEL B",
                                size_bytes=8 << 30, configured_mts=2666)]
        pagina = self._pagina(MemoryTraffic(4_030_000_000, 3_320_000_000), modulos)
        texto = self._celda(pagina, "memory.traffic.now")._full
        self.assertIn("%", texto)
        self.assertIn("43 GB/s", texto)

    def test_sin_saber_los_canales_no_se_inventa_el_porcentaje(self):
        pagina = self._pagina(MemoryTraffic(4_030_000_000, 3_320_000_000))
        self.assertNotIn("%", self._celda(pagina, "memory.traffic.now")._full)

    def test_sin_contador_la_tarjeta_no_sale(self):
        """Escondida, no a guiones: no falta la cifra, es que no la hay."""
        pagina = self._pagina(None)
        self.assertTrue(pagina.traffic_card.isHidden())

    def test_la_fila_del_procesador_se_esconde_si_no_se_mide(self):
        pagina = self._pagina(MemoryTraffic(1_000_000_000, 1_000_000_000))
        self.assertTrue(self._celda(pagina, "memory.traffic.cpu").isHidden())
        self.assertFalse(self._celda(pagina, "memory.traffic.read").isHidden())

    def test_el_aviso_de_que_no_lo_hay_sale_en_gris(self):
        """Ámbar es lo accionable; esto no lo arregla nadie."""
        from silux.model import CpuInfo, CpuType, Note, Snapshot
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from silux.ui.widgets import Notice

        pagina = MemoryPage(theme.palette_for(self.app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
            notes=(Note("memory.traffic", Need.HARDWARE, "No lo publica."),),
        ))
        self.app.processEvents()
        self._viva = pagina
        avisos = [n for n in pagina.findChildren(Notice) if not n.isHidden()]
        self.assertTrue(avisos, "el dato desaparecería sin decir por qué")


class TestElTraficoEnElArbolDeLaVentana(unittest.TestCase):
    """Que la fila salga en el árbol de verdad, no solo en el modelo."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_la_fila_sale_con_su_maximo_de_la_sesion(self):
        """El máximo es lo que aporta el árbol: el pico que llegó a moverse."""
        from silux.i18n import _
        from silux.model import CpuInfo, CpuType, Sensor, Snapshot
        from silux.settings import Preferences
        from silux.tracking import Tracker
        from silux.ui import theme
        from silux.ui.pages.monitor import MonitorPage
        from silux.ui.sensortree import SensorTree

        sensores = (Sensor(key="imc/read", chip="uncore_imc", device="Memoria",
                           label=_("sensor.imc.read"), kind=SensorKind.BANDWIDTH,
                           value=3613.8),
                    Sensor(key="imc/write", chip="uncore_imc", device="Memoria",
                           label=_("sensor.imc.write"), kind=SensorKind.BANDWIDTH,
                           value=2642.8, order=1))
        seguidor = Tracker()
        seguidor.update("imc/read", 3613.8)
        seguidor.update("imc/read", 9120.4)      # el pico
        seguidor.update("imc/write", 2642.8)

        pagina = MonitorPage(theme.palette_for(self.app, "dark"),
                             Preferences(), seguidor)
        self.addCleanup(pagina.deleteLater)
        pagina.apply(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
            sensors=sensores,
        ))
        self.app.processEvents()
        self._viva = pagina

        arboles = pagina.findChildren(SensorTree)
        self.assertTrue(arboles, "la página no montó ningún árbol")
        fila = arboles[0]._rows.get("imc/read")
        self.assertIsNotNone(fila, "la lectura de memoria no llegó al árbol")
        textos = [fila.text(n) for n in range(arboles[0].columnCount())]
        self.assertTrue(any("3613.8" in x for x in textos), textos)
        self.assertTrue(any("9120.4" in x for x in textos),
                        f"el máximo de la sesión no se ve: {textos}")
        self.assertTrue(any("MB/s" in x for x in textos), textos)


class TestElTraficoEnElInforme(unittest.TestCase):
    """El informe es lo primero que se pide cuando algo no sale."""

    def _informe(self, trafico):
        from silux import report
        from silux.model import CpuInfo, CpuType, Snapshot
        return report.build(Snapshot(
            monotonic_ns=0,
            cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
            memory_traffic=trafico,
        ))

    def test_la_cifra_sale_y_dice_que_es_de_un_instante(self):
        texto = self._informe(MemoryTraffic(4_030_000_000, 3_320_000_000,
                                            1_240_000_000))
        self.assertIn("Tráfico del controlador", texto)
        self.assertIn("instante", texto,
                      "sin eso, una cifra baja parece un diagnóstico")
        self.assertIn("4.0 GB/s", texto)
        self.assertIn("1.2 GB/s", texto)

    def test_sin_contador_no_se_inventa_la_linea(self):
        self.assertNotIn("Tráfico del controlador", self._informe(None))


class TestElTraficoEnElArbolDeSensores(unittest.TestCase):
    """El árbol guarda mínimo, máximo y media: aquí eso significa algo."""

    def test_el_tipo_nuevo_tiene_unidad_y_rama(self):
        from silux.model import CATEGORIES, CATEGORY_ORDER, UNITS
        self.assertEqual(UNITS[SensorKind.BANDWIDTH], "MB/s")
        self.assertIn(CATEGORIES[SensorKind.BANDWIDTH], CATEGORY_ORDER)

    def test_los_sensores_cuelgan_de_memoria_y_en_su_rama(self):
        from silux.model import CpuInfo, CpuType, Snapshot
        import silux.providers.imc as modulo

        original = modulo.hay_controlador
        modulo.hay_controlador = lambda: True
        self.addCleanup(setattr, modulo, "hay_controlador", original)

        proveedor = ImcTraffic(client=ClienteFalso([
            _lectura(0, 0, 0),
            _lectura(1_000_000_000, 4 * GiB, 2 * GiB)]))
        borrador = Draft()
        proveedor.collect(borrador)
        proveedor.collect(borrador)

        foto = Snapshot(monotonic_ns=0,
                        cpu=CpuInfo(types=(CpuType(key="general", label="g"),)),
                        sensors=tuple(borrador.sensors))
        arbol = foto.sensor_tree()
        self.assertIn("Memoria", arbol)
        self.assertIn("cat.bandwidth", arbol["Memoria"])
        valores = [s.value for s in arbol["Memoria"]["cat.bandwidth"]]
        self.assertEqual(len(valores), 2)
        # 4 GiB en un segundo son 4295 MB/s.
        self.assertAlmostEqual(max(valores), 4295, delta=5)

    def test_las_claves_de_los_sensores_no_bailan_entre_muestreos(self):
        """Sin `key` estable no hay mínimos ni máximos que acumular."""
        import silux.providers.imc as modulo
        original = modulo.hay_controlador
        modulo.hay_controlador = lambda: True
        self.addCleanup(setattr, modulo, "hay_controlador", original)

        proveedor = ImcTraffic(client=ClienteFalso([
            _lectura(0, 0, 0),
            _lectura(1_000_000_000, GiB, GiB),
            _lectura(2_000_000_000, 3 * GiB, 3 * GiB)]))
        claves = []
        for _vuelta in range(3):
            borrador = Draft()
            proveedor.collect(borrador)
            if borrador.sensors:
                claves.append(tuple(s.key for s in borrador.sensors))
        self.assertEqual(len(set(claves)), 1, f"las claves cambiaron: {claves}")


if __name__ == "__main__":
    unittest.main()
