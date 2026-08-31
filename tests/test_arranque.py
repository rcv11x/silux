"""Lo que decide el programa antes de que haya una ventana.

Dos cosas que hasta ahora pasaban en silencio, y las dos acaban con alguien
mirando una pantalla que no explica nada: un Qt que el procesador no puede
ejecutar —«Instrucción ilegal» y un volcado— y un `--page` con un nombre que
no existe, que guardaba la captura de la página que no era y decía que todo
había ido bien.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from silux.ui import guarda

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Un Phenom II: llega hasta SSE3 y no tiene SSE4.1, SSE4.2 ni POPCNT. Es una
# de las piezas que el techo de Qt deja fuera, y de las que el autor quiere
# que sigan pudiendo mirar qué llevan dentro.
PHENOM_II = ("processor\t: 0\n"
             "model name\t: AMD Phenom(tm) II X4 955\n"
             "flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr "
             "sse sse2 pni cx16 lahf_lm\n")

MODERNO = ("processor\t: 0\n"
           "model name\t: Intel(R) Core(TM) i5-10400\n"
           "flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr sse "
           "sse2 pni ssse3 sse4_1 sse4_2 popcnt cx16 lahf_lm avx avx2\n")


class BancoDeGuarda(unittest.TestCase):
    """Le da a la guarda un procesador y un Qt inventados.

    Los parches se arrancan a mano y se paran en `addCleanup` en vez de con
    `self.enterContext`, que es de Python 3.11: el suelo declarado es el 3.10 y
    es el que va dentro del AppImage.
    """

    def _con_cierre(self, parche):
        parche.start()
        self.addCleanup(parche.stop)

    def montar(self, cpuinfo=PHENOM_II, pyside=(6, 11), maquina="x86_64",
               entorno=None):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        ruta = pathlib.Path(carpeta.name) / "cpuinfo"
        ruta.write_text(cpuinfo, encoding="utf-8")

        self._con_cierre(mock.patch.object(guarda, "CPUINFO", str(ruta)))
        self._con_cierre(mock.patch.object(
            guarda.os, "uname", return_value=mock.Mock(machine=maquina)))
        self._con_cierre(mock.patch.object(
            guarda, "version_de_pyside", return_value=pyside))
        self._con_cierre(mock.patch.dict(os.environ, entorno or {}, clear=False))
        if entorno is None:
            os.environ.pop(guarda.ESCAPE, None)


class TestLaGuardaAvisaCuandoToca(BancoDeGuarda):
    def test_un_procesador_al_que_le_faltan_instrucciones_se_para(self):
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11))
        aviso = guarda.diagnostico()
        self.assertIsNotNone(aviso, "un Phenom II con Qt 6.11 no arranca, y "
                                    "callarse aquí es dejarle un SIGILL")

    def test_el_aviso_nombra_las_instrucciones_que_faltan(self):
        """Sin decir cuáles, el mensaje no se puede ni verificar ni buscar."""
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11))
        aviso = guarda.diagnostico()
        for bandera in ("sse4_1", "sse4_2", "popcnt", "ssse3"):
            self.assertIn(bandera, aviso)
        # Las que sí tiene no se nombran: sobran y confunden.
        self.assertNotIn("pni", aviso)

    def test_el_aviso_dice_como_salir_de_ahi(self):
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11))
        aviso = guarda.diagnostico()
        self.assertIn("PySide6<6.10", aviso,
                      "hay que decir con qué versión sí abre")
        self.assertIn("silux.cli", aviso,
                      "y que el volcado en terminal funciona igual sin Qt")

    def test_el_aviso_sale_traducido_y_no_en_claves(self):
        """`_()` devuelve la clave cuando la frase no está escrita, y una
        pantalla con «guard.cpu.why» es peor que no decir nada."""
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11))
        aviso = guarda.diagnostico()
        self.assertNotIn("guard.cpu.", aviso)


class TestLaGuardaSeCallaCuandoNoSabe(BancoDeGuarda):
    """Equivocarse hacia el otro lado es no dejar arrancar a quien sí podía."""

    def test_un_procesador_moderno_no_se_entera_de_nada(self):
        self.montar(cpuinfo=MODERNO, pyside=(6, 11))
        self.assertIsNone(guarda.diagnostico())

    def test_con_un_qt_por_debajo_del_techo_no_hay_problema(self):
        """6.9 es la última serie que se compila para x86-64 a secas: en ese
        Phenom II arranca, así que pararlo sería inventarse un fallo."""
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 9))
        self.assertIsNone(guarda.diagnostico())

    def test_sin_saber_que_qt_hay_no_se_bloquea(self):
        """Es lo normal dentro del AppImage, que lleva PySide6 copiado y no
        instalado. Ahí la guarda de verdad es la del AppRun, que ya corrió."""
        self.montar(cpuinfo=PHENOM_II, pyside=None)
        self.assertIsNone(guarda.diagnostico())

    def test_fuera_de_x86_la_pregunta_no_aplica(self):
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11), maquina="aarch64")
        self.assertIsNone(guarda.diagnostico())

    def test_un_cpuinfo_sin_linea_de_banderas_no_bloquea(self):
        """El fallo que se paga caro: sin banderas, «no publica ninguna de las
        cinco» y «no contestó» son la misma respuesta con el signo cambiado.
        Confundirlas deja sin interfaz a un equipo que iba bien."""
        self.montar(cpuinfo="processor\t: 0\nmodel name\t: algo raro\n",
                    pyside=(6, 11))
        self.assertEqual(guarda.banderas_que_faltan(), ())
        self.assertIsNone(guarda.diagnostico())

    def test_sin_cpuinfo_tampoco(self):
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11))
        with mock.patch.object(guarda, "CPUINFO", "/no/existe/cpuinfo"):
            self.assertEqual(guarda.banderas_que_faltan(), ())
            self.assertIsNone(guarda.diagnostico())

    def test_la_variable_de_escape_abre_la_puerta(self):
        """La regla puede equivocarse —una distribución compila su Qt como
        quiere—, y equivocarse tiene que costar una variable de entorno."""
        self.montar(cpuinfo=PHENOM_II, pyside=(6, 11),
                    entorno={guarda.ESCAPE: "1"})
        self.assertIsNone(guarda.diagnostico())


class TestLasDosGuardasMiranLoMismo(unittest.TestCase):
    """La del AppRun y la del código fuente, con la misma lista de banderas.

    Si el empaquetador aprende a reconocer una instrucción más leyendo el
    desensamblado, la de aquí tiene que enterarse: son la misma comprobación
    hecha en dos sitios, y separadas dejarían de decir lo mismo del mismo
    equipo. Es la misma razón por la que las dos listas blancas de MSR tienen
    su test.
    """

    def test_las_banderas_son_las_mismas(self):
        import tools.build_appimage as build

        del_empaquetador = {juego for juego, _patron in build.JUEGOS}
        self.assertEqual(set(guarda.JUEGOS_V2), del_empaquetador)


class TestUnaSeccionQueNoExiste(unittest.TestCase):
    """`--page` con un nombre que no está.

    Se tragaba en silencio: `select_section` recorría la lista, no encontraba
    nada y volvía sin decirlo, así que la ventana se quedaba donde estaba. En
    la rama de la captura eso es peor que un fallo, porque el archivo se
    escribe igual y el programa dice «captura guardada» con la página que no
    era dentro.
    """

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _ventana(self):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences())
        self.addCleanup(ventana.close)
        return ventana

    def test_un_nombre_que_no_existe_se_dice(self):
        ventana = self._ventana()
        self.assertFalse(ventana.select_section("Berenjena"))

    def test_y_no_mueve_la_seccion_abierta(self):
        ventana = self._ventana()
        ventana.select_section("Sensores")
        antes = ventana.nav.currentRow()
        ventana.select_section("Berenjena")
        self.assertEqual(ventana.nav.currentRow(), antes)

    def test_rendimiento_no_es_el_nombre_de_ninguna(self):
        """El caso que lo destapó: la sección se llama «Benchmark», y
        `--page Rendimiento` guardaba una captura de Inicio sin quejarse."""
        ventana = self._ventana()
        self.assertFalse(ventana.select_section("Rendimiento"))
        self.assertTrue(ventana.select_section("Benchmark"))

    def test_una_que_si_existe_se_encuentra(self):
        ventana = self._ventana()
        for nombre in ("Sensores", "nav.sensors", "CPU"):
            with self.subTest(nombre=nombre):
                self.assertTrue(ventana.select_section(nombre))

    def test_se_pueden_ofrecer_los_nombres_que_hay(self):
        """Decir que no existe sin decir cuáles existen es media respuesta."""
        ventana = self._ventana()
        nombres = ventana.section_names()
        self.assertIn("Sensores", nombres)
        self.assertIn("Benchmark", nombres)
        self.assertNotIn("Rendimiento", nombres)


class TestLaCapturaNoSaleDeLaPaginaEquivocada(unittest.TestCase):
    """De punta a punta, porque es donde estaba el fallo.

    En proceso no se puede: `build_app` construye su propia `QApplication` y
    en esta suite ya hay una. Así que se lanza de verdad, que además es lo que
    ejercita el camino real de `--screenshot`.
    """

    def _lanzar(self, *argumentos):
        entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        return subprocess.run(
            [sys.executable, "-m", "silux.ui.app", *argumentos],
            cwd=str(RAIZ), env=entorno, capture_output=True, text=True,
            timeout=180)

    def test_un_page_desconocido_falla_y_no_escribe_nada(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            destino = pathlib.Path(carpeta) / "no-deberia-existir.png"
            hecho = self._lanzar("--screenshot", str(destino),
                                 "--page", "Rendimiento", "--size", "400x300")

        self.assertEqual(hecho.returncode, 2, hecho.stderr)
        self.assertIn("Rendimiento", hecho.stderr)
        self.assertNotIn("captura guardada", hecho.stdout,
                         "dijo que la había guardado")
        self.assertFalse(destino.exists(),
                         "escribió una captura de la página que no era")

    def test_y_dice_cuales_hay(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            destino = pathlib.Path(carpeta) / "x.png"
            hecho = self._lanzar("--screenshot", str(destino),
                                 "--page", "Berenjena", "--size", "400x300")

        self.assertIn("Sensores", hecho.stderr)
        self.assertIn("Benchmark", hecho.stderr)


if __name__ == "__main__":
    unittest.main()
