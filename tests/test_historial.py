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
    """Una prueba con las cargas que guarda una de verdad: las dos que
    puntúan y la verificación, que se mide en bytes y no en operaciones."""
    medidas = tuple(
        Medida(load=carga, threads=n, operations=int(ops_por_hilo * n * 2), seconds=2.0,
               bytes_=64 * 1024**2 if carga == "verificacion" else None)
        for carga in ("hash", "compresion_dura", "verificacion")
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



class TestUnHistorialEstropeadoNoImpideArrancar(_ConCarpetaPropia):
    """El historial lo escribe el programa, pero vive en el disco de alguien.

    Solo se atrapaban un archivo ilegible y un JSON mal formado. Un UTF-8
    roto lanzaba `UnicodeDecodeError`, y una entrada con un campo del tipo
    equivocado se leía sin rechistar y reventaba después: al ordenar si la
    fecha era texto, al sumar si las medidas eran una lista. En los dos casos
    la traza moría montando la página de Rendimiento, o sea, la ventana no
    abría, y tampoco el `--report`, que lee el historial para su apartado.
    """

    def _con(self, contenido: bytes):
        history.data_dir().mkdir(parents=True, exist_ok=True)
        history.history_path().write_bytes(contenido)

    def _buena(self) -> dict:
        import dataclasses
        entrada = history.from_result(_resultado(), "CPU", 2.0)
        return {k: v for k, v in dataclasses.asdict(entrada).items()}

    def _entradas(self, *malas):
        import json
        self._con(json.dumps([self._buena(), *malas]).encode())
        return history.load()

    def test_un_utf8_roto(self):
        self._con(b'[{"cpu": "\xff\xfe"}]')
        self.assertEqual(history.load(), [])

    def test_una_fecha_que_es_texto(self):
        mala = dict(self._buena(), timestamp="ayer")
        self.assertEqual(len(self._entradas(mala)), 1)

    def test_unas_medidas_que_son_una_lista(self):
        mala = dict(self._buena(), scores=[1, 2, 3])
        self.assertEqual(len(self._entradas(mala)), 1)

    def test_una_duracion_vacia(self):
        mala = dict(self._buena(), seconds=None)
        self.assertEqual(len(self._entradas(mala)), 1)

    def test_una_medida_que_no_es_un_numero(self):
        mala = dict(self._buena(), scores={"compresion/8": "mucho"})
        self.assertEqual(len(self._entradas(mala)), 1)

    def test_lo_que_queda_se_puede_usar(self):
        """Que no se cuele nada que reviente al ordenar, sumar o comparar."""
        leidas = self._entradas(dict(self._buena(), timestamp="ayer"),
                                dict(self._buena(), scores=[1]),
                                dict(self._buena(), seconds=None))
        for entrada in leidas:
            entrada.total()
            entrada.comparable_con(entrada)

    def test_la_pagina_de_rendimiento_se_monta_igual(self):
        import json
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from silux.settings import Preferences
        from silux.ui import theme
        from silux.ui.pages.performance import PerformancePage

        app = QApplication.instance() or QApplication([])
        self._con(json.dumps([dict(self._buena(), timestamp="ayer"),
                              self._buena()]).encode())
        PerformancePage(theme.palette_for(app, "dark"), Preferences())


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



class TestLaCifraConQueSeCompara(_ConCarpetaPropia):
    """Comparar dos pruebas con la puntuación, no con la suma en crudo.

    `Entry.total()` sumaba lo medido a todos los hilos de todas las cargas, y
    la verificación va en bytes por segundo —unos 1,6·10¹¹ en el patrón—
    mientras las demás van en operaciones: pesaba el 99,99999 % del total. Así
    el «±X %» del historial y el filtro de la deriva térmica los decidía la
    carga que no puntúa y que depende de la zlib de cada distribución. Con la
    misma puntuación y otra zlib salía −50 %, y una prueba cancelada antes de
    la verificación, −100 %. Los datos de aquí son los que guarda una prueba
    de verdad: las cargas que puntúan y la verificación en bytes.
    """

    def _entrada(self, ts, puntua=1000.0, verifica=1.6e11, faltan=()):
        from silux import score
        medidas = {}
        for carga in score.PUNTUABLES:
            if carga not in faltan:
                medidas[f"{carga}/8"] = puntua
                medidas[f"{carga}/1"] = puntua / 8
        if verifica:
            medidas["verificacion/8"] = verifica
        return history.Entry(timestamp=ts, cpu="CPU", threads=8, seconds=15.0,
                             scores=medidas, score_version=score.VERSION)

    def test_otra_zlib_no_cambia_la_comparacion(self):
        antes = self._entrada(1)
        despues = self._entrada(2, verifica=0.8e11)
        _, cambio = history.comparar(despues, [despues, antes])
        self.assertAlmostEqual(cambio, 0.0, places=1)

    def test_lo_que_puntua_si_la_cambia(self):
        antes = self._entrada(1)
        despues = self._entrada(2, puntua=1100.0)
        _, cambio = history.comparar(despues, [despues, antes])
        self.assertAlmostEqual(cambio, 10.0, places=0)

    def test_una_prueba_sin_la_verificacion_se_compara_igual(self):
        antes = self._entrada(1)
        despues = self._entrada(2, verifica=None)
        _, cambio = history.comparar(despues, [despues, antes])
        self.assertAlmostEqual(cambio, 0.0, places=1)

    def test_a_una_que_le_falta_una_que_puntua_no_se_la_compara(self):
        """Era el −100 % de una prueba cancelada a medias."""
        from silux import score
        antes = self._entrada(1)
        despues = self._entrada(2, faltan=(score.PUNTUABLES[-1],))
        self.assertIsNone(history.comparar(despues, [despues, antes]))

    def test_la_deriva_termica_tampoco_mira_la_verificacion(self):
        import dataclasses
        viejas = [dataclasses.replace(self._entrada(10 + i), temperature_peak_c=70.0)
                  for i in range(4)]
        nueva = dataclasses.replace(self._entrada(100, verifica=0.8e11),
                                    temperature_peak_c=80.0)
        self.assertIsNotNone(history.deriva_termica(nueva, viejas))



class TestLaMismaDuracion(unittest.TestCase):
    """Lo que se guarda es lo que duró de verdad, no lo que se pidió.

    `comparable_con` exigía que dos duraciones coincidieran con 0,01 s de
    margen, sobre lo que tardó la medida más larga: el pedido más lo que tarde
    en acabar la operación en vuelo. Son de 3 a 8 ms con la zlib-ng de Fedora
    y hasta 128 ms con la del AppImage, así que dos pruebas de quince segundos
    dejaban de compararse según la suerte (F-M33). El margen nuevo cubre ese
    exceso y no junta las dos duraciones más cercanas que se ofrecen: la
    prueba rápida de 2 s y la de 3.
    """

    def _entrada(self, segundos):
        return history.Entry(timestamp=0, cpu="CPU", threads=8, seconds=segundos,
                             scores={})

    def test_quince_segundos_y_unos_milisegundos_son_quince(self):
        self.assertTrue(self._entrada(15.004).comparable_con(self._entrada(15.016)))

    def test_con_la_zlib_mas_lenta_tambien(self):
        self.assertTrue(self._entrada(2.003).comparable_con(self._entrada(2.128)))

    def test_pero_dos_y_tres_segundos_no_son_lo_mismo(self):
        self.assertFalse(self._entrada(2.0).comparable_con(self._entrada(3.0)))

    def test_ni_quince_y_treinta(self):
        self.assertFalse(self._entrada(15.0).comparable_con(self._entrada(30.0)))


class TestPuntuacion(unittest.TestCase):
    def test_es_la_puntuacion_a_todos_los_hilos(self):
        from silux import score
        entrada = history.from_result(_resultado(100.0, hilos=8), "CPU", 2.0)
        self.assertEqual(round(entrada.total()),
                         score.puntuar(entrada.scores, 8)[1])

    def test_sin_medidas_no_hay_puntuación(self):
        vacia = history.from_result(Result((), Conditions(), ()), "CPU", 2.0)
        self.assertIsNone(vacia.total())


if __name__ == "__main__":
    unittest.main()


class TestConQueSeMidio(unittest.TestCase):
    """Cada prueba guarda con qué bibliotecas se tomó.

    Ya no deciden la puntuación —desde la v6 las cargas que dependen del
    sistema no cuentan—, y siguen guardándose porque son lo único que permite
    leer las cifras de esas cargas: la misma pieza da 14,9 GB/s en la
    verificación con zlib-ng y 1,5 con la zlib de Ubuntu 22.04.
    """

    def test_se_guardan_las_dos_bibliotecas_y_las_banderas(self):
        entrada = history.from_result(Result(), "CPU de prueba", 15.0)
        self.assertTrue(entrada.zlib_version,
                        "sin la versión de zlib no se pueden leer sus cargas")
        self.assertTrue(entrada.openssl_version,
                        "la derivación de clave se lleva un ×1,38 entre "
                        "OpenSSL 3.0 y 3.5, así que hay que saber cuál era")
        self.assertIsInstance(entrada.zlib_simd, tuple)

    def test_una_entrada_vieja_se_lee_sin_ellas(self):
        """El campo es nuevo: las pruebas de antes no lo traen y valen igual."""
        vieja = {"timestamp": 1.0, "cpu": "x", "threads": 8, "seconds": 15.0,
                 "scores": {}}
        campos = {f.name for f in __import__("dataclasses").fields(history.Entry)}
        entrada = history.Entry(**{k: v for k, v in vieja.items() if k in campos})
        self.assertIsNone(entrada.openssl_version)


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
