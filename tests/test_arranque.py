"""Lo que decide el programa antes de que haya una ventana.

Un Qt que el procesador no puede ejecutar acaba en «Instrucción ilegal» y un
volcado, sin nada que explique de quién es la culpa. Aquí se le dan a la
guarda procesadores y versiones de Qt inventados para ver qué decide con cada
uno, en los dos sentidos: que avise donde hay que avisar, y sobre todo que no
avise donde no lo sabe.
"""

import os
import pathlib
import unittest
from unittest import mock

from silux.ui import guarda

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
    """Le da a la guarda un procesador y un Qt inventados."""

    def montar(self, cpuinfo=PHENOM_II, pyside=(6, 11), maquina="x86_64",
               entorno=None):
        tmp = self.enterContext(
            __import__("tempfile").TemporaryDirectory())
        ruta = pathlib.Path(tmp) / "cpuinfo"
        ruta.write_text(cpuinfo, encoding="utf-8")
        self.enterContext(mock.patch.object(guarda, "CPUINFO", str(ruta)))
        self.enterContext(mock.patch.object(
            guarda.os, "uname", return_value=mock.Mock(machine=maquina)))
        self.enterContext(mock.patch.object(
            guarda, "version_de_pyside", return_value=pyside))
        self.enterContext(mock.patch.dict(
            os.environ, entorno or {}, clear=False))
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


if __name__ == "__main__":
    unittest.main()
