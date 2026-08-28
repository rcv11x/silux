"""El historial de pruebas del propio equipo.

Una puntuación suelta no dice nada. Lo de internet casi nunca sirve para
comparar, porque está medido con otro gobernador y otra temperatura; lo que
sí compara bien es el mismo equipo consigo mismo, antes y después de cambiar
algo.
"""

import os
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from silux import history
from silux.benchmark import Conditions, Medida, Result


def _resultado(ops_por_hilo=100.0, hilos=8, gobernador="performance") -> Result:
    medidas = tuple(
        Medida(load=carga, threads=n, operations=int(ops_por_hilo * n * 2), seconds=2.0)
        for carga in ("compresion", "hash")
        for n in (1, hilos)
    )
    return Result(medidas,
                  Conditions(governor=gobernador, temperature_peak_c=65.0,
                             frequency_avg_hz=4_200_000_000),
                  ())


class _ConCarpetaPropia(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self._tmp.name})
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(self._tmp.cleanup)


class TestGuardarYLeer(_ConCarpetaPropia):
    def test_una_prueba_ida_y_vuelta(self):
        entrada = history.from_result(_resultado(), "Ryzen 7 5800X3D", 2.0)
        history.append(entrada)
        leidas = history.load()
        self.assertEqual(len(leidas), 1)
        self.assertEqual(leidas[0].cpu, "Ryzen 7 5800X3D")
        self.assertEqual(leidas[0].scores, entrada.scores)

    def test_sin_archivo_no_hay_historial_y_no_revienta(self):
        self.assertEqual(history.load(), [])

    def test_un_archivo_roto_no_tira_el_programa(self):
        history.data_dir().mkdir(parents=True, exist_ok=True)
        history.history_path().write_text("{esto no es json", encoding="utf-8")
        self.assertEqual(history.load(), [])

    def test_una_entrada_de_otra_version_se_salta_ella_sola(self):
        """Y no se lleva por delante a las que sí valen."""
        import json
        buena = history.from_result(_resultado(), "CPU", 2.0)
        history.append(buena)
        crudo = json.loads(history.history_path().read_text())
        crudo.append({"campo_que_no_existe": 1})
        history.history_path().write_text(json.dumps(crudo), encoding="utf-8")
        self.assertEqual(len(history.load()), 1)

    def test_las_mas_nuevas_van_primero(self):
        vieja = history.from_result(_resultado(), "CPU", 2.0)
        history.append(vieja)
        nueva = history.from_result(_resultado(), "CPU", 2.0)
        history.append(nueva)
        leidas = history.load()
        self.assertGreater(leidas[0].timestamp, leidas[1].timestamp)

    def test_no_se_guardan_infinitas(self):
        for _ in range(history.MAXIMO + 12):
            history.append(history.from_result(_resultado(), "CPU", 2.0))
        self.assertLessEqual(len(history.load()), history.MAXIMO)


class TestComparar(_ConCarpetaPropia):
    def test_dice_cuanto_ha_cambiado(self):
        antes = history.from_result(_resultado(100.0), "CPU", 2.0)
        despues = history.from_result(_resultado(110.0), "CPU", 2.0)
        salida = history.comparar(despues, [despues, antes])
        self.assertIsNotNone(salida)
        _, cambio = salida
        self.assertAlmostEqual(cambio, 10.0, places=1)

    def test_la_primera_vez_no_hay_con_qué(self):
        sola = history.from_result(_resultado(), "CPU", 2.0)
        self.assertIsNone(history.comparar(sola, [sola]))

    def test_no_compara_contra_otro_procesador(self):
        otra = history.from_result(_resultado(100.0), "Core i5-10400", 2.0)
        time.sleep(0.01)
        mia = history.from_result(_resultado(200.0), "Ryzen 7 5800X3D", 2.0)
        self.assertIsNone(history.comparar(mia, [mia, otra]))

    def test_ni_contra_otra_duración(self):
        """Una medida de 3 s coge el turbo entero y una de 30 no: compararlas
        diría que el equipo se ha vuelto lento cuando cambió la pregunta."""
        corta = history.from_result(_resultado(100.0), "CPU", 3.0)
        time.sleep(0.01)
        larga = history.from_result(_resultado(80.0), "CPU", 30.0)
        self.assertIsNone(history.comparar(larga, [larga, corta]))

    def test_ni_contra_una_posterior(self):
        vieja = history.from_result(_resultado(100.0), "CPU", 2.0)
        time.sleep(0.01)
        nueva = history.from_result(_resultado(110.0), "CPU", 2.0)
        self.assertIsNone(history.comparar(vieja, [nueva, vieja]))


class TestPuntuacion(unittest.TestCase):
    def test_suma_solo_las_medidas_a_todos_los_hilos(self):
        entrada = history.from_result(_resultado(100.0, hilos=8), "CPU", 2.0)
        # dos cargas × 8 hilos × 100 op/s
        self.assertAlmostEqual(entrada.total(), 1600.0, places=1)

    def test_sin_medidas_no_hay_puntuación(self):
        vacia = history.from_result(Result((), Conditions(), ()), "CPU", 2.0)
        self.assertIsNone(vacia.total())


if __name__ == "__main__":
    unittest.main()


class TestNombrarYBorrar(_ConCarpetaPropia):
    """Una lista de fechas no dice qué cambió entre una prueba y otra."""

    def _tres(self):
        entradas = []
        for _ in range(3):
            entrada = history.from_result(_resultado(), "CPU", 2.0)
            history.append(entrada)
            entradas.append(entrada)
            time.sleep(0.01)
        return entradas

    def test_una_prueba_puede_llevar_nombre(self):
        entrada = history.from_result(_resultado(), "CPU", 2.0)
        history.append(entrada)
        history.rename(entrada.timestamp, "con la pasta nueva")
        self.assertEqual(history.load()[0].label, "con la pasta nueva")

    def test_el_nombre_se_guarda_en_el_disco(self):
        entrada = history.from_result(_resultado(), "CPU", 2.0)
        history.append(entrada)
        history.rename(entrada.timestamp, "verano")
        self.assertIn("verano", history.history_path().read_text(encoding="utf-8"))

    def test_renombrar_no_toca_a_las_demas(self):
        primera, segunda, tercera = self._tres()
        history.rename(segunda.timestamp, "la de en medio")
        nombres = {e.timestamp: e.label for e in history.load()}
        self.assertEqual(nombres[segunda.timestamp], "la de en medio")
        self.assertEqual(nombres[primera.timestamp], "")
        self.assertEqual(nombres[tercera.timestamp], "")

    def test_se_borra_una_sola(self):
        primera, segunda, tercera = self._tres()
        quedan = history.remove(segunda.timestamp)
        self.assertEqual(len(quedan), 2)
        self.assertNotIn(segunda.timestamp, [e.timestamp for e in quedan])
        self.assertIn(primera.timestamp, [e.timestamp for e in quedan])

    def test_borrar_una_que_no_esta_no_rompe_nada(self):
        self._tres()
        self.assertEqual(len(history.remove(1.0)), 3)

    def test_sin_nombre_se_queda_sin_nombre(self):
        entrada = history.from_result(_resultado(), "CPU", 2.0)
        self.assertEqual(entrada.label, "")

    def test_un_nombre_con_espacios_de_sobra_se_recorta(self):
        entrada = history.from_result(_resultado(), "CPU", 2.0)
        history.append(entrada)
        history.rename(entrada.timestamp, "   verano   ")
        self.assertEqual(history.load()[0].label, "verano")

    def test_la_duracion_de_la_medida_se_guarda(self):
        """Es la mitad de lo que hace comparable una cifra con otra."""
        entrada = history.from_result(_resultado(), "CPU", 15.0)
        history.append(entrada)
        self.assertEqual(history.load()[0].seconds, 15.0)
