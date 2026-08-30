"""La medida del ancho de banda de la memoria.

Aquí sí se mide de verdad sobre la máquina que ejecuta los tests, porque la
medida es lo único que hay que probar y tarda una décima. Lo que no se hace es
exigir una cifra concreta: en un contenedor apretado o en una máquina virtual
sale lo que salga, y un test que dependa de eso falla los martes.
"""

import unittest
from unittest import mock

from silux import membench


class TestVueltas(unittest.TestCase):
    def test_muchas_en_los_bloques_pequeños_y_pocas_en_los_grandes(self):
        self.assertGreater(membench._vueltas(1024 * 1024),
                           membench._vueltas(256 * 1024 * 1024))

    def test_nunca_menos_de_tres(self):
        """Con una sola vuelta, el mejor tiempo es el único tiempo."""
        self.assertGreaterEqual(membench._vueltas(2 * 1024**3), 3)


class TestMedidaDeVerdad(unittest.TestCase):
    def test_mide_la_ram_de_esta_maquina(self):
        r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        ram = [m for m in r.medidas if m.donde == "ram"]
        self.assertEqual(len(ram), 1)
        self.assertGreater(ram[0].bandwidth_bytes, 0)

    def test_y_la_cache_cuando_es_bastante_grande(self):
        r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        self.assertEqual([m.donde for m in r.medidas], ["cache", "ram"])

    def test_una_cache_diminuta_no_se_mide(self):
        """Por debajo de un mega la llamada pesa más que la memoria.

        Una llamada cuesta 570 ns; en un bloque de 32 KB eso es casi todo el
        tiempo, y la cifra hablaría de ctypes y no del equipo.
        """
        r = membench.en_este_proceso(cache_bytes=512 * 1024)
        self.assertEqual([m.donde for m in r.medidas], ["ram"])

    def test_sin_saber_la_cache_se_mide_la_ram_igual(self):
        r = membench.en_este_proceso(cache_bytes=None)
        self.assertEqual([m.donde for m in r.medidas], ["ram"])

    def test_el_bloque_de_ram_se_sale_de_la_cache(self):
        """Si cupiera dentro, se estaría midiendo la caché otra vez."""
        cache = 4 * 1024**2
        r = membench.en_este_proceso(cache_bytes=cache)
        ram = [m for m in r.medidas if m.donde == "ram"][0]
        self.assertGreaterEqual(ram.bytes_, cache * membench.VECES_FUERA_DE_LA_CACHE)


class TestCuandoNoSePuede(unittest.TestCase):
    def test_una_cache_enorme_pediria_demasiado(self):
        """Hay Threadripper con 256 MB: el triple no lo pide un programa así."""
        r = membench.en_este_proceso(cache_bytes=400 * 1024**2)
        self.assertEqual(r.motivo, "cache_enorme")
        self.assertNotIn("ram", [m.donde for m in r.medidas])

    def test_con_la_memoria_justa_no_se_mide(self):
        """Medir no puede ser el motivo de que algo se vaya a la swap."""
        with mock.patch.object(membench, "_memoria_disponible",
                               return_value=64 * 1024**2):
            r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        self.assertEqual(r.motivo, "sin_memoria")

    def test_pero_lo_que_ya_se_midio_se_conserva(self):
        with mock.patch.object(membench, "_memoria_disponible",
                               return_value=64 * 1024**2):
            r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        self.assertEqual([m.donde for m in r.medidas], ["cache"])

    def test_si_no_se_puede_leer_meminfo_se_sigue(self):
        with mock.patch.object(membench, "_memoria_disponible", return_value=None):
            r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        self.assertIsNone(r.motivo)


class TestEnOtroProceso(unittest.TestCase):
    """Para salirse de una caché de 96 MB hace falta un bloque de casi 300, y
    el programa entero tiene un presupuesto de 300."""

    def test_el_hijo_devuelve_lo_mismo_que_medir_aqui(self):
        r = membench.consultar(8 * 1024**2)
        self.assertIsNone(r.motivo)
        self.assertEqual([m.donde for m in r.medidas], ["cache", "ram"])
        self.assertTrue(all(m.bandwidth_bytes > 0 for m in r.medidas))

    def test_si_el_hijo_no_sale_adelante_se_dice(self):
        with mock.patch.object(membench.subprocess, "run",
                               side_effect=OSError):
            self.assertEqual(membench.consultar(0).motivo, "no_arranco")

    def test_una_salida_que_no_es_json_no_revienta(self):
        falso = mock.Mock(returncode=0, stdout=b"esto no es json")
        with mock.patch.object(membench.subprocess, "run", return_value=falso):
            self.assertEqual(membench.consultar(0).motivo, "no_arranco")

    def test_ni_una_salida_vacia(self):
        falso = mock.Mock(returncode=0, stdout=b"")
        with mock.patch.object(membench.subprocess, "run", return_value=falso):
            self.assertEqual(membench.consultar(0).motivo, "no_arranco")



class TestElTeorico(unittest.TestCase):
    """La multiplicación con la que se compara lo medido.

    Sirve para saber cuánto se aprovecha; sola no dice gran cosa, porque
    ninguna máquina llega a su teórico.
    """

    @staticmethod
    def _modulo(locator, mts=3200):
        from silux.model import MemoryModule
        return MemoryModule(locator=locator, populated=True, configured_mts=mts)

    def test_dos_canales_dan_el_doble(self):
        from silux import render
        # Los del ThinkPad: dos controladores y los dos llaman «A» a su canal.
        dos = (self._modulo("Controller0-ChannelA"),
               self._modulo("Controller1-ChannelA-DIMM0"))
        self.assertEqual(render.memory_theoretical_bandwidth(dos),
                         3200 * 1_000_000 * 8 * 2)

    def test_uno_solo_da_la_mitad(self):
        from silux import render
        uno = (self._modulo("Controller0-ChannelA"),)
        self.assertEqual(render.memory_theoretical_bandwidth(uno),
                         3200 * 1_000_000 * 8)

    def test_sin_saber_los_canales_no_se_calcula(self):
        """Suponer dos doblaría el porcentaje de una máquina en canal único."""
        from silux import render
        ciegos = (self._modulo("BANK 0"), self._modulo("BANK 1"))
        self.assertIsNone(render.memory_theoretical_bandwidth(ciegos))

    def test_manda_el_modulo_mas_lento(self):
        """El controlador iguala a la baja lo que le pongan."""
        from silux import render
        mezcla = (self._modulo("Controller0-ChannelA", 3200),
                  self._modulo("Controller1-ChannelA", 2666))
        self.assertEqual(render.memory_theoretical_bandwidth(mezcla),
                         2666 * 1_000_000 * 8 * 2)

    def test_la_fraccion_sale_en_tanto_por_ciento(self):
        from silux import render
        self.assertEqual(
            render.memory_bandwidth_share(42_000_000_000, 51_200_000_000), 82.0)

    def test_sin_uno_de_los_dos_no_hay_fracción(self):
        from silux import render
        self.assertIsNone(render.memory_bandwidth_share(42_000_000_000, None))
        self.assertIsNone(render.memory_bandwidth_share(None, 51_200_000_000))

if __name__ == "__main__":
    unittest.main()
