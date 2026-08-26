"""El árbol de sensores: agrupado, orden y nombres de los aparatos."""

import os
import unittest

from cpuz.model import (
    Board, CpuInfo, CpuType, Power, Sensor, SensorKind, Snapshot,
    short_brand, short_vendor,
)
from cpuz.providers.base import Draft
from cpuz.providers.derived import DerivedSensors
from cpuz.tracking import Tracker

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
        self.assertEqual(set(arbol["CPU"]), {"Voltajes", "Temperaturas", "Potencias", "Uso"})

    def test_las_ramas_van_en_el_orden_de_hwmonitor(self):
        # Voltajes primero, luego temperaturas, ventiladores, potencias…
        self.assertEqual(
            list(self._snapshot().sensor_tree()["CPU"]),
            ["Voltajes", "Temperaturas", "Potencias", "Uso"],
        )

    def test_dentro_de_una_rama_manda_el_campo_order(self):
        uso = self._snapshot().sensor_tree()["CPU"]["Uso"]
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
        from cpuz.ui import theme
        from cpuz.ui.widgets import SensorTree

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
