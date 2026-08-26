"""El decodificador de SPD, contra el volcado de un módulo real.

El fixture es el chip SPD de un Crucial CT8G4DFRA32A —un DDR4-3200 corriente—
con el número de serie puesto a cero. Un volcado real vale más que cualquier
tabla inventada: los desplazamientos de este formato son fáciles de leer mal,
y un byte de más no falla, simplemente enseña otra cifra.
"""

import pathlib
import struct
import unittest
from unittest import mock

from silux import spd

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ddr4-crucial-3200.spd"


class TestModuloReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()
        cls.info = spd.decode(cls.raw, address="10-0050", slot=0)

    def test_identifica_el_formato(self):
        self.assertTrue(self.info.decoded)
        self.assertEqual(self.info.dram_type, "DDR4")
        self.assertEqual(self.info.module_type, "UDIMM")

    def test_referencia_y_fabricantes(self):
        self.assertEqual(self.info.part_number, "CT8G4DFRA32A.M8FR")
        self.assertEqual(self.info.manufacturer, "Crucial")
        # Quien vende el módulo y quien fabrica el silicio no son lo mismo.
        self.assertEqual(self.info.dram_manufacturer, "Micron")

    def test_velocidad_catalogada(self):
        """Este módulo va a 2667 en su equipo, pero está catalogado a 3200."""
        self.assertEqual(self.info.jedec.speed_mts, 3200)
        self.assertEqual(self.info.rated_mts, 3200)

    def test_temporizaciones_con_el_ajuste_fino(self):
        # Ignorar los offsets finos con signo da CL21 en vez de CL22.
        self.assertEqual(self.info.jedec.cl, 22)
        self.assertEqual(self.info.jedec.trcd, 22)
        self.assertEqual(self.info.jedec.trp, 22)
        self.assertEqual(self.info.jedec.tras, 51)
        self.assertEqual(self.info.jedec.summary, "22-22-22-51")

    def test_organizacion(self):
        self.assertEqual(self.info.ranks, 1)
        self.assertEqual(self.info.device_width, 8)
        self.assertEqual(self.info.bus_width, 64)
        self.assertEqual(self.info.ecc_bits, 0)

    def test_fecha_en_bcd(self):
        # El año va en BCD: 0x23 son 2023, no 35.
        self.assertEqual(self.info.manufactured, "semana 37 de 2023")

    def test_este_modulo_no_trae_xmp(self):
        self.assertIsNone(self.info.xmp_revision)
        self.assertEqual(self.info.profiles, ())


class TestCodigosJedec(unittest.TestCase):
    def test_el_primer_byte_cuenta_continuaciones_no_bancos(self):
        # 0x85 = paridad + 5 continuaciones -> banco 6. Leerlo como número
        # suelto daría el banco 133 y ningún fabricante.
        self.assertEqual(spd._vendor(0x85, 0x9B), "Crucial")
        self.assertEqual(spd._vendor(0x80, 0x2C), "Micron")

    def test_un_codigo_desconocido_no_inventa_nada(self):
        self.assertIsNone(spd._vendor(0x7F, 0x01))


class TestFechas(unittest.TestCase):
    def test_bcd(self):
        self.assertEqual(spd._date(0x21, 0x32), "semana 32 de 2021")
        self.assertEqual(spd._date(0x23, 0x01), "semana 1 de 2023")

    def test_valores_imposibles(self):
        self.assertIsNone(spd._date(0x00, 0x00))
        self.assertIsNone(spd._date(0x2A, 0x10))        # nibble no BCD
        self.assertIsNone(spd._date(0x21, 0x99))        # semana 99


class TestPlausibilidad(unittest.TestCase):
    """La estructura de XMP no está publicada, así que todo lo decodificado
    pasa un filtro antes de enseñarse."""

    def test_una_velocidad_absurda_se_descarta(self):
        self.assertFalse(spd.Timings(name="XMP 1", speed_mts=99999).plausible)
        self.assertFalse(spd.Timings(name="XMP 1", speed_mts=100).plausible)

    def test_una_latencia_absurda_se_descarta(self):
        self.assertFalse(spd.Timings(name="XMP 1", speed_mts=3200, cl=200).plausible)

    def test_un_perfil_razonable_pasa(self):
        self.assertTrue(spd.Timings(name="XMP 1", speed_mts=3600, cl=16).plausible)

    def test_resumen_sin_datos(self):
        self.assertEqual(spd.Timings(name="x", speed_mts=3200).summary, "—")


class TestCapacidadSinPermisos(unittest.TestCase):
    """La capacidad sale del propio chip del módulo, que se lee sin ser root.

    Hasta ahora solo la daba la tabla SMBIOS, que el kernel reserva al
    administrador. En un equipo donde nadie eleve permisos, esta es la única
    forma de saber cuánta memoria hay en cada zócalo.
    """

    def test_contra_un_modulo_real(self):
        # El fixture es el volcado de un Crucial CT8G4DFRA32A, que es de 8 GB.
        raw = pathlib.Path(FIXTURE).read_bytes()
        self.assertEqual(spd.decode(raw).capacity_bytes, 8 * 1024**3)

    def test_la_misma_cuenta_vale_para_ddr5(self):
        info = spd.decode(construir_ddr5())
        self.assertEqual(info.capacity_bytes, 8 * 1024**3)

    def test_sin_densidad_conocida_no_se_inventa(self):
        info = spd.decode(construir_ddr5(densidad=0))
        self.assertIsNone(info.capacity_bytes)


class TestFormatosNoSoportados(unittest.TestCase):
    def test_ddr3_se_identifica_pero_no_se_decodifica(self):
        # DDR4 y DDR5 sí se decodifican; lo anterior se reconoce y se dice.
        raw = bytearray(512)
        raw[2] = 0x0B                                  # DDR3
        info = spd.decode(bytes(raw))
        self.assertEqual(info.dram_type, "DDR3")
        self.assertFalse(info.decoded)
        self.assertIsNone(info.jedec)

    def test_un_volcado_truncado_no_revienta(self):
        info = spd.decode(b"\x23\x11\x0c")
        self.assertFalse(info.decoded)
        self.assertIsNone(info.rated_mts)

    def test_un_volcado_vacio_no_revienta(self):
        self.assertFalse(spd.decode(b"").decoded)


class TestEmparejado(unittest.TestCase):
    """Pegar cada lectura de SPD al módulo de SMBIOS que le corresponde."""

    def setUp(self):
        from silux.model import MemoryModule
        from silux.providers.base import Draft
        from silux.providers.spd_modules import SpdModules

        self.Draft = Draft
        self.MemoryModule = MemoryModule
        self.merge = SpdModules._merge
        self.lectura = spd.decode(FIXTURE.read_bytes(), address="10-0050", slot=0)

    def test_casa_por_referencia(self):
        draft = self.Draft()
        otra = spd.decode(FIXTURE.read_bytes(), address="10-0052", slot=2)
        draft.modules = [
            self.MemoryModule(locator="DIMM A", populated=True, part_number="OTRO-MODULO"),
            self.MemoryModule(locator="DIMM B", populated=True,
                              part_number="CT8G4DFRA32A.M8FR"),
        ]
        # La segunda lectura casa por referencia con el segundo módulo.
        self.merge(draft, [otra, self.lectura])
        self.assertIsNotNone(draft.modules[1].spd)

    def test_los_zocalos_vacios_se_saltan(self):
        draft = self.Draft()
        draft.modules = [
            self.MemoryModule(locator="DIMM A", populated=False),
            self.MemoryModule(locator="DIMM B", populated=True),
        ]
        self.merge(draft, [self.lectura])
        self.assertIsNone(draft.modules[0].spd)
        self.assertIsNotNone(draft.modules[1].spd)

    def test_sin_modulos_de_smbios_no_hace_nada(self):
        draft = self.Draft()
        self.merge(draft, [self.lectura])
        self.assertEqual(draft.modules, [])


class TestVelocidadReal(unittest.TestCase):
    def test_detecta_un_modulo_por_debajo_de_su_velocidad(self):
        from silux.model import MemoryModule

        info = spd.decode(FIXTURE.read_bytes())
        modulo = MemoryModule(populated=True, speed_mts=2667,
                              configured_mts=2667, spd=info)
        self.assertEqual(modulo.rated_mts, 3200)
        self.assertTrue(modulo.underclocked)

    def test_sin_spd_se_fia_de_smbios(self):
        from silux.model import MemoryModule

        modulo = MemoryModule(populated=True, speed_mts=3200, configured_mts=3200)
        self.assertEqual(modulo.rated_mts, 3200)
        self.assertFalse(modulo.underclocked)


if __name__ == "__main__":
    unittest.main()


def construir_ddr5(*, tck_ps=357, taa=16250, trcd=16250, trp=16250,
                   tras=32000, trc=48000, densidad=4, dies=0, io_width=2,
                   ranks=1, canales=2, ancho_canal=2, ecc=0, tipo_modulo=0x02,
                   fabricante=(0x80, 0x2C), part="CT16G56C46U5.M8G1",
                   anno=0x24, semana=0x32, xmp=False, expo=False,
                   longitud=1024) -> bytes:
    """Un SPD de DDR5 armado a mano, con los valores que se quieran probar.

    Los offsets salen de JEDEC JESD400-5. Se construye en vez de guardar el
    volcado de un módulo real porque así se pueden probar configuraciones que
    no se tienen delante, y porque un volcado real lleva el número de serie del
    equipo de alguien.
    """
    b = bytearray(longitud)
    b[0], b[1] = 0x30, 0x10
    b[2] = 0x12                                   # la firma de DDR5
    b[3] = tipo_modulo
    b[4] = (dies << 5) | densidad
    b[6] = io_width << 5
    for offset, valor in ((20, tck_ps), (24, taa), (26, trcd), (28, trp),
                          (30, tras), (32, trc)):
        b[offset] = valor & 0xFF
        b[offset + 1] = (valor >> 8) & 0xFF
    b[234] = (ranks - 1) << 3
    b[235] = ((canales - 1) << 5) | (ecc << 3) | ancho_canal
    if longitud > 553:
        b[512], b[513] = fabricante
        b[515], b[516] = anno, semana
        b[521:521 + len(part)] = part.encode()
        b[552], b[553] = 0x80, 0x2C
    if xmp and longitud > 642:
        b[640], b[641] = 0x0C, 0x4A
    if expo and longitud > 836:
        b[832:836] = b"EXPO"
    return bytes(b)


class TestDdr5(unittest.TestCase):
    """El formato de DDR5, que no se parece al de DDR4 en casi nada."""

    def setUp(self):
        self.info = spd.decode(construir_ddr5(), address="0-0050", slot=0)

    def test_reconoce_el_tipo(self):
        self.assertEqual(self.info.dram_type, "DDR5")
        self.assertEqual(self.info.module_type, "UDIMM")
        self.assertTrue(self.info.decoded)

    def test_velocidad_desde_los_picosegundos(self):
        # DDR5 guarda el tiempo de ciclo en picosegundos de dieciséis bits, sin
        # la parte fina que tenía DDR4. Un tCK de 357 ps son 5600 MT/s.
        self.assertEqual(self.info.jedec.speed_mts, 5600)

    def test_las_latencias_se_redondean_hacia_arriba(self):
        # 16250 ps entre 357 son 45,5 ciclos. La memoria no puede responder
        # antes de tiempo, así que es un CL46: redondear al más cercano daría
        # un CL45 que no existe.
        self.assertEqual(self.info.jedec.cl, 46)

    def test_voltaje_de_ddr5(self):
        self.assertEqual(self.info.jedec.voltage_v, 1.1)

    def test_identidad_del_modulo(self):
        self.assertEqual(self.info.manufacturer, "Micron")
        self.assertEqual(self.info.part_number, "CT16G56C46U5.M8G1")
        self.assertEqual(self.info.manufactured, "semana 32 de 2024")

    def test_los_dos_subcanales(self):
        # Un DIMM de DDR5 se parte en dos canales de 32 bits. Sin decirlo, un
        # bus de 64 bits con chips de 16 no cuadra.
        self.assertEqual(self.info.channels, 2)
        self.assertEqual(self.info.bus_width, 64)
        self.assertEqual(self.info.device_width, 16)

    def test_la_capacidad_sale_del_spd_sin_permisos(self):
        # 16 Gb por chip, cuatro chips por rank, un rank: 8 GiB. El mismo
        # número que da SMBIOS, que sí pide ser administrador.
        self.assertEqual(self.info.capacity_bytes, 8 * 1024**3)

    def test_un_modulo_de_dos_ranks_y_chips_grandes(self):
        info = spd.decode(construir_ddr5(densidad=6, ranks=2))   # 32 Gb por chip
        self.assertEqual(info.ranks, 2)
        self.assertEqual(info.capacity_bytes, 32 * 1024**3)

    def test_ecc(self):
        info = spd.decode(construir_ddr5(ecc=2))
        self.assertEqual(info.ecc_bits, 16)
        self.assertTrue(info.has_ecc if hasattr(info, "has_ecc") else info.ecc_bits)


class TestPerfilesDeDdr5(unittest.TestCase):
    """Se reconoce que están; sus cifras no se inventan."""

    def test_detecta_xmp_3(self):
        info = spd.decode(construir_ddr5(xmp=True))
        self.assertEqual(info.overclock_profiles, ("XMP 3.0",))

    def test_detecta_expo(self):
        info = spd.decode(construir_ddr5(expo=True))
        self.assertEqual(info.overclock_profiles, ("EXPO",))

    def test_un_modulo_puede_traer_los_dos(self):
        info = spd.decode(construir_ddr5(xmp=True, expo=True))
        self.assertEqual(info.overclock_profiles, ("XMP 3.0", "EXPO"))

    def test_sin_perfiles(self):
        self.assertEqual(spd.decode(construir_ddr5()).overclock_profiles, ())

    def test_no_se_inventan_temporizaciones(self):
        # Los formatos de XMP 3.0 y EXPO no son públicos como el de JEDEC.
        # Reconocer la firma es seguro; leer sus cifras a ojo, no.
        info = spd.decode(construir_ddr5(xmp=True, expo=True))
        self.assertEqual(info.profiles, ())


class TestDdr5Roto(unittest.TestCase):
    def test_un_chip_cortado_no_revienta(self):
        # Algunos controladores devuelven solo el primer bloque.
        info = spd.decode(construir_ddr5(longitud=256))
        self.assertEqual(info.dram_type, "DDR5")
        self.assertEqual(info.jedec.speed_mts, 5600)
        self.assertIsNone(info.part_number)

    def test_un_tiempo_de_ciclo_a_cero(self):
        info = spd.decode(construir_ddr5(tck_ps=0))
        self.assertIsNone(info.jedec)

    def test_una_velocidad_imposible_se_descarta(self):
        # 20 ps de ciclo serían 100 000 MT/s: el chip está mal leído.
        info = spd.decode(construir_ddr5(tck_ps=20))
        self.assertIsNone(info.jedec)


class TestDiagnosticoDelBus(unittest.TestCase):
    """Por qué no se lee el SPD, que no siempre es por lo mismo.

    Antes se contestaba siempre «carga ee1004», y en la mayoría de las placas
    AMD ese consejo no sirve: el módulo ya está y lo que falta es el bus. Cada
    causa tiene su solución y no se parecen entre sí.
    """

    def _con(self, controlador: bool, bus: bool):
        return (mock.patch.object(spd, "_hay_controlador_smbus", lambda: controlador),
                mock.patch.object(spd, "_hay_bus_de_memoria", lambda: bus))

    def test_sin_controlador_no_hay_nada_que_hacer(self):
        with self._con(False, False)[0], self._con(False, False)[1]:
            motivo, solucion = spd.diagnostico()
        self.assertIn("no expone", motivo)
        self.assertIn("No hay forma", solucion)

    def test_con_controlador_pero_sin_bus_lo_reserva_el_firmware(self):
        with self._con(True, False)[0], self._con(True, False)[1]:
            motivo, solucion = spd.diagnostico()
        self.assertIn("firmware", motivo)
        self.assertIn("acpi_enforce_resources=lax", solucion)

    def test_con_bus_solo_falta_el_modulo(self):
        with self._con(True, True)[0], self._con(True, True)[1]:
            motivo, solucion = spd.diagnostico()
        self.assertIn("driver", motivo)
        self.assertIn("ee1004", solucion)
        self.assertIn("spd5118", solucion)

    def test_los_buses_de_la_grafica_no_cuentan(self):
        # Una tarjeta gráfica registra buses i2c para hablar con los monitores
        # y con sus sensores. Ninguno lleva a la memoria, así que contarlos
        # haría creer que el bus está listo cuando no lo está.
        import pathlib as _p
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _p.Path(tmp)
            for n, nombre in enumerate(("AMDGPU SMU 0", "AMDGPU DM i2c hw bus 0")):
                bus = raiz / f"i2c-{n}"
                bus.mkdir()
                (bus / "name").write_text(nombre)
            with mock.patch.object(spd, "SYS_I2C", raiz):
                self.assertFalse(spd._hay_bus_de_memoria())
            # Y con uno de verdad, sí.
            real = raiz / "i2c-9"
            real.mkdir()
            (real / "name").write_text("SMBus PIIX4 adapter port 0")
            with mock.patch.object(spd, "SYS_I2C", raiz):
                self.assertTrue(spd._hay_bus_de_memoria())
