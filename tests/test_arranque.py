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
from tests import qt

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


class TestWhetherItHasV2(BancoDeGuarda):
    """For the compatible build to say when the normal one would run: yes,
    no, and «can't tell», which is not «no»."""

    def test_a_modern_one_has_it(self):
        self.montar(cpuinfo=MODERNO)
        self.assertIs(guarda.has_x86_64_v2(), True)

    def test_a_phenom_ii_has_not(self):
        self.montar(cpuinfo=PHENOM_II)
        self.assertIs(guarda.has_x86_64_v2(), False)

    def test_without_flags_or_off_x86_it_cannot_tell(self):
        self.montar(cpuinfo="processor\t: 0\n")
        self.assertIsNone(guarda.has_x86_64_v2())
        self.montar(cpuinfo=MODERNO, maquina="aarch64")
        self.assertIsNone(guarda.has_x86_64_v2())


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

        cls.app = qt.app()

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

    def test_el_nombre_que_no_esta_no_se_traga(self):
        """El caso que lo destapó fue `--page Rendimiento` cuando la sección
        se llamaba «Benchmark»: guardaba una captura de Inicio sin quejarse.
        Aquel nombre ya existe —la barra lateral va en castellano—, así que lo
        que se comprueba es lo de fondo: uno que no está se dice."""
        ventana = self._ventana()
        self.assertTrue(ventana.select_section("Rendimiento"))
        self.assertFalse(ventana.select_section("Benchmarking"))

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
        self.assertIn("Rendimiento", nombres)
        self.assertNotIn("Benchmark", nombres,
                         "la barra lateral va en castellano")


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

        # El caso real fue «Rendimiento» cuando la sección se llamaba
        # «Benchmark». Desde que el menú va entero en castellano ese nombre sí
        # existe, así que aquí va uno que no puede existir: lo que se prueba es
        # el camino, no aquel nombre.
        with tempfile.TemporaryDirectory() as carpeta:
            destino = pathlib.Path(carpeta) / "no-deberia-existir.png"
            hecho = self._lanzar("--screenshot", str(destino),
                                 "--page", "Berenjena", "--size", "400x300")

        self.assertEqual(hecho.returncode, 2, hecho.stderr)
        self.assertIn("Berenjena", hecho.stderr)
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
        self.assertIn("Rendimiento", hecho.stderr)



class TestUnaSeccionQueEsteEquipoNoTiene(unittest.TestCase):
    """`--page Batería` en un sobremesa.

    La sección existe en la lista y se esconde con la primera lectura, cuando
    se ve que el equipo no tiene batería. La validación de `--page` corría
    antes de esa lectura, así que daba por buena la sección, la captura se
    hacía después de esconderla —con la ventana ya en Inicio— y salía con
    código 0 y «captura guardada». Es el mismo fallo que el de un nombre que
    no existe, por otro camino.
    """

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = qt.app()

    def _ventana_con(self, baterias):
        from silux.model import Battery, CpuInfo, Snapshot
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        ventana = MainWindow(Preferences())
        self.addCleanup(ventana.close)
        self.assertTrue(ventana.select_section("Batería"))
        foto = Snapshot(monotonic_ns=0, cpu=CpuInfo(),
                        batteries=(Battery(name="BAT0", percent=80.0),) if baterias else ())
        ventana._on_sample(foto)
        return ventana

    def test_sin_bateria_la_seccion_pedida_ya_no_esta(self):
        from silux.ui.app import seccion_que_falta

        ventana = self._ventana_con(baterias=False)
        self.assertIsNotNone(seccion_que_falta(ventana, "Batería"))

    def test_con_bateria_si_esta(self):
        from silux.ui.app import seccion_que_falta

        ventana = self._ventana_con(baterias=True)
        self.assertIsNone(seccion_que_falta(ventana, "Batería"))

    def test_de_punta_a_punta_en_un_equipo_sin_bateria(self):
        """Con el programa de verdad. Solo donde no hay batería, que es donde
        pasa: en un portátil la captura de Batería es correcta."""
        import subprocess
        import sys
        import tempfile

        from silux.providers.battery import Batteries

        if Batteries().available() and _hay_bateria():
            self.skipTest("este equipo tiene batería")
        with tempfile.TemporaryDirectory() as carpeta:
            destino = pathlib.Path(carpeta) / "bateria.png"
            hecho = subprocess.run(
                [sys.executable, "-m", "silux.ui.app", "--screenshot",
                 str(destino), "--page", "Batería", "--size", "400x300"],
                cwd=str(RAIZ), env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
                capture_output=True, text=True, timeout=180)
            self.assertEqual(hecho.returncode, 2, hecho.stdout + hecho.stderr)
            self.assertNotIn("captura guardada", hecho.stdout)
            self.assertFalse(destino.exists(), "guardó la captura de otra página")


def _hay_bateria() -> bool:
    from tests import muestras

    return bool(muestras.foto_real().batteries)



class TestLoQueSeFuerzaNoSeGuarda(unittest.TestCase):
    """`--dark`, `--compact`, `--font-scale` y `--size` son para
    esta ejecución, y la ventana los guardaba al cerrar.

    `closeEvent` guarda las preferencias que tiene en memoria, y esas llevaban
    dentro lo que se le había forzado. Una captura con `--compact` dejaba la
    densidad compacta para siempre; la quinta auditoría lo vio cuando todas
    sus capturas a 1280×800 empezaron a salir compactas a partir de la
    primera que lo era.
    """

    GUARDADAS = {"theme": "light", "density": "normal", "font_scale": "normal",
                 "window_width": 900, "window_height": 680}

    def test_una_captura_no_cambia_las_preferencias(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as config:
            ajustes = pathlib.Path(config) / "silux" / "settings.json"
            ajustes.parent.mkdir()
            ajustes.write_text(json.dumps(self.GUARDADAS))
            hecho = subprocess.run(
                [sys.executable, "-m", "silux.ui.app", "--screenshot",
                 str(pathlib.Path(config) / "x.png"), "--page", "CPU",
                 "--dark", "--compact",
                 "--font-scale", "grande", "--size", "700x500"],
                cwd=str(RAIZ), capture_output=True, text=True, timeout=180,
                env=dict(os.environ, QT_QPA_PLATFORM="offscreen",
                         XDG_CONFIG_HOME=config))
            self.assertEqual(hecho.returncode, 0, hecho.stderr)
            despues = json.loads(ajustes.read_text())
        for campo, valor in self.GUARDADAS.items():
            with self.subTest(campo=campo):
                self.assertEqual(despues.get(campo), valor)

    def test_pero_lo_que_se_cambia_en_ajustes_si(self):
        """Si durante la sesión alguien elige otro valor del que se forzó,
        eso es una preferencia y se guarda."""
        import json
        import tempfile
        from dataclasses import replace

        from PySide6.QtWidgets import QApplication

        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        qt.app()
        with tempfile.TemporaryDirectory() as config, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
            forzadas = {"theme": ("light", "dark"), "density": ("normal", "compact")}
            ventana = MainWindow(Preferences(theme="dark", density="compact"),
                                 forzadas=forzadas)
            ventana._on_preferences(replace(ventana.prefs, theme="system"))
            ventana.close()
            despues = json.loads(
                (pathlib.Path(config) / "silux" / "settings.json").read_text())
        self.assertEqual(despues["theme"], "system")
        self.assertEqual(despues["density"], "normal")


if __name__ == "__main__":
    unittest.main()
