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
            score.puntuar(scores, hilos, score.SEGUNDOS_CANONICOS),
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
                _uno, multi = score.puntuar(tocado, hilos,
                                            score.SEGUNDOS_CANONICOS)
                # Cinco cargas a partes iguales: doblar una sube un quinto.
                self.assertAlmostEqual(multi / score.ESCALA, 1.2, delta=0.01)

    def test_ir_al_doble_en_todo_es_el_doble_de_puntuacion(self):
        tabla = self._referencia()
        hilos = tabla["patron"]["hilos"]
        scores = {f"{c}/1": v * 2 for c, v in tabla["un_hilo"].items()}
        scores |= {f"{c}/{hilos}": v * 2 for c, v in tabla["multihilo"].items()}
        self.assertEqual(score.puntuar(scores, hilos, score.SEGUNDOS_CANONICOS),
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

    def test_otra_duracion_no_puntua(self):
        for segundos in (3.0, 5.0, 30.0, 120.0):
            with self.subTest(segundos=segundos):
                self.assertIsNone(
                    score.puntuar(self.scores, self.hilos, segundos))

    def test_la_duracion_canonica_admite_el_desvio_del_bucle(self):
        """No corta en mitad de una operación: 15 pedidos salen 15 y pico."""
        self.assertIsNotNone(score.puntuar(self.scores, self.hilos, 15.4))
        self.assertTrue(score.comparable(score.SEGUNDOS_CANONICOS + 1.0))
        self.assertFalse(score.comparable(score.SEGUNDOS_CANONICOS + 5.0))

    def test_una_prueba_a_la_que_le_falte_una_carga_no_puntua(self):
        """Con cuatro de cinco, la cifra parecería igual de válida."""
        incompleta = {k: v for k, v in self.scores.items()
                      if not k.startswith("memoria/")}
        self.assertIsNone(
            score.puntuar(incompleta, self.hilos, score.SEGUNDOS_CANONICOS))


class TestLaEscalaSeDeclaraYSeVersiona(unittest.TestCase):
    """Cambiar las referencias mueve todas las puntuaciones a la vez."""

    def test_la_tabla_dice_para_que_version_vale(self):
        import json
        import pathlib

        ruta = pathlib.Path(score.__file__).parent / "db" / "scores.json"
        if not ruta.is_file():
            self.skipTest("no hay escala medida")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(datos.get("version_formula"), score.VERSION)

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
