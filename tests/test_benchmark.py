"""La prueba de rendimiento y, sobre todo, el contexto que la acompaña.

Las cargas no se ejecutan de verdad aquí: medir tarda veinte segundos y el
resultado depende de la máquina, así que no se puede afirmar nada sobre él. Lo
que sí se comprueba es todo lo demás, que es donde está el valor: que los
avisos salgan cuando toca, que la caída de frecuencia se detecte, y que la
escala se calcule bien.
"""

import threading
import unittest
from unittest import mock

from silux import benchmark
from silux.benchmark import Conditions, Medida, Result


class TestMedidas(unittest.TestCase):
    def test_operaciones_por_segundo(self):
        m = Medida(load="hash", threads=1, operations=1250, seconds=5.0)
        self.assertEqual(m.per_second, 250.0)

    def test_una_medida_sin_tiempo_no_divide_entre_cero(self):
        self.assertEqual(Medida(load="x", threads=1, operations=10, seconds=0).per_second, 0)

    def test_la_escala_entre_un_hilo_y_todos(self):
        r = Result((Medida("hash", 1, 1000, 5.0), Medida("hash", 16, 8500, 5.0)))
        self.assertEqual(r.scaling("hash", 16), 8.5)

    def test_sin_las_dos_medidas_no_hay_escala(self):
        r = Result((Medida("hash", 1, 1000, 5.0),))
        self.assertIsNone(r.scaling("hash", 16))


class TestDeteccionDeFrenos(unittest.TestCase):
    """Que la frecuencia caiga a mitad de prueba es la mitad del diagnóstico."""

    def test_una_caida_apreciable_se_detecta(self):
        c = Conditions(frequency_peak_hz=4_500_000_000,
                       frequency_end_hz=3_900_000_000)
        self.assertTrue(c.throttled)

    def test_una_variacion_normal_no_cuenta(self):
        # Un procesador nunca mantiene una frecuencia exacta; solo importa
        # cuando la caída es de las que se notan.
        c = Conditions(frequency_peak_hz=4_500_000_000,
                       frequency_end_hz=4_400_000_000)
        self.assertFalse(c.throttled)

    def test_sin_datos_no_se_afirma_nada(self):
        self.assertFalse(Conditions().throttled)


class TestAvisos(unittest.TestCase):
    """Lo que hay que saber antes de comparar la cifra con otra."""

    def test_la_carga_de_fondo_invalida_la_comparacion(self):
        avisos = benchmark._avisos(Conditions(background_load=35.0,
                                              governor="performance"))
        self.assertTrue(any("carga de fondo" in a for a in avisos))

    def test_un_poco_de_fondo_es_normal(self):
        # Siempre hay algo corriendo; avisar por un 3 % sería ruido.
        avisos = benchmark._avisos(Conditions(background_load=3.0,
                                              governor="performance"))
        self.assertEqual(avisos, ())

    def test_el_gobernador_de_ahorro_se_dice(self):
        avisos = benchmark._avisos(Conditions(governor="powersave"))
        self.assertTrue(any("powersave" in a for a in avisos))

    def test_en_rendimiento_no_hay_nada_que_avisar(self):
        self.assertEqual(benchmark._avisos(Conditions(governor="performance")), ())

    def test_la_caida_de_frecuencia_se_explica_con_cifras(self):
        avisos = benchmark._avisos(Conditions(
            governor="performance",
            frequency_peak_hz=4_500_000_000, frequency_end_hz=3_600_000_000))
        self.assertTrue(any("4.50" in a and "3.60" in a for a in avisos))


class TestCargas(unittest.TestCase):
    def test_las_dos_cargas_funcionan(self):
        for carga in benchmark.CARGAS:
            self.assertIsNotNone(carga.work(), carga.key)

    def test_ninguna_necesita_un_compilador(self):
        # Dentro de un AppImage no hay `cc`, así que una carga que se compilara
        # al vuelo funcionaría desde el código fuente y no para quien lo
        # descarga.
        import inspect
        fuente = inspect.getsource(benchmark)
        for prohibido in ("subprocess", "cc ", "gcc", "ctypes.CDLL"):
            self.assertNotIn(prohibido, fuente)

    def test_el_hash_evita_la_instruccion_acelerada(self):
        # `sha_ni` acelera SHA-256 pero no SHA-512. Con la primera, un chip que
        # la tenga saldría inflado y dejaría de compararse con uno que no.
        import inspect
        fuente = inspect.getsource(benchmark)
        self.assertIn("sha512", fuente)
        self.assertNotIn("sha256", fuente)


class TestEjecucion(unittest.TestCase):
    def test_se_puede_cancelar(self):
        parar = threading.Event()
        parar.set()
        with mock.patch.object(benchmark, "_carga_de_fondo", lambda: 0.0):
            resultado = benchmark.run(quick=True, stop=parar)
        self.assertEqual(resultado.measures, ())

    def test_informa_del_avance(self):
        pasos = []
        parar = threading.Event()
        parar.set()
        with mock.patch.object(benchmark, "_carga_de_fondo", lambda: 0.0):
            benchmark.run(quick=True, stop=parar,
                          on_progress=lambda que, cuanto: pasos.append((que, cuanto)))
        self.assertEqual(pasos[-1][1], 1.0)

    def test_el_nucleo_preferido_es_un_numero_valido(self):
        import os
        self.assertIn(benchmark._nucleo_preferido(), range(os.cpu_count() or 1))


if __name__ == "__main__":
    unittest.main()
