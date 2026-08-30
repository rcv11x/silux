"""El árbol de sensores: agrupado, orden y nombres de los aparatos."""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.model import (
    Board, CpuInfo, CpuType, Power, Sensor, SensorKind, Snapshot,
    short_brand, short_vendor,
)
from silux.providers import hwmon
from silux.providers.base import Draft
from silux.providers.derived import DerivedSensors
from silux.tracking import HISTORIAL, Tracker

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _sensor(device: str, label: str, kind: SensorKind, value: float, order: int = 0) -> Sensor:
    return Sensor(key=f"{device}/{label}", chip="x", device=device,
                  label=label, kind=kind, value=value, order=order)


class TestNombres(unittest.TestCase):
    def test_el_fabricante_se_acorta(self):
        self.assertEqual(short_vendor("Micro-Star International Co., Ltd."), "MSI")
        self.assertEqual(short_vendor("ASUSTeK COMPUTER INC."), "ASUS")
        self.assertEqual(short_vendor("Fabricante Raro S.L."), "Fabricante Raro S.L.")
        self.assertIsNone(short_vendor(None))

    def test_la_marca_del_procesador_se_limpia(self):
        self.assertEqual(
            short_brand("Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz"),
            "Intel Core i5-10400",
        )
        self.assertEqual(
            short_brand("AMD Ryzen 7 5800X 8-Core Processor"),
            "AMD Ryzen 7 5800X",
        )
        self.assertEqual(short_brand(None), "Procesador")

    def test_nombre_de_la_placa(self):
        board = Board(vendor="Micro-Star International Co., Ltd.", name="H510M PRO-E")
        self.assertEqual(board.display_name, "MSI H510M PRO-E")
        self.assertEqual(Board().display_name, "Placa base")


class TestArbol(unittest.TestCase):
    def _snapshot(self) -> Snapshot:
        sensores = (
            _sensor("Placa", "TMPIN0", SensorKind.TEMPERATURE, 34.0),
            _sensor("CPU", "Core #1", SensorKind.USAGE, 20.0, order=1),
            _sensor("CPU", "Core #0", SensorKind.USAGE, 10.0, order=0),
            _sensor("CPU", "Package", SensorKind.TEMPERATURE, 45.0),
            _sensor("CPU", "Vcore", SensorKind.VOLTAGE, 1.2),
            _sensor("CPU", "Paquete", SensorKind.POWER, 40.0),
        )
        return Snapshot(1, CpuInfo(), sensors=sensores)

    def test_agrupa_por_aparato_y_categoria(self):
        arbol = self._snapshot().sensor_tree()
        self.assertEqual(set(arbol), {"Placa", "CPU"})
        # Las categorías del árbol son claves de idioma: el nombre visible lo
        # pone la interfaz al montarlo.
        self.assertEqual(set(arbol["CPU"]),
                         {"cat.voltage", "cat.temperature", "cat.power", "cat.usage"})

    def test_las_ramas_van_en_el_orden_de_hwmonitor(self):
        # Voltajes primero, luego temperaturas, ventiladores, potencias…
        self.assertEqual(
            list(self._snapshot().sensor_tree()["CPU"]),
            ["cat.voltage", "cat.temperature", "cat.power", "cat.usage"],
        )

    def test_dentro_de_una_rama_manda_el_campo_order(self):
        uso = self._snapshot().sensor_tree()["CPU"]["cat.usage"]
        self.assertEqual([s.label for s in uso], ["Core #0", "Core #1"])

    def test_un_snapshot_sin_sensores_da_un_arbol_vacio(self):
        self.assertEqual(Snapshot(1, CpuInfo()).sensor_tree(), {})


class TestSensoresDerivados(unittest.TestCase):
    def _draft(self) -> Draft:
        draft = Draft()
        draft.types["general"] = {
            "key": "general", "label": "g", "cpus": [0, 1],
            "brand": "Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz",
        }
        draft.logical[0] = {"index": 0, "core_id": 0, "package_id": 0,
                            "freq_hz": 2_900_000_000, "usage_percent": 30.0}
        draft.logical[1] = {"index": 1, "core_id": 1, "package_id": 0,
                            "freq_hz": 800_000_000, "usage_percent": 5.0}
        draft.cpu_extra["usage_percent"] = 17.5
        draft.cpu_extra["power"] = Power(package_w=40.0, core_w=36.0,
                                         limit_long_w=65.0, limit_short_w=115.0)
        return draft

    def test_convierte_relojes_uso_y_potencia_en_sensores(self):
        draft = self._draft()
        DerivedSensors().collect(draft)
        por_tipo = {}
        for sensor in draft.sensors:
            por_tipo.setdefault(sensor.kind, []).append(sensor)

        self.assertEqual(len(por_tipo[SensorKind.CLOCK]), 2)
        self.assertEqual(len(por_tipo[SensorKind.USAGE]), 3)      # total + dos núcleos
        self.assertEqual(len(por_tipo[SensorKind.POWER]), 2)      # paquete y núcleos

    def test_los_relojes_van_en_megahercios(self):
        draft = self._draft()
        DerivedSensors().collect(draft)
        reloj = next(s for s in draft.sensors if s.kind is SensorKind.CLOCK)
        self.assertEqual(reloj.value, 2900.0)
        self.assertEqual(reloj.unit, "MHz")

    def test_el_limite_del_chip_es_el_umbral_del_paquete(self):
        draft = self._draft()
        DerivedSensors().collect(draft)
        paquete = next(s for s in draft.sensors
                       if s.kind is SensorKind.POWER and s.label == "Paquete")
        self.assertEqual(paquete.high, 65.0)
        self.assertEqual(paquete.critical, 115.0)
        self.assertFalse(paquete.alarm)

    def test_todo_cuelga_del_nombre_corto_del_procesador(self):
        draft = self._draft()
        DerivedSensors().collect(draft)
        self.assertEqual({s.device for s in draft.sensors}, {"Intel Core i5-10400"})

    def test_sin_datos_no_inventa_sensores(self):
        draft = Draft()
        DerivedSensors().collect(draft)
        self.assertEqual(draft.sensors, [])


class TestSeguimiento(unittest.TestCase):
    def test_los_extremos_se_acumulan(self):
        tracker = Tracker()
        for valor in (40, 55, 38, 61, 47):
            tracker.update("t", valor)
        extremos = tracker.get("t")
        self.assertEqual((extremos.minimum, extremos.maximum), (38, 61))
        self.assertAlmostEqual(extremos.average, 48.2)
        self.assertEqual(extremos.last, 47)

    def test_los_nulos_se_ignoran(self):
        tracker = Tracker()
        tracker.update("t", None)
        self.assertIsNone(tracker.get("t"))

    def test_reiniciar(self):
        tracker = Tracker()
        tracker.update("a", 1)
        tracker.update("b", 2)
        tracker.reset("a")
        self.assertIsNone(tracker.get("a"))
        self.assertIsNotNone(tracker.get("b"))
        tracker.reset()
        self.assertEqual(len(tracker), 0)


@unittest.skipUnless(__import__("importlib").util.find_spec("PySide6"), "sin PySide6")
class TestWidgetDelArbol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _tree(self):
        from silux.ui import theme
        from silux.ui.widgets import SensorTree

        return SensorTree(theme.DARK)

    def test_construye_la_jerarquia(self):
        arbol = self._tree()
        snapshot = Snapshot(1, CpuInfo(), sensors=(
            _sensor("CPU", "Core 0", SensorKind.TEMPERATURE, 40.0),
            _sensor("CPU", "Core 1", SensorKind.TEMPERATURE, 42.0),
            _sensor("Placa", "Fan #1", SensorKind.FAN, 900.0),
        ))
        arbol.rebuild(snapshot.sensor_tree())
        self.assertEqual(arbol.topLevelItemCount(), 2)
        self.assertTrue(arbol.has("CPU/Core 0"))
        self.assertTrue(arbol.has("Placa/Fan #1"))

    def test_actualiza_sin_reconstruir(self):
        arbol = self._tree()
        snapshot = Snapshot(1, CpuInfo(), sensors=(
            _sensor("CPU", "Core 0", SensorKind.TEMPERATURE, 40.0),
        ))
        arbol.rebuild(snapshot.sensor_tree())
        item = arbol._rows["CPU/Core 0"]
        arbol.update_row("CPU/Core 0", ["41.0 °C", "40.0", "41.0", "40.5"])
        self.assertEqual(item.text(1), "41.0 °C")
        self.assertIs(arbol._rows["CPU/Core 0"], item)   # el mismo objeto

    def test_una_clave_desconocida_no_revienta(self):
        arbol = self._tree()
        arbol.rebuild({})
        arbol.update_row("no/existe", ["1", "2", "3", "4"])


if __name__ == "__main__":
    unittest.main()


class TestHistorialDelSeguidor(unittest.TestCase):
    """La serie reciente que alimenta las curvas del árbol de sensores."""

    def test_la_serie_esta_acotada(self):
        """Un monitor se deja abierto horas. Sin tope, cien sensores a una
        muestra por segundo son treinta y seis mil valores cada uno en una
        tarde, y el programa crece hasta que alguien lo cierra."""
        seguidor = Tracker()
        for muestra in range(HISTORIAL * 3):
            seguidor.update("cpu", float(muestra))
        historial = seguidor.get("cpu").history
        self.assertEqual(len(historial), HISTORIAL)
        # Y lo que queda es lo último, no lo primero.
        self.assertEqual(historial[-1], float(HISTORIAL * 3 - 1))

    def test_la_primera_muestra_ya_cuenta(self):
        seguidor = Tracker()
        seguidor.update("cpu", 42.0)
        self.assertEqual(list(seguidor.get("cpu").history), [42.0])

    def test_reiniciar_tambien_borra_la_curva(self):
        """El botón dice «reiniciar mín/máx» y lo que hace es empezar a contar
        de nuevo: dejar la curva vieja colgando de unos extremos nuevos
        enseñaría dos tramos de tiempo distintos en el mismo renglón."""
        seguidor = Tracker()
        for muestra in range(10):
            seguidor.update("cpu", float(muestra))
        seguidor.reset("cpu")
        self.assertIsNone(seguidor.get("cpu"))

    def test_un_valor_ausente_no_entra_en_la_curva(self):
        """Un sensor que deja de responder no dibuja un cero: no hay dato."""
        seguidor = Tracker()
        seguidor.update("cpu", 50.0)
        seguidor.update("cpu", None)
        self.assertEqual(list(seguidor.get("cpu").history), [50.0])


class TestAQuienPerteneceUnSensor(unittest.TestCase):
    """El nombre del aparato bajo el que cuelga cada sensor de hwmon."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _dispositivo(self, ruta: pathlib.Path) -> pathlib.Path:
        """Un directorio que sysfs reconocería como dispositivo."""
        ruta.mkdir(parents=True, exist_ok=True)
        (ruta / "uevent").write_text("", encoding="utf-8")
        return ruta

    def test_el_sensor_de_una_tarjeta_de_red_lleva_su_interfaz(self):
        from silux.providers.hwmon import _net_name

        tarjeta = self._dispositivo(self.raiz / "devices" / "pci0000:00" / "0000:04:00.0")
        (tarjeta / "net" / "enp4s0").mkdir(parents=True)
        hwmon = self.raiz / "hwmon0"
        hwmon.mkdir()
        (hwmon / "device").symlink_to(tarjeta)

        self.assertEqual(_net_name(hwmon), "Red (enp4s0)")

    def test_un_sensor_virtual_no_acaba_colgado_del_bucle_local(self):
        """Subiendo a ciegas se llegaba a `/sys/devices/virtual`, que también
        tiene un `net/` dentro —con `lo`— y un ThinkPad enseñaba el loopback a
        34 °C. El bucle local no tiene con qué calentarse."""
        from silux.providers.hwmon import _net_name

        virtual = self.raiz / "devices" / "virtual"
        (virtual / "net" / "lo").mkdir(parents=True)
        zona = self._dispositivo(virtual / "thermal" / "thermal_zone0")
        hwmon = self.raiz / "hwmon1"
        hwmon.mkdir()
        (hwmon / "device").symlink_to(zona)

        self.assertIsNone(_net_name(hwmon))

    def test_sube_por_el_bus_hasta_la_tarjeta(self):
        """El sensor de una Realtek cuelga del bus MDIO, no de la tarjeta."""
        from silux.providers.hwmon import _net_name

        tarjeta = self._dispositivo(self.raiz / "0000:04:00.0")
        (tarjeta / "net" / "enp4s0").mkdir(parents=True)
        mdio = self._dispositivo(tarjeta / "mdio_bus" / "r8169-4-200")
        hwmon = self.raiz / "hwmon2"
        hwmon.mkdir()
        (hwmon / "device").symlink_to(mdio)

        self.assertEqual(_net_name(hwmon), "Red (enp4s0)")


class TestNombresDeAlimentacion(unittest.TestCase):
    """Lo que un portátil publica como chip y salía en crudo en el árbol."""

    def test_una_bateria_se_llama_bateria(self):
        from silux.providers.hwmon import _nombre_de_alimentacion

        self.assertEqual(_nombre_de_alimentacion("BAT0"), "Batería")

    def test_la_segunda_bateria_se_distingue(self):
        from silux.providers.hwmon import _nombre_de_alimentacion

        self.assertEqual(_nombre_de_alimentacion("BAT1"), "Batería 2")

    def test_el_puerto_usbc_no_lleva_el_nombre_del_kernel(self):
        """`ucsi_source_psy_USBC000:001` no lo reconoce nadie en un árbol."""
        from silux.providers.hwmon import _nombre_de_alimentacion

        self.assertEqual(
            _nombre_de_alimentacion("ucsi_source_psy_USBC000:001"),
            "Puerto USB-C")

    def test_lo_que_sigue_a_usbc_no_es_un_numero_de_puerto(self):
        """Es un identificador de ACPI. Numerarlo daba «Puerto USB-C 2» en un
        portátil que tiene uno solo."""
        from silux.providers.hwmon import _nombre_de_alimentacion

        self.assertEqual(
            _nombre_de_alimentacion("ucsi_source_psy_USBC000:002"),
            "Puerto USB-C")

    def test_un_chip_normal_no_se_toca(self):
        from silux.providers.hwmon import _nombre_de_alimentacion

        for chip in ("coretemp", "nct6798", "thinkpad", "amdgpu", "nvme"):
            with self.subTest(chip=chip):
                self.assertIsNone(_nombre_de_alimentacion(chip))

    def test_de_una_fuente_externa_no_se_avisa(self):
        """Un puerto USB-C sin nada conectado marca 0 V, y eso queda por
        debajo de cualquier mínimo que declare el chip: un ThinkPad tenía un
        aviso permanente por llevar el cargador desenchufado."""
        from silux.model import SensorKind
        from silux.providers.hwmon import _umbrales

        limites = _umbrales(SensorKind.VOLTAGE, 4.0, 20.0, 22.0,
                            "ucsi_source_psy_USBC000:001")
        self.assertEqual(limites, {"low": None, "high": None, "critical": None})

    def test_un_chip_de_verdad_conserva_sus_umbrales(self):
        from silux.model import SensorKind
        from silux.providers.hwmon import _umbrales

        limites = _umbrales(SensorKind.VOLTAGE, 1.0, 1.5, 1.6, "nct6798")
        self.assertEqual(limites["high"], 1.5)


class TestCalorDeUnSensor(unittest.TestCase):
    """El degradado que tiñe la columna del valor actual.

    Noventa y nueve renglones de cifras del mismo color se leen uno a uno; el
    que se está acercando a su umbral tiene que encontrarse mirando.
    """

    def _temp(self, valor, high=None, crit=None):
        from silux.model import Sensor, SensorKind

        return Sensor(key="t", chip="c", device="d", label="l",
                      kind=SensorKind.TEMPERATURE, value=valor,
                      high=high, critical=crit)

    def test_bien_lejos_del_umbral_no_se_tiñe(self):
        """Un procesador a 45 grados de 90 no está «medio caliente»: está
        bien, y darle un color intermedio convierte el color en decoración."""
        self.assertEqual(self._temp(45.0, crit=90.0).heat, 0.0)

    def test_acercarse_lo_va_subiendo(self):
        tibio = self._temp(75.0, crit=90.0).heat
        caliente = self._temp(85.0, crit=90.0).heat
        self.assertGreater(tibio, 0.0)
        self.assertGreater(caliente, tibio)
        self.assertLessEqual(caliente, 1.0)

    def test_en_el_umbral_llega_al_maximo(self):
        self.assertEqual(self._temp(90.0, crit=90.0).heat, 1.0)

    def test_pasarse_no_se_sale_de_la_escala(self):
        self.assertEqual(self._temp(120.0, crit=90.0).heat, 1.0)

    def test_sin_umbral_no_hay_escala(self):
        """Solo siete de veintiocho temperaturas de un equipo corriente traen
        umbral; el resto no se puede situar."""
        self.assertIsNone(self._temp(60.0).heat)

    def test_solo_las_temperaturas(self):
        """Un voltaje a media escala no significa nada, y un ventilador a tope
        es lo que se espera bajo carga."""
        from silux.model import Sensor, SensorKind

        for tipo in (SensorKind.VOLTAGE, SensorKind.FAN, SensorKind.POWER):
            with self.subTest(tipo=tipo):
                s = Sensor(key="k", chip="c", device="d", label="l",
                           kind=tipo, value=50.0, critical=60.0)
                self.assertIsNone(s.heat)

    def test_manda_el_critico_sobre_el_alto(self):
        """`high` es donde el fabricante se incomoda y `critical` donde el
        equipo se apaga solo: la escala se mide contra el segundo."""
        sensor = self._temp(80.0, high=70.0, crit=100.0)
        self.assertLess(sensor.heat, 1.0)

    def test_un_sensor_sin_lectura_no_tiene_calor(self):
        self.assertIsNone(self._temp(None, crit=90.0).heat)


class TestLaBateriaNoSaleDosVeces(unittest.TestCase):
    """En un portátil, la batería cuelga de hwmon y de power_supply.

    Lo trajo un ThinkPad T14: el árbol enseñaba «Alimentación · BAT0» y
    «Batería» como dos aparatos distintos con exactamente las mismas cifras
    —11,384 V y 9,1 W— y los dos puertos USB-C repetidos igual. De 55 sensores,
    seis estaban contados dos veces.

    Se queda la lectura de `power_supply` porque ahí el kernel dice qué es cada
    archivo: sale «Tensión» y no «Tensión 0», que es como lo nombra hwmon.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        parche = mock.patch.object(hwmon, "POWER_SUPPLY", self.raiz)
        parche.start()
        self.addCleanup(parche.stop)

    def _energia(self, nombre, **campos):
        carpeta = self.raiz / nombre
        carpeta.mkdir(parents=True, exist_ok=True)
        for clave, valor in campos.items():
            (carpeta / clave).write_text(f"{valor}\n", encoding="utf-8")

    def test_un_chip_que_también_está_en_power_supply_se_salta(self):
        self._energia("BAT0", voltage_now=11_384_000, power_now=9_100_000)
        self.assertTrue(hwmon._tambien_en_power_supply("BAT0"))

    def test_un_chip_normal_no(self):
        self.assertFalse(hwmon._tambien_en_power_supply("coretemp"))

    def test_una_carpeta_sin_los_valores_no_cuenta(self):
        """Si power_supply no publica nada legible, saltarse el chip de hwmon
        perdería el dato en vez de deduplicarlo."""
        self._energia("BAT9", capacity=80)
        self.assertFalse(hwmon._tambien_en_power_supply("BAT9"))

    def test_el_puerto_usbc_también_se_deduplica(self):
        self._energia("ucsi-source-psy-USBC000:001", voltage_now=0,
                      current_now=0)
        self.assertTrue(
            hwmon._tambien_en_power_supply("ucsi-source-psy-USBC000:001"))
