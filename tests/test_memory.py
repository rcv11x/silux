"""La memoria: canales, velocidad y lo que se puede decir de los dos.

En canal único la memoria rinde la mitad, y no hay nada en todo el sistema que
lo diga. Es de los pocos problemas de hardware a la vez muy comunes, muy caros
en rendimiento y completamente invisibles.
"""

import unittest

from silux import render




class TestCanalesDeMemoria(unittest.TestCase):
    """Cuántos canales tienen módulo puesto, y cuándo eso es un problema."""

    def _mod(self, locator=None, bank=None, poblado=True):
        from silux.model import MemoryModule

        return MemoryModule(locator=locator, bank=bank, populated=poblado)

    def test_dos_bancos_distintos_son_doble_canal(self):
        """Los datos son los de una X570 de verdad."""
        modulos = [
            self._mod("DIMM 0", "P0 CHANNEL A", False),
            self._mod("DIMM 1", "P0 CHANNEL A", True),
            self._mod("DIMM 0", "P0 CHANNEL B", False),
            self._mod("DIMM 1", "P0 CHANNEL B", True),
        ]
        self.assertEqual(render.memory_channels(modulos), 2)
        self.assertIn("doble canal", render.memory_channel_label(modulos))
        self.assertIsNone(render.memory_channel_warning(modulos))

    def test_dos_modulos_en_el_mismo_canal_se_avisan(self):
        modulos = [self._mod("DIMM 0", "P0 CHANNEL A"),
                   self._mod("DIMM 1", "P0 CHANNEL A"),
                   self._mod("DIMM 0", "P0 CHANNEL B", False)]
        self.assertEqual(render.memory_channels(modulos), 1)
        aviso = render.memory_channel_warning(modulos)
        self.assertIn("mismo canal", aviso)

    def test_un_portatil_con_un_solo_modulo(self):
        """La convención de los portátiles es otra: el canal va en el
        localizador y no en el banco."""
        modulos = [self._mod("ChannelA-DIMM0", None, True),
                   self._mod("ChannelB-DIMM0", None, False)]
        self.assertEqual(render.memory_channels(modulos), 1)
        self.assertIn("mitad de ancho de banda",
                      render.memory_channel_warning(modulos))

    def test_cuatro_canales_se_llaman_por_su_nombre(self):
        modulos = [self._mod(f"DIMM_{c}1") for c in "ABCD"]
        self.assertEqual(render.memory_channels(modulos), 4)
        self.assertIn("cuádruple canal", render.memory_channel_label(modulos))

    def test_una_placa_que_no_dice_el_canal_no_se_adivina(self):
        """Inventarlo sería peor que callarse: manda a alguien a abrir el
        equipo para nada."""
        modulos = [self._mod("DIMM 0", "BANK 0"), self._mod("DIMM 1", "BANK 1")]
        self.assertIsNone(render.memory_channels(modulos))
        self.assertIsNone(render.memory_channel_label(modulos))
        self.assertIsNone(render.memory_channel_warning(modulos))

    def test_los_zocalos_vacios_no_cuentan_como_canal(self):
        modulos = [self._mod("DIMM_A1", None, True),
                   self._mod("DIMM_B1", None, False)]
        self.assertEqual(render.memory_channels(modulos), 1)

    def test_sin_modulos_no_hay_nada_que_decir(self):
        self.assertIsNone(render.memory_channels([]))
        self.assertIsNone(render.memory_channel_warning([]))

    def test_un_solo_modulo_sin_zocalos_libres_no_se_reprocha(self):
        """Si no hay dónde poner otro, el aviso solo sirve para fastidiar."""
        self.assertIsNone(render.memory_channel_warning([self._mod("DIMM_A1")]))


class TestElCanalNoEsSoloLaLetra(unittest.TestCase):
    """Dos canales pueden llamarse los dos «A».

    Lo trajo un ThinkPad T14 con dos módulos bien repartidos: el firmware los
    llama «Controller0-ChannelA» y «Controller1-ChannelA-DIMM0», que son dos
    canales, uno por controlador. Contando solo la letra salía «canal único»
    en una máquina que va en doble canal, y encima con el consejo de repartir
    los módulos, que ya estaban repartidos.
    """

    class _Modulo:
        def __init__(self, locator, bank=None, populated=True):
            self.locator, self.bank, self.populated = locator, bank, populated

    def test_dos_controladores_son_dos_canales(self):
        from silux import render

        modulos = [self._Modulo("Controller0-ChannelA"),
                   self._Modulo("Controller1-ChannelA-DIMM0")]
        self.assertEqual(render.memory_channels(modulos), 2)

    def test_y_no_se_aconseja_repartir_lo_que_ya_está_repartido(self):
        from silux import render

        modulos = [self._Modulo("Controller0-ChannelA"),
                   self._Modulo("Controller1-ChannelA-DIMM0")]
        self.assertIsNone(render.memory_channel_warning(modulos))

    def test_dos_en_el_mismo_controlador_siguen_siendo_uno(self):
        from silux import render

        modulos = [self._Modulo("ChannelA-DIMM0"),
                   self._Modulo("ChannelA-DIMM1")]
        self.assertEqual(render.memory_channels(modulos), 1)
        self.assertIsNotNone(render.memory_channel_warning(modulos))

    def test_el_sobremesa_de_toda_la_vida_no_cambia(self):
        from silux import render

        modulos = [self._Modulo("DIMM A1"), self._Modulo("DIMM B1")]
        self.assertEqual(render.memory_channels(modulos), 2)

    def test_sin_canal_en_el_localizador_se_sigue_callando(self):
        from silux import render

        self.assertIsNone(render.memory_channels([self._Modulo("BANK 0")]))


def _modulo(catalogado, funcionando, poblado=True):
    """Un módulo sin SPD, donde `rated_mts` cae en la velocidad de SMBIOS."""
    from silux.model import MemoryModule

    return MemoryModule(populated=poblado, speed_mts=catalogado,
                        configured_mts=funcionando)


class TestElRedondeoDeLosGradosJedec(unittest.TestCase):
    """Un MT/s de diferencia no es un recorte.

    Los grados JEDEC salen de un reloj que cae en tercios —DDR4-2666 son
    1333,33 MHz, o sea 2666,67 MT/s— y cada firmware redondea a su manera: el
    SPD de un SK Hynix dice 2667 y la BIOS pone 2666. Comparando a pelo, eso
    encendía el aviso, la insignia «por debajo de su velocidad» y el triángulo
    de la fila. Lo trajo un ThinkCentre M80q.
    """

    def test_un_mts_de_diferencia_no_marca_nada(self):
        self.assertFalse(_modulo(2667, 2666).underclocked)

    def test_ni_en_los_otros_grados_con_tercio(self):
        for catalogado, funcionando in ((2134, 2133), (2934, 2933),
                                        (3734, 3733), (1867, 1866)):
            with self.subTest(grado=catalogado):
                self.assertFalse(_modulo(catalogado, funcionando).underclocked)

    def test_un_recorte_de_verdad_se_sigue_viendo(self):
        """El margen no puede tragarse un grado entero: entre dos contiguos
        hay 133 MT/s como poco en DDR4 y 400 en DDR5."""
        for catalogado, funcionando in ((3200, 2666), (2666, 2400),
                                        (5600, 4800), (2933, 2666)):
            with self.subTest(de=catalogado, a=funcionando):
                self.assertTrue(_modulo(catalogado, funcionando).underclocked)


class TestElTechoDelConjuntoEsElDelMasLento(unittest.TestCase):
    """El consejo mandaba a la BIOS a por algo imposible.

    Se tomaba el primer módulo que fuera lento y se prometía su velocidad
    catalogada. Con uno de 3200 y otro de 2667 eso decía «va a 2666 de los
    3200 que declara admitir, suele ser el perfil rápido sin activar», y es
    falso: todos los módulos van al mismo reloj, así que el conjunto se queda
    en el del que menos da y ese equipo no verá 3200 active lo que active.
    """

    def _aviso(self, *pares):
        from silux import render

        return render.memory_speed_warning([_modulo(c, f) for c, f in pares])

    def test_con_modulos_desparejos_ya_a_tope_no_se_promete_nada(self):
        """El caso del M80q entero: 3200 y 2667 corriendo a 2666."""
        aviso = self._aviso((3200, 2666), (2667, 2666))
        self.assertIsNotNone(aviso, "callarse deja la cifra de 3200 sin explicar")
        self.assertIn("2667", aviso)
        self.assertNotIn("perfil rápido", aviso,
                         "no hay perfil que activar: ya va a tope")

    def test_y_se_dice_que_el_3200_no_cambia_nada(self):
        aviso = self._aviso((3200, 2666), (2667, 2666))
        self.assertIn("3200", aviso, "hay que nombrar al que declara más")
        self.assertIn("2666", aviso)

    def test_cuando_hay_margen_de_verdad_se_promete_el_techo_del_conjunto(self):
        """Desparejos y los dos por debajo: lo alcanzable es 2667, no 3200."""
        aviso = self._aviso((3200, 2133), (2667, 2133))
        self.assertIn("2667", aviso)
        self.assertNotIn("3200", aviso,
                         "prometer 3200 manda a pelearse con la BIOS para nada")

    def test_con_modulos_iguales_sigue_el_consejo_de_siempre(self):
        aviso = self._aviso((3200, 2666), (3200, 2666))
        self.assertIn("3200", aviso)
        self.assertIn("XMP", aviso)

    def test_todo_en_orden_no_dice_nada(self):
        self.assertIsNone(self._aviso((3200, 3200), (3200, 3200)))

    def test_el_redondeo_tampoco_dispara_el_aviso(self):
        self.assertIsNone(self._aviso((2667, 2666), (2667, 2666)))

    def test_sin_velocidades_no_se_inventa(self):
        """Sin permisos no hay SMBIOS y no se sabe a cuánto va."""
        from silux import render

        self.assertIsNone(render.memory_speed_warning(
            [_modulo(None, None), _modulo(None, None)]))
