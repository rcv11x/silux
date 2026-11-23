"""Avisar cuando un sensor se pasa, y sobre todo no avisar cuando no.

Un aviso falso gasta más confianza de la que gana uno acertado: quien ve seis
alarmas con la placa a 34 grados deja de mirarlas todas, incluida la que un
día importe. Por eso aquí se prueba más lo que NO tiene que saltar.
"""

import unittest

from silux.model import Sensor, SensorKind
from silux.providers.hwmon import _thresholds


def _sensor(**campos) -> Sensor:
    base = dict(key="k", chip="k10temp", device="CPU", label="Tctl",
                kind=SensorKind.TEMPERATURE, value=50.0)
    base.update(campos)
    return Sensor(**base)


class TestNiveles(unittest.TestCase):
    def test_por_debajo_de_todo_esta_bien(self):
        self.assertEqual(_sensor(value=45.0, high=80.0, critical=95.0).alarm_level, "ok")

    def test_pasado_el_alto_avisa(self):
        self.assertEqual(_sensor(value=85.0, high=80.0, critical=95.0).alarm_level, "alto")

    def test_y_el_critico_es_otra_cosa(self):
        """No es lo mismo incomodar al fabricante que hacer que el equipo se
        proteja solo, y pintarlos igual deja sin saber si hay que actuar."""
        self.assertEqual(_sensor(value=97.0, high=80.0, critical=95.0).alarm_level,
                         "crítico")

    def test_sin_umbral_no_se_avisa_de_nada(self):
        self.assertEqual(_sensor(value=200.0).alarm_level, "ok")

    def test_un_sensor_sin_lectura_tampoco(self):
        self.assertEqual(_sensor(value=None, high=10.0).alarm_level, "ok")


class TestUmbralesQueNoValen(unittest.TestCase):
    """Los chips devuelven de fábrica los campos que nadie configuró."""

    def test_el_centinela_de_un_nvme(self):
        """65261.85 son 0xFFFF en kelvin: un umbral que nunca se alcanza. Se
        descarta y no entra otro en su lugar: sin límite, sin color."""
        salida = _thresholds(SensorKind.TEMPERATURE, -273.15, 65261.85, None, "nvme")
        self.assertEqual((salida["high"], salida["critical"]), (None, None))

    def test_y_en_un_chip_desconocido_se_queda_sin_umbral(self):
        salida = _thresholds(SensorKind.TEMPERATURE, None, 65261.85, None, "it8688")
        self.assertIsNone(salida["high"])

    def test_un_minimo_por_encima_del_maximo(self):
        """Un nct6798 publica min=127 y max=127 en sus seis temperaturas, y con
        eso una placa a 34 grados quedaba «por debajo del mínimo»."""
        salida = _thresholds(SensorKind.TEMPERATURE, 127.0, 127.0, None, "it8688")
        self.assertIsNone(salida["low"])
        self.assertIsNone(salida["high"])

    def test_de_los_ventiladores_no_se_avisa(self):
        """Que uno vaya a tope es lo normal bajo carga, y que esté parado
        también: casi todas las tarjetas los paran en reposo."""
        salida = _thresholds(SensorKind.FAN, 0.0, 3650.0, None, "amdgpu")
        self.assertEqual(set(salida.values()), {None})

    def test_los_buenos_se_respetan(self):
        salida = _thresholds(SensorKind.TEMPERATURE, None, 84.85, 84.85, "nvme")
        self.assertEqual((salida["high"], salida["critical"]), (84.85, 84.85))


class TestNoLimitIsMadeUp(unittest.TestCase):
    """A chip that declares no limits keeps none: a made-up one painted a
    machine's normal work as a warning (a Ryzen's Tctl at 80 °C, amber)."""

    def test_for_any_chip(self):
        for chip in ("k10temp", "zenpower", "coretemp", "nvme", "drivetemp", "it8688"):
            with self.subTest(chip=chip):
                salida = _thresholds(SensorKind.TEMPERATURE, None, None, None, chip)
                self.assertEqual((salida["high"], salida["critical"]), (None, None))

    def test_a_zero_is_no_limit(self):
        salida = _thresholds(SensorKind.TEMPERATURE, None, 0.0, 0.0, "nvme")
        self.assertEqual((salida["high"], salida["critical"]), (None, None))

    def test_what_the_hardware_declares_stays(self):
        salida = _thresholds(SensorKind.TEMPERATURE, None, 84.0, 100.0, "coretemp")
        self.assertEqual((salida["high"], salida["critical"]), (84.0, 100.0))


class TestEsteEquipo(unittest.TestCase):
    def test_no_salta_ningun_aviso_en_reposo(self):
        """La prueba que de verdad importa: con el equipo tranquilo, silencio."""
        from tests import muestras
        muestra = muestras.foto_real()
        falsos = [(s.device, s.label, s.value, s.high)
                  for s in muestra.sensors if s.alarm_level != "ok"]
        self.assertEqual(falsos, [], f"avisos falsos: {falsos}")


if __name__ == "__main__":
    unittest.main()
