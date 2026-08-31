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
    """Se reparte por tiempo y no por número de vueltas.

    Con las tres que salían antes para el bloque de RAM, una tanda entera podía
    caer dentro de una interferencia: la cifra se movía un 15 % entre pasadas
    seguidas y quien pulsaba el botón veía otro número cada vez. Repartiendo
    por tiempo baja al 3 %.
    """

    def test_da_muchas_mas_vueltas_en_un_bloque_pequeño(self):
        libc = membench._libc()
        bloque = __import__("ctypes").create_string_buffer(2 * 1024**2)
        p = __import__("ctypes").addressof(bloque)
        with mock.patch.object(membench, "PRESUPUESTO", 0.02):
            with mock.patch.object(membench.time, "perf_counter",
                                   wraps=membench.time.perf_counter) as reloj:
                membench._leer(libc, p, 2 * 1024**2)
                pequeño = reloj.call_count
        self.assertGreater(pequeño, membench.MINIMO_VUELTAS * 2)

    def test_nunca_menos_del_minimo(self):
        """Con una sola vuelta, el mejor tiempo es el único tiempo."""
        import ctypes
        libc = membench._libc()
        bloque = ctypes.create_string_buffer(4 * 1024**2)
        with mock.patch.object(membench, "PRESUPUESTO", 0.0):
            with mock.patch.object(membench.time, "perf_counter",
                                   wraps=membench.time.perf_counter) as reloj:
                membench._leer(libc, ctypes.addressof(bloque), 4 * 1024**2)
        # Dos llamadas al reloj por vuelta.
        self.assertGreaterEqual(reloj.call_count, membench.MINIMO_VUELTAS * 2)


class TestMedidaDeVerdad(unittest.TestCase):
    def test_mide_la_ram_de_esta_maquina(self):
        r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        ram = [m for m in r.medidas if m.donde == "ram"]
        self.assertEqual(len(ram), 1)
        self.assertGreater(ram[0].bandwidth_bytes, 0)

    def test_y_la_cache_cuando_es_bastante_grande(self):
        r = membench.en_este_proceso(cache_bytes=8 * 1024**2)
        self.assertEqual([m.donde for m in r.medidas], ["techo", "ram"])

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
        self.assertEqual([m.donde for m in r.medidas], ["techo"])

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
        self.assertEqual([m.donde for m in r.medidas], ["techo", "ram"])
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


class TestLatencias(unittest.TestCase):
    """Lo que tarda un acceso que el procesador no puede adelantar.

    Se mide con un fragmento de código máquina —doce bytes que persiguen
    punteros— porque en Python el intérprete cuesta más que el propio acceso.
    Las cifras de este equipo, un 5800X3D, salieron 0,9 · 2,7 · 12,3 · 80,6 ns
    contra los 0,9 · 2,7 · 12,4 · 66,1 que da AIDA64 en la misma pieza con
    memoria más rápida.
    """

    # Cachés de juguete: lo que se prueba es el reparto, no la máquina.
    NIVELES = [("L1", 32 * 1024), ("L2", 256 * 1024), ("L3", 2 * 1024**2)]

    @classmethod
    def setUpClass(cls):
        # Una sola medida para todos los que miran el mismo resultado: medir
        # de verdad cuesta un segundo por tanda y eran siete tandas iguales.
        cls.salidas, cls.motivo = membench.latencias(cls.NIVELES)

    def test_mide_un_nivel_por_cada_cache_y_la_ram(self):
        self.assertIsNone(self.motivo)
        self.assertEqual([l.nivel for l in self.salidas],
                         ["L1", "L2", "L3", "RAM"])

    def test_todas_dan_un_tiempo_positivo(self):
        self.assertTrue(all(l.nanoseconds > 0 for l in self.salidas))

    def test_cada_nivel_tarda_mas_que_el_anterior(self):
        """Es la comprobación que cazaría una medida falsa de raíz.

        Si la cadena de la RAM cupiera en la caché, saldría más rápida que la
        L3 y esto lo vería. Pasó: con menos saltos que líneas salían 28 ns
        donde hay 76.
        """
        tiempos = [l.nanoseconds for l in self.salidas]
        self.assertEqual(tiempos, sorted(tiempos),
                         f"los niveles no van de menos a más: {tiempos}")

    def test_el_bloque_de_la_ram_no_cabe_en_la_cache(self):
        ram = [l for l in self.salidas if l.nivel == "RAM"][0]
        mayor = max(tam for _, tam in self.NIVELES)
        self.assertGreaterEqual(ram.bytes_, mayor * membench.VECES_FUERA_PARA_LATENCIA)

    def test_el_bloque_de_una_cache_no_pasa_del_tope(self):
        """La L3 de un Zen 3 es caché de víctimas: con la mitad de sus 96 MB
        recorridos al azar da 66 ns donde tiene que dar 12.

        Con el tope de eslabones a cero se salta la RAM, que para una caché de
        96 MB pide un bloque de 192 y se lleva casi cuatro segundos: aquí lo
        que se comprueba es el tamaño del bloque de la caché.
        """
        with mock.patch.object(membench, "MAXIMO_ESLABONES", 500_000):
            salidas, _motivo = membench.latencias([("L3", 96 * 1024**2)])
        l3 = [l for l in salidas if l.nivel == "L3"][0]
        self.assertLessEqual(l3.bytes_, membench.MAXIMO_BLOQUE_DE_CACHE)

    def test_una_cache_enorme_deja_sin_latencia_de_ram_y_lo_dice(self):
        salidas, motivo = membench.latencias([("L3", 900 * 1024**2)])
        self.assertEqual(motivo, "cadena_enorme")
        self.assertNotIn("RAM", [l.nivel for l in salidas])

    def test_fuera_de_x86_no_se_intenta(self):
        with mock.patch.object(membench.rawcpuid, "is_supported",
                               return_value=False):
            salidas, motivo = membench.latencias(self.NIVELES)
        self.assertEqual((salidas, motivo), ((), "no_x86"))

    def test_si_el_sistema_prohibe_ejecutar_memoria_se_dice(self):
        """Pasa bajo políticas SELinux estrictas y en algunos sandboxes."""
        with mock.patch.object(membench.rawcpuid, "pagina_ejecutable",
                               side_effect=RuntimeError("mprotect")):
            salidas, motivo = membench.latencias(self.NIVELES)
        self.assertEqual((salidas, motivo), ((), "sin_ejecutable"))

    def test_sin_niveles_solo_mide_la_ram(self):
        salidas, _motivo = membench.latencias([])
        self.assertEqual([l.nivel for l in salidas], ["RAM"])
