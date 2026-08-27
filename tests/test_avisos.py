"""Avisar cuando un sensor se pasa, y sobre todo no avisar cuando no.

Un aviso falso gasta más confianza de la que gana uno acertado: quien ve seis
alarmas con la placa a 34 grados deja de mirarlas todas, incluida la que un
día importe. Por eso aquí se prueba más lo que NO tiene que saltar.
"""

import unittest

from silux.model import Sensor, SensorKind
from silux.providers.hwmon import LIMITES_ESTIMADOS, _umbrales


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
        """65261.85 son 0xFFFF en kelvin: un umbral que nunca se alcanza.

        Se descarta, y como el chip es conocido entra el estimado en su lugar,
        que es justo lo que se quiere: un límite que sí se puede cruzar.
        """
        salida = _umbrales(SensorKind.TEMPERATURE, None, 65261.85, None, "nvme")
        self.assertNotEqual(salida["high"], 65261.85)
        self.assertEqual(salida["high"], LIMITES_ESTIMADOS["nvme"][0])
        self.assertTrue(salida["estimated_limits"])

    def test_y_en_un_chip_desconocido_se_queda_sin_umbral(self):
        salida = _umbrales(SensorKind.TEMPERATURE, None, 65261.85, None, "it8688")
        self.assertIsNone(salida["high"])

    def test_un_minimo_por_encima_del_maximo(self):
        """Un nct6798 publica min=127 y max=127 en sus seis temperaturas, y con
        eso una placa a 34 grados quedaba «por debajo del mínimo»."""
        salida = _umbrales(SensorKind.TEMPERATURE, 127.0, 127.0, None, "it8688")
        self.assertIsNone(salida["low"])
        self.assertIsNone(salida["high"])

    def test_de_los_ventiladores_no_se_avisa(self):
        """Que uno vaya a tope es lo normal bajo carga, y que esté parado
        también: casi todas las tarjetas los paran en reposo."""
        salida = _umbrales(SensorKind.FAN, 0.0, 3650.0, None, "amdgpu")
        self.assertEqual(set(salida.values()), {None})

    def test_los_buenos_se_respetan(self):
        salida = _umbrales(SensorKind.TEMPERATURE, None, 84.85, 84.85, "nvme")
        self.assertEqual(salida["high"], 84.85)
        self.assertFalse(salida.get("estimated_limits"))


class TestUmbralesEstimados(unittest.TestCase):
    """De 28 temperaturas de un equipo real, solo 7 traen umbral, y el
    procesador —el que más importa— no trae ninguno."""

    def test_se_ponen_cuando_el_chip_no_los_da(self):
        salida = _umbrales(SensorKind.TEMPERATURE, None, None, None, "k10temp")
        self.assertEqual(salida["high"], LIMITES_ESTIMADOS["k10temp"][0])
        self.assertTrue(salida["estimated_limits"])

    def test_pero_nunca_pisan_a_los_del_hardware(self):
        salida = _umbrales(SensorKind.TEMPERATURE, None, 70.0, None, "k10temp")
        self.assertEqual(salida["high"], 70.0)
        self.assertFalse(salida.get("estimated_limits"))

    def test_no_se_inventan_para_un_chip_desconocido(self):
        salida = _umbrales(SensorKind.TEMPERATURE, None, None, None, "it8688")
        self.assertIsNone(salida["high"])

    def test_ni_para_lo_que_no_sea_temperatura(self):
        """De un voltaje no hay forma de estimar nada: depende del raíl."""
        salida = _umbrales(SensorKind.VOLTAGE, None, None, None, "k10temp")
        self.assertIsNone(salida["high"])

    def test_y_van_del_lado_prudente(self):
        """Tctl llega a 90 en Zen 3 por diseño y no es una avería."""
        alto, critico = LIMITES_ESTIMADOS["k10temp"]
        self.assertGreaterEqual(alto, 85.0)
        self.assertGreater(critico, alto)


class TestEsteEquipo(unittest.TestCase):
    def test_no_salta_ningun_aviso_en_reposo(self):
        """La prueba que de verdad importa: con el equipo tranquilo, silencio."""
        from silux.collector import Collector
        muestra = Collector().snapshot()
        falsos = [(s.device, s.label, s.value, s.high)
                  for s in muestra.sensors if s.alarm_level != "ok"]
        self.assertEqual(falsos, [], f"avisos falsos: {falsos}")


if __name__ == "__main__":
    unittest.main()
