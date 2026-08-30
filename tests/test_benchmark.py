"""La prueba de rendimiento y, sobre todo, el contexto que la acompaña.

Las cargas no se ejecutan de verdad aquí: medir tarda veinte segundos y el
resultado depende de la máquina, así que no se puede afirmar nada sobre él. Lo
que sí se comprueba es todo lo demás, que es donde está el valor: que los
avisos salgan cuando toca, que la caída de frecuencia se detecte, y que la
escala se calcule bien.
"""

import pathlib
import threading
import unittest
from unittest import mock

from silux import benchmark, history
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

    def test_la_medida_de_un_hilo_no_paga_el_arranque_de_la_carga(self):
        """La escala entre un hilo y todos tiene que ser creíble.

        La primera vez que una carga corre en un proceso da una cifra distinta
        de las siguientes —la compresión pesada, 1 780 operaciones por segundo
        en vez de 2 950—, y como el orden es un hilo primero y todos después,
        ese arranque lo pagaba siempre la medida de un hilo. La escala salía en
        catorce veces con ocho núcleos, que no es posible; ninguna carga puede
        escalar por encima del número de hilos.
        """
        import os

        hilos = os.cpu_count() or 1
        resultado = benchmark.run(seconds=1.0)
        por_carga = {}
        for medida in resultado.measures:
            if medida.seconds:
                por_carga.setdefault(medida.load, {})[medida.threads] = (
                    medida.operations / medida.seconds)
        for carga, medidas in por_carga.items():
            if 1 in medidas and hilos in medidas and medidas[1]:
                with self.subTest(carga=carga):
                    self.assertLessEqual(medidas[hilos] / medidas[1], hilos,
                                         "escala por encima del número de hilos")


if __name__ == "__main__":
    unittest.main()


class TestCargaDeMemoria(unittest.TestCase):
    """La carga que sale a buscar datos fuera del núcleo.

    El bloque tiene que no caber en la caché, y cuánto es eso depende del
    procesador: un 5800X3D lleva 96 MB de L3 y se traga entero un bloque de
    64, con lo que la prueba mediría la caché y no la memoria. Medido aquí,
    con el bloque pequeño escalaba ×8.3 —igual que las cargas de cómputo— y
    con el bloque bien dimensionado baja a ×5, que es lo que se espera de un
    camino a memoria que se comparte entre todos los núcleos.
    """

    def test_esta_entre_las_cargas(self):
        self.assertIn("memoria", [c.key for c in benchmark.CARGAS])

    def test_el_bloque_se_dimensiona_con_la_cache(self):
        from unittest import mock
        with mock.patch.object(benchmark, "_leer", side_effect=lambda r: "32768K"):
            self.assertEqual(benchmark._tamano_del_bloque(), 64)
        with mock.patch.object(benchmark, "_leer", side_effect=lambda r: "96M"):
            self.assertEqual(benchmark._tamano_del_bloque(), 192)

    def test_con_un_suelo_y_un_techo(self):
        from unittest import mock
        with mock.patch.object(benchmark, "_leer", return_value=None):
            self.assertEqual(benchmark._tamano_del_bloque(),
                             benchmark.BLOQUE_MINIMO_MB)
        with mock.patch.object(benchmark, "_leer", return_value="512M"):
            self.assertEqual(benchmark._tamano_del_bloque(),
                             benchmark.BLOQUE_MAXIMO_MB)

    def test_el_bloque_se_suelta_al_terminar(self):
        """Son hasta 192 MB y el programa entero se mueve en 130."""
        benchmark._bloque_grande()
        self.assertIsNotNone(benchmark._grande)
        benchmark._soltar_el_bloque()
        self.assertIsNone(benchmark._grande)


class TestDuracion(unittest.TestCase):
    def test_se_puede_pedir_cuanto_dura(self):
        resultado = benchmark.run(seconds=benchmark.MINIMO_SEGUNDOS)
        for medida in resultado.measures:
            self.assertLess(medida.seconds, benchmark.MINIMO_SEGUNDOS * 3)

    def test_no_se_acepta_una_barbaridad(self):
        from unittest import mock
        vistas = []
        with mock.patch.object(benchmark, "_medir",
                               side_effect=lambda c, h, d: vistas.append(d) or
                               benchmark.Medida(c.key, h, 1, d)):
            benchmark.run(seconds=9999.0)
        self.assertTrue(all(d <= benchmark.MAXIMO_SEGUNDOS for d in vistas))
        vistas.clear()
        with mock.patch.object(benchmark, "_medir",
                               side_effect=lambda c, h, d: vistas.append(d) or
                               benchmark.Medida(c.key, h, 1, d)):
            benchmark.run(seconds=0.001)
        self.assertTrue(all(d >= benchmark.MINIMO_SEGUNDOS for d in vistas))

    def test_sin_pedir_nada_manda_el_modo(self):
        from unittest import mock
        vistas = []
        with mock.patch.object(benchmark, "_medir",
                               side_effect=lambda c, h, d: vistas.append(d) or
                               benchmark.Medida(c.key, h, 1, d)):
            benchmark.run(quick=True)
        self.assertEqual(set(vistas), {benchmark.SEGUNDOS_RAPIDO})


class TestCargasNuevas(unittest.TestCase):
    """Las cinco cargas, y por qué son cinco y no siete."""

    def test_estan_las_cinco(self):
        claves = [c.key for c in benchmark.CARGAS]
        self.assertEqual(claves, ["compresion", "hash", "compresion_dura",
                                  "derivacion", "memoria"])

    def test_ninguna_usa_un_hash_que_acelere_sha_ni(self):
        """Vale para las dos que usan hash, no solo para la del resumen.

        En la derivación de clave el efecto sería mayor todavía: son miles de
        rondas encadenadas, así que una CPU con la instrucción saldría muy por
        encima de otra sin ella por algo que no es su velocidad.
        """
        fuente = pathlib.Path(benchmark.__file__).read_text(encoding="utf-8")
        self.assertNotIn("sha256", fuente)
        self.assertNotIn("sha_256", fuente)

    def test_todas_reparten_de_verdad_entre_hilos(self):
        """La condición para entrar: si no suelta el GIL, no mide la CPU.

        Se comprueba de verdad, ejecutándolas: una carga que escale ×1 con
        dieciséis hilos estaría midiendo el candado del intérprete y no el
        procesador, y eso ya pasó con una candidata de coma flotante.
        """
        import os
        import threading
        import time

        hilos = os.cpu_count() or 1
        if hilos < 4:
            self.skipTest("hacen falta varios núcleos para ver el reparto")

        for carga in benchmark.CARGAS:
            with self.subTest(carga=carga.key):
                def cuantas(n: int) -> int:
                    total = [0] * n
                    fin = time.perf_counter() + 0.4

                    def bucle(i: int) -> None:
                        veces = 0
                        while time.perf_counter() < fin:
                            carga.work()
                            veces += 1
                        total[i] = veces

                    obreros = [threading.Thread(target=bucle, args=(i,))
                               for i in range(n)]
                    for o in obreros:
                        o.start()
                    for o in obreros:
                        o.join()
                    return sum(total)

                uno = max(1, cuantas(1))
                escala = cuantas(hilos) / uno
                self.assertGreater(escala, 1.8,
                                   f"{carga.key} no reparte: ×{escala:.1f}")

    def test_cada_una_explica_qué_mide(self):
        for carga in benchmark.CARGAS:
            self.assertTrue(carga.explanation.strip(), carga.key)
            self.assertGreater(len(carga.explanation), 40, carga.key)


class TestDuracionLarga(unittest.TestCase):
    def test_se_puede_pedir_media_hora_por_medida(self):
        """Para dejar el equipo cociéndose y ver si aguanta."""
        self.assertGreaterEqual(benchmark.MAXIMO_SEGUNDOS, 1800.0)

    def test_pero_no_más(self):
        from unittest import mock
        vistas = []
        with mock.patch.object(benchmark, "_medir",
                               side_effect=lambda c, h, d: vistas.append(d) or
                               benchmark.Medida(c.key, h, 1, d)):
            benchmark.run(seconds=99_999.0)
        self.assertTrue(all(d <= benchmark.MAXIMO_SEGUNDOS for d in vistas))


class TestCancelar(unittest.TestCase):
    """Poder parar es lo que hace que probar una duración larga no dé miedo."""

    def test_se_para_entre_medidas(self):
        parar = threading.Event()
        parar.set()
        resultado = benchmark.run(seconds=1.0, stop=parar)
        self.assertEqual(resultado.measures, ())

    def test_lo_medido_antes_de_parar_se_conserva(self):
        parar = threading.Event()
        hechas = []

        def contar(que, cuanto):
            hechas.append(que)
            if len(hechas) >= 2:
                parar.set()

        resultado = benchmark.run(seconds=1.0, stop=parar, on_progress=contar)
        self.assertGreaterEqual(len(resultado.measures), 1)
        self.assertLess(len(resultado.measures), len(benchmark.CARGAS) * 2)

    def test_el_bloque_grande_se_suelta_aunque_se_cancele(self):
        """Si no, quedarían 192 MB colgados por haber pulsado Cancelar."""
        parar = threading.Event()
        parar.set()
        benchmark._bloque_grande()
        benchmark.run(seconds=1.0, stop=parar)
        self.assertIsNone(benchmark._grande)


class TestDuracionTotal(unittest.TestCase):
    """Diez medidas: lo que se elige por medida no es lo que dura la prueba."""

    def _pagina(self):
        from PySide6.QtWidgets import QApplication
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.performance import PerformancePage
        app = QApplication.instance() or QApplication([])
        theme.set_density("normal", "normal")
        return PerformancePage(theme.palette_for(app, "dark"),
                               Preferences(font_scale="normal").normalized())

    def test_el_total_es_la_medida_por_diez(self):
        pagina = self._pagina()
        pagina.duracion.setCurrentIndex(1)          # 5 s
        self.assertIn("50 s", pagina.duracion_total.text())

    def test_y_se_dice_en_minutos_cuando_toca(self):
        pagina = self._pagina()
        for indice in range(pagina.duracion.count()):
            if pagina.duracion.itemData(indice) == 30.0:
                pagina.duracion.setCurrentIndex(indice)
                break
        self.assertIn("min", pagina.duracion_total.text())

    def test_diez_porque_son_cinco_cargas_en_uno_y_en_todos(self):
        self.assertEqual(len(benchmark.CARGAS) * 2, 10)


class TestDerivaTermica(unittest.TestCase):
    """El aviso de «el mismo trabajo, más caliente».

    Es lo que delata pasta seca o polvo antes de que la cifra baje: la
    puntuación aguanta mientras el ventilador compensa.
    """

    def _prueba(self, ts, puntuacion, grados, segundos=3.0):
        return history.Entry(
            timestamp=ts, cpu="Ryzen 7 5800X3D", threads=16, seconds=segundos,
            scores={"compresion/16": puntuacion}, temperature_peak_c=grados,
        )

    def _historial(self, grados=70.0, cuantas=5):
        return [self._prueba(100 + i, 1000.0, grados + i * 0.3)
                for i in range(cuantas)]

    def test_calentarse_de_mas_se_avisa(self):
        deriva = history.deriva_termica(self._prueba(500, 1000.0, 78.0),
                                        self._historial())
        self.assertIsNotNone(deriva)
        grados, cuantas = deriva
        self.assertGreater(grados, 6)
        self.assertEqual(cuantas, 5)

    def test_un_par_de_grados_es_ruido(self):
        """La misma prueba dos veces seguidas ya varía según cómo estuviera el
        equipo antes de empezar."""
        self.assertIsNone(history.deriva_termica(self._prueba(500, 1000.0, 71.5),
                                                 self._historial()))

    def test_si_rindio_mas_la_temperatura_se_explica_sola(self):
        """Un 40 % más de trabajo calienta más, y eso no es una avería."""
        self.assertIsNone(history.deriva_termica(self._prueba(500, 1400.0, 80.0),
                                                 self._historial()))

    def test_con_una_sola_referencia_no_se_dice_nada(self):
        """Con una prueba detrás no se distingue una tendencia de un día
        raro."""
        self.assertIsNone(history.deriva_termica(self._prueba(500, 1000.0, 80.0),
                                                 self._historial(cuantas=2)))

    def test_no_se_compara_contra_otra_duracion(self):
        """Una medida de tres segundos coge el turbo entero y una de treinta
        no: sus temperaturas no son la misma pregunta."""
        largas = [self._prueba(100 + i, 1000.0, 70.0, segundos=30.0)
                  for i in range(5)]
        self.assertIsNone(history.deriva_termica(self._prueba(500, 1000.0, 80.0),
                                                 largas))

    def test_una_prueba_sin_temperatura_no_entra(self):
        sin = [self._prueba(100 + i, 1000.0, None) for i in range(5)]
        self.assertIsNone(history.deriva_termica(self._prueba(500, 1000.0, 80.0), sin))

    def test_enfriarse_tambien_se_dice(self):
        """Si acabas de limpiarlo, ahí se ve."""
        deriva = history.deriva_termica(self._prueba(500, 1000.0, 62.0),
                                        self._historial())
        self.assertIsNotNone(deriva)
        self.assertLess(deriva[0], 0)

    def test_la_mediana_aguanta_una_prueba_rara(self):
        """Una lanzada con el equipo ya caliente no debe mover la referencia."""
        raras = self._historial() + [self._prueba(150, 1000.0, 95.0)]
        self.assertIsNone(history.deriva_termica(self._prueba(500, 1000.0, 72.0),
                                                 raras))


class TestElRodajeNoDependeDeLoRapidoQueSeaElEquipo(unittest.TestCase):
    """Lo que hay que dejar atrás son vueltas, no segundos.

    La primera vez que una carga corre en un proceso paga su arranque, y hacen
    falta unas ochenta llamadas para dejarlo atrás. Medio segundo aquí son
    cientos de vueltas y en un portátil de hace diez años pueden ser ninguna,
    así que contar tiempo dejaba el arreglo a medias justo en los equipos
    modestos, que son los que menos margen tienen.
    """

    def test_se_cuentan_vueltas(self):
        self.assertGreaterEqual(benchmark.VUELTAS_EN_VACIO, 80)

    def test_pero_con_un_tope_para_no_colgar_la_prueba(self):
        """Más vale medir con el arranque a medio pagar que no terminar."""
        self.assertLessEqual(benchmark.TOPE_EN_VACIO_S, 5.0)

    def test_una_carga_lentisima_no_alarga_la_prueba(self):
        import time

        class Lenta:
            key = "lenta"
            def work(self):
                time.sleep(0.05)

        inicio = time.perf_counter()
        benchmark._rodar_en_vacio(Lenta(), 1)
        self.assertLess(time.perf_counter() - inicio,
                        benchmark.TOPE_EN_VACIO_S + 1.0)


class TestLaCargaAjenaDuranteLaPrueba(unittest.TestCase):
    """Lo que roba otro programa mientras se mide, no antes de empezar.

    `background_load` se toma en tres décimas antes del primer paso, y una
    prueba de quince segundos por carga dura dos minutos y medio: quien la
    lanzaba y se iba a hacer otra cosa, o tenía una actualización en marcha sin
    saberlo, salía con «0 % de carga de fondo» y una cifra baja que no tenía
    explicación en ninguna parte del informe.
    """

    def test_se_mide_la_resta_y_no_lo_ocupado(self):
        """La prueba ocupa el equipo entero: a secas, todo daría el 100 %."""
        vigilante = benchmark._Vigilante()
        # Dos lecturas seguidas donde todo lo ocupado es de este proceso.
        with mock.patch.object(benchmark, "_jiffies",
                               side_effect=[(1000, 0, 0), (2000, 0, 1000)]):
            vigilante._cpu_antes = benchmark._jiffies()
            self.assertEqual(vigilante._cuanto_roban(), 0.0)

    def test_lo_que_consume_otro_sí_cuenta(self):
        vigilante = benchmark._Vigilante()
        # De mil jiffies, ninguno inactivo y solo la mitad nuestros.
        with mock.patch.object(benchmark, "_jiffies",
                               side_effect=[(1000, 0, 0), (2000, 0, 500)]):
            vigilante._cpu_antes = benchmark._jiffies()
            self.assertAlmostEqual(vigilante._cuanto_roban(), 50.0)

    def test_lo_inactivo_no_es_de_nadie(self):
        vigilante = benchmark._Vigilante()
        with mock.patch.object(benchmark, "_jiffies",
                               side_effect=[(1000, 0, 0), (2000, 1000, 0)]):
            vigilante._cpu_antes = benchmark._jiffies()
            self.assertEqual(vigilante._cuanto_roban(), 0.0)

    def test_una_resta_negativa_es_cero_y_no_un_error(self):
        """Los dos ficheros no se leen en el mismo instante."""
        vigilante = benchmark._Vigilante()
        with mock.patch.object(benchmark, "_jiffies",
                               side_effect=[(1000, 0, 0), (2000, 0, 1200)]):
            vigilante._cpu_antes = benchmark._jiffies()
            self.assertEqual(vigilante._cuanto_roban(), 0.0)

    def test_sin_poder_leer_no_se_inventa_una_cifra(self):
        vigilante = benchmark._Vigilante()
        with mock.patch.object(benchmark, "_jiffies", return_value=None):
            self.assertIsNone(vigilante._cuanto_roban())

    def test_el_pico_manda_sobre_la_media(self):
        """Algo que se despierta a mitad se diluye si se promedia."""
        vigilante = benchmark._Vigilante()
        vigilante._ajeno = [0.1, 0.2, 45.0, 0.3]
        self.assertEqual(vigilante.ajeno_pico(), 45.0)

    def test_sin_muestras_no_hay_pico(self):
        self.assertIsNone(benchmark._Vigilante().ajeno_pico())

    def test_se_avisa_de_lo_que_pasó_durante_y_no_solo_de_lo_de_antes(self):
        avisos = benchmark._avisos(benchmark.Conditions(
            governor="performance", background_load=0.5, background_peak=40.0))
        self.assertTrue(any("mientras se medía" in a for a in avisos),
                        f"no se avisa del pico: {avisos}")

    def test_un_pico_pequeño_no_es_para_avisar(self):
        avisos = benchmark._avisos(benchmark.Conditions(
            governor="performance", background_peak=2.0))
        self.assertEqual(avisos, ())
