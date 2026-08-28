"""El seguimiento de los recortes: cuánto lleva frenándose algo, y por qué.

Los motivos ya se leían y salían como una fila más de una ficha. Eso dice qué
pasa ahora y no lo que se quiere saber: medio segundo de límite de potencia en
un cambio de escena es el funcionamiento normal de cualquier tarjeta, y un
minuto contra el límite térmico es un problema de refrigeración.
"""

import unittest

from silux import render
from silux.throttling import MEMORIA_S, MINIMO_S, SeguidorDeRecortes

SEG = 1_000_000_000


class TestSeguidorDeRecortes(unittest.TestCase):

    def setUp(self):
        self.s = SeguidorDeRecortes()

    def test_un_episodio_en_curso_cuenta_desde_que_empezo(self):
        self.s.update("gpu", True, ["temperatura del punto caliente"], 0)
        self.s.update("gpu", True, ["temperatura del punto caliente"], 40 * SEG)
        episodio = self.s.relevante("gpu", 40 * SEG)
        self.assertIsNotNone(episodio)
        self.assertTrue(episodio.en_curso())
        self.assertAlmostEqual(episodio.duracion_s(40 * SEG), 40.0)

    def test_un_parpadeo_no_se_cuenta(self):
        """Un recorte de dos décimas en un cambio de escena es lo normal, y
        avisar de él convierte el aviso en ruido de fondo."""
        self.s.update("gpu", True, ["límite de potencia (PPT0)"], 0)
        corto = int(MINIMO_S * SEG / 2)
        self.s.update("gpu", False, [], corto)
        self.assertIsNone(self.s.relevante("gpu", corto))

    def test_se_recuerda_un_rato_lo_que_acaba_de_terminar(self):
        """Quien mira la pantalla justo después del pico también quiere
        saberlo."""
        self.s.update("gpu", True, ["temperatura de la GPU"], 0)
        self.s.update("gpu", False, [], 20 * SEG)
        episodio = self.s.relevante("gpu", 25 * SEG)
        self.assertIsNotNone(episodio)
        self.assertFalse(episodio.en_curso())
        self.assertAlmostEqual(episodio.duracion_s(25 * SEG), 20.0)

    def test_pasado_el_rato_deja_de_enseñarse(self):
        self.s.update("gpu", True, ["temperatura de la GPU"], 0)
        self.s.update("gpu", False, [], 20 * SEG)
        tarde = int((20 + MEMORIA_S + 5) * SEG)
        self.assertIsNone(self.s.relevante("gpu", tarde))

    def test_se_guardan_todos_los_motivos_del_episodio(self):
        """Una tarjeta que empieza por potencia y acaba por temperatura ha
        hecho las dos cosas; quedarse con la de ahora pierde la mitad."""
        self.s.update("gpu", True, ["límite de potencia (PPT0)"], 0)
        self.s.update("gpu", True, ["temperatura del punto caliente"], 10 * SEG)
        episodio = self.s.relevante("gpu", 10 * SEG)
        self.assertEqual(episodio.motivos,
                         {"límite de potencia (PPT0)",
                          "temperatura del punto caliente"})

    def test_volver_a_recortar_abre_un_episodio_nuevo(self):
        self.s.update("gpu", True, ["a"], 0)
        self.s.update("gpu", False, [], 10 * SEG)
        self.s.update("gpu", True, ["b"], 20 * SEG)
        episodio = self.s.relevante("gpu", 30 * SEG)
        self.assertTrue(episodio.en_curso())
        self.assertEqual(episodio.motivos, {"b"})
        self.assertAlmostEqual(episodio.duracion_s(30 * SEG), 10.0)

    def test_no_saber_no_abre_ni_cierra_nada(self):
        """Una tarjeta cuyo driver no publica el estado no está recortando ni
        deja de hacerlo: no se sabe."""
        self.s.update("gpu", True, ["a"], 0)
        self.s.update("gpu", None, [], 10 * SEG)
        self.assertTrue(self.s.relevante("gpu", 10 * SEG).en_curso())

    def test_cada_tarjeta_va_por_su_cuenta(self):
        self.s.update("uno", True, ["a"], 0)
        self.s.update("otro", False, [], 0)
        self.assertIsNotNone(self.s.relevante("uno", 10 * SEG))
        self.assertIsNone(self.s.relevante("otro", 10 * SEG))


class TestComoSeCuenta(unittest.TestCase):

    def test_en_curso_y_terminado_se_dicen_distinto(self):
        s = SeguidorDeRecortes()
        s.update("g", True, ["temperatura de la GPU"], 0)
        frase = render.throttle_episode(s.relevante("g", 40 * SEG), 40 * SEG)
        self.assertTrue(frase.startswith("Lleva 40 s"), frase)

        s.update("g", False, [], 40 * SEG)
        frase = render.throttle_episode(s.relevante("g", 45 * SEG), 45 * SEG)
        self.assertTrue(frase.startswith("Ha estado 40 s"), frase)

    def test_los_minutos_se_dicen_en_minutos(self):
        self.assertEqual(render.duracion(45), "45 s")
        self.assertEqual(render.duracion(130), "2 min 10 s")
        self.assertEqual(render.duracion(120), "2 min")

    def test_sin_motivos_no_se_inventa_uno(self):
        """NVML dice que recorta y a veces no dice por qué."""
        s = SeguidorDeRecortes()
        s.update("g", True, [], 0)
        frase = render.throttle_episode(s.relevante("g", 10 * SEG), 10 * SEG)
        self.assertIn("no publica", frase)

    def test_sin_episodio_no_hay_frase(self):
        self.assertIsNone(render.throttle_episode(None, 0))
