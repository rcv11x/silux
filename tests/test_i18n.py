"""El idioma de la interfaz.

El original es el español y no una lista de claves simbólicas: cuando falta
una traducción, la pantalla enseña el español, que es lo que el programa decía
antes de que existiera esto.
"""

import ast
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
    """Lo que sale del propio equipo no es texto del programa: es el dato.

    Los proveedores traducen, pero solo lo que se inventan: el aviso que
    explica por qué falta un dato, el nombre que le ponen a un sensor
    —«Punto caliente» donde amdgpu dice `junction`—, la función de un motor
    gráfico. Eso lo escribió el autor y se lee en pantalla.

    Lo que leen del equipo pasa entero y sin tocar: el nombre del procesador,
    la etiqueta que publica un chip de sensores, el modelo de un disco. La
    línea que lo separa es verificable sin ejecutar nada: a `_()` solo puede
    llegar un literal escrito en el archivo, o una variable que salga de una
    tabla de claves declarada ahí mismo. Un `_(read_text(...))` o un
    `_(entry["label"])` traduciría un dato, y eso es lo que rompe la
    detección de una gráfica cuando alguien se pone la interfaz en inglés.
    """

    def test_los_proveedores_solo_traducen_lo_que_escriben_ellos(self):
        raiz = pathlib.Path(__file__).resolve().parent.parent
        for archivo in sorted((raiz / "silux" / "providers").rglob("*.py")):
            fuente = archivo.read_text(encoding="utf-8")
            if "i18n import _" not in fuente:
                continue
            arbol = ast.parse(fuente)
            # Las tablas del módulo valen en todas partes; las variables de
            # una función solo dentro de ella.
            fuera = self._fuera_de_toda_funcion(arbol)
            del_modulo = self._tablas_de_literales(fuera)
            asignados_modulo = {n.targets[0].id: n.value for n in fuera.body
                                if isinstance(n, ast.Assign)
                                and len(n.targets) == 1
                                and isinstance(n.targets[0], ast.Name)}
            malas = []
            for ambito in self._ambitos(arbol):
                tablas = self._tablas_de_literales(
                    ambito, asignados_modulo, del_modulo)
                for nodo in ast.walk(ambito):
                    if not (isinstance(nodo, ast.Call)
                            and isinstance(nodo.func, ast.Name)
                            and nodo.func.id == "_" and nodo.args):
                        continue
                    if not self._sale_del_propio_archivo(nodo.args[0], tablas):
                        malas.append(f"{nodo.lineno}: {ast.unparse(nodo)}")
            with self.subTest(archivo=archivo.name):
                self.assertEqual(malas, [],
                                 f"{archivo.name} traduce algo que no escribió: "
                                 f"{malas}")

    @staticmethod
    def _fuera_de_toda_funcion(arbol: ast.AST) -> ast.Module:
        """El módulo con lo que está escrito a su nivel, sin los cuerpos.

        Recogiendo cualquier asignación del archivo se colaban las de dentro
        de las funciones, que es exactamente lo que había que separar.
        """
        return ast.Module(
            body=[n for n in arbol.body
                  if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.ClassDef))],
            type_ignores=[])

    @classmethod
    def _ambitos(cls, arbol: ast.AST) -> list:
        """Cada función del archivo por separado, y el módulo sin ellas."""
        funciones = [n for n in ast.walk(arbol)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        return funciones + [cls._fuera_de_toda_funcion(arbol)]

    @classmethod
    def _tablas_de_literales(cls, arbol: ast.AST, heredado: dict = None,
                             semilla: set = frozenset()) -> set:
        """Los nombres cuyo valor sale de una cadena escrita en este archivo.

        Se parte de las estructuras cuyas hojas son todas cadenas —las tablas
        de claves— y se propaga por asignaciones y bucles hasta que no queda
        nada nuevo: `INTEL_AVISOS` marca `aviso = DRIVERS_CIEGOS.get(driver)`,
        y este a su vez marca la `clave` del bucle que lo recorre.

        Los bucles sobre una tabla de tuplas se miran por columna. En
        `for patron, clave in _ALIMENTACION` cada fila lleva una expresión
        regular y una clave; `clave` es literal y `patron` no, y la diferencia
        está en la posición, no en la fila entera.
        """
        # Las tablas del módulo llegan heredadas: un bucle dentro de una
        # función recorre una tabla declarada arriba del archivo.
        asignados: dict = dict(heredado or {})
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                    and isinstance(nodo.targets[0], ast.Name)):
                asignados[nodo.targets[0].id] = nodo.value

        def es_cadena(nodo) -> bool:
            return isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)

        def sale_de(expresion, nombres: set) -> bool:
            """Si esto es leer una tabla, y no llamar a algo que la menciona.

            Vale `INTEL_AVISOS[clave]` y `DRIVERS_CIEGOS.get(driver)`, que
            devuelven lo que hay dentro de la tabla. No vale
            `read_int(str(entry / filename))`, que devuelve lo que diga el
            equipo aunque el nombre del archivo salga de una: mirar solo si
            «menciona» una tabla dejaba pasar justo eso.
            """
            objeto = expresion
            if isinstance(objeto, ast.Call):
                if not (isinstance(objeto.func, ast.Attribute)
                        and objeto.func.attr in ("get", "pop")):
                    return False
                objeto = objeto.func.value
            while isinstance(objeto, ast.Subscript):
                objeto = objeto.value
            return isinstance(objeto, ast.Name) and objeto.id in nombres

        nombres: set = set(semilla)
        creciendo = True
        while creciendo:
            antes = len(nombres)
            # La semilla se rehace en cada vuelta: una tabla puede estar
            # escrita con el nombre de otra dentro, como INTEL_AVISOS, que
            # reutiliza INTEL_SIN_TEMPERATURA en dos de sus tres filas.
            nombres |= {n for n, v in asignados.items()
                        if isinstance(v, (ast.Dict, ast.Tuple, ast.List,
                                          ast.Constant))
                        and cls._todo_cadenas(v, nombres)}
            for nombre, valor in asignados.items():
                if sale_de(valor, nombres):
                    nombres.add(nombre)
            for nodo in ast.walk(arbol):
                if not isinstance(nodo, (ast.For, ast.comprehension)):
                    continue
                objetivo, fuente = nodo.target, nodo.iter
                if isinstance(objetivo, ast.Name):
                    if (sale_de(fuente, nombres)
                            or cls._todo_cadenas(fuente, nombres)):
                        nombres.add(objetivo.id)
                    continue
                if not isinstance(objetivo, ast.Tuple):
                    continue
                # Por columnas, cuando se recorre una tabla directamente.
                tabla = (asignados.get(fuente.id)
                         if isinstance(fuente, ast.Name) else fuente)
                filas = (tabla.values if isinstance(tabla, ast.Dict)
                         else tabla.elts
                         if isinstance(tabla, (ast.Tuple, ast.List)) else [])
                for indice, parte in enumerate(objetivo.elts):
                    if not isinstance(parte, ast.Name):
                        continue
                    celdas = [f.elts[indice] for f in filas
                              if isinstance(f, ast.Tuple) and indice < len(f.elts)]
                    if celdas and all(es_cadena(c) for c in celdas):
                        nombres.add(parte.id)
            creciendo = len(nombres) > antes
        return nombres

    @staticmethod
    def _todo_cadenas(valor, conocidos: set = frozenset()) -> bool:
        """Una estructura cuyas hojas son todas cadenas escritas a mano."""
        hojas = [n for n in ast.walk(valor) if not isinstance(n, (
            ast.Dict, ast.Tuple, ast.List, ast.expr_context))]
        return bool(hojas) and all(
            (isinstance(n, ast.Constant) and isinstance(n.value, str))
            or (isinstance(n, ast.Name) and n.id in conocidos)
            for n in hojas)

    @classmethod
    def _sale_del_propio_archivo(cls, nodo, tablas: set) -> bool:
        """Si lo que se traduce está escrito aquí y no leído del equipo."""
        if isinstance(nodo, ast.Constant):
            return isinstance(nodo.value, str)
        if isinstance(nodo, ast.IfExp):
            return (cls._sale_del_propio_archivo(nodo.body, tablas)
                    and cls._sale_del_propio_archivo(nodo.orelse, tablas))
        return any(isinstance(hijo, ast.Name) and hijo.id in tablas
                   for hijo in ast.walk(nodo))


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

    def test_una_poda_de_verdad_no_se_lleva_ninguna_clave_viva(self):
        """`--podar` borra a conciencia, así que conviene probarlo entero.

        La red que lo sostiene es `sin_rastro_en_el_codigo`, que busca cada
        clave como texto en todo el paquete: con eso da igual que se traduzca
        con `_(variable)` desde una constante, porque escrita está. Lo que se
        vigila aquí es esa red, no el extractor: se ejecuta la poda de verdad
        sobre una copia y se comprueba que nada de lo que el código nombra
        acaba fuera. Sin esto, un cambio en esa función se lleva por delante
        traducciones sin que falle ningún test.
        """
        import importlib.util

        raiz = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "gen_lang", raiz / "tools" / "gen_lang.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        antes = json.loads((raiz / "silux" / "db" / "lang" / "es.json")
                           .read_text(encoding="utf-8"))
        cadenas = dict(modulo.cadenas_del_codigo())
        for clave, donde in modulo.cadenas_de_tablas().items():
            cadenas.setdefault(clave, donde)
        podar = modulo.sin_rastro_en_el_codigo(
            [k for k in antes if k not in cadenas])

        with tempfile.TemporaryDirectory() as tmp:
            carpeta = pathlib.Path(tmp)
            (carpeta / "es.json").write_text(
                json.dumps(antes, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(modulo, "LANG", carpeta):
                modulo.actualizar("es", cadenas, escribir=True, podar=podar)
            despues = json.loads((carpeta / "es.json").read_text(encoding="utf-8"))

        fuente = "\n".join(a.read_text(encoding="utf-8")
                           for a in (raiz / "silux").rglob("*.py"))
        perdidas = [k for k in antes if k not in despues and k in fuente]
        self.assertEqual(perdidas, [], "la poda se ha llevado claves que el "
                                       "código sigue nombrando")

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

    # Se descubren solas. Con una lista escrita a mano, cinco páginas enteras
    # se quedaron sin traducir y el test seguía en verde: no las miraba.

    def _sueltas(self, ruta):
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
        archivos = sorted(raiz.rglob("*.py"))
        self.assertGreater(len(archivos), 12, "no se están mirando las páginas")
        for archivo in archivos:
            with self.subTest(archivo=archivo.name):
                sueltas = self._sueltas(archivo)
                self.assertEqual(sueltas, [], f"{archivo.name}: {sueltas}")


class TestNadieSombreaLaTraduccion(unittest.TestCase):
    """`_` es la función que traduce, así que no puede usarse de descarte.

    En Python, `for _ in range(10)` o `ruta, _ = dialogo()` es lo idiomático
    para decir «esto no me importa». Aquí eso reemplaza la función dentro de
    esa función, y la siguiente llamada revienta con «'int' object is not
    callable» — un error que no menciona ni el idioma ni la traducción.

    Y lo peor es cuándo aparece: el código funciona hasta que alguien añade
    una cadena traducible en ese mismo método, meses después.
    """

    def test_ningun_archivo_de_interfaz_usa_guion_bajo_de_descarte(self):

        raiz = pathlib.Path(__file__).resolve().parent.parent / "silux"
        malos = []
        for archivo in sorted(raiz.rglob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            # Solo importa donde `_` es la traducción.
            if "i18n import _" not in archivo.read_text(encoding="utf-8"):
                continue
            for nodo in ast.walk(arbol):
                objetivos = []
                if isinstance(nodo, ast.Assign):
                    objetivos = nodo.targets
                elif isinstance(nodo, (ast.For, ast.comprehension)):
                    objetivos = [nodo.target]
                for objetivo in objetivos:
                    for nombre in ast.walk(objetivo):
                        if isinstance(nombre, ast.Name) and nombre.id == "_":
                            malos.append(
                                f"{archivo.name}:{getattr(nodo, 'lineno', '?')}")
        self.assertEqual(malos, [], f"sombrean _(): {malos}")


class TestNadieTraduceAlImportar(unittest.TestCase):
    """Ninguna constante de módulo llama a `_()` en su valor.

    Una tupla de campos escrita como `("cpu.field.vendor", _("gpu.tile.usage"))`
    parece igual de correcta que la de al lado y no lo es: lo que va dentro de
    `_()` se resuelve al importar el módulo, cuando todavía no se ha leído qué
    idioma quiere el usuario, así que se queda con el castellano para toda la
    sesión. Y como quien monta la ficha vuelve a pasar cada entrada por `_()`,
    la segunda llamada recibe «Uso» —que no es una clave— y devuelve «Uso».

    Así salía la columna «LEYENDO» en medio de una tabla de discos en inglés:
    la tupla llevaba once claves y una traducción ya hecha, y era la única que
    no cambiaba de idioma.
    """

    def test_las_constantes_llevan_claves_no_traducciones(self):
        raiz = pathlib.Path(__file__).resolve().parent.parent / "silux"
        malos = []
        for archivo in sorted(raiz.rglob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            for nodo in arbol.body:          # solo el nivel de módulo
                if not isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                    continue
                if nodo.value is None:
                    continue
                for hijo in ast.walk(nodo.value):
                    if (isinstance(hijo, ast.Call)
                            and isinstance(hijo.func, ast.Name)
                            and hijo.func.id == "_"):
                        malos.append(f"{archivo.name}:{hijo.lineno} "
                                     f"{ast.unparse(hijo)}")
        self.assertEqual(malos, [], f"traducen al importar: {malos}")


class TestLasFichasSeMontanConLoMismoQueSeRellenan(unittest.TestCase):
    """Quien monta una fila y quien la rellena tienen que usar la misma clave.

    `InfoGrid` guarda cada fila por el nombre con el que se creó, y `set` la
    busca por ese mismo nombre. Si una parte pasa la clave —«storage.col.model»—
    y la otra la traduce —«Modelo»—, no casan: la fila se monta con la clave
    cruda a la vista y no se rellena nunca. En pantalla salen catorce renglones
    diciendo «storage.field.firmware  —».

    Pasó dos veces, en la ficha de procesador y en la de cada disco, y las dos
    llegaron por una captura de un usuario. El bug no se ve en español, porque
    ahí la clave sin traducir y la traducción son cosas distintas pero las dos
    salen mal igual; se ve en cuanto alguien abre esa página.
    """

    def test_ninguna_pagina_monta_filas_con_la_clave_sin_traducir(self):
        raiz = pathlib.Path(__file__).resolve().parent.parent / "silux" / "ui"
        malos = []
        for archivo in sorted(raiz.rglob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            # Las tuplas de campos del módulo: son listas de claves.
            tablas = {objetivo.id for nodo in arbol.body
                      if isinstance(nodo, ast.Assign)
                      for objetivo in nodo.targets
                      if isinstance(objetivo, ast.Name)
                      and isinstance(nodo.value, (ast.Tuple, ast.List))
                      and any(isinstance(e, ast.Constant)
                              and isinstance(e.value, str) and "." in e.value
                              for e in nodo.value.elts)}
            if not tablas:
                continue
            # `for campo in TABLA: grid.add(campo)` sin pasar por `_()`.
            for nodo in ast.walk(arbol):
                if not (isinstance(nodo, ast.For)
                        and isinstance(nodo.iter, ast.Name)
                        and nodo.iter.id in tablas
                        and isinstance(nodo.target, ast.Name)):
                    continue
                variable = nodo.target.id
                for hijo in ast.walk(nodo):
                    if (isinstance(hijo, ast.Call)
                            and isinstance(hijo.func, ast.Attribute)
                            and hijo.func.attr in ("add", "set") and hijo.args
                            and isinstance(hijo.args[0], ast.Name)
                            and hijo.args[0].id == variable):
                        malos.append(f"{archivo.name}:{hijo.lineno} "
                                     f"{ast.unparse(hijo)[:60]}")
        self.assertEqual(malos, [], f"montan con la clave cruda: {malos}")
