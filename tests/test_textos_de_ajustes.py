"""Dos frases de Ajustes que decían lo que no era.

«Activado, aparecen las 53 que devuelve CPUID en este equipo»: el 53 estaba
escrito en la frase, y la página CPU contaba 61 en el 5800X3D. La cuenta la
da un solo sitio, la página CPU, que la saca del procesador.

Y en «Construido con», Python figuraba «sin dependencias fuera de la
biblioteca estándar» justo encima de PySide6, que es una.
"""

import json
import pathlib
import re
import subprocess
import sys
import unittest

from silux import i18n
from silux.i18n import _
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

IDIOMAS = pathlib.Path(i18n.__file__).parent / "db" / "lang"


class TestLasFrases(unittest.TestCase):

    def test_la_ayuda_de_las_banderas_no_lleva_una_cuenta_escrita(self):
        for archivo in sorted(IDIOMAS.glob("*.json")):
            with self.subTest(idioma=archivo.stem):
                frase = json.loads(archivo.read_text())["settings.allflags.help"]
                self.assertIsNone(re.search(r"\d", frase), frase)

    def test_python_no_presume_de_no_depender_de_nada(self):
        es = json.loads((IDIOMAS / "es.json").read_text())
        self.assertNotIn("sin dependencias", es["about.python"])
        en = json.loads((IDIOMAS / "en.json").read_text())
        self.assertNotIn("no dependencies", en["about.python"])

    def test_y_lo_que_dice_ahora_es_verdad(self):
        """El volcado en terminal no carga PySide6."""
        raiz = pathlib.Path(__file__).resolve().parent.parent
        salida = subprocess.run(
            [sys.executable, "-c",
             "import sys, silux.cli; print('PySide6' in sys.modules)"],
            cwd=raiz, capture_output=True, text=True, timeout=60)
        self.assertEqual(salida.stdout.strip(), "False", salida.stderr[-300:])


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestEnPantalla(unittest.TestCase):

    def test_ajustes_y_cpu_no_dan_dos_cuentas(self):
        app = qt.app()
        f = foto(EQUIPOS / "5800x3d")[0]
        cuantas = len(f.cpu.types[0].features)
        with pantalla.Ventana(f) as ventana:
            ventana.select_section("Ajustes")
            for _vez in range(3):
                app.processEvents()
            ajustes = pantalla.textos_de(ventana.settings_page)
            self.assertIn(_("settings.allflags.help"), ajustes)
            self.assertIn(_("about.python"), ajustes)
            con_cifra = [t for t in ajustes if "CPUID" in t and re.search(r"\d", t)]
            self.assertEqual(con_cifra, [])
            ventana.select_section("CPU")
            for _vez in range(3):
                app.processEvents()
            cpu = pantalla.textos_de(ventana.stack.currentWidget())
            self.assertTrue([t for t in cpu
                             if t.startswith(_("cpu.flags.count").format(n=cuantas))], cuantas)

    def test_network_speed_says_what_the_network_page_says(self):
        """The same sentence in both places, not two explanations of bits
        and bytes."""
        app = qt.app()
        with pantalla.Ventana(foto(EQUIPOS / "5800x3d")[0]) as window:
            window.select_section("Red")
            for _turn in range(3):
                app.processEvents()
            network = [t for t in pantalla.textos_de(window.stack.currentWidget())
                       if "MB/s" in t and "Mb/s" in t]
            window.select_section("Ajustes")
            for _turn in range(3):
                app.processEvents()
            settings = [t for t in pantalla.textos_de(window.settings_page)
                        if "MB/s" in t and "Mb/s" in t]
        self.assertEqual(len(network), 1, network)
        self.assertEqual(settings, network)


if __name__ == "__main__":
    unittest.main()
