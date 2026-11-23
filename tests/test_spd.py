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

from silux import render, spd

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
        # As JEDEC names them, and the brand on screen.
        self.assertEqual(self.info.manufacturer, "Crucial Technology")
        self.assertEqual(render.maker(self.info.manufacturer), "Crucial")
        # Quien vende el módulo y quien fabrica el silicio no son lo mismo.
        self.assertEqual(render.maker(self.info.dram_manufacturer), "Micron")

    def test_velocidad_catalogada(self):
        """Este módulo va a 2667 en su equipo, pero está catalogado a 3200."""
        self.assertEqual(self.info.jedec.speed_mts, 3200)
        self.assertEqual(self.info.rated_mts, 3200)

    def test_temporizaciones_con_el_ajuste_fino(self):
        # Ignorar los offsets finos con signo da CL21 en vez de CL22.
        self.assertEqual(self.info.jedec.cl, 22)
        self.assertEqual(self.info.jedec.trcd, 22)
        self.assertEqual(self.info.jedec.trp, 22)
        # 32 000 ps entre un ciclo de 625 son 51,2: con 51 el módulo se
        # quedaría en 31,875 ns, por debajo de lo que declara. Es 52, el tRAS
        # de JEDEC para DDR4-3200AA; el 51 que había aquí era el redondeo al
        # más cercano.
        self.assertEqual(self.info.jedec.tras, 52)
        self.assertEqual(self.info.jedec.summary, "22-22-22-52")

    def test_organizacion(self):
        self.assertEqual(self.info.ranks, 1)
        self.assertEqual(self.info.device_width, 8)
        self.assertEqual(self.info.bus_width, 64)
        self.assertEqual(self.info.ecc_bits, 0)

    def test_fecha_en_bcd(self):
        # El año va en BCD: 0x23 son 2023, no 35.
        self.assertEqual((self.info.manufactured_year, self.info.manufactured_week), (2023, 37))

    def test_este_modulo_no_trae_xmp(self):
        self.assertIsNone(self.info.xmp_revision)
        self.assertEqual(self.info.profiles, ())


class TestCodigosJedec(unittest.TestCase):
    def test_el_primer_byte_cuenta_continuaciones_no_bancos(self):
        # 0x85 = paridad + 5 continuaciones -> banco 6. Leerlo como número
        # suelto daría el banco 133 y ningún fabricante.
        from silux import render
        self.assertEqual(render.maker(spd._vendor(0x85, 0x9B)), "Crucial")
        self.assertEqual(render.maker(spd._vendor(0x80, 0x2C)), "Micron")

    def test_un_codigo_desconocido_no_inventa_nada(self):
        self.assertIsNone(spd._vendor(0x7F, 0x01))


class TestFechas(unittest.TestCase):
    def test_bcd(self):
        self.assertEqual(spd._date(0x21, 0x32), {"manufactured_year": 2021, "manufactured_week": 32})
        self.assertEqual(spd._date(0x23, 0x01), {"manufactured_year": 2023, "manufactured_week": 1})

    def test_valores_imposibles(self):
        self.assertEqual(spd._date(0x00, 0x00), {})
        self.assertEqual(spd._date(0x2A, 0x10), {})        # nibble no BCD
        self.assertEqual(spd._date(0x21, 0x99), {})        # semana 99


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
    def test_ddr_se_identifica_pero_no_se_decodifica(self):
        # DDR2 to DDR5 are decoded; the first DDR is recognized and said.
        raw = bytearray(512)
        raw[2] = 0x07                                  # DDR
        info = spd.decode(bytes(raw))
        self.assertEqual(info.dram_type, "DDR")
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

    def _t14(self, reading_part):
        """The author's ThinkPad T14 Gen 2i: 8 GB soldered on the board and an
        8 GB SODIMM in the slot, which is the only SPD the bus has."""
        draft = self.Draft()
        draft.modules = [
            self.MemoryModule(locator="Controller0-ChannelA", populated=True,
                              part_number="M471A1G44AB0-CWE"),
            self.MemoryModule(locator="Controller1-ChannelA-DIMM0", populated=True,
                              part_number="9905711-049.A00G"),
        ]
        lectura = spd.decode(FIXTURE.read_bytes(), address="0-0050", slot=0)
        self.merge(draft, [__import__("dataclasses").replace(lectura, part_number=reading_part)])
        return draft.modules

    def test_a_reading_that_matches_a_later_module_is_not_taken_first(self):
        # Module by module, the soldered one took the slot's only reading by
        # order before the slot's module could match it by part number.
        soldado, ranura = self._t14("9905711-049.A00G")
        self.assertIsNone(soldado.spd)
        self.assertIsNotNone(ranura.spd)

    def test_by_order_a_slot_goes_before_memory_soldered_on_the_board(self):
        soldado, ranura = self._t14("KF3200C20S4/8G")
        self.assertIsNone(soldado.spd)
        self.assertIsNotNone(ranura.spd)

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


# Los grados que publica JEDEC, con el tCK ya cuantizado como lo guarda el SPD:
# en picosegundos enteros, que es de donde viene todo el problema. Un DDR4-2133
# no guarda 937,5 sino 938, y `2000000/938` da 2132,2.
GRADOS = {
    "DDR3": {800: 2500, 1066: 1875, 1333: 1500, 1600: 1250, 1866: 1071,
             2133: 938},
    "DDR4": {1600: 1250, 1866: 1071, 2133: 938, 2400: 833, 2666: 750,
             2933: 682, 3200: 625},
    "DDR5": {4000: 500, 4400: 455, 4800: 417, 5200: 385, 5600: 357, 6000: 333,
             6400: 313, 6800: 294, 7200: 278},
    # Perfiles del fabricante, que se salen de la tabla oficial pero no de la
    # rejilla: el reloj de referencia va en tercios igual.
    "XMP": {3600: 556, 3733: 536, 4133: 484, 4266: 469, 6600: 303, 7000: 286},
}


# Los grados que la rejilla de 200/3 no nombra bien (revisión del autor: un
# DDR2-667 salía «666 MT/s»). JEDEC nombra DDR2-667 redondeando 666,67, y la
# LPDDR5/5X no cae en esa rejilla: 5500 y 7500 están a media casilla y salían
# 5466 y 7466. Los de DDR y DDR2, por su tCK en ps (JESD79F, JESD79-2F); los
# de LPDDR, como los escribe el firmware en la tabla SMBIOS.
GRADOS_FUERA_DE_LA_REJILLA = {
    "DDR": {266: 7500, 333: 6000, 400: 5000},
    "DDR2": {533: 3750, 667: 3000, 800: 2500, 1066: 1875},
}
LPDDR_DEL_FIRMWARE = {"LPDDR4X-4266": 4266, "LPDDR5-5500": 5500, "LPDDR5-6400": 6400,
                      "LPDDR5X-7467": 7467, "LPDDR5X-7500": 7500, "LPDDR5X-8533": 8533}


class TestLosGradosDeTodasLasGeneraciones(unittest.TestCase):

    def test_ddr_y_ddr2_por_su_tck(self):
        from silux.spd import jedec_grade

        for generacion, grados in GRADOS_FUERA_DE_LA_REJILLA.items():
            for nombre, tck in grados.items():
                with self.subTest(generacion=generacion, grado=nombre):
                    self.assertEqual(jedec_grade(2_000_000 / tck), nombre)

    def test_lpddr_como_la_da_el_firmware(self):
        from silux import render

        for nombre, mts in LPDDR_DEL_FIRMWARE.items():
            with self.subTest(grado=nombre):
                self.assertEqual(render.memory_speed(mts), int(nombre.split("-")[1]))

    def test_el_firmware_que_redondea_al_otro_lado(self):
        """2666 o 2667, 666 o 667: el mismo grado se nombra igual."""
        from silux import render

        for crudo, grado in ((2667, 2666), (2666, 2666), (666, 667), (667, 667),
                             (1067, 1066), (1333, 1333)):
            with self.subTest(crudo=crudo):
                self.assertEqual(render.memory_speed(crudo), grado)


class TestElGradoDeCadaVelocidad(unittest.TestCase):
    """Que un módulo no salga catalogado a una velocidad que no existe.

    El tCK del SPD viene en picosegundos enteros, así que la división no cae
    redonda. Antes se redondeaba a la centena más cercana, que va bien con los
    grados redondos y mal con los que llevan tercio: un DDR4-2666 salía
    «2700 MT/s». Y no era solo feo: con el catalogado en 2700 y el real en
    2667, el módulo parecía ir por debajo de su velocidad y encendía el aviso.

    Once de los veintiocho grados conocidos salían mal. No se veía porque la
    máquina donde se desarrolla y el fixture del repositorio son DDR4-3200, que
    es de los que caen redondos.
    """

    def test_todos_los_grados_salen_con_su_nombre(self):
        from silux.spd import jedec_grade

        for generacion, grados in GRADOS.items():
            for nombre, tck in grados.items():
                with self.subTest(generacion=generacion, grado=nombre):
                    self.assertEqual(jedec_grade(2_000_000 / tck), nombre)

    def test_la_formula_de_antes_fallaba_en_once(self):
        """Para que el test valga: se ejecuta la de antes y se cuenta.

        Sin esto no hay forma de saber si esta tabla estaba comprobando algo o
        pasaba sola.
        """
        fallos = sum(round(2_000_000 / tck / 100) * 100 != nombre
                     for grados in GRADOS.values()
                     for nombre, tck in grados.items())
        self.assertEqual(fallos, 11)

    def test_una_velocidad_que_no_se_parece_a_nada_se_deja_como_está(self):
        """Un SPD ilegible no tiene por qué salir con un número bonito."""
        from silux.spd import jedec_grade

        self.assertEqual(jedec_grade(50), 50,
                         "50 MT/s no es un grado, y decir que son 66 sería "
                         "maquillar un dato roto")

    def test_por_debajo_de_la_rejilla_no_hay_grado_que_dar(self):
        """Cero es lo que el resto del módulo entiende como «no hay dato»."""
        from silux.spd import jedec_grade

        for absurdo in (0, 7, -1):
            with self.subTest(mts=absurdo):
                self.assertEqual(jedec_grade(absurdo), 0)

    def test_la_cuenta_va_en_enteros(self):
        """Con flotantes, 12 × 266,666… puede dar 3199,9999 y truncar a 3199.

        Se comprueba en toda la rejilla y no en un caso suelto: es el tipo de
        fallo que aparece en un múltiplo cualquiera y no en el que se probó.
        """
        from silux.spd import jedec_grade

        # Dos casillas que JEDEC nombra redondeando y no truncando: 666,67 es
        # DDR2-667 y 7466,67, LPDDR5X-7467 (TestLosGradosDeTodasLasGeneraciones).
        redondeadas = {10: 667, 112: 7467}
        for n in range(3, 120):
            exacto = n * 200 / 3
            with self.subTest(n=n):
                self.assertEqual(jedec_grade(exacto), redondeadas.get(n, n * 200 // 3))


class TestLaFormulaNoSeCopiaEnVariosSitios(unittest.TestCase):
    """Estaba escrita tres veces —DDR4, DDR5 y los perfiles— y por eso el
    fallo era el mismo en las tres. Arreglar una y olvidar las otras es
    exactamente lo que este test impide."""

    def test_nadie_calcula_la_velocidad_por_su_cuenta(self):
        import pathlib as _p
        import re as _re

        fuente = _p.Path("silux/spd.py").read_text(encoding="utf-8")
        # Fuera de `jedec_grade`, nadie puede redondear una velocidad.
        cuerpo = fuente.split("def jedec_grade")[1].split("\ndef ", 1)[1]
        sospechosas = _re.findall(r"2_000_000\s*/\s*\w+\s*/\s*100", cuerpo)
        self.assertEqual(sospechosas, [],
                         "hay quien vuelve a redondear a la centena en vez de "
                         "pasar por jedec_grade")



class TestLasLatenciasDeDdr4SeRedondeanComoJedec(unittest.TestCase):
    """Un tiempo que no cae en un número entero de ciclos se redondea hacia
    arriba: la memoria no puede responder antes de tiempo.

    DDR4 y los perfiles XMP redondeaban al más cercano, y solo la ruta de
    DDR5 subía. Un módulo que necesita 13 875 ps con un ciclo de 625 son 22,2
    ciclos, o sea CL23, y salía CL22 (F-A2). Pero el techo a secas tampoco
    vale aquí: el SPD guarda el ciclo truncado a picosegundos —833 en
    DDR4-2400, que son 833,33—, y un tiempo de exactamente 17 ciclos sale
    17,006 y subiría a 18. Por eso JEDEC redondea hacia arriba con un margen
    del 2,6 %, y es lo que se hace.
    """

    def test_lo_que_no_cae_en_un_ciclo_entero_sube(self):
        self.assertEqual(spd._jedec_cycles(13_875, 625), 23)

    def test_lo_que_cae_en_un_ciclo_entero_se_queda(self):
        self.assertEqual(spd._jedec_cycles(13_750, 625), 22)

    def test_el_ciclo_truncado_no_hace_subir_de_mas(self):
        self.assertEqual(spd._jedec_cycles(14_166, 833), 17)
        self.assertEqual(spd._jedec_cycles(13_320, 833), 16)

    def test_sin_ciclo_no_hay_latencia(self):
        self.assertIsNone(spd._jedec_cycles(13_875, 0))

    def test_la_lectura_de_ddr4_lo_usa(self):
        """Por el camino de verdad: un SPD con tAA de 111 × 125 ps."""
        datos = bytearray(512)
        datos[spd._Ddr4.TAA] = 111
        self.assertEqual(spd._ddr4_timing(bytes(datos), spd._Ddr4.TAA,
                                          spd._Ddr4.FINE_TAA, 625), 23)



class TestTeamGroup(unittest.TestCase):
    """A tester's TEAMGROUP-UD4-3200: its maker read «04EF».

    MSI's firmware writes the JEDEC code in hex, continuation count and code
    (bank 5, 0xEF with its parity bit), and the table did not have it.
    """

    def test_in_the_spd(self):
        from silux import render
        self.assertEqual(render.maker(spd._vendor(0x04, 0xEF)), "Team Group")

    def test_and_as_the_firmware_writes_it(self):
        from silux import render
        self.assertEqual(render.memory_maker("04EF"), "Team Group")
        self.assertEqual(render.memory_maker("80CE"), "Samsung")
        self.assertEqual(render.memory_maker("Kingston"), "Kingston")



class TestAnXmpThatCannotBeRead(unittest.TestCase):
    """A profile whose values make no sense is not shown, and the page says
    the module has XMP it cannot read. It is what kept F-A2 (CL 18, tRP 4,
    0.81 V) off the screen until a desktop's dump fixed the decoder
    (TestTheI7_10700fsModules)."""

    def test_an_impossible_voltage_is_not_a_profile(self):
        self.assertFalse(spd.Timings(name="XMP 1", speed_mts=3200, cl=18, trp=4,
                                     voltage_v=0.815).plausible)
        self.assertTrue(spd.Timings(name="XMP 1", speed_mts=3200, cl=16,
                                    voltage_v=1.35).plausible)

    def test_its_speed_still_counts_as_rated(self):
        # A profile with an impossible value still has a cycle. Dropping all
        # of it, a DDR4-3200 read «catalogado a 2400» and lost «al máximo
        # del procesador». Here the Crucial above with an XMP header and a
        # profile 1 at 500 ps, over its JEDEC 3200, at an impossible 0.81 V.
        raw = bytearray(FIXTURE.read_bytes())
        raw[384:386] = b"\x0c\x4a"
        raw[387] = 0x20
        raw[spd.XMP1_VOLTAGE] = 0x51
        raw[spd.XMP1_TCK] = 4
        raw[spd.XMP1_TAA:spd.XMP1_TRP + 1] = bytes((80, 90, 90))
        info = spd.decode(bytes(raw), address="10-0050", slot=0)
        self.assertEqual(info.profiles, ())
        self.assertEqual(info.rated_mts, 4000)

    def test_and_the_warning_of_the_processors_maximum_is_back(self):
        # That tester's case whole: TEAMGROUP DDR4-3200 at 2933 on an
        # i7-10700F, whose official maximum is 2933.
        from silux import db, render
        from silux.i18n import _
        from silux.model import MemoryModule
        jedec = spd.Timings(name="JEDEC", speed_mts=2400, cl=16, trcd=16, trp=16,
                            tras=39, trc=55, voltage_v=1.2)
        info = spd.SpdInfo(address="0-0050", slot=0, dram_type="DDR4", jedec=jedec,
                           xmp_revision="2.0", xmp_speeds_mts=(3200,), decoded=True)
        modulos = tuple(MemoryModule(populated=True, locator=f"DIMM {n}", type="DDR4",
                                     size_bytes=8 << 30, speed_mts=2400,
                                     configured_mts=2933, spd=info) for n in (0, 1))
        self.assertEqual(modulos[0].rated_mts, 3200)
        limite = db.memory_limit("Intel(R) Core(TM) i7-10700F CPU @ 2.90GHz", "DDR4")
        self.assertEqual(render.memory_speed_warning(modulos, limite),
                         _("mem.cpumax").format(actual=2933, rated=3200,
                                                modelo=render.memory_limit_label(limite)))

    def test_the_page_says_it_has_xmp_and_does_not_show_it(self):
        if not __import__("importlib").util.find_spec("PySide6"):
            self.skipTest("sin PySide6")
        import dataclasses

        from silux.i18n import _
        from silux.model import MemoryModule
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.memory import MemoryPage
        from tests import qt
        from tests.test_equipos import EQUIPOS, foto

        app = qt.app()
        jedec = spd.Timings(name="JEDEC", speed_mts=2400, cl=16, trcd=16, trp=16,
                            tras=39, trc=55, voltage_v=1.2)
        info = spd.SpdInfo(address="0-0050", slot=0, dram_type="DDR4", jedec=jedec,
                           xmp_revision="2.0", decoded=True)
        modulos = (MemoryModule(populated=True, locator="DIMM 0", type="DDR4",
                                size_bytes=8 << 30, speed_mts=3200, configured_mts=2933,
                                spd=info),)
        pagina = MemoryPage(theme.palette_for(app, "dark"), Preferences())
        self.addCleanup(pagina.deleteLater)
        pagina.apply(dataclasses.replace(foto(EQUIPOS / "i5-10400")[0], modules=modulos))
        self.assertEqual(pagina.spd_note.toolTip(), _("memory.spd.note.xmpunread"))


if __name__ == "__main__":
    unittest.main()


# Every even CL from 22 to 64, as the chip's list writes them (bit 0, CL20).
CL_DE_22_A_64 = sum(1 << ((cl - 20) // 2) for cl in range(22, 66, 2))


def construir_ddr5(*, tck_ps=357, taa=16250, trcd=16250, trp=16250,
                   tras=32000, trc=48000, latencias=CL_DE_22_A_64,
                   densidad=4, dies=0, io_width=2,
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
    for offset, valor in ((20, tck_ps), (30, taa), (32, trcd), (34, trp),
                          (36, tras), (38, trc)):
        b[offset] = valor & 0xFF
        b[offset + 1] = (valor >> 8) & 0xFF
    b[24:29] = latencias.to_bytes(5, "little")
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


# Page 0 of a Samsung M425R1GB4BB0-CQKOL (8 GB DDR5-4800 SODIMM), read on its
# laptop with `dd bs=128 count=1`.
PAGINA0_M425R1GB4BB0 = bytes.fromhex(
    "3010 1203 0400 4042 0000 0000 9002 0000"
    "0000 0000 a001 f203 7a0d 0000 0000 803e"
    "803e 803e 007d 80bb 3075 2701 a000 8200"
    "0000 0000 0000 0000 0000 0000 0000 0000"
    "0000 0000 0000 8813 0888 1308 204e 2010"
    "2710 1a41 2810 2710 c409 044c 1d0c 0000"
    "0000 0000 0000 0000 0000 0000 0000 0000"
    "0000 0000 0000 0000 0000 0000 0000 0000")


class TestUnaDdr5DeVerdad(unittest.TestCase):
    """Its timings, as JEDEC writes them and a person reads them: tCK 416 ps
    (DDR5-4800); tAA, tRCD and tRP 16 ns; tRAS 32 ns; tRC 48 ns. The decoder
    read them two bytes early, from the list of CAS latencies, and the test
    chip was built with the same mistake: CL9, tRAS 39."""

    def test_sus_temporizaciones(self):
        self.assertEqual(len(PAGINA0_M425R1GB4BB0), 128)
        info = spd.first_page(PAGINA0_M425R1GB4BB0, "0-0050", 0)
        self.assertEqual((info.dram_type, info.module_type, info.device_width),
                         ("DDR5", "SODIMM", 16))
        jedec = info.jedec
        self.assertEqual((jedec.speed_mts, jedec.cl, jedec.trcd, jedec.trp, jedec.tras,
                          jedec.trc), (4800, 40, 39, 39, 77, 116))

    def test_el_cl_es_uno_de_los_que_admite(self):
        # 16 ns son 39 ciclos a 416 ps; su lista admite 36, 40 y 42: CL40.
        self.assertEqual(spd._ddr5_cas(PAGINA0_M425R1GB4BB0, 39), 40)
        self.assertEqual(spd._ddr5_cas(PAGINA0_M425R1GB4BB0, 37), 40)
        self.assertEqual(spd._ddr5_cas(PAGINA0_M425R1GB4BB0, 23), 26)


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
        self.assertEqual(render.maker(self.info.manufacturer), "Micron")
        self.assertEqual(self.info.part_number, "CT16G56C46U5.M8G1")
        self.assertEqual((self.info.manufactured_year, self.info.manufactured_week), (2024, 32))

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
        # With the bus, one chip registered without its driver nor a name.
        chips = [pathlib.Path("/nonexistent/8-0050")] if bus else []
        return (mock.patch.object(spd, "_has_smbus_controller", lambda: controlador),
                mock.patch.multiple(spd, memory_buses=lambda: ["8"] if bus else [],
                                    spd_chips=lambda buses=None: chips,
                                    has_driver=lambda chip: False))

    def test_sin_controlador_no_hay_nada_que_hacer(self):
        with self._con(False, False)[0], self._con(False, False)[1]:
            motivo, solucion = spd.diagnosis()
        self.assertIn("no expone", motivo)
        self.assertIn("No hay forma", solucion)

    def test_con_controlador_pero_sin_bus_lo_reserva_el_firmware(self):
        with self._con(True, False)[0], self._con(True, False)[1]:
            motivo, solucion = spd.diagnosis()
        self.assertIn("firmware", motivo)
        self.assertIn("acpi_enforce_resources=lax", solucion)

    def test_con_bus_solo_falta_el_modulo(self):
        with self._con(True, True)[0], self._con(True, True)[1]:
            motivo, solucion = spd.diagnosis()
        self.assertIn("driver", motivo)
        self.assertIn("ee1004", solucion)
        self.assertIn("spd5118", solucion)


class TestCodigosDeFabricante(unittest.TestCase):
    """La tabla JEDEC guarda identificadores, no los bytes del SPD.

    El byte que trae el módulo lleva paridad impar en el bit más alto: un
    Crucial se presenta como 0x9B y su identificador es 0x1B. `_vendor` quita
    ese bit antes de buscar, así que un código copiado tal y como se publica
    —Samsung 0xCE, Kingston 0x98, SK Hynix 0xAD— no casa con nada y el módulo
    sale sin fabricante. Pasó con siete de las catorce entradas, y entre ellas
    estaban las tres marcas que más memoria venden.
    """

    def test_ninguno_lleva_el_bit_de_paridad(self):
        from silux.spd import _jep106

        con_paridad = {f"0x{code:02X} ({nombre})"
                       for (_banco, code), nombre in _jep106().items() if code & 0x80}
        self.assertEqual(con_paridad, set())
        self.assertGreater(len(_jep106()), 2000)

    def test_las_marcas_mas_comunes_se_reconocen(self):
        """Con los bytes tal y como los publica un módulo, paridad incluida."""
        from silux.spd import _vendor

        # (byte de banco, byte de identificador) -> quién es.
        # Kingston's, from the SODIMM of the author's T14 (its dump): bank 2,
        # one continuation code. The table had it in bank 1, and the SPD of
        # every Kingston came out without a maker.
        reales = {
            (0x80, 0xCE): "Samsung", (0x01, 0x98): "Kingston",
            (0x80, 0xAD): "SK Hynix", (0x80, 0x2C): "Micron",
            (0x85, 0x9B): "Crucial", (0x04, 0xCB): "ADATA",
        }
        for (banco, code), quien in reales.items():
            with self.subTest(marca=quien):
                from silux import render
                self.assertEqual(render.maker(_vendor(banco, code)), quien)


class TestTheT14sDump(unittest.TestCase):
    """The author's ThinkPad T14 Gen 2i, from its prueba4 annex: 8 GB soldered
    and a Kingston SODIMM, the only SPD on its bus. Its modules are SMBIOS's,
    which the annex (without permissions) does not carry: as its report with
    permissions gave them."""

    @classmethod
    def setUpClass(cls):
        from silux import volcado
        dump = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos" / "i5-1135g7"
        with volcado.mounted(dump):
            cls.lecturas = spd.read_all()

    def test_the_slots_spd_is_a_kingston(self):
        self.assertEqual([(r.part_number, r.manufacturer, render.maker(r.dram_manufacturer))
                          for r in self.lecturas],
                         [("9905711-049.A00G", "Kingston", "Micron")])

    def test_and_it_goes_to_the_slot_not_to_the_soldered_memory(self):
        from silux.model import MemoryModule
        from silux.providers.base import Draft
        from silux.providers.spd_modules import SpdModules
        draft = Draft()
        draft.modules = [
            MemoryModule(locator="Controller0-ChannelA", populated=True,
                         part_number="M471A1G44AB0-CWE", manufacturer="Samsung"),
            MemoryModule(locator="Controller1-ChannelA-DIMM0", populated=True,
                         part_number="9905711-049.A00G", manufacturer="Kingston"),
        ]
        SpdModules._merge(draft, list(self.lecturas))
        soldada, ranura = draft.modules
        self.assertIsNone(soldada.spd)
        self.assertEqual(ranura.spd.part_number, "9905711-049.A00G")


class TestTheI7_10700fsModules(unittest.TestCase):
    """A desktop's two TEAMGROUP-UD4-3200 (T-Force Vulcan Z), from the annex of
    its prueba4 report. Sold as DDR4-3200 16-18-18-38 at 1.35 V; read a byte
    off, its XMP said CL 18, tRP 4 and 0.81 V (F-A2)."""

    def test_their_xmp_is_what_the_module_is_sold_as(self):
        from silux import volcado
        dump = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos" / "i7-10700f"
        with volcado.mounted(dump):
            lecturas = spd.read_all()
        self.assertEqual(len(lecturas), 2)
        for lectura in lecturas:
            with self.subTest(modulo=lectura.address):
                from silux import render
                self.assertEqual(render.maker(lectura.manufacturer), "Team Group")
                self.assertEqual(lectura.jedec.speed_mts, 2400)
                self.assertEqual(lectura.profiles, (spd.Timings(
                    name="XMP 1", speed_mts=3200, cl=16, trcd=18, trp=18, tras=38,
                    trc=56, voltage_v=1.35, taa_ps=10000),))
                self.assertEqual(lectura.rated_mts, 3200)


class TestTheWholeJep106List(unittest.TestCase):
    """The makers by their JEDEC code, from OpenOCD's copy of JEP106. The hand
    table of 15 had Kingston, Infineon, Elpida and Transcend in the wrong
    place, and every other maker out."""

    def test_makers_the_old_table_did_not_have(self):
        from silux import render
        # As a module's SPD writes them: continuation count and code, both
        # with their odd parity bit.
        for (banco, codigo), quien in {(0x04, 0xCD): "G.Skill", (0x02, 0x9E): "Corsair",
                                      (0x80, 0xC1): "Infineon (Siemens)"}.items():
            with self.subTest(marca=quien):
                self.assertEqual(render.maker(spd._vendor(banco, codigo)), quien)

    def test_a_code_with_no_name_says_so(self):
        from silux import render
        from silux.i18n import _
        self.assertEqual(render.memory_maker("7FFF"),
                         _("mem.maker.code").format(codigo="7FFF"))

    def test_the_generator_reads_openocds_lines(self):
        import importlib.util
        ruta = pathlib.Path(__file__).resolve().parent.parent / "tools" / "gen_jep106.py"
        especificacion = importlib.util.spec_from_file_location("gen_jep106", ruta)
        gen = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(gen)
        revision, makers = gen.table("/* This file is aligned to revision JEP106BP September 2026. */\n"
                                     '[0][0x2c - 1] = "Micron Technology",\n'
                                     '[1][0x18 - 1] = "Kingston",\n')
        self.assertEqual(revision, "JEP106BP")
        self.assertEqual(makers, {"1": {"2C": "Micron Technology"}, "2": {"18": "Kingston"}})

