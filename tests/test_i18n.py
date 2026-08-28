"""El idioma de la interfaz.

El original es el español y no una lista de claves simbólicas: cuando falta
una traducción, la pantalla enseña el español, que es lo que el programa decía
antes de que existiera esto.
"""

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from silux import i18n
from silux.i18n import _


class TestIdioma(unittest.TestCase):

    def setUp(self):
        self.addCleanup(i18n.set_language, "es")

    def test_en_espanol_el_texto_sale_tal_cual(self):
        i18n.set_language("es")
        self.assertEqual(_("Apariencia"), "Apariencia")

    def test_traduce_lo_que_esta_en_el_archivo(self):
        i18n.set_language("en")
        self.assertEqual(_("Apariencia"), "Appearance")

    def test_lo_que_falta_sale_en_español(self):
        """Con claves simbólicas la pantalla enseñaría «settings.fluid.desc»;
        con el español de original, enseña el español."""
        i18n.set_language("en")
        self.assertEqual(_("Una frase que nadie ha traducido todavía"),
                         "Una frase que nadie ha traducido todavía")

    def test_un_idioma_que_no_existe_vuelve_al_español(self):
        """No es un error que deba parar el programa."""
        self.assertEqual(i18n.set_language("zz"), "es")
        self.assertEqual(_("Apariencia"), "Apariencia")

    def test_un_archivo_roto_no_tira_la_interfaz(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = pathlib.Path(tmp)
            (carpeta / "xx.json").write_text("{esto no es json", encoding="utf-8")
            with mock.patch.object(i18n, "CARPETA", carpeta):
                self.assertEqual(i18n.set_language("xx"), "es")

    def test_una_entrada_vacia_no_borra_el_texto(self):
        """Un archivo a medio traducir deja huecos, no líneas en blanco."""
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = pathlib.Path(tmp)
            (carpeta / "xx.json").write_text(
                json.dumps({"Tema": "", "Densidad": "Density"}), encoding="utf-8")
            with mock.patch.object(i18n, "CARPETA", carpeta):
                i18n.set_language("xx")
                self.assertEqual(_("Tema"), "Tema")
                self.assertEqual(_("Densidad"), "Density")

    def test_el_español_siempre_está_en_la_lista(self):
        self.assertIn("es", i18n.disponible())

    def test_el_ingles_esta_completo(self):
        """Un hueco en el archivo que se reparte es una frase en español en
        medio de una interfaz en inglés."""
        ruta = i18n.CARPETA / "en.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        vacias = [k for k, v in datos.items() if not v]
        self.assertEqual(vacias, [], f"{len(vacias)} sin traducir")

    def test_cada_idioma_se_lee_en_su_propia_lengua(self):
        """Quien busca el suyo lo reconoce escrito como lo escribe él."""
        self.assertEqual(i18n.IDIOMAS["en"], "English")


class TestLoQueNoSeTraduce(unittest.TestCase):
    """Lo que sale del propio equipo no es texto del programa: es el dato."""

    def test_los_proveedores_no_llaman_a_la_traduccion(self):
        raiz = pathlib.Path(__file__).resolve().parent.parent
        for archivo in (raiz / "silux" / "providers").rglob("*.py"):
            with self.subTest(archivo=archivo.name):
                self.assertNotIn("from ..i18n import",
                                 archivo.read_text(encoding="utf-8"))


class TestElIdiomaLlegaALaInterfaz(unittest.TestCase):
    """Traducir las cadenas no basta: hay que aplicarlas donde se montan."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(i18n.set_language, "es")

    def _ventana(self, idioma):
        from silux.settings import Preferences
        from silux.ui.app import MainWindow

        i18n.set_language(idioma)
        self.ventana = MainWindow(Preferences(language=idioma).normalized())
        return self.ventana

    def _menu(self, ventana):
        return [ventana.nav.item(i).text() for i in range(ventana.nav.count())]

    def test_el_menu_se_traduce(self):
        self.assertIn("Sensors", self._menu(self._ventana("en")))

    def test_en_español_sigue_en_español(self):
        self.assertIn("Sensores", self._menu(self._ventana("es")))

    def test_una_seccion_se_pide_por_su_nombre_en_español(self):
        """Un script escrito contra `--page Sensores` no puede dejar de
        funcionar porque alguien se ponga la interfaz en inglés."""
        ventana = self._ventana("en")
        ventana.select_section("Sensores")
        self.assertEqual(ventana.nav.currentItem().text(), "Sensors")

    def test_y_tambien_por_el_traducido(self):
        ventana = self._ventana("en")
        ventana.select_section("Sensors")
        self.assertEqual(ventana.nav.currentItem().text(), "Sensors")


class TestLaHerramientaNoBorraTrabajo(unittest.TestCase):
    """`gen_lang --write` reescribe los archivos, y lo que no encuentra el
    extractor no puede desaparecer sin más: puede ser una cadena que se
    traduce con una variable, y tirar el trabajo de alguien sin preguntar es
    lo peor que puede hacer esta herramienta."""

    def test_una_traduccion_que_el_extractor_no_ve_se_conserva(self):
        import importlib.util

        raiz = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "gen_lang", raiz / "tools" / "gen_lang.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        with tempfile.TemporaryDirectory() as tmp:
            carpeta = pathlib.Path(tmp)
            (carpeta / "xx.json").write_text(
                json.dumps({"Sensores": "Sensors"}), encoding="utf-8")
            with mock.patch.object(modulo, "LANG", carpeta):
                modulo.actualizar("xx", {"Tema": []}, escribir=True)
            datos = json.loads((carpeta / "xx.json").read_text(encoding="utf-8"))

        self.assertEqual(datos.get("Sensores"), "Sensors")
        self.assertIn("Tema", datos)

    def test_el_menu_esta_entre_lo_que_se_extrae(self):
        """Se traduce con `_(name)` sobre una variable, así que hay que
        declararlo: sin eso desapareció del archivo en la primera pasada."""
        import importlib.util

        raiz = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "gen_lang", raiz / "tools" / "gen_lang.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.assertIn("Sensores", modulo.cadenas_de_tablas())
