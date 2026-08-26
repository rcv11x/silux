"""La tabla de telemetría del firmware de una Radeon.

Las tablas se arman a mano porque el formato ha cambiado varias veces y hay que
poder probar versiones que no se tienen delante. Lo que más importa aquí es la
prueba de que una versión desconocida se rechaza: leerla con las posiciones de
otra no da error, da números creíbles y falsos.
"""

import struct
import unittest

from silux import gpumetrics

# Los valores reales de una RX 9070 XT en reposo, para poder contrastarlos.
CAMPOS = {
    "temp_edge": 56, "temp_hotspot": 58, "temp_mem": 74,
    "temp_vr_gfx": 58, "temp_vr_soc": 58, "temp_vr_mem": 60,
    "gfx_activity": 13, "memory_activity": 2, "video_activity": 0,
    "socket_power": 52,
    "gfx_clock_average": 1609, "soc_clock_average": 0xFFFF,
    "memory_clock_average": 2505,
    "gfx_clock": 1611, "soc_clock": 1280, "memory_clock": 1258,
    "throttle_status": 0, "fan_rpm": 0, "link_width": 16, "link_speed": 160,
    "voltage_soc": 845, "voltage_gfx": 696, "voltage_mem": 1350,
    "throttle_independent": 0,
}


def tabla(version=(1, 3), tamano=120, **cambios) -> bytes:
    formato, contenido = version
    crudo = bytearray(tamano)
    struct.pack_into("<HBB", crudo, 0, tamano, formato, contenido)
    posiciones = gpumetrics.VERSIONES.get(version, gpumetrics.VERSIONES[(1, 3)])
    for nombre, valor in {**CAMPOS, **cambios}.items():
        if nombre not in posiciones:
            continue
        tipo, sitio = posiciones[nombre]
        if sitio + struct.calcsize(tipo) <= tamano:
            struct.pack_into("<" + tipo, crudo, sitio, valor)
    return bytes(crudo)


class TestLectura(unittest.TestCase):
    def setUp(self):
        self.m = gpumetrics.parse(tabla())

    def test_version(self):
        self.assertEqual(self.m.version, "1.3")

    def test_temperaturas_incluidas_las_de_los_reguladores(self):
        self.assertEqual((self.m.temp_edge_c, self.m.temp_hotspot_c, self.m.temp_memory_c),
                         (56.0, 58.0, 74.0))
        # Estas tres no están en hwmon: solo las cuenta el firmware.
        self.assertEqual((self.m.temp_vr_gfx_c, self.m.temp_vr_soc_c, self.m.temp_vr_mem_c),
                         (58.0, 58.0, 60.0))

    def test_reloj_de_memoria_base_y_efectivo(self):
        self.assertEqual(self.m.memory_clock_hz, 1_258_000_000)
        self.assertEqual(self.m.memory_clock_effective_hz, 2_505_000_000)

    def test_enlace_en_decimas_de_gigatransferencia(self):
        # 160 son 16,0 GT/s, o sea PCIe 4.0.
        self.assertEqual(self.m.link_speed_gts, 16.0)
        self.assertEqual(self.m.link_width, 16)

    def test_voltajes_en_milivoltios(self):
        self.assertEqual((self.m.voltage_gfx_v, self.m.voltage_soc_v,
                          self.m.voltage_memory_v), (0.696, 0.845, 1.35))

    def test_una_tarjeta_sin_frenos(self):
        self.assertFalse(self.m.throttled)
        self.assertEqual(self.m.throttle_reasons, ())

    def test_un_campo_a_todo_unos_es_que_no_se_mide(self):
        # 0xFFFF no son 65 535 MHz: es «este chip no lo cuenta».
        self.assertIsNone(self.m.soc_clock_hz if False else
                          gpumetrics.parse(tabla(soc_clock=0xFFFF)).soc_clock_hz)


class TestFrenos(unittest.TestCase):
    def test_nombra_el_motivo(self):
        m = gpumetrics.parse(tabla(throttle_independent=1 << 10))
        self.assertTrue(m.throttled)
        self.assertEqual(m.throttle_reasons, ("temperatura del punto caliente",))

    def test_varios_motivos_a_la_vez(self):
        m = gpumetrics.parse(tabla(throttle_independent=(1 << 0) | (1 << 7)))
        self.assertEqual(len(m.throttle_reasons), 2)

    def test_no_repite_un_motivo_que_tiene_dos_bits(self):
        # Los bits 14 y 15 son los dos reguladores de memoria y se llaman igual.
        m = gpumetrics.parse(tabla(throttle_independent=(1 << 14) | (1 << 15)))
        self.assertEqual(m.throttle_reasons, ("temperatura del regulador de memoria",))

    def test_sin_el_campo_independiente_se_sabe_que_hay_freno_pero_no_cual(self):
        # Las v1.0 a v1.2 solo traen el estado que depende del modelo de chip.
        m = gpumetrics.parse(tabla(version=(1, 1), tamano=96, throttle_status=0x40))
        self.assertTrue(m.throttled)
        self.assertEqual(m.throttle_reasons, ())


class TestVersiones(unittest.TestCase):
    def test_una_version_desconocida_se_rechaza(self):
        # Las v1.4 en adelante reordenaron los campos. Leerlas con las
        # posiciones de una v1.3 daría cifras creíbles y equivocadas.
        self.assertIsNone(gpumetrics.parse(tabla(version=(1, 4))))
        self.assertIsNone(gpumetrics.parse(tabla(version=(2, 1))))

    def test_pero_su_version_si_se_puede_saber(self):
        self.assertEqual(gpumetrics.version_of(tabla(version=(1, 4))), "1.4")

    def test_una_v1_0_no_llega_a_los_voltajes(self):
        m = gpumetrics.parse(tabla(version=(1, 0), tamano=80))
        self.assertEqual(m.temp_edge_c, 56.0)
        self.assertIsNone(m.voltage_gfx_v)

    def test_una_tabla_cortada_no_lee_de_mas(self):
        # El firmware dice 120 bytes pero solo llegan 40: lo que hay detrás no
        # es que valga cero, es que no está.
        m = gpumetrics.parse(tabla()[:40])
        self.assertEqual(m.temp_edge_c, 56.0)
        self.assertIsNone(m.gfx_clock_hz)

    def test_basura(self):
        self.assertIsNone(gpumetrics.parse(b""))
        self.assertIsNone(gpumetrics.parse(b"\x00\x00"))


if __name__ == "__main__":
    unittest.main()
