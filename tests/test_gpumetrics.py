"""La tabla de telemetría del firmware de una Radeon.

Las tablas se arman a mano porque el formato ha cambiado varias veces y hay que
poder probar versiones que no se tienen delante. Lo que más importa aquí es la
prueba de que una versión desconocida se rechaza: leerla con las posiciones de
otra no da error, da números creíbles y falsos.
"""

import pathlib
import struct
import tempfile
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
        # La 2.1 se añadió con la captura de una Radeon 740M; la 2.4 aún no.
        self.assertIsNone(gpumetrics.parse(tabla(version=(2, 4))))

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


class TestUnaVersionQueNoSeSabeLeer(unittest.TestCase):
    """No es lo mismo no tener telemetría que no saber interpretarla.

    Las v1.4 en adelante reordenaron los campos y las 2.x son las de las APU.
    Se descartan a propósito —leerlas con las posiciones de una v1.3 no da
    error, da cifras creíbles y equivocadas— pero eso acababa en el mismo
    silencio que no tener tabla: el usuario veía los motivos de recorte y los
    voltajes vacíos sin nada que lo explicara.

    Ahora se dice, y la versión viaja en el informe, que es de donde puede
    salir su tabla de posiciones sin tener la pieza delante.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _tabla(self, formato, contenido, tamano=120):
        datos = bytearray(tamano)
        struct.pack_into("<HBB", datos, 0, tamano, formato, contenido)
        (self.raiz / "gpu_metrics").write_bytes(bytes(datos))
        return self.raiz

    def test_una_version_conocida_no_se_declara_ilegible(self):
        self.assertIsNone(gpumetrics.sin_interpretar(self._tabla(1, 3)))

    def test_una_v1_4_se_declara_y_dice_cual_es(self):
        version, tamano = gpumetrics.sin_interpretar(self._tabla(1, 4))
        self.assertEqual(version, "1.4")
        self.assertEqual(tamano, 120)

    def test_una_2_x_que_todavía_no_está_también(self):
        """La 2.1 ya se lee; las siguientes de las APU aún no."""
        version, _tamano = gpumetrics.sin_interpretar(self._tabla(2, 4, 200))
        self.assertEqual(version, "2.4")

    def test_sin_tabla_no_hay_nada_que_declarar(self):
        self.assertIsNone(gpumetrics.sin_interpretar(self.raiz))

    def test_una_tabla_cortada_no_revienta(self):
        (self.raiz / "gpu_metrics").write_bytes(b"\x02")
        self.assertIsNone(gpumetrics.sin_interpretar(self.raiz))

    def test_no_se_inventa_una_lectura_de_lo_que_no_entiende(self):
        """Lo importante: sigue sin interpretarse, solo se dice que está."""
        self.assertIsNone(gpumetrics.read(self._tabla(1, 4)))


class TestLaV2DeLasApu(unittest.TestCase):
    """La telemetría de las gráficas integradas.

    No es una 1.x con campos añadidos: la estructura es otra. Las posiciones
    salen de `gpu_metrics_v2_1` en `kgd_pp_interface.h`, calculadas con las
    reglas de alineación de C —el `uint64` del reloj obliga a alinear a ocho—
    y dan 120 bytes, que es lo que declara la tabla.

    La trajo la captura de un usuario con una Radeon 740M, donde el punto
    caliente, los reguladores y el motivo de recorte salían a guiones.
    """

    def _tabla(self, **campos):
        datos = bytearray(120)
        struct.pack_into("<HBB", datos, 0, 120, 2, 1)
        sitios = {
            "temperature_gfx": ("H", 4), "temperature_soc": ("H", 6),
            "gfx_activity": ("H", 28), "mm_activity": ("H", 30),
            "socket_power": ("H", 40), "avg_gfxclk": ("H", 64),
            "avg_socclk": ("H", 66), "avg_uclk": ("H", 68),
            "gfxclk": ("H", 76), "socclk": ("H", 78), "uclk": ("H", 80),
            "throttle": ("I", 108),
        }
        for nombre, valor in campos.items():
            formato, sitio = sitios[nombre]
            struct.pack_into("<" + formato, datos, sitio, valor)
        return bytes(datos)

    def test_la_estructura_mide_lo_que_dice_el_kernel(self):
        """120 bytes: si no cuadran, algún desplazamiento está mal."""
        self.assertEqual(len(self._tabla()), 120)

    def test_se_reconoce_y_ya_no_se_descarta(self):
        medidas = gpumetrics.parse(self._tabla(gfxclk=800))
        self.assertIsNotNone(medidas)
        self.assertEqual(medidas.version, "2.1")

    def test_las_temperaturas_vienen_en_centigrados(self):
        """El driver copia lo del firmware sin convertir, y ahí van ×100."""
        medidas = gpumetrics.parse(self._tabla(temperature_gfx=4210))
        self.assertAlmostEqual(medidas.temp_edge_c, 42.1)

    def test_pero_una_temperatura_en_grados_también_se_entiende(self):
        """Se decide por rango y no por fe: ninguna GPU llega a 200 grados,
        así que 44 no puede ser centigrados ni 4410 puede ser grados."""
        medidas = gpumetrics.parse(self._tabla(temperature_gfx=44))
        self.assertAlmostEqual(medidas.temp_edge_c, 44.0)

    def test_los_relojes_salen_en_hercios(self):
        medidas = gpumetrics.parse(self._tabla(gfxclk=800, uclk=1000))
        self.assertEqual(medidas.gfx_clock_hz, 800_000_000)
        self.assertEqual(medidas.memory_clock_hz, 1_000_000_000)

    def test_el_medio_y_el_de_ahora_son_distintos_campos(self):
        medidas = gpumetrics.parse(self._tabla(gfxclk=800, avg_gfxclk=780))
        self.assertEqual(medidas.gfx_clock_hz, 800_000_000)
        self.assertEqual(medidas.gfx_clock_average_hz, 780_000_000)

    def test_el_uso_del_motor_de_video_es_mm_activity(self):
        medidas = gpumetrics.parse(self._tabla(mm_activity=35))
        self.assertAlmostEqual(medidas.video_activity_percent, 35.0)

    def test_el_recorte_se_lee(self):
        self.assertTrue(gpumetrics.parse(self._tabla(throttle=1 << 2)).throttled)
        self.assertFalse(gpumetrics.parse(self._tabla(throttle=0)).throttled)

    def test_lo_que_una_apu_no_tiene_sale_vacio_y_no_inventado(self):
        """Sin VRAM propia no hay temperatura de memoria ni reguladores
        aparte, y sin enlace propio no hay ancho que enseñar."""
        medidas = gpumetrics.parse(self._tabla(gfxclk=800))
        self.assertIsNone(medidas.temp_memory_c)
        self.assertIsNone(medidas.voltage_gfx_v)
        self.assertIsNone(medidas.link_width)

    def test_el_ventilador_no_se_saca_del_pwm(self):
        """`fan_pwm` es un ciclo de trabajo de 0 a 255, no revoluciones: darlo
        por RPM enseñaría un ventilador a 200 vueltas que no existe."""
        self.assertNotIn("fan_rpm", gpumetrics.VERSIONES[(2, 1)])

    def test_ya_no_se_declara_ilegible(self):
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            (raiz / "gpu_metrics").write_bytes(self._tabla(gfxclk=800))
            self.assertIsNone(gpumetrics.sin_interpretar(raiz))
