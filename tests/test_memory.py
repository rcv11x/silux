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
