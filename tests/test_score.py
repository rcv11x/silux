"""La puntuación que se puede comparar entre equipos.

Lo que se vigila aquí es que no vuelva a colarse una cifra que parece
comparable y no lo es, que es exactamente lo que hacía la anterior.
"""

import unittest

from silux import score


class TestLasCincoCargasPesanLoMismo(unittest.TestCase):
    """El motivo por el que la puntuación vieja no servía entre equipos.

    Sumaba operaciones por segundo de cinco cargas con magnitudes muy
    distintas: en un 5800X3D la compresión pesada daba 28 494 op/s y la
    memoria 533, así que la primera se llevaba el 82 % del total. La cifra era
    en la práctica la compresión pesada, y un procesador bueno en todo lo demás
    salía mal sin que se pudiera ver por qué.
    """

    def _referencia(self):
        tabla = score.referencias()
        if not tabla:
            self.skipTest("no hay escala medida")
        return tabla

    def test_el_patron_puntua_mil_por_definicion(self):
        tabla = self._referencia()
        hilos = tabla["patron"]["hilos"]
        scores = {f"{c}/1": v for c, v in tabla["un_hilo"].items()}
        scores |= {f"{c}/{hilos}": v for c, v in tabla["multihilo"].items()}
        self.assertEqual(
            score.puntuar(scores, hilos),
            (score.ESCALA, score.ESCALA))

    def test_ninguna_carga_decide_ella_sola(self):
        """Doblar una sola carga no puede doblar la puntuación."""
        tabla = self._referencia()
        hilos = tabla["patron"]["hilos"]
        base = {f"{c}/1": v for c, v in tabla["un_hilo"].items()}
        base |= {f"{c}/{hilos}": v for c, v in tabla["multihilo"].items()}

        for carga in tabla["multihilo"]:
            with self.subTest(carga=carga):
                tocado = dict(base)
                tocado[f"{carga}/{hilos}"] *= 2
                _uno, multi = score.puntuar(tocado, hilos)
                # Cinco cargas a partes iguales: doblar una sube un quinto.
                self.assertAlmostEqual(multi / score.ESCALA, 1.2, delta=0.01)

    def test_ir_al_doble_en_todo_es_el_doble_de_puntuacion(self):
        tabla = self._referencia()
        hilos = tabla["patron"]["hilos"]
        scores = {f"{c}/1": v * 2 for c, v in tabla["un_hilo"].items()}
        scores |= {f"{c}/{hilos}": v * 2 for c, v in tabla["multihilo"].items()}
        self.assertEqual(score.puntuar(scores, hilos),
                         (2 * score.ESCALA, 2 * score.ESCALA))


class TestSoloPuntuaLoQueSePuedeComparar(unittest.TestCase):
    """Una cifra sin puntuación es mejor que una que engaña.

    La duración cambia el resultado: tres segundos cogen el turbo entero y
    treinta lo pierden a mitad. Comparar dos pruebas de duraciones distintas
    diría que un equipo es más lento cuando lo único que cambió fue la
    pregunta.
    """

    def setUp(self):
        tabla = score.referencias()
        if not tabla:
            self.skipTest("no hay escala medida")
        self.hilos = tabla["patron"]["hilos"]
        self.scores = {f"{c}/1": v for c, v in tabla["un_hilo"].items()}
        self.scores |= {f"{c}/{self.hilos}": v
                        for c, v in tabla["multihilo"].items()}

    def test_cualquier_duracion_tiene_puntuacion(self):
        """Poner las cinco cargas en la misma escala vale para toda prueba.

        Es mejor cifra que la suma en crudo también dentro de un mismo equipo,
        que es lo que compara el historial. Lo que la duración decide es otra
        cosa, y se contesta aparte.
        """
        self.assertIsNotNone(score.puntuar(self.scores, self.hilos))

    def test_pero_solo_una_se_compara_con_otras_maquinas(self):
        for segundos in (3.0, 5.0, 30.0, 120.0):
            with self.subTest(segundos=segundos):
                self.assertFalse(score.comparable(segundos))
        self.assertTrue(score.comparable(score.SEGUNDOS_CANONICOS))

    def test_la_duracion_canonica_admite_el_desvio_del_bucle(self):
        """No corta en mitad de una operación: 15 pedidos salen 15 y pico."""
        self.assertTrue(score.comparable(15.4))
        self.assertTrue(score.comparable(score.SEGUNDOS_CANONICOS + 1.0))
        self.assertFalse(score.comparable(score.SEGUNDOS_CANONICOS + 5.0))

    def test_una_prueba_a_la_que_le_falte_una_carga_no_puntua(self):
        """Con cuatro de cinco, la cifra parecería igual de válida."""
        incompleta = {k: v for k, v in self.scores.items()
                      if not k.startswith("memoria/")}
        self.assertIsNone(
            score.puntuar(incompleta, self.hilos))


class TestLaEscalaSeDeclaraYSeVersiona(unittest.TestCase):
    """Cambiar las referencias mueve todas las puntuaciones a la vez."""

    def test_una_tabla_de_otra_version_no_llega_a_usarse(self):
        """Lo que importa no es que siempre haya escala al día.

        Es que una escala vieja no se cuele: cambiar las referencias mueve
        todas las puntuaciones a la vez, y una cifra medida con la anterior
        junto a otra medida con esta diría una diferencia que no existe.
        Mientras la escala esté pendiente de rehacer, lo correcto es no
        puntuar, y eso es lo que se comprueba aquí.
        """
        import json
        import pathlib

        ruta = pathlib.Path(score.__file__).parent / "db" / "scores.json"
        if not ruta.is_file():
            self.skipTest("no hay archivo de escala")
        declarada = json.loads(ruta.read_text(encoding="utf-8")).get(
            "version_formula")
        if declarada == score.VERSION:
            self.assertTrue(score.referencias(), "la escala vigente no carga")
        else:
            self.assertEqual(score.referencias(), {},
                             "una escala de otra versión no debe usarse")

    def test_una_escala_de_otra_version_no_se_usa(self):
        """Antes que mezclar dos escalas, ninguna."""
        import unittest.mock as mock

        with mock.patch.object(score, "VERSION", score.VERSION + 99):
            score.referencias.cache_clear()
            self.assertEqual(score.referencias(), {})
        score.referencias.cache_clear()

    def test_la_escala_dice_en_que_condiciones_se_tomo(self):
        patron = score.patron()
        if not patron:
            self.skipTest("no hay escala medida")
        for campo in ("cpu", "hilos", "segundos", "carga_de_fondo"):
            self.assertIn(campo, patron)


class TestDondeCaeUnaPuntuacion(unittest.TestCase):
    """La comparación con otras medidas de la misma pieza."""

    PIEZA = "Procesador de prueba"

    def _con(self, muestras):
        """Una tabla con esas medidas para la pieza de prueba."""
        import unittest.mock as mock

        tabla = dict(score.referencias())
        tabla["piezas"] = {self.PIEZA: {"hilos": 8, "un_hilo": muestras,
                                        "multihilo": muestras}}
        return mock.patch.object(score, "referencias", lambda: tabla)

    def test_con_menos_de_tres_medidas_no_se_dice_nada(self):
        """Situar a alguien entre dos medidas sueltas es peor que callar."""
        for muestras in ([], [1000], [900, 1100]):
            with self.subTest(muestras=len(muestras)), self._con(muestras):
                self.assertIsNone(score.comparar(self.PIEZA, 1000))

    def test_una_pieza_desconocida_no_se_compara(self):
        self.assertIsNone(score.comparar("Procesador que no existe", 1000))

    def test_sitúa_la_puntuación_entre_los_extremos(self):
        with self._con([800, 900, 1000, 1100, 1200]):
            c = score.comparar(self.PIEZA, 1000)
            self.assertEqual((c.minimo, c.maximo, c.mediana), (800, 1200, 1000))
            self.assertEqual(c.muestras, 5)
            self.assertAlmostEqual(c.fraccion, 0.5)

    def test_lo_que_se_sale_del_rango_se_queda_en_el_borde(self):
        """Una pieza mejor que todo lo registrado se ve al final, no fuera."""
        with self._con([800, 900, 1000]):
            self.assertAlmostEqual(score.comparar(self.PIEZA, 5000).fraccion, 1.0)
            self.assertAlmostEqual(score.comparar(self.PIEZA, 10).fraccion, 0.0)

    def test_cerca_de_la_mediana_es_lo_normal(self):
        """Entre dos equipos con la misma CPU hay placa, RAM y disipador."""
        with self._con([800, 900, 1000, 1100, 1200]):
            self.assertTrue(score.comparar(self.PIEZA, 1000).normal)
            self.assertTrue(score.comparar(self.PIEZA, 1050).normal)
            self.assertFalse(score.comparar(self.PIEZA, 1300).normal)
            self.assertFalse(score.comparar(self.PIEZA, 700).normal)

    def test_el_signo_dice_si_va_por_encima_o_por_debajo(self):
        with self._con([800, 900, 1000, 1100, 1200]):
            self.assertGreater(score.comparar(self.PIEZA, 1300).desvio, 0)
            self.assertLess(score.comparar(self.PIEZA, 700).desvio, 0)
