"""El decodificador de SPD, contra el volcado de un módulo real.

El fixture es el chip SPD de un Crucial CT8G4DFRA32A —un DDR4-3200 corriente—
con el número de serie puesto a cero. Un volcado real vale más que cualquier
tabla inventada: los desplazamientos de este formato son fáciles de leer mal,
y un byte de más no falla, simplemente enseña otra cifra.
"""

import pathlib
import struct
import unittest

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


class TestFormatosNoSoportados(unittest.TestCase):
    def test_ddr5_se_identifica_pero_no_se_decodifica(self):
        raw = bytearray(512)
        raw[2] = 0x12                                  # DDR5
        info = spd.decode(bytes(raw))
        self.assertEqual(info.dram_type, "DDR5")
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
