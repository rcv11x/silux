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

    def test_una_clave_da_el_español(self):
        i18n.set_language("es")
        self.assertEqual(_("settings.card.appearance"), "Apariencia")

    def test_y_el_ingles_cuando_toca(self):
        i18n.set_language("en")
        self.assertEqual(_("settings.card.appearance"), "Appearance")

    def test_lo_que_falta_en_ingles_sale_en_español(self):
        """El escalón que hace utilizable esto: una traducción a medias enseña
        español entre inglés, que se lee, y no la clave pelada."""
        i18n.set_language("en")
        with mock.patch.dict(i18n._tabla, clear=False) as tabla:
            i18n._tabla.pop("cpu.card.clocks", None)
            self.assertEqual(_("cpu.card.clocks"), "Relojes")

    def test_una_clave_que_no_existe_en_ningun_idioma_se_ve(self):
        """Es lo que hace falta ver para ir a escribirla en las dos lenguas."""
        i18n.set_language("en")
        self.assertEqual(_("esto.no.existe"), "esto.no.existe")

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
            (carpeta / "es.json").write_text(
                json.dumps({"a.uno": "Uno", "a.dos": "Dos"}), encoding="utf-8")
            (carpeta / "xx.json").write_text(
                json.dumps({"a.uno": "", "a.dos": "Two"}), encoding="utf-8")
            with mock.patch.object(i18n, "CARPETA", carpeta):
                i18n._base = {}
                i18n.set_language("xx")
                self.assertEqual(_("a.uno"), "Uno")
                self.assertEqual(_("a.dos"), "Two")
        i18n._base = {}

    def test_el_español_siempre_está_en_la_lista(self):
        self.assertIn("es", i18n.disponible())

    def test_cada_clave_del_español_tiene_su_inglés(self):
        """Un hueco es una frase en español en medio de una interfaz en
        inglés: se lee, pero canta."""
        es = json.loads((i18n.CARPETA / "es.json").read_text(encoding="utf-8"))
        en = json.loads((i18n.CARPETA / "en.json").read_text(encoding="utf-8"))
        faltan = [k for k in es if not en.get(k)]
        self.assertEqual(faltan, [], f"{len(faltan)} sin traducir al inglés")

    def test_las_claves_son_simbolos_y_no_frases(self):
        """Si una clave es una frase, retocarla en el código deja su
        traducción colgada: eso es lo que se dejó atrás."""
        es = json.loads((i18n.CARPETA / "es.json").read_text(encoding="utf-8"))
        frases = [k for k in es if " " in k or len(k) > 40]
        self.assertEqual(frases, [])

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
        self.assertIn("nav.sensors", modulo.cadenas_de_tablas())


class TestCambiarElEspañol(unittest.TestCase):
    """Con la clave siendo el texto español, retocar una frase deja su
    traducción colgada de la versión vieja. No se puede evitar sin reescribir
    el código entero con claves simbólicas, así que al menos se avisa."""

    def _modulo(self):
        import importlib.util

        raiz = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "gen_lang", raiz / "tools" / "gen_lang.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_una_frase_retocada_se_reconoce(self):
        modulo = self._modulo()
        sugerencias = modulo.emparejar(
            {"Movimiento fluido de las gráficas": "Smooth chart motion"},
            ["Movimiento fluido de las gráficas y barras"])
        self.assertEqual(len(sugerencias), 1)
        self.assertEqual(sugerencias[0][2], "Smooth chart motion")

    def test_dos_frases_distintas_no_se_confunden(self):
        """«Frecuencia» y «Frecuencia máxima» se parecen mucho y no significan
        lo mismo: emparejarlas daría una traducción que dice otra cosa."""
        modulo = self._modulo()
        self.assertEqual(
            modulo.emparejar({"Frecuencia": "Frequency"}, ["Frecuencia máxima"]),
            [])

    def test_no_se_arrastra_sola(self):
        """Se sugiere y decide una persona: una traducción movida a la frase
        equivocada es peor que un hueco, porque el hueco se ve."""
        modulo = self._modulo()
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = pathlib.Path(tmp)
            (carpeta / "xx.json").write_text(
                json.dumps({"Tema viejo": "Old theme"}), encoding="utf-8")
            with mock.patch.object(modulo, "LANG", carpeta):
                modulo.actualizar("xx", {"Tema viejo retocado": []}, escribir=True)
            datos = json.loads((carpeta / "xx.json").read_text(encoding="utf-8"))
        self.assertEqual(datos["Tema viejo retocado"], "")
        self.assertEqual(datos["Tema viejo"], "Old theme")


class TestRenderTraduce(unittest.TestCase):
    """La capa de presentación arma frases pegando texto a números, así que
    traducirla no era envolver cadenas sino reescribir las plantillas."""

    def setUp(self):
        self.addCleanup(i18n.set_language, "es")

    def _en(self, funcion, *args):
        from silux import render

        i18n.set_language("en")
        return getattr(render, funcion)(*args)

    def test_una_frase_con_numeros_se_arma_entera(self):
        from silux.model import Clocks

        frase = self._en("turbo_note", Clocks(turbo_enabled=False,
                                              max_turbo_hz=4_550_000_000))
        self.assertIn("silicon", frase)
        self.assertIn("4.55 GHz", frase)

    def test_las_unidades_no_se_traducen(self):
        """«GHz» es «GHz» en cualquier idioma, y el punto decimal se queda:
        es lo que espera quien lee una ficha técnica."""
        from silux import render

        for idioma in ("es", "en"):
            with self.subTest(idioma=idioma):
                i18n.set_language(idioma)
                self.assertEqual(render.hz(4_550_000_000), "4.55 GHz")
                self.assertEqual(render.temperature(82.5), "82.5 °C")

    def test_el_plural_va_dentro_de_la_clave(self):
        from silux.model import MemoryModule as M
        from silux import render

        uno = [M(locator="DIMM_A1", populated=True),
               M(locator="DIMM_B1", populated=False)]
        dos = [M(locator="DIMM_A1", populated=True),
               M(locator="DIMM_B1", populated=True)]
        i18n.set_language("en")
        self.assertIn("1 module", render.memory_channel_label(uno))
        self.assertIn("2 modules", render.memory_channel_label(dos))

    def test_los_avisos_del_disco_se_traducen(self):
        from silux.model import DiskHealth

        avisos = self._en("disk_warnings", DiskHealth(critical_warning=0b1))
        self.assertIn("spare", avisos[0][1].lower())

    def test_el_nivel_del_aviso_sigue_siendo_interno(self):
        """«crítico» decide el color, no se enseña: traducirlo rompería la
        comparación que elige el rojo."""
        from silux.model import DiskHealth

        avisos = self._en("disk_warnings", DiskHealth(critical_warning=0b1))
        self.assertEqual(avisos[0][0], "crítico")


class TestNoQuedaTextoSuelto(unittest.TestCase):
    """Ninguna página monta un widget con una cadena en español a pelo.

    Es lo que no se ve hasta abrir la pantalla en el otro idioma: un título
    que no pasó por `_()` sale en castellano en medio de una interfaz inglesa,
    y ningún test de los normales lo nota.
    """

    PAGINAS = ("app.py", "pages/cpu.py", "pages/memory.py", "pages/monitor.py",
               "pages/graphics.py", "pages/storage.py", "pages/settings.py",
               "pages/performance.py")

    def _sueltas(self, ruta):
        import ast
        import re

        fuente = ruta.read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        docs = set()
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, (ast.FunctionDef, ast.ClassDef, ast.Module))
                    and nodo.body):
                primero = nodo.body[0]
                if (isinstance(primero, ast.Expr)
                        and isinstance(primero.value, ast.Constant)):
                    docs.add(id(primero.value))

        # Los constructores que ponen texto en pantalla. Se comprueban estos y
        # no todas las llamadas: un `subprocess.run(["pkexec", …])` lleva
        # cadenas que no son texto de interfaz.
        pintan = {"Card", "QLabel", "QPushButton", "QCheckBox", "Notice",
                  "_Field", "StatTile"}
        sueltas = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            quien = nodo.func.id if isinstance(nodo.func, ast.Name) else None
            if quien not in pintan:
                continue
            for arg in nodo.args:
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and id(arg) not in docs
                        and re.search(r"[a-záéíóúñ]{4}", arg.value)
                        and not re.fullmatch(r"[a-zA-Z_.#]+", arg.value)):
                    sueltas.append((arg.lineno, arg.value[:60]))
        return sueltas

    def test_ninguna_pagina_pinta_español_a_pelo(self):
        raiz = pathlib.Path(__file__).resolve().parent.parent / "silux" / "ui"
        for nombre in self.PAGINAS:
            with self.subTest(archivo=nombre):
                sueltas = self._sueltas(raiz / nombre)
                self.assertEqual(sueltas, [], f"{nombre}: {sueltas}")
